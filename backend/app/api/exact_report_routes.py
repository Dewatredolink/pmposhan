from calendar import monthrange
from datetime import date
from decimal import Decimal
from io import BytesIO
from urllib.parse import quote

import xlsxwriter
from xlsxwriter.utility import xl_col_to_name
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
    aliases={
        'rice':['rice','तांदूळ'], 'moong':['moong dal','mung dal','मुगदाळ'], 'tur':['tur dal','toor dal','तूरदाळ'],
        'masoor':['masoor','मसूर'], 'matki':['matki','मटकी'], 'mung':['whole moong','whole mung','मूग'],
        'chawli':['chawli','cowpea','चवळी'], 'chana':['chana','harbhara','हरभरा'], 'peas':['peas','वाटाणा'],
        'soya':['soya','soybean','सोयाबीन'], 'cumin':['cumin','जिरे'], 'mustard':['mustard','मोहरी'],
        'turmeric':['turmeric','हळद'], 'masala':['garam masala','masala','मसाला'], 'oil':['oil','तेल'],
        'salt':['salt','मीठ'], 'sugar':['sugar','jaggery','गुळ','साखर'], 'milk':['milk powder','दूध पावडर'],
        'ragi':['ragi','nachni','नाचणी'], 'egg':['egg','अंडी'], 'supplement':['supplement','पूरक'],
        'vegetable':['vegetable','fuel','भाजीपाला','इंधन'],
    }
    for mr,key in ING_ORDER:
        found=None
        needles=[x.replace(' ','').lower() for x in aliases.get(key,[key,mr])]
        for x in rows:
            nm=((x.name_mr or '')+' '+(x.name_en or '')+' '+(x.code or '')).replace(' ','').lower()
            if any(n in nm for n in needles):
                found=x; break
        out.append((mr,found))
    return out

def _txs(db, school_id, ing, first, last):
    if not ing: return []
    return db.scalars(select(StockTransaction).where(
        StockTransaction.school_id==school_id,
        StockTransaction.ingredient_id==ing.id,
        StockTransaction.transaction_date.between(first,last)
    )).all()

def _tx_summary(db, school_id, ing, first, last):
    if not ing:
        return dict(opening=Decimal(0),received=Decimal(0),used=Decimal(0),closing=Decimal(0),other=Decimal(0))
    opening=_D(db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(
        StockTransaction.school_id==school_id,
        StockTransaction.ingredient_id==ing.id,
        StockTransaction.transaction_date<first)))
    txs=_txs(db,school_id,ing,first,last)
    received=sum((_D(t.quantity) for t in txs if _D(t.quantity)>0),Decimal(0))
    used=-sum((_D(t.quantity) for t in txs if t.transaction_type=='CONSUMPTION' and _D(t.quantity)<0),Decimal(0))
    total=sum((_D(t.quantity) for t in txs),Decimal(0))
    closing=opening+total
    other=-(sum((_D(t.quantity) for t in txs if _D(t.quantity)<0 and t.transaction_type!='CONSUMPTION'),Decimal(0)))
    return dict(opening=opening,received=received,used=used,closing=closing,other=other)

def _first_receipt_date(db, school_id, ing, first, last):
    if not ing: return ''
    rows=db.scalars(select(StockTransaction).where(
        StockTransaction.school_id==school_id,
        StockTransaction.ingredient_id==ing.id,
        StockTransaction.transaction_date.between(first,last),
        StockTransaction.quantity>0
    ).order_by(StockTransaction.transaction_date)).all()
    return rows[0].transaction_date.strftime('%d-%m-%Y') if rows else ''

def _attendance_month(db, school_id, first, last, group):
    rows=db.scalars(select(DailyAttendance).where(
        DailyAttendance.school_id==school_id,
        DailyAttendance.meal_date.between(first,last))).all()
    return sum(((r.class_1_5_present if group=='1_5' else r.class_6_8_present) or 0) for r in rows)

def _meal_days(db, school_id, first, last, group):
    rows=db.scalars(select(DailyMealEntry).where(
        DailyMealEntry.school_id==school_id,
        DailyMealEntry.meal_date.between(first,last),
        DailyMealEntry.status=='VERIFIED')).all()
    n=0
    for r in rows:
        a=db.scalar(select(DailyAttendance).where(
            DailyAttendance.school_id==school_id,
            DailyAttendance.meal_date==r.meal_date))
        if a and ((a.class_1_5_present if group=='1_5' else a.class_6_8_present) or 0)>0:
            n+=1
    return n

