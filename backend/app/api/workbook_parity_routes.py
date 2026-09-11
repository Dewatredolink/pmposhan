from calendar import monthrange
from datetime import date
from decimal import Decimal
from io import BytesIO

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user, require_roles
from app.db.session import get_db
from app.models import (
    School, Cluster, Block, Ingredient, Menu, Recipe, MenuSchedule,
    DailyAttendance, DailyMealEntry, StockTransaction, SchoolCalendarDay,
    UserSchoolAccess, UserOrgAccess,
)
from app.models.workbook_parity import StockLoan, BmiRecord
from app.schemas.workbook_parity import StockLoanInput, BmiRecordInput

router = APIRouter(prefix="/workbook-parity", tags=["Workbook parity"])


def _accessible_school_ids(db: Session, user: CurrentUser) -> list[str]:
    if "SYSTEM_ADMIN" in user.roles:
        return [str(x) for x in db.scalars(select(School.id).where(School.active.is_(True))).all()]
    ids = {str(x) for x in db.scalars(select(UserSchoolAccess.school_id).where(
        UserSchoolAccess.keycloak_subject == user.subject,
        UserSchoolAccess.active.is_(True),
        UserSchoolAccess.school_id.is_not(None),
    )).all() if x}
    rows = db.scalars(select(UserOrgAccess).where(
        UserOrgAccess.keycloak_subject == user.subject,
        UserOrgAccess.active.is_(True),
    )).all()
    for row in rows:
        q = select(School.id).join(Cluster, School.cluster_id == Cluster.id).join(Block, Cluster.block_id == Block.id).where(School.active.is_(True))
        if row.cluster_id:
            q = q.where(School.cluster_id == row.cluster_id)
        elif row.block_id:
            q = q.where(Cluster.block_id == row.block_id)
        elif row.district_id:
            q = q.where(Block.district_id == row.district_id)
        else:
            continue
        ids.update(str(x) for x in db.scalars(q).all())
    return sorted(ids)


def _access(db: Session, user: CurrentUser, school_id: str):
    if school_id not in _accessible_school_ids(db, user):
        raise HTTPException(status_code=403, detail="No access to this school")
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    return school


def _balance(db: Session, school_id: str, ingredient_id: str) -> Decimal:
    v = db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity), 0)).where(
        StockTransaction.school_id == school_id,
        StockTransaction.ingredient_id == ingredient_id,
    ))
    return Decimal(str(v or 0))


def _recipe_items(db: Session, menu_id: str, on_date: date, c15: int, c68: int):
    rows = db.scalars(select(Recipe).where(
        Recipe.menu_id == menu_id,
        Recipe.active.is_(True),
        Recipe.effective_from <= on_date,
        (Recipe.effective_to.is_(None) | (Recipe.effective_to >= on_date)),
    )).all()
    grouped = {}
    for r in rows:
        g = grouped.setdefault(str(r.ingredient_id), {"q15": Decimal("0"), "q68": Decimal("0")})
        q = Decimal(str(r.qty_per_student))
        if r.student_group == "CLASS_1_5": g["q15"] += q
        elif r.student_group == "CLASS_6_8": g["q68"] += q
        elif r.student_group == "ALL":
            g["q15"] += q; g["q68"] += q
    out=[]
    for iid, q in grouped.items():
        ing=db.get(Ingredient,iid)
        if not ing: continue
        r15=q["q15"]*c15; r68=q["q68"]*c68
        out.append({
            "ingredient_id":iid,"code":ing.code,"name_en":ing.name_en,"name_mr":ing.name_mr,
            "unit":ing.base_unit,"per_student_class_1_5":float(q["q15"]),"per_student_class_6_8":float(q["q68"]),
            "required_class_1_5":float(r15),"required_class_6_8":float(r68),"required_total":float(r15+r68),
            "available":float(_balance(db, "__none__", iid)) if False else None,
        })
    return out


