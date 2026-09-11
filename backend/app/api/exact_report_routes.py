from calendar import monthrange
from datetime import date
from decimal import Decimal
from io import BytesIO

import xlsxwriter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db
from app.models import School, Ingredient, DailyAttendance, DailyMealEntry, StockTransaction, SchoolCalendarDay
from app.api.workbook_parity_routes import _access

router = APIRouter(prefix='/workbook-parity/exact-report', tags=['Exact official reports'])

ING_ORDER = [
    ('तांदूळ','rice'),('मुगदाळ','moong'),('तूरदाळ','tur'),('मसूरदाळ','masoor'),('मटकी','matki'),('मूग','mung'),
    ('चवळी','chawli'),('हरभरा','chana'),('वाटाणा','peas'),('सोयाबीन','soya'),('जिरे','cumin'),('मोहरी','mustard'),
    ('हळद','turmeric'),('ग. मसाला','masala'),('तेल','oil'),('मीठ','salt'),('साखर / गुळ','sugar'),('दूध पावडर','milk'),
    ('नाचणी','ragi'),('अंडी','egg'),('पूरक आहार व भाजीपाला','supplement'),('भाजीपाला व इंधनखर्च','vegetable')
]

MONTH_MR=['','जानेवारी','फेब्रुवारी','मार्च','एप्रिल','मे','जून','जुलै','ऑगस्ट','सप्टेंबर','ऑक्टोबर','नोव्हेंबर','डिसेंबर']
DAY_MR=['सोमवार','मंगळवार','बुधवार','गुरुवार','शुक्रवार','शनिवार','रविवार']


def _D(v): return Decimal(str(v or 0))

def _ingredient_map(db):
    rows=db.scalars(select(Ingredient).where(Ingredient.active.is_(True))).all()
    out=[]
    for mr,enkey in ING_ORDER:
        found=None
        for x in rows:
            nm=(x.name_mr or '').replace(' ','').lower(); ne=(x.name_en or '').replace(' ','').lower()
            if mr.replace(' ','').lower() in nm or enkey in ne:
                found=x; break
        out.append((mr,found))
    return out


def _tx_summary(db, school_id, ing, first, last):
    if not ing: return dict(opening=Decimal(0),received=Decimal(0),used=Decimal(0),closing=Decimal(0))
    opening=_D(db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(
        StockTransaction.school_id==school_id, StockTransaction.ingredient_id==ing.id, StockTransaction.transaction_date<first)))
    txs=db.scalars(select(StockTransaction).where(StockTransaction.school_id==school_id,
        StockTransaction.ingredient_id==ing.id,StockTransaction.transaction_date.between(first,last))).all()
    received=sum((_D(t.quantity) for t in txs if _D(t.quantity)>0),Decimal(0))
    used=-sum((_D(t.quantity) for t in txs if _D(t.quantity)<0),Decimal(0))
    closing=opening+sum((_D(t.quantity) for t in txs),Decimal(0))
    return dict(opening=opening,received=received,used=used,closing=closing)


def _attendance_month(db, school_id, first, last, group):
    rows=db.scalars(select(DailyAttendance).where(DailyAttendance.school_id==school_id,DailyAttendance.meal_date.between(first,last))).all()
    if group=='1_5': return sum((r.class_1_5_present or 0) for r in rows)
    return sum((r.class_6_8_present or 0) for r in rows)


def _meal_days(db, school_id, first, last, group):
    rows=db.scalars(select(DailyMealEntry).where(DailyMealEntry.school_id==school_id,DailyMealEntry.meal_date.between(first,last),DailyMealEntry.status=='VERIFIED')).all()
    # One verified school meal date counts as a cooked day for the selected group when attendance is > 0.
    n=0
    for r in rows:
        a=db.scalar(select(DailyAttendance).where(DailyAttendance.school_id==school_id,DailyAttendance.meal_date==r.meal_date))
        if a and ((a.class_1_5_present if group=='1_5' else a.class_6_8_present) or 0)>0: n+=1
    return n