def _working_days(db, school_id, first, last):
    rows=db.scalars(select(SchoolCalendarDay).where(
        SchoolCalendarDay.school_id==school_id,
        SchoolCalendarDay.calendar_date.between(first,last))).all()
    if rows:
        return sum(1 for r in rows if bool(r.meal_required))
    return sum(1 for d in range(1,last.day+1) if date(first.year,first.month,d).weekday()!=6)

def _styles(w):
    font='Noto Sans Devanagari'
    return {
      'title':w.add_format({'bold':True,'font_name':font,'font_size':11,'align':'center','valign':'vcenter'}),
      'red':w.add_format({'bold':True,'font_name':font,'font_size':9,'font_color':'#E60000','align':'center','valign':'vcenter'}),
      'yellow':w.add_format({'bold':True,'font_name':font,'font_size':18,'bg_color':'#FFF200','font_color':'#E60000','align':'center','valign':'vcenter','border':1}),
      'month':w.add_format({'bold':True,'font_name':font,'font_size':14,'bg_color':'#D60000','font_color':'#FFFFFF','align':'center','valign':'vcenter','border':1}),
      'year':w.add_format({'bold':True,'font_name':font,'font_size':16,'bg_color':'#FF0000','font_color':'#FFFF00','align':'center','valign':'vcenter','border':1}),
      'h':w.add_format({'bold':True,'font_name':font,'font_size':7,'border':1,'align':'center','valign':'vcenter','text_wrap':True}),
      'c':w.add_format({'font_name':font,'font_size':8,'border':1,'align':'center','valign':'vcenter'}),
      'l':w.add_format({'font_name':font,'font_size':8,'border':1,'align':'left','valign':'vcenter'}),
      'n':w.add_format({'font_name':font,'font_size':8,'border':1,'align':'center','num_format':'0.000'}),
      'n1':w.add_format({'font_name':font,'font_size':8,'border':1,'align':'center','num_format':'0.0##'}),
      'money':w.add_format({'font_name':font,'font_size':8,'border':1,'align':'center','num_format':'0.00'}),
      'note':w.add_format({'font_name':font,'font_size':7,'border':1,'text_wrap':True,'valign':'vcenter'}),
      'sig':w.add_format({'bold':True,'font_name':font,'font_size':8,'align':'center','valign':'vcenter'}),
      'pink':w.add_format({'font_name':font,'font_size':7,'border':1,'align':'center','bg_color':'#F4CCCC'}),
      'dailyh':w.add_format({'bold':True,'font_name':font,'font_size':7,'border':1,'align':'center','valign':'vcenter','text_wrap':True,'bg_color':'#FCE5CD'}),
      'daily':w.add_format({'font_name':font,'font_size':7,'border':1,'align':'center','valign':'vcenter'}),
      'daily_l':w.add_format({'font_name':font,'font_size':7,'border':1,'align':'left','valign':'vcenter'}),
      'yellow_cell':w.add_format({'font_name':font,'font_size':8,'border':1,'align':'center','bg_color':'#FFF200','num_format':'0.000'}),
    }

def _school_line(school):
    c=school.cluster; b=c.block if c else None; d=b.district if b else None
    return f"{school.name_mr or school.name_en} , केंद्र - {(c.name_mr or c.name_en) if c else ''} , तालुका - {(b.name_mr or b.name_en) if b else ''} , जिल्हा - {(d.name_mr or d.name_en) if d else ''}"

