from calendar import monthrange
from datetime import date
from decimal import Decimal
from io import BytesIO
from urllib.parse import quote

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db
from app.models import Ingredient, MenuSchedule, DailyAttendance, DailyMealEntry, StockTransaction, SchoolCalendarDay
from app.models.workbook_parity import StockLoan, BmiRecord
from app.api.workbook_parity_routes import _access, _balance, _recipe_items

router=APIRouter(prefix='/workbook-parity/register',tags=['Marathi workbook reports'])

MONTH_MR=['','जानेवारी','फेब्रुवारी','मार्च','एप्रिल','मे','जून','जुलै','ऑगस्ट','सप्टेंबर','ऑक्टोबर','नोव्हेंबर','डिसेंबर']
DAY_MR=['सोमवार','मंगळवार','बुधवार','गुरुवार','शुक्रवार','शनिवार','रविवार']

REPORT_NAMES={
 'PART1':'दैनंदिन धान्य नोंदवही भाग १',
 'PART2':'दैनंदिन खर्च नोंदवही भाग २',
 'RATION':'राशन आवश्यकता अहवाल',
 'MONTHLY':'मासिक साठा अहवाल',
 'SUMMARY':'मासिक गोषवारा',
 'UTILIZATION':'उपयोगिता अहवाल',
 'BMI':'बीएमआय नोंदवही',
 'LOANS':'उसणवार साठा नोंदवही',
 'SPECIAL_DAYS':'विशेष दिवस व सुट्टी नोंदवही',
}

def D(v): return Decimal(str(v or 0))

def period(year,month):
    return date(year,month,1),date(year,month,monthrange(year,month)[1])

def school_lines(s):
    c=s.cluster; b=c.block if c else None; d=b.district if b else None
    return [
      s.name_mr or s.name_en,
      f'यू-डायस: {s.udise_code}',
      f'केंद्र: {(c.name_mr or c.name_en) if c else ""}',
      f'तालुका: {(b.name_mr or b.name_en) if b else ""}',
      f'जिल्हा: {(d.name_mr or d.name_en) if d else ""}',
    ]

def formats(w):
    font='Noto Sans Devanagari'
    return {
      'title':w.add_format({'bold':True,'font_name':font,'font_size':15,'align':'center','valign':'vcenter','font_color':'#0B4F7A'}),
      'sub':w.add_format({'bold':True,'font_name':font,'font_size':10,'align':'center','valign':'vcenter'}),
      'hdr':w.add_format({'bold':True,'font_name':font,'font_size':9,'border':1,'bg_color':'#D9EAF7','align':'center','valign':'vcenter','text_wrap':True}),
      'cell':w.add_format({'font_name':font,'font_size':9,'border':1,'valign':'vcenter'}),
      'center':w.add_format({'font_name':font,'font_size':9,'border':1,'align':'center','valign':'vcenter'}),
      'num':w.add_format({'font_name':font,'font_size':9,'border':1,'align':'center','num_format':'0.000'}),
      'money':w.add_format({'font_name':font,'font_size':9,'border':1,'align':'center','num_format':'0.00'}),
      'note':w.add_format({'font_name':font,'font_size':8,'text_wrap':True,'border':1}),
    }

def start_sheet(w,title,school,year,month,cols=9):
    ws=w.add_worksheet(title[:31]); f=formats(w)
    ws.set_landscape(); ws.set_paper(9); ws.fit_to_pages(1,0); ws.set_margins(.2,.2,.25,.25); ws.hide_gridlines(2)
    ws.merge_range(0,0,0,cols-1,'प्रधानमंत्री पोषणशक्ती निर्माण योजना',f['title'])
    ws.merge_range(1,0,1,cols-1,title,f['title'])
    ws.merge_range(2,0,2,cols-1,f'{school_lines(school)[0]}  |  {school_lines(school)[1]}  |  {school_lines(school)[2]}  |  {school_lines(school)[3]}  |  {school_lines(school)[4]}',f['sub'])
    ws.merge_range(3,0,3,cols-1,f'महिना: {MONTH_MR[month]}   वर्ष: {year}',f['sub'])
    return ws,f,6

def write_headers(ws,f,row,headers):
    for c,h in enumerate(headers): ws.write(row,c,h,f['hdr'])