@router.get("/ration-preview")
def ration_preview(school_id: str, ration_date: date, class_1_5: int | None = None, class_6_8: int | None = None,
                   db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    school=_access(db,user,school_id)
    c15=school.class_1_5_strength if class_1_5 is None else max(0,class_1_5)
    c68=school.class_6_8_strength if class_6_8 is None else max(0,class_6_8)
    plan=db.scalar(select(MenuSchedule).where(MenuSchedule.school_id==school_id,MenuSchedule.menu_date==ration_date))
    if not plan:
        raise HTTPException(status_code=404, detail="No menu planned for this date")
    menu=db.get(Menu,plan.menu_id)
    items=_recipe_items(db,plan.menu_id,ration_date,c15,c68)
    for x in items:
        x["available"]=float(_balance(db,school_id,x["ingredient_id"]))
        x["shortage"]=max(0.0, x["required_total"]-x["available"])
    return {"school_id":school_id,"ration_date":ration_date,"menu":{"id":menu.id,"code":menu.code,"name_en":menu.name_en,"name_mr":menu.name_mr},"class_1_5":c15,"class_6_8":c68,"items":items}


@router.get("/loans")
def loans(school_id: str, year: int | None = None, month: int | None = None,
          db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _access(db,user,school_id)
    q=select(StockLoan).where(StockLoan.school_id==school_id)
    if year and month:
        first=date(year,month,1); last=date(year,month,monthrange(year,month)[1]); q=q.where(StockLoan.loan_date.between(first,last))
    rows=db.scalars(q.order_by(StockLoan.loan_date.desc(),StockLoan.created_at.desc())).all()
    return [{"id":r.id,"loan_date":r.loan_date,"loan_no":r.loan_no,"direction":r.direction,"counterparty_name":r.counterparty_name,
             "ingredient_id":r.ingredient_id,"ingredient_name":r.ingredient.name_mr or r.ingredient.name_en,"unit":r.ingredient.base_unit,
             "quantity":float(r.quantity),"remarks":r.remarks} for r in rows]


@router.post("/loans")
def create_loan(payload: StockLoanInput, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("HEADMASTER","SYSTEM_ADMIN"))):
    _access(db,user,payload.school_id)
    ing=db.get(Ingredient,payload.ingredient_id)
    if not ing: raise HTTPException(status_code=404,detail="Ingredient not found")
    qty=Decimal(str(payload.quantity))
    if payload.direction=="GIVEN" and ing.track_inventory and _balance(db,payload.school_id,payload.ingredient_id)<qty:
        raise HTTPException(status_code=409,detail="Insufficient stock for loan given")
    row=StockLoan(school_id=payload.school_id,loan_date=payload.loan_date,loan_no=payload.loan_no,direction=payload.direction,
                  counterparty_name=payload.counterparty_name,ingredient_id=payload.ingredient_id,quantity=qty,remarks=payload.remarks,
                  entered_by_subject=user.subject,entered_by_username=user.username,created_by=user.username)
    db.add(row); db.flush()
    signed=qty if payload.direction=="RECEIVED" else -qty
    tx=StockTransaction(school_id=payload.school_id,ingredient_id=payload.ingredient_id,transaction_date=payload.loan_date,
        transaction_type="LOAN_IN" if signed>0 else "LOAN_OUT",quantity=signed,reference_type="STOCK_LOAN",reference_id=row.id,
        reference_no=payload.loan_no,remarks=f"{payload.direction}: {payload.counterparty_name}",entered_by_subject=user.subject,
        entered_by_username=user.username,created_by=user.username)
    db.add(tx); db.commit(); db.refresh(row)
    return {"ok":True,"id":row.id}


@router.get("/bmi")
def bmi_list(school_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    _access(db,user,school_id)
    rows=db.scalars(select(BmiRecord).where(BmiRecord.school_id==school_id).order_by(BmiRecord.measurement_date.desc(),BmiRecord.student_name)).all()
    return [{"id":r.id,"measurement_date":r.measurement_date,"student_identifier":r.student_identifier,"student_name":r.student_name,
             "class_name":r.class_name,"gender":r.gender,"height_cm":float(r.height_cm),"weight_kg":float(r.weight_kg),"bmi":float(r.bmi),"remarks":r.remarks} for r in rows]


@router.post("/bmi")
def bmi_create(payload: BmiRecordInput, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("TEACHER","HEADMASTER","SYSTEM_ADMIN"))):
    _access(db,user,payload.school_id)
    h=Decimal(str(payload.height_cm))/Decimal("100")
    bmi=(Decimal(str(payload.weight_kg))/(h*h)).quantize(Decimal("0.01"))
    row=BmiRecord(school_id=payload.school_id,measurement_date=payload.measurement_date,student_identifier=payload.student_identifier,
        student_name=payload.student_name,class_name=payload.class_name,gender=payload.gender,height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,bmi=bmi,remarks=payload.remarks,entered_by_subject=user.subject,entered_by_username=user.username,created_by=user.username)
    db.add(row); db.commit(); return {"ok":True,"id":row.id,"bmi":float(bmi)}


def _period(year:int,month:int):
    return date(year,month,1),date(year,month,monthrange(year,month)[1])


def _school_heading(school: School):
    c=school.cluster; b=c.block if c else None; d=b.district if b else None
    return [school.name_mr or school.name_en, f"UDISE: {school.udise_code}", f"Cluster/Kendra: {(c.name_mr or c.name_en) if c else ''}", f"Taluka/Block: {(b.name_mr or b.name_en) if b else ''}", f"District: {(d.name_mr or d.name_en) if d else ''}"]


def _xlsx(report_type:str, school:School, year:int, month:int, db:Session):
    first,last=_period(year,month); bio=BytesIO(); w=xlsxwriter.Workbook(bio,{"in_memory":True}); ws=w.add_worksheet(report_type[:31])
    title=w.add_format({"bold":True,"font_size":14,"align":"center","valign":"vcenter"}); hdr=w.add_format({"bold":True,"border":1,"bg_color":"#D9EAD3","text_wrap":True}); cell=w.add_format({"border":1}); num=w.add_format({"border":1,"num_format":"0.000"})
    ws.set_column(0,0,12); ws.set_column(1,1,13); ws.set_column(2,30,16)
    ws.merge_range(0,0,0,8,f"PM POSHAN - {report_type} - {month:02d}/{year}",title)
    for i,x in enumerate(_school_heading(school),start=1): ws.write(i,0,x)
    start=7
    if report_type=="PART1":
        headers=["Sr No","Date","Enrolment","Beneficiaries","Rice Received","Other Receipt/Loan In","Total Rice","Rice Consumed","Closing Rice"]
        for c,h in enumerate(headers): ws.write(start,c,h,hdr)
        rice=db.scalar(select(Ingredient).where(func.lower(Ingredient.name_en).contains("rice"))) or db.scalar(select(Ingredient).where(Ingredient.name_mr.contains("तांदूळ")))
        bal=Decimal("0"); r=start+1; sr=1
        if rice:
            pre=db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==rice.id,StockTransaction.transaction_date<first)); bal=Decimal(str(pre or 0))
        for day in range(1,last.day+1):
            dt=date(year,month,day); a=db.scalar(select(DailyAttendance).where(DailyAttendance.school_id==school.id,DailyAttendance.meal_date==dt))
            txs=[] if not rice else db.scalars(select(StockTransaction).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==rice.id,StockTransaction.transaction_date==dt)).all()
            rec=sum(Decimal(str(t.quantity)) for t in txs if t.quantity>0 and t.transaction_type not in {"LOAN_IN"}); loan=sum(Decimal(str(t.quantity)) for t in txs if t.transaction_type=="LOAN_IN"); con=-sum(Decimal(str(t.quantity)) for t in txs if t.quantity<0 and t.transaction_type=="CONSUMPTION"); bal += sum(Decimal(str(t.quantity)) for t in txs)
            vals=[sr,dt.isoformat(),(a.class_1_5_enrolled+a.class_6_8_enrolled) if a else 0,(a.class_1_5_present+a.class_6_8_present) if a else 0,float(rec),float(loan),None,float(con),float(bal)]
            vals[6]=float((bal+con))
            for c,v in enumerate(vals): ws.write(r,c,v,num if isinstance(v,float) else cell)
            r+=1; sr+=1
    elif report_type=="PART2":
        ingredients=db.scalars(select(Ingredient).where(Ingredient.active.is_(True)).order_by(Ingredient.name_mr,Ingredient.name_en)).all()
        headers=["Date","Day","Menu","Beneficiaries"]+[(i.name_mr or i.name_en) for i in ingredients]
        for c,h in enumerate(headers): ws.write(start,c,h,hdr)
        r=start+1
        for day in range(1,last.day+1):
            dt=date(year,month,day); meal=db.scalar(select(DailyMealEntry).where(DailyMealEntry.school_id==school.id,DailyMealEntry.meal_date==dt))
            a=db.scalar(select(DailyAttendance).where(DailyAttendance.school_id==school.id,DailyAttendance.meal_date==dt))
            menu=(meal.menu.name_mr or meal.menu.name_en) if meal and meal.menu else ""
            ws.write_row(r,0,[dt.isoformat(),dt.strftime("%A"),menu,(a.class_1_5_present+a.class_6_8_present) if a else 0],cell)
            for c,ing in enumerate(ingredients,start=4):
                q=db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==ing.id,StockTransaction.transaction_date==dt,StockTransaction.transaction_type=="CONSUMPTION")); ws.write_number(r,c,float(-Decimal(str(q or 0))),num)
            r+=1
    elif report_type=="RATION":
        headers=["Date","Menu","Estimated 1-5","Estimated 6-8","Ingredient","Unit","Required","Available","Shortage"]
        for c,h in enumerate(headers): ws.write(start,c,h,hdr)
        r=start+1
        plans=db.scalars(select(MenuSchedule).where(MenuSchedule.school_id==school.id,MenuSchedule.menu_date.between(first,last)).order_by(MenuSchedule.menu_date)).all()
        for p in plans:
            m=p.menu; items=_recipe_items(db,p.menu_id,p.menu_date,school.class_1_5_strength,school.class_6_8_strength)
            for x in items:
                av=float(_balance(db,school.id,x["ingredient_id"])); req=x["required_total"]
                ws.write_row(r,0,[p.menu_date.isoformat(),m.name_mr or m.name_en,school.class_1_5_strength,school.class_6_8_strength,x["name_mr"] or x["name_en"],x["unit"],req,av,max(0,req-av)],cell); r+=1
    elif report_type in {"MONTHLY","SUMMARY","UTILIZATION"}:
        headers=["Ingredient","Unit","Opening","Receipts","Loan In","Consumption","Loan Out","Adjustments/Other","Closing"]
        for c,h in enumerate(headers): ws.write(start,c,h,hdr)
        r=start+1
        for ing in db.scalars(select(Ingredient).where(Ingredient.active.is_(True)).order_by(Ingredient.name_mr,Ingredient.name_en)).all():
            opening=Decimal(str(db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==ing.id,StockTransaction.transaction_date<first)) or 0))
            txs=db.scalars(select(StockTransaction).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==ing.id,StockTransaction.transaction_date.between(first,last))).all()
            receipt=sum(Decimal(str(t.quantity)) for t in txs if t.quantity>0 and t.transaction_type not in {"LOAN_IN"}); loanin=sum(Decimal(str(t.quantity)) for t in txs if t.transaction_type=="LOAN_IN")
            consume=-sum(Decimal(str(t.quantity)) for t in txs if t.transaction_type=="CONSUMPTION"); loanout=-sum(Decimal(str(t.quantity)) for t in txs if t.transaction_type=="LOAN_OUT")
            known=sum(Decimal(str(t.quantity)) for t in txs if t.transaction_type in {"LOAN_IN","LOAN_OUT","CONSUMPTION"} or (t.quantity>0 and t.transaction_type not in {"LOAN_IN"}))
            total=sum(Decimal(str(t.quantity)) for t in txs); other=total-known; closing=opening+total
            ws.write_row(r,0,[ing.name_mr or ing.name_en,ing.base_unit,float(opening),float(receipt),float(loanin),float(consume),float(loanout),float(other),float(closing)],cell); r+=1
    elif report_type=="BMI":
        headers=["Date","Student ID","Student Name","Class","Gender","Height cm","Weight kg","BMI","Remarks"]
        for c,h in enumerate(headers): ws.write(start,c,h,hdr)
        r=start+1
        for x in db.scalars(select(BmiRecord).where(BmiRecord.school_id==school.id,BmiRecord.measurement_date.between(first,last)).order_by(BmiRecord.student_name)).all():
            ws.write_row(r,0,[x.measurement_date.isoformat(),x.student_identifier or "",x.student_name,x.class_name or "",x.gender or "",float(x.height_cm),float(x.weight_kg),float(x.bmi),x.remarks or ""],cell); r+=1
    elif report_type=="LOANS":
        headers=["Date","Loan No","Direction","Counterparty","Ingredient","Unit","Quantity","Remarks"]
        for c,h in enumerate(headers): ws.write(start,c,h,hdr)
        r=start+1
        for x in db.scalars(select(StockLoan).where(StockLoan.school_id==school.id,StockLoan.loan_date.between(first,last)).order_by(StockLoan.loan_date)).all():
            ws.write_row(r,0,[x.loan_date.isoformat(),x.loan_no,x.direction,x.counterparty_name,x.ingredient.name_mr or x.ingredient.name_en,x.ingredient.base_unit,float(x.quantity),x.remarks or ""],cell); r+=1
    elif report_type=="SPECIAL_DAYS":
        headers=["Date","Day Type","Meal Required","Special Day / Holiday","Remarks"]
        for c,h in enumerate(headers): ws.write(start,c,h,hdr)
        r=start+1
        for x in db.scalars(select(SchoolCalendarDay).where(SchoolCalendarDay.school_id==school.id,SchoolCalendarDay.calendar_date.between(first,last)).order_by(SchoolCalendarDay.calendar_date)).all():
            ws.write_row(r,0,[x.calendar_date.isoformat(),x.day_type,"Yes" if x.meal_required else "No",x.title_mr or x.title_en or "",x.remarks or ""],cell); r+=1
    else:
        raise HTTPException(status_code=400,detail="Unsupported report type")
    ws.freeze_panes(start+1,0); w.close(); bio.seek(0); return bio


@router.get("/register/export")
def export_register(report_type: str, school_id: str, year: int, month: int,
                    db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    school=_access(db,user,school_id); rt=report_type.upper()
    allowed={"PART1","PART2","RATION","MONTHLY","SUMMARY","UTILIZATION","BMI","LOANS","SPECIAL_DAYS"}
    if rt not in allowed: raise HTTPException(status_code=400,detail=f"report_type must be one of {', '.join(sorted(allowed))}")
    bio=_xlsx(rt,school,year,month,db); name=f"PM_POSHAN_{rt}_{year}_{month:02d}.xlsx"
    return StreamingResponse(bio,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="{name}"'})