def _monthly_block(ws,w,school,db,year,month,group,start_col):
    f=_styles(w); first=date(year,month,1); last=date(year,month,monthrange(year,month)[1]); sc=start_col
    strength=(school.class_1_5_strength if group=='1_5' else school.class_6_8_strength) or 0
    att=_attendance_month(db,school.id,first,last,group)
    cooked=_meal_days(db,school.id,first,last,group)
    working=_working_days(db,school.id,first,last)
    imap=_ingredient_map(db)
    rice=imap[0][1] if imap else None
    first_any=next((ing for _,ing in imap[1:] if ing),None)

    ws.merge_range(0,sc,0,sc+8,'शालेय पोषण आहार प्रपत्र',f['title'])
    ws.merge_range(1,sc,1,sc+8,'शाळेने केंद्रप्रमुखांना दरमहा 5 तारखेपर्यंत द्यावयाचा अहवाल  ( 2 प्रतीत )',f['title'])
    ws.merge_range(2,sc,2,sc+8,_school_line(school),f['red'])
    ws.merge_range(3,sc,4,sc+2,'1 ते 5' if group=='1_5' else '6 ते 8',f['yellow'])
    ws.merge_range(3,sc+3,3,sc+4,'पटसंख्या 1 ली ते 5 वी -' if group=='1_5' else 'पटसंख्या ६ वी ते ८ वी -',f['c'])
    ws.merge_range(3,sc+5,3,sc+6,strength,f['c'])
    ws.merge_range(4,sc+3,4,sc+4,'महिन्यातील उपस्थिती',f['c'])
    ws.merge_range(4,sc+5,4,sc+6,att,f['c'])
    ws.merge_range(5,sc,5,sc+2,MONTH_MR[month],f['month'])
    ws.merge_range(6,sc,6,sc+2,str(year),f['year'])
    ws.merge_range(5,sc+3,5,sc+4,'तांदूळ प्राप्त दिनांक',f['c'])
    ws.merge_range(5,sc+5,5,sc+6,_first_receipt_date(db,school.id,rice,first,last),f['c'])
    ws.write(5,sc+7,'एकूण कार्यदिन-',f['c']); ws.write(5,sc+8,working,f['c'])
    ws.merge_range(6,sc+3,6,sc+4,'धान्यादी वस्तू प्राप्त दिनांक',f['c'])
    ws.merge_range(6,sc+5,6,sc+6,_first_receipt_date(db,school.id,first_any,first,last),f['c'])
    ws.write(6,sc+7,'अन्न शिजवलेले दिवस -',f['c']); ws.write(6,sc+8,cooked,f['c'])
    headers=['अ. क्र.','वस्तूचे नाव','मागील शिल्लक वस्तू','चालू महिन्यात प्राप्त वस्तू','एकूण वस्तू','अन्न शिजवण्यासाठी वापरलेल्या वस्तू','शिल्लक वस्तू','पुढील महिन्यासाठी मागणी','शेरा (उसना दिला/परत केला/इतर बाबी)']
    for c,h in enumerate(headers): ws.write(7,sc+c,h,f['h'])
    for c,n in enumerate(range(1,10)): ws.write(8,sc+c,n,f['c'])

    row=9
    for idx,(mr,ing) in enumerate(imap,1):
        s=_tx_summary(db,school.id,ing,first,last); total=s['opening']+s['received']
        vals=[idx,mr,float(s['opening']),float(s['received']),float(total),float(s['used']),float(s['closing']),'','']
        for c,v in enumerate(vals):
            fmt=f['n'] if isinstance(v,float) else (f['l'] if c==1 else f['c'])
            if isinstance(v,float) and v<0: fmt=f['yellow_cell']
            ws.write(row,sc+c,v,fmt)
        row+=1

    ws.merge_range(row,sc,row,sc+8,'मागणी नोंदविताना शाळेकडे २० दिवसांचा साठा शिल्लक राहील याची दक्षता घेऊन मागणी नोंदवावी. आवश्यकतेपेक्षा जास्त साठा करून धान्य खराब होणार नाही याची दक्षता घ्यावी.',f['note']); row+=1
    rate=Decimal('2.59') if group=='1_5' else Decimal('3.88')
    total_cost=(Decimal(att)*rate).quantize(Decimal('0.01'))
    fuel=(total_cost*Decimal('0.34')).quantize(Decimal('0'))
    supp=(total_cost*Decimal('0.28')).quantize(Decimal('0'))
    veg=total_cost-fuel-supp

    ws.merge_range(row,sc,row,sc+3,'खर्च',f['h'])
    ws.write(row,sc+4,'इंधन बिल',f['h']); ws.write(row,sc+5,'पूरक आहार',f['h']); ws.write(row,sc+6,'भाजीपाला',f['h']); ws.write(row,sc+7,'एकूण',f['h']); ws.write(row,sc+8,'दर',f['h']); row+=1
    ws.merge_range(row,sc,row,sc+3,'शेकडा प्रमाण',f['c'])
    ws.write(row,sc+4,34,f['c']); ws.write(row,sc+5,28,f['c']); ws.write(row,sc+6,38,f['c']); ws.write(row,sc+7,'',f['c']); ws.write(row,sc+8,float(rate),f['money']); row+=1
    ws.merge_range(row,sc,row,sc+3,f'1  महिन्यातील ताटांची संख्या - {att}',f['l'])
    ws.write(row,sc+4,float(fuel),f['money']); ws.write(row,sc+5,float(supp),f['money']); ws.write(row,sc+6,float(veg),f['money']); ws.write(row,sc+7,float(total_cost),f['money']); ws.write(row,sc+8,'',f['c']); row+=1
    ws.merge_range(row,sc,row,sc+8,f'2  इंधन व भाजीपाल्यासाठी खर्च केलेले अनुदान रुपये = {total_cost}  (ताटांची संख्या × दर)',f['l']); row+=1
    ws.merge_range(row,sc,row,sc+8,'3  स्वयंपाकी तथा मदतनीस मानधन रु. = __________   मदतनीस संख्या = ____   दर = ______',f['l']); row+=1
    ws.merge_range(row,sc,row,sc+8,'प्रमाणित करण्यात येते की, वर नमूद केलेली माहिती दैनंदिन नोंदवहीवरून घेतलेली आहे. ती तपासली व बरोबर आहे.',f['note']); row+=1
    ws.merge_range(row,sc,row+1,sc+2,'दिनांक -',f['sig'])
    ws.merge_range(row,sc+3,row+1,sc+5,'मुख्याध्यापक / सचिव\nशालेय व्यवस्थापन समिती',f['sig'])
    ws.merge_range(row,sc+6,row+1,sc+8,'केंद्र प्रमुख',f['sig'])
    return row+1