def _styles(w):
    return {
      'title':w.add_format({'bold':True,'font_name':'Noto Sans Devanagari','font_size':13,'align':'center','valign':'vcenter'}),
      'red':w.add_format({'bold':True,'font_name':'Noto Sans Devanagari','font_color':'#FF0000','align':'center','valign':'vcenter'}),
      'yellow':w.add_format({'bold':True,'font_name':'Noto Sans Devanagari','font_size':22,'bg_color':'#FFFF00','font_color':'#FF0000','align':'center','valign':'vcenter','border':1}),
      'month':w.add_format({'bold':True,'font_name':'Noto Sans Devanagari','font_size':18,'bg_color':'#D60000','font_color':'#FFFFFF','align':'center','valign':'vcenter','border':1}),
      'year':w.add_format({'bold':True,'font_name':'Noto Sans Devanagari','font_size':20,'bg_color':'#FF0000','font_color':'#FFFF00','align':'center','valign':'vcenter','border':1}),
      'h':w.add_format({'bold':True,'font_name':'Noto Sans Devanagari','font_size':9,'border':1,'align':'center','valign':'vcenter','text_wrap':True}),
      'c':w.add_format({'font_name':'Noto Sans Devanagari','font_size':9,'border':1,'align':'center','valign':'vcenter'}),
      'l':w.add_format({'font_name':'Noto Sans Devanagari','font_size':9,'border':1,'align':'left','valign':'vcenter'}),
      'n':w.add_format({'font_name':'Noto Sans Devanagari','font_size':9,'border':1,'align':'center','num_format':'0.000'}),
      'money':w.add_format({'font_name':'Noto Sans Devanagari','font_size':9,'border':1,'align':'center','num_format':'0.00'}),
      'note':w.add_format({'font_name':'Noto Sans Devanagari','font_size':9,'border':1,'text_wrap':True,'valign':'vcenter'}),
      'sig':w.add_format({'bold':True,'font_name':'Noto Sans Devanagari','font_size':9,'align':'center','valign':'vcenter'}),
      'pink':w.add_format({'font_name':'Noto Sans Devanagari','font_size':8,'border':1,'align':'center','bg_color':'#F4CCCC'}),
      'dailyh':w.add_format({'bold':True,'font_name':'Noto Sans Devanagari','font_size':8,'border':1,'align':'center','valign':'vcenter','text_wrap':True,'bg_color':'#FCE5CD'}),
    }


def _school_line(school):
    c=school.cluster; b=c.block if c else None; d=b.district if b else None
    return f", {school.name_mr or school.name_en} , केंद्र - {(c.name_mr or c.name_en) if c else ''} , तालुका - {(b.name_mr or b.name_en) if b else ''} , जिल्हा - {(d.name_mr or d.name_en) if d else ''}"