def marathi_xlsx(rt,school,year,month,db):
    first,last=period(year,month); bio=BytesIO(); w=xlsxwriter.Workbook(bio,{'in_memory':True})
    w.set_properties({'title':REPORT_NAMES[rt],'subject':'पीएम पोषण मराठी अहवाल'})
    if rt=='PART1':
        ws,f,r=start_sheet(w,REPORT_NAMES[rt],school,year,month,9)
        headers=['अ. क्र.','दिनांक','पटसंख्या','लाभार्थी','तांदूळ प्राप्त','उसणवार प्राप्त','एकूण तांदूळ','तांदूळ वापर','शिल्लक तांदूळ']; write_headers(ws,f,r,headers); r+=1
        rice=db.scalar(select(Ingredient).where(func.lower(Ingredient.name_en).contains('rice'))) or db.scalar(select(Ingredient).where(Ingredient.name_mr.contains('तांदूळ')))
        bal=D(db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==rice.id,StockTransaction.transaction_date<first))) if rice else Decimal(0)
        for sr,day in enumerate(range(1,last.day+1),1):
            dt=date(year,month,day); a=db.scalar(select(DailyAttendance).where(DailyAttendance.school_id==school.id,DailyAttendance.meal_date==dt))
            txs=[] if not rice else db.scalars(select(StockTransaction).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==rice.id,StockTransaction.transaction_date==dt)).all()
            rec=sum((D(t.quantity) for t in txs if D(t.quantity)>0 and t.transaction_type!='LOAN_IN'),Decimal(0))
            loan=sum((D(t.quantity) for t in txs if t.transaction_type=='LOAN_IN'),Decimal(0))
            con=-sum((D(t.quantity) for t in txs if t.transaction_type=='CONSUMPTION' and D(t.quantity)<0),Decimal(0))
            before=bal+rec+loan; bal+=sum((D(t.quantity) for t in txs),Decimal(0))
            vals=[sr,dt.strftime('%d-%m-%Y'),((a.class_1_5_enrolled+a.class_6_8_enrolled) if a else 0),((a.class_1_5_present+a.class_6_8_present) if a else 0),float(rec),float(loan),float(before),float(con),float(bal)]
            for c,v in enumerate(vals): ws.write(r,c,v,f['num'] if isinstance(v,float) else f['center']); r+=1
    elif rt=='PART2':
        ws,f,r=start_sheet(w,REPORT_NAMES[rt],school,year,month,4)
        headers=['दिनांक','वार','मेनू','लाभार्थी']; write_headers(ws,f,r,headers); r+=1
        for day in range(1,last.day+1):
            dt=date(year,month,day); meal=db.scalar(select(DailyMealEntry).where(DailyMealEntry.school_id==school.id,DailyMealEntry.meal_date==dt)); a=db.scalar(select(DailyAttendance).where(DailyAttendance.school_id==school.id,DailyAttendance.meal_date==dt))
            menu=(meal.menu.name_mr or meal.menu.name_en) if meal and meal.menu else ''
            vals=[dt.strftime('%d-%m-%Y'),DAY_MR[dt.weekday()],menu,(a.class_1_5_present+a.class_6_8_present) if a else 0]
            for c,v in enumerate(vals): ws.write(r,c,v,f['cell'] if c==2 else f['center'])
            r+=1
    elif rt=='RATION':
        ws,f,r=start_sheet(w,REPORT_NAMES[rt],school,year,month,9)
        headers=['दिनांक','मेनू','अंदाजित १-५','अंदाजित ६-८','घटक','एकक','आवश्यक','उपलब्ध','तूट']; write_headers(ws,f,r,headers); r+=1
        plans=db.scalars(select(MenuSchedule).where(MenuSchedule.school_id==school.id,MenuSchedule.menu_date.between(first,last)).order_by(MenuSchedule.menu_date)).all()
        for p in plans:
            items=_recipe_items(db,p.menu_id,p.menu_date,school.class_1_5_strength,school.class_6_8_strength)
            for x in items:
                av=float(_balance(db,school.id,x['ingredient_id'])); req=x['required_total']
                vals=[p.menu_date.strftime('%d-%m-%Y'),p.menu.name_mr or p.menu.name_en,school.class_1_5_strength,school.class_6_8_strength,x['name_mr'] or x['name_en'],x['unit'],req,av,max(0,req-av)]
                for c,v in enumerate(vals): ws.write(r,c,v,f['num'] if isinstance(v,float) else f['cell'])
                r+=1
    elif rt in {'MONTHLY','SUMMARY','UTILIZATION'}:
        ws,f,r=start_sheet(w,REPORT_NAMES[rt],school,year,month,9)
        headers=['घटक','एकक','मागील शिल्लक','प्राप्ती','उसणवार प्राप्त','वापर','उसणवार दिले','समायोजन/इतर','अखेर शिल्लक']; write_headers(ws,f,r,headers); r+=1
        for ing in db.scalars(select(Ingredient).where(Ingredient.active.is_(True)).order_by(Ingredient.name_mr,Ingredient.name_en)).all():
            opening=D(db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==ing.id,StockTransaction.transaction_date<first)))
            txs=db.scalars(select(StockTransaction).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==ing.id,StockTransaction.transaction_date.between(first,last))).all()
            receipt=sum((D(t.quantity) for t in txs if D(t.quantity)>0 and t.transaction_type!='LOAN_IN'),Decimal(0))
            loanin=sum((D(t.quantity) for t in txs if t.transaction_type=='LOAN_IN'),Decimal(0))
            consume=-sum((D(t.quantity) for t in txs if t.transaction_type=='CONSUMPTION' and D(t.quantity)<0),Decimal(0))
            loanout=-sum((D(t.quantity) for t in txs if t.transaction_type=='LOAN_OUT' and D(t.quantity)<0),Decimal(0))
            total=sum((D(t.quantity) for t in txs),Decimal(0)); known=receipt+loanin-consume-loanout; other=total-known; closing=opening+total
            vals=[ing.name_mr or ing.name_en,ing.base_unit,float(opening),float(receipt),float(loanin),float(consume),float(loanout),float(other),float(closing)]
            for c,v in enumerate(vals): ws.write(r,c,v,f['num'] if isinstance(v,float) else f['cell'])
            r+=1
    elif rt=='BMI':
        ws,f,r=start_sheet(w,REPORT_NAMES[rt],school,year,month,9)
        headers=['दिनांक','विद्यार्थी आयडी','विद्यार्थ्याचे नाव','इयत्ता','लिंग','उंची सेमी','वजन कि.ग्रॅ.','BMI','शेरा']; write_headers(ws,f,r,headers); r+=1
        for x in db.scalars(select(BmiRecord).where(BmiRecord.school_id==school.id,BmiRecord.measurement_date.between(first,last)).order_by(BmiRecord.student_name)).all():
            vals=[x.measurement_date.strftime('%d-%m-%Y'),x.student_identifier or '',x.student_name,x.class_name or '',x.gender or '',float(x.height_cm),float(x.weight_kg),float(x.bmi),x.remarks or '']
            for c,v in enumerate(vals): ws.write(r,c,v,f['num'] if isinstance(v,float) else f['cell'])
            r+=1
    elif rt=='LOANS':
        ws,f,r=start_sheet(w,REPORT_NAMES[rt],school,year,month,8)
        headers=['दिनांक','उसणवार क्र.','प्रकार','समोरील शाळा/संस्था','घटक','एकक','मात्रा','शेरा']; write_headers(ws,f,r,headers); r+=1
        for x in db.scalars(select(StockLoan).where(StockLoan.school_id==school.id,StockLoan.loan_date.between(first,last)).order_by(StockLoan.loan_date)).all():
            direction='प्राप्त' if x.direction=='RECEIVED' else 'दिले'
            vals=[x.loan_date.strftime('%d-%m-%Y'),x.loan_no,direction,x.counterparty_name,x.ingredient.name_mr or x.ingredient.name_en,x.ingredient.base_unit,float(x.quantity),x.remarks or '']
            for c,v in enumerate(vals): ws.write(r,c,v,f['num'] if isinstance(v,float) else f['cell'])
            r+=1
    elif rt=='SPECIAL_DAYS':
        ws,f,r=start_sheet(w,REPORT_NAMES[rt],school,year,month,5)
        headers=['दिनांक','दिवस प्रकार','आहार आवश्यक','विशेष दिवस / सुट्टी','शेरा']; write_headers(ws,f,r,headers); r+=1
        type_mr={'WORKING':'कार्यदिन','SUNDAY':'रविवार','PUBLIC_HOLIDAY':'सार्वजनिक सुट्टी','SCHOOL_HOLIDAY':'शाळा सुट्टी','LOCAL_HOLIDAY':'स्थानिक सुट्टी','CLOSURE':'शाळा बंद','EXAM_NON_MEAL':'परीक्षा - आहार नाही'}
        for x in db.scalars(select(SchoolCalendarDay).where(SchoolCalendarDay.school_id==school.id,SchoolCalendarDay.calendar_date.between(first,last)).order_by(SchoolCalendarDay.calendar_date)).all():
            vals=[x.calendar_date.strftime('%d-%m-%Y'),type_mr.get(x.day_type,x.day_type),'होय' if x.meal_required else 'नाही',x.title_mr or x.title_en or '',x.remarks or '']
            for c,v in enumerate(vals): ws.write(r,c,v,f['cell'])
            r+=1
    else:
        w.close(); raise HTTPException(400,'Unsupported report type')
    ws.freeze_panes(7,0); ws.autofilter(6,0,max(6,r-1),max(0,len(headers)-1)); ws.repeat_rows(0,6)
    ws.print_area(0,0,max(6,r-1),max(0,len(headers)-1)); w.close(); bio.seek(0); return bio

@router.get('/export-marathi')
def export_marathi(report_type:str,school_id:str,year:int,month:int,db:Session=Depends(get_db),user:CurrentUser=Depends(get_current_user)):
    rt=report_type.upper(); allowed=set(REPORT_NAMES)
    if rt not in allowed: raise HTTPException(400,f'report_type must be one of {", ".join(sorted(allowed))}')
    if month<1 or month>12: raise HTTPException(400,'Invalid month')
    school=_access(db,user,school_id); bio=marathi_xlsx(rt,school,year,month,db)
    fn=f'पीएम_पोषण_{REPORT_NAMES[rt].replace(" ","_")}_{year}_{month:02d}.xlsx'
    return StreamingResponse(bio,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(fn)}"})