def _monthly_combined_sheet(w,school,db,year,month):
    ws=w.add_worksheet('मासिक अहवाल'); f=_styles(w)
    ws.set_landscape(); ws.set_paper(9); ws.fit_to_pages(1,1); ws.set_margins(0.15,0.15,0.2,0.2); ws.center_horizontally(); ws.hide_gridlines(2)
    for c in range(19): ws.set_column(c,c,9)
    ws.set_column(1,1,15); ws.set_column(10,10,2); ws.set_column(11,11,15)
    end1=_monthly_block(ws,w,school,db,year,month,'1_5',0)
    end2=_monthly_block(ws,w,school,db,year,month,'6_8',10)
    end=max(end1,end2)
    ws.print_area(0,0,end,18)
    ws.repeat_rows(0,8)

def _monthly_individual_sheet(w,school,db,year,month,group,name):
    ws=w.add_worksheet(name); f=_styles(w)
    ws.set_landscape(); ws.set_paper(9); ws.fit_to_pages(1,1); ws.set_margins(0.2,0.2,0.25,0.25); ws.center_horizontally(); ws.hide_gridlines(2)
    ws.set_column(0,0,4); ws.set_column(1,1,18); ws.set_column(2,6,12); ws.set_column(7,7,13); ws.set_column(8,8,18)
    end=_monthly_block(ws,w,school,db,year,month,group,0)
    ws.print_area(0,0,end,8); ws.repeat_rows(0,8)

def _daily_display_qty(q, ing):
    if not ing: return 0
    unit=(ing.base_unit or '').strip().upper()
    q=_D(q)
    if unit in {'KG','KGS','KILOGRAM','KILOGRAMS'}: return float(q*Decimal('1000'))
    if unit in {'L','LTR','LITRE','LITER','LITRES','LITERS'}: return float(q*Decimal('1000'))
    return float(q)

def _daily_total_base(q_display, ing):
    if not ing: return 0
    unit=(ing.base_unit or '').strip().upper()
    q=_D(q_display)
    if unit in {'KG','KGS','KILOGRAM','KILOGRAMS','L','LTR','LITRE','LITER','LITRES','LITERS'}:
        return float(q/Decimal('1000'))
    return float(q)