def _monthly_sheet(w, school, db, year, month, group, name):
    ws=w.add_worksheet(name); f=_styles(w); first=date(year,month,1); last=date(year,month,monthrange(year,month)[1])
    ws.set_landscape(); ws.set_paper(9); ws.fit_to_pages(1,1); ws.set_margins(0.2,0.2,0.25,0.25); ws.center_horizontally(); ws.hide_gridlines(2)
    ws.set_column('A:A',4); ws.set_column('B:B',18); ws.set_column('C:G',12); ws.set_column('H:H',13); ws.set_column('I:I',18)
    ws.merge_range('A1:I1','शालेय पोषण आहार प्रपत्र',f['title'])
    ws.merge_range('A2:I2','शाळेने केंद्रप्रमुखांना दरमहा 5 तारखेपर्यंत द्यावयाचा अहवाल  ( 2 प्रतीत )',f['title'])
    ws.merge_range('A3:I3',_school_line(school),f['red'])
    ws.merge_range('A4:C5','1 ते 5' if group=='1_5' else '6 ते 8',f['yellow'])
    strength=(school.class_1_5_strength if group=='1_5' else school.class_6_8_strength) or 0
    att=_attendance_month(db,school.id,first,last,group); cooked=_meal_days(db,school.id,first,last,group)
    ws.merge_range('D4:E4','पटसंख्या 1 ली ते 5 वी -' if group=='1_5' else 'पटसंख्या ६ वी ते ८ वी -',f['c']); ws.merge_range('F4:G4',strength,f['c'])
    ws.merge_range('D5:E5','महिन्यातील उपस्थिती',f['c']); ws.merge_range('F5:G5',att,f['c'])
    ws.merge_range('A6:C6',MONTH_MR[month],f['month']); ws.merge_range('A7:C7',str(year),f['year'])
    ws.merge_range('D6:E6','तांदूळ प्राप्त दिनांक',f['c']); ws.merge_range('F6:G6','',f['c']); ws.write('H6','एकूण कार्यदिन-',f['c']); ws.write('I6',cooked,f['c'])
    ws.merge_range('D7:E7','धान्यादी प्राप्त दिनांक',f['c']); ws.merge_range('F7:G7','',f['c']); ws.write('H7','अन्न शिजवलेले दिवस -',f['c']); ws.write('I7',cooked,f['c'])
    headers=['अ. क्र.','वस्तूचे नाव','मागील शिल्लक वस्तू','चालू महिन्यात प्राप्त वस्तू','एकूण वस्तू','अन्न शिजवण्यासाठी वापरलेल्या वस्तू','शिल्लक वस्तू','पुढील महिन्यासाठी मागणी','शेरा ( उसना दिला किंवा परत केला किंवा इतर बाबी)']
    for col,h in enumerate(headers): ws.write(7,col,h,f['h'])
    for col,n in enumerate(range(1,10)): ws.write(8,col,n,f['c'])
    imap=_ingredient_map(db); row=9
    for idx,(mr,ing) in enumerate(imap,1):
        s=_tx_summary(db,school.id,ing,first,last); total=s['opening']+s['received']
        vals=[idx,mr,float(s['opening']),float(s['received']),float(total),float(s['used']),float(s['closing']),'','']
        for col,v in enumerate(vals): ws.write(row,col,v,f['n'] if isinstance(v,float) else (f['l'] if col==1 else f['c']))
        row+=1
    ws.merge_range(row,0,row,8,'मागणी नोंदविताना शाळेकडे २० दिवसांचा साठा शिल्लक राहील याची दक्षता घेऊन मागणी नोंदवावी. आवश्यकतेपेक्षा जास्त साठा करून धान्य खराब होणार नाही याची दक्षता घ्यावी.',f['note']); row+=1
    rate=Decimal('2.59') if group=='1_5' else Decimal('3.88'); total_cost=(Decimal(att)*rate).quantize(Decimal('0.01'))
    fuel=(total_cost*Decimal('0.34')).quantize(Decimal('0')); supp=(total_cost*Decimal('0.28')).quantize(Decimal('0')); veg=total_cost-fuel-supp
    ws.merge_range(row,0,row,3,'खर्च',f['h']); ws.write(row,4,'इंधन बिल',f['h']); ws.write(row,5,'पूरक आहार',f['h']); ws.write(row,6,'भाजीपाला',f['h']); ws.write(row,7,'एकूण',f['h']); ws.write(row,8,'',f['c']); row+=1
    ws.merge_range(row,0,row,3,'शेकडा प्रमाण',f['c']); ws.write(row,4,34,f['c']); ws.write(row,5,28,f['c']); ws.write(row,6,38,f['c']); ws.write(row,7,float(rate),f['money']); ws.write(row,8,'',f['c']); row+=1
    ws.merge_range(row,0,row,3,f'1    महिन्यातील ताटांची संख्या -    {att}',f['l']); ws.write(row,4,float(fuel),f['money']); ws.write(row,5,float(supp),f['money']); ws.write(row,6,float(veg),f['money']); ws.write(row,7,float(total_cost),f['money']); ws.write(row,8,'',f['c']); row+=1
    ws.merge_range(row,0,row,8,f'2    इंधन व भाजीपाल्यासाठी खर्च केलेले अनुदान रुपये = {total_cost}    (ताटांची संख्या * दर)',f['l']); row+=1
    ws.merge_range(row,0,row,8,'3    स्वयंपाकी तथा मदतनीस मानधन रु. = __________    मदतनीस संख्या = ____    दर = ______',f['l']); row+=1
    ws.merge_range(row,0,row,8,'प्रमाणित करण्यात येते की, वर नमूद केलेली माहिती दैनंदिन नोंदवहीवरून घेतलेली आहे. ती तपासली व बरोबर आहे.',f['note']); row+=1
    ws.merge_range(row,0,row+1,2,'दिनांक -',f['sig']); ws.merge_range(row,3,row+1,5,'मुख्याध्यापक / सचिव\nशालेय व्यवस्थापन समिती',f['sig']); ws.merge_range(row,6,row+1,8,'केंद्र प्रमुख',f['sig'])
    ws.set_print_area(0,0,row+1,8); ws.repeat_rows(0,8)