def _daily_sheet(w, school, db, year, month, group, name):
    ws=w.add_worksheet(name); f=_styles(w)
    first=date(year,month,1); last=date(year,month,monthrange(year,month)[1]); imap=_ingredient_map(db)
    physical=imap[:20]
    ws.set_landscape(); ws.set_paper(9); ws.fit_to_pages(1,1); ws.set_margins(0.1,0.1,0.15,0.15); ws.hide_gridlines(2)
    ws.set_column(0,0,3.5); ws.set_column(1,1,9); ws.set_column(2,2,9); ws.set_column(3,3,18); ws.set_column(4,4,7)
    ws.set_column(5,24,6.2); ws.set_column(25,25,10); ws.set_column(26,26,9)

    ws.merge_range(0,0,0,2,MONTH_MR[month],f['month'])
    ws.merge_range(0,3,0,4,str(year),f['yellow'])
    ws.merge_range(0,5,0,26,'प्रधानमंत्री पोषणशक्ती निर्माण योजना दैनंदिन खर्च नोंदवही भाग 2',f['title'])
    ws.merge_range(1,0,1,26,_school_line(school)+('   1 ते 5' if group=='1_5' else '   6 ते 8'),f['red'])

    headers=['अ. क्र.','दिनांक','वार','मेनु','लाभार्थी']+[mr for mr,_ in physical]+['पूरक आहार व भाजीपाला','भाजीपाला व इंधनखर्च']
    for c,h in enumerate(headers): ws.write(2,c,h,f['dailyh'])

    # Opening / receipt / total rows match the supplied register structure.
    top_labels=['मागील शिल्लक','प्राप्त','एकूण']
    summaries=[]
    for _,ing in physical:
        s=_tx_summary(db,school.id,ing,first,last)
        summaries.append((s['opening'],s['received'],s['opening']+s['received']))
    for rr,label in enumerate(top_labels,start=3):
        ws.merge_range(rr,0,rr,3,label,f['h']); ws.write(rr,4,'कि.ग्रॅ./लि./नग',f['h'])
        for j,(mr,ing) in enumerate(physical,start=5):
            v=summaries[j-5][rr-3]
            ws.write_number(rr,j,float(v),f['n'])
        ws.write(rr,25,'',f['c']); ws.write(rr,26,'',f['money'])

    unit_row=6
    ws.merge_range(unit_row,0,unit_row,3,'दैनंदिन वापराचे एकक',f['h']); ws.write(unit_row,4,'लाभार्थी',f['h'])
    for j,(mr,ing) in enumerate(physical,start=5):
        unit=(ing.base_unit or '').upper() if ing else ''
        disp='नग↓' if j==24 else ('मिली↓' if mr=='तेल' else ('ग्रॅम↓' if unit in {'KG','KGS','KILOGRAM','KILOGRAMS'} or mr!='अंडी' else 'नग↓'))
        if mr=='तेल': disp='मिली↓'
        if mr=='अंडी': disp='नग↓'
        ws.write(unit_row,j,disp,f['h'])
    ws.write(unit_row,25,'कोड',f['h']); ws.write(unit_row,26,'रु.',f['h'])

    rate=Decimal('2.59') if group=='1_5' else Decimal('3.88')
    row=7
    display_totals=[Decimal('0') for _ in physical]
    for day in range(1,last.day+1):
        dt=date(year,month,day)
        a=db.scalar(select(DailyAttendance).where(DailyAttendance.school_id==school.id,DailyAttendance.meal_date==dt))
        meal=db.scalar(select(DailyMealEntry).where(DailyMealEntry.school_id==school.id,DailyMealEntry.meal_date==dt))
        ben=((a.class_1_5_present if group=='1_5' else a.class_6_8_present) or 0) if a else 0
        menu=(meal.menu.name_mr or meal.menu.name_en) if meal and meal.menu else ''
        cal=db.scalar(select(SchoolCalendarDay).where(SchoolCalendarDay.school_id==school.id,SchoolCalendarDay.calendar_date==dt))
        if not menu and cal:
            menu=(getattr(cal,'title_mr',None) or getattr(cal,'title_en',None) or '')
        holiday=bool(cal and not cal.meal_required)
        fmt=f['pink'] if holiday else f['daily']
        lfmt=f['pink'] if holiday else f['daily_l']
        base=[day,dt.strftime('%d-%m-%Y'),DAY_MR[dt.weekday()],menu,ben if ben else ('-' if holiday else 0)]
        for c,v in enumerate(base): ws.write(row,c,v,lfmt if c==3 else fmt)
        for j,(mr,ing) in enumerate(physical,start=5):
            raw=Decimal(0)
            if ing:
                raw=-_D(db.scalar(select(func.coalesce(func.sum(StockTransaction.quantity),0)).where(
                    StockTransaction.school_id==school.id,
                    StockTransaction.ingredient_id==ing.id,
                    StockTransaction.transaction_date==dt,
                    StockTransaction.transaction_type=='CONSUMPTION')))
            dv=Decimal(str(_daily_display_qty(raw,ing)))
            display_totals[j-5]+=dv
            ws.write(row,j,'-' if holiday and dv==0 else float(dv),fmt)
        ws.write(row,25,'-' if holiday else '',fmt)
        ws.write(row,26,'-' if holiday else float((Decimal(ben)*rate).quantize(Decimal('0.01'))),f['pink'] if holiday else f['money'])
        row+=1

    ws.merge_range(row,0,row,3,'एकूण कार्यदिन / एकूण वापर',f['h'])
    total_ben=_attendance_month(db,school.id,first,last,group)
    ws.write(row,4,total_ben,f['h'])
    for j,(mr,ing) in enumerate(physical,start=5):
        ws.write_number(row,j,_daily_total_base(display_totals[j-5],ing),f['n'])
    ws.write(row,25,'',f['h']); ws.write(row,26,float((Decimal(total_ben)*rate).quantize(Decimal('0.01'))),f['money'])
    row+=1

    ws.merge_range(row,0,row,3,'शिल्लक',f['h']); ws.write(row,4,'महिना अखेर',f['h'])
    for j,(mr,ing) in enumerate(physical,start=5):
        ws.write_number(row,j,float(_tx_summary(db,school.id,ing,first,last)['closing']),f['n'])
    ws.write(row,25,'',f['h']); ws.write(row,26,0,f['money']); row+=1

    ws.merge_range(row,0,row,17,'भाजीपाला = 1-टोमॅटो, 2-मिरची, 3-वांगी, 4-बटाटा, 5-तोंडली, 6-शेवगा, 7-वालपापडी, 8-वाल, 9-फरसबी, 10-तेलपड, 11-ढोबळी मिरची, 12-दोडका, 13-सुरण, 14-करटोली, 15-माठ, 16-दुधी भोपळा, 17-लसूण, 18-पालक, 19-मेथी, 20-शेपू, 21-मुळा, 22-घोसाळी, 23-शेरोळे, 24-डांगर(भोपळा)',f['note'])
    ws.merge_range(row,18,row,26,'पूरक आहार = b-बिस्किट, g-गुळ, r-राजगिरा लाडू, c-चिक्की, s-शेंगदाणा लाडू',f['note'])
    ws.print_area(0,0,row,26); ws.repeat_rows(0,6)