def _daily_sheet(w, school, db, year, month, group, name):
    ws=w.add_worksheet(name); f=_styles(w); first=date(year,month,1); last=date(year,month,monthrange(year,month)[1]); imap=_ingredient_map(db)
    ws.set_landscape(); ws.set_paper(9); ws.fit_to_pages(1,1); ws.set_margins(0.15,0.15,0.2,0.2); ws.hide_gridlines(2)
    ws.set_column(0,0,4); ws.set_column(1,1,11); ws.set_column(2,2,11); ws.set_column(3,3,18); ws.set_column(4,4,8); ws.set_column(5,26,7)
    ws.merge_range(0,0,0,26,'प्रधानमंत्री पोषणशक्ती निर्माण योजना दैनंदिन खर्च नोंदवही भाग 2',f['title'])
    ws.merge_range(1,0,1,26,_school_line(school)+('    1 ते 5' if group=='1_5' else '    6 ते 8'),f['red'])
    ws.merge_range(2,0,2,2,MONTH_MR[month],f['month']); ws.merge_range(2,3,2,4,str(year),f['yellow'])
    headers=['अ. क्र.','दिनांक','वार','मेनु','लाभार्थी']+[mr for mr,_ in imap]
    for c,h in enumerate(headers): ws.write(3,c,h,f['dailyh'])
    row=4
    for day in range(1,last.day+1):
        dt=date(year,month,day); a=db.scalar(select(DailyAttendance).where(DailyAttendance.school_id==school.id,DailyAttendance.meal_date==dt)); meal=db.scalar(select(DailyMealEntry).where(DailyMealEntry.school_id==school.id,DailyMealEntry.meal_date==dt))
        ben=((a.class_1_5_present if group=='1_5' else a.class_6_8_present) or 0) if a else 0
        menu=(meal.menu.name_mr or meal.menu.name_en) if meal and meal.menu else ''
        cal=db.scalar(select(SchoolCalendarDay).where(SchoolCalendarDay.school_id==school.id,SchoolCalendarDay.calendar_date==dt))
        if not menu and cal and cal.title_mr: menu=cal.title_mr
        base=[day,dt.strftime('%d-%b-%y'),DAY_MR[dt.weekday()],menu,ben]
        for c,v in enumerate(base): ws.write(row,c,v,f['pink'] if (cal and not cal.meal_required) else f['c'])
        for j,(mr,ing) in enumerate(imap,start=5):
            q=Decimal(0)
            if ing:
                q=-_D(db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(StockTransaction.school_id==school.id,StockTransaction.ingredient_id==ing.id,StockTransaction.transaction_date==dt,StockTransaction.transaction_type=='CONSUMPTION')))
            ws.write_number(row,j,float(q),f['pink'] if (cal and not cal.meal_required) else f['n'])
        row+=1
    ws.write(row,0,'एकूण',f['h']); ws.merge_range(row,1,row,3,'महिन्याची एकूण नोंद',f['h']); ws.write_formula(row,4,f'=SUM(E5:E{row})',f['h'])
    for c in range(5,27): ws.write_formula(row,c,f'=SUM({xlsxwriter.utility.xl_col_to_name(c)}5:{xlsxwriter.utility.xl_col_to_name(c)}{row})',f['n'])
    row+=1
    ws.write(row,0,'शिल्लक',f['h']); ws.merge_range(row,1,row,3,'महिना अखेर',f['h']); ws.write(row,4,'',f['h'])
    for c,(_,ing) in enumerate(imap,start=5): ws.write_number(row,c,float(_tx_summary(db,school.id,ing,first,last)['closing']),f['n'])
    ws.merge_range(row+1,0,row+1,26,'भाजीपाला व पूरक आहाराची नोंद संबंधित कोड/शेरा नुसार करावी.',f['note'])
    ws.set_print_area(0,0,row+1,26); ws.repeat_rows(0,3)


@router.get('/export')
def exact_export(format: str, school_id: str, year: int, month: int,
                 db: Session=Depends(get_db), user: CurrentUser=Depends(get_current_user)):
    if month<1 or month>12: raise HTTPException(400,'Invalid month')
    school=_access(db,user,school_id); fmt=format.upper(); bio=BytesIO(); w=xlsxwriter.Workbook(bio,{'in_memory':True})
    w.set_properties({'title':'PM POSHAN Official Register','subject':'Workbook-matched school report'})
    if fmt=='MONTHLY_CENTER':
        _monthly_sheet(w,school,db,year,month,'1_5','1 ते 5'); _monthly_sheet(w,school,db,year,month,'6_8','6 ते 8')
        fn=f'PM_POSHAN_Monthly_Centre_Report_{year}_{month:02d}.xlsx'
    elif fmt=='DAILY_PART2':
        _daily_sheet(w,school,db,year,month,'1_5','भाग 2 - 1 ते 5'); _daily_sheet(w,school,db,year,month,'6_8','भाग 2 - 6 ते 8')
        fn=f'PM_POSHAN_Daily_Expense_Part2_{year}_{month:02d}.xlsx'
    else:
        w.close(); raise HTTPException(400,'format must be MONTHLY_CENTER or DAILY_PART2')
    w.close(); bio.seek(0)
    return StreamingResponse(bio,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{fn}"'})