def _stream(bio, filename):
    encoded=quote(filename)
    return StreamingResponse(
        bio,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':f"attachment; filename*=UTF-8''{encoded}"}
    )

@router.get('/export')
def exact_export(format: str, school_id: str, year: int, month: int,
                 db: Session=Depends(get_db), user: CurrentUser=Depends(get_current_user)):
    if month<1 or month>12: raise HTTPException(400,'Invalid month')
    school=_access(db,user,school_id); fmt=format.upper(); bio=BytesIO()
    w=xlsxwriter.Workbook(bio,{'in_memory':True})
    w.set_properties({'title':'पीएम पोषण अधिकृत अहवाल','subject':'मराठी शालेय अहवाल'})
    if fmt=='MONTHLY_CENTER':
        _monthly_combined_sheet(w,school,db,year,month)
        _monthly_individual_sheet(w,school,db,year,month,'1_5','१ ते ५')
        _monthly_individual_sheet(w,school,db,year,month,'6_8','६ ते ८')
        fn=f'पीएम_पोषण_मासिक_केंद्र_अहवाल_{year}_{month:02d}.xlsx'
    elif fmt=='DAILY_PART2':
        _daily_sheet(w,school,db,year,month,'1_5','भाग २ - १ ते ५')
        _daily_sheet(w,school,db,year,month,'6_8','भाग २ - ६ ते ८')
        fn=f'पीएम_पोषण_दैनंदिन_खर्च_नोंदवही_भाग_२_{year}_{month:02d}.xlsx'
    else:
        w.close(); raise HTTPException(400,'format must be MONTHLY_CENTER or DAILY_PART2')
    w.close(); bio.seek(0)
    return _stream(bio,fn)

