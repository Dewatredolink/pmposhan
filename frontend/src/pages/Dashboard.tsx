import { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../auth';
import { Lang } from '../i18n/translations';

type School = { id:string; code?:string; udise_code:string; name_en:string; name_mr:string; village?:string|null; class_1_5_strength:number; class_6_8_strength:number };
type Props = { lang: Lang; schoolId:string; school?:School; onNavigate?:(page:string)=>void };
type Summary={students:number;present_today:number;meals_today:number;meals_month:number;attendance_status:string;meal_status:string};
type CalendarDay={date:string;day_type:string;meal_required:boolean;title_en?:string|null;title_mr?:string|null};
type Compliance={required_days:number;complete_days:number;missing_days:number;compliance_percent:number;missing_dates:string[]};
type Balance={ingredient_id:string;name_en:string;name_mr:string;unit:string;balance:number;reorder_level:number;low_stock:boolean};
type Plan={plan?:{menu_date:string;menu_name_en?:string|null;menu_name_mr?:string|null}|null};

const fmt=(d:Date)=>d.toISOString().slice(0,10);
const addDays=(d:Date,n:number)=>{const x=new Date(d);x.setDate(x.getDate()+n);return x};
const dayMr=['रविवार','सोमवार','मंगळवार','बुधवार','गुरुवार','शुक्रवार','शनिवार'];
const dayEn=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const monthMr=['जानेवारी','फेब्रुवारी','मार्च','एप्रिल','मे','जून','जुलै','ऑगस्ट','सप्टेंबर','ऑक्टोबर','नोव्हेंबर','डिसेंबर'];
const monthEn=['January','February','March','April','May','June','July','August','September','October','November','December'];

export default function Dashboard({lang,schoolId,school,onNavigate}:Props){
 const mr=lang==='mr';
 const today=useMemo(()=>new Date(),[]);
 const [s,setS]=useState<Summary>({students:0,present_today:0,meals_today:0,meals_month:0,attendance_status:'NOT_ENTERED',meal_status:'NOT_ENTERED'});
 const [ops,setOps]=useState<any>(null);const [calendar,setCalendar]=useState<CalendarDay[]>([]);const [compliance,setCompliance]=useState<Compliance>({required_days:0,complete_days:0,missing_days:0,compliance_percent:0,missing_dates:[]});const [balances,setBalances]=useState<Balance[]>([]);const [plans,setPlans]=useState<Array<{date:Date;menu:string;holiday:boolean}>>([]);
 useEffect(()=>{if(!schoolId)return;const y=today.getFullYear(),m=today.getMonth()+1,ds=fmt(today);Promise.all([
  apiFetch(`/dashboard-summary?school_id=${schoolId}`).then(r=>r.ok?r.json():Promise.reject()),
  apiFetch(`/daily-operations?school_id=${schoolId}&meal_date=${ds}`).then(r=>r.ok?r.json():null),
  apiFetch(`/calendar/month?school_id=${schoolId}&year=${y}&month=${m}`).then(r=>r.ok?r.json():[]),
  apiFetch(`/compliance/month?school_id=${schoolId}&year=${y}&month=${m}`).then(r=>r.ok?r.json():null),
  apiFetch(`/stock/balances?school_id=${schoolId}`).then(r=>r.ok?r.json():[])
 ]).then(([sum,day,cal,comp,stock])=>{setS(sum);setOps(day);setCalendar(Array.isArray(cal)?cal:[]);if(comp)setCompliance(comp);setBalances(Array.isArray(stock)?stock:[])}).catch(()=>{});
 const dates=Array.from({length:5},(_,i)=>addDays(today,i));Promise.all(dates.map(d=>apiFetch(`/menu-plan?school_id=${schoolId}&menu_date=${fmt(d)}`).then(r=>r.ok?r.json():({} as Plan)).catch(()=>({} as Plan)))).then((xs:any[])=>setPlans(xs.map((x,i)=>{const d=dates[i];const calDay=calendar.find(c=>c.date===fmt(d));return{date:d,menu:x?.plan?(mr?x.plan.menu_name_mr:x.plan.menu_name_en)||(mr?'मेनू नियोजित':'Menu planned'):(calDay&&!calDay.meal_required?(mr?'सुट्टी':'Holiday'):(mr?'मेनू निश्चित नाही':'Not planned')),holiday:!!calDay&&!calDay.meal_required}}))).catch(()=>{});
 },[schoolId,lang]);
 const missing=new Set(compliance.missing_dates||[]);const low=balances.filter(x=>x.low_stock).slice(0,4);const ok=balances.filter(x=>!x.low_stock).slice(0,3);const schoolPhoto=localStorage.getItem('pmposhan.brand.schoolPhoto')||'';
 const currentMenu=ops?.meal?(mr?ops.meal.menu_name_mr:ops.meal.menu_name_en):ops?.planned_menu?(mr?ops.planned_menu.menu_name_mr:ops.planned_menu.menu_name_en):(mr?'मेनू नियोजित नाही':'Menu not planned');
 const verified=(s.attendance_status==='VERIFIED'&&s.meal_status==='VERIFIED');
 const quick=[
  {icon:'＋',title:mr?'दैनिक आहार नोंद':'Daily Meal Entry',cls:'q-green',page:'dailyMeal'},
  {icon:'▣',title:mr?'मेनू नियोजन':'Menu Planning',cls:'q-blue',page:'menuPlanner'},
  {icon:'◈',title:mr?'राशन आवश्यकता':'Ration Requirement',cls:'q-orange',page:'workbookRegisters'},
  {icon:'⬡',title:mr?'साठा नोंदवा':'Stock Receipt',cls:'q-purple',page:'stockReceipt'},
  {icon:'⇄',title:mr?'उसनवार नोंद':'Borrowed Stock',cls:'q-cyan',page:'workbookRegisters'},
  {icon:'▤',title:mr?'Excel अहवाल':'Excel Reports',cls:'q-red',page:'customReports'}
 ];
 return <main className="content dashboard-pro">
  <section className="welcome-grid">
   <div className="welcome-card">
    <div className="school-photo">{schoolPhoto?<img src={schoolPhoto} alt="School"/>:<div className="school-photo-fallback">🏫</div>}</div>
    <div className="welcome-copy"><h2>{mr?'नमस्कार, मुख्याध्यापक महोदय!':'Welcome, Headmaster!'}</h2><h3>{school?(mr?school.name_mr:school.name_en):(mr?'आपली शाळा':'Your School')}</h3><div className="school-meta"><span>🏫 UDISE: {school?.udise_code||'—'}</span><span>{mr?'एकूण विद्यार्थी':'Total students'}: {s.students}</span></div></div>
    <div className="quote"><strong>“{mr?'संतुलित आहार, उज्ज्वल भविष्य':'Balanced nutrition, brighter future'}”</strong><span>— PM POSHAN</span><div className="leaf">🌿</div></div>
   </div>
   <div className="today-card"><div className="today-label">▣ {mr?'आज':'Today'}</div><strong>{mr?dayMr[today.getDay()]:dayEn[today.getDay()]}, {today.getDate()} {mr?monthMr[today.getMonth()]:monthEn[today.getMonth()]} {today.getFullYear()}</strong><button onClick={()=>onNavigate?.('dailyMeal')}>{mr?'आजचे संपूर्ण कार्य पहा →':'View today’s work →'}</button></div>
  </section>

  <section className="dashboard-kpis">
   <article><div className="kpi-icon green">👥</div><div><span>{mr?'एकूण विद्यार्थी':'Total Students'}</span><strong>{s.students}</strong><small>{mr?'इ. 1-5':'Cls 1-5'}: {school?.class_1_5_strength||0} &nbsp;|&nbsp; {mr?'इ. 6-8':'Cls 6-8'}: {school?.class_6_8_strength||0}</small></div></article>
   <article><div className="kpi-icon blue">🍴</div><div><span>{mr?'आजचा मेनू':'Today’s Menu'}</span><strong className="kpi-menu">{currentMenu||'—'}</strong><small>{fmt(today)}</small></div></article>
   <article><div className="kpi-icon orange">⬡</div><div><span>{mr?'आजची साठा स्थिती':'Stock Status'}</span><strong>{low.length}</strong><small className={low.length?'warn-text':''}>{low.length?(mr?'महत्त्वाच्या वस्तू कमी':'items low'):(mr?'साठा ठीक':'Stock healthy')}</small></div></article>
   <article><div className="kpi-icon red">▥</div><div><span>{mr?'महिन्याचे आहार पालन':'Monthly Compliance'}</span><strong className="red-text">{Math.round(compliance.compliance_percent||0)}%</strong><small>{compliance.complete_days} / {compliance.required_days} {mr?'दिवस':'days'}</small></div></article>
   <article><div className="kpi-icon purple">✓</div><div><span>{mr?'नोंदी पडताळणी':'Verification'}</span><strong>{verified?'0':'1'}</strong><small className={!verified?'red-text':''}>{verified?(mr?'पूर्ण':'Complete'):(mr?'प्रलंबित':'Pending')}</small></div></article>
  </section>

  <section className="dashboard-main-grid">
   <div className="panel chart-panel"><div className="panel-title"><h3>{mr?'महिन्याचा आहार पालन आढावा':'Monthly Meal Compliance Overview'}</h3><div className="legend"><span><i className="lg-good"></i>{mr?'मेनू/नोंद पूर्ण':'Complete'}</span><span><i className="lg-off"></i>{mr?'सुट्टी / इतर':'Holiday / Other'}</span></div></div><div className="bar-chart"><div className="axis"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div><div className="bars">{calendar.map((d,i)=>{const h=d.meal_required?(missing.has(d.date)?40:86):72;const cls=!d.meal_required?'off':missing.has(d.date)?'miss':'good';return <div className="bar-col" key={d.date}><div className={`bar ${cls}`} style={{height:`${h}%`}}></div><small>{i+1}</small></div>})}</div></div><div className="chart-month">{mr?monthMr[today.getMonth()]:monthEn[today.getMonth()]} {today.getFullYear()}</div></div>
   <div className="panel quick-panel"><div className="panel-title"><h3>{mr?'त्वरित कृती':'Quick Actions'}</h3></div><div className="quick-grid">{quick.map(q=><button key={q.page+q.title} className={q.cls} onClick={()=>onNavigate?.(q.page)}><b>{q.icon}</b><span>{q.title}</span></button>)}</div></div>
  </section>

  <section className="dashboard-bottom-grid">
   <div className="panel upcoming-panel"><div className="panel-title"><h3>{mr?'आगामी शालेय दिवस':'Upcoming School Days'}</h3></div><div className="table-wrap"><table><thead><tr><th>{mr?'दिनांक':'Date'}</th><th>{mr?'वार':'Day'}</th><th>{mr?'मेनू':'Menu'}</th><th>{mr?'स्थिती':'Status'}</th></tr></thead><tbody>{plans.map((p,i)=><tr key={i}><td>{p.date.toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'})}</td><td>{mr?dayMr[p.date.getDay()]:dayEn[p.date.getDay()]}</td><td>{p.menu}</td><td><span className={`pill ${p.holiday?'neutral':'planned'}`}>{p.holiday?(mr?'सुट्टी':'Holiday'):(mr?'नियोजित':'Planned')}</span></td></tr>)}</tbody></table></div><button className="text-link" onClick={()=>onNavigate?.('schoolCalendar')}>{mr?'संपूर्ण दिनदर्शिका पहा →':'View full calendar →'}</button></div>
   <div className="panel stock-panel"><div className="panel-title"><h3>{mr?'साठा सूचना':'Stock Alerts'}</h3><button className="text-link" onClick={()=>onNavigate?.('stockRegister')}>{mr?'सर्व साठा पहा →':'View all stock →'}</button></div>{low.length>0&&<div className="stock-section low-section"><div className="stock-section-head">{mr?'कमी साठा (Low Stock)':'Low Stock'}</div>{low.map(x=><div className="stock-row" key={x.ingredient_id}><span>{mr?x.name_mr:x.name_en}</span><b>{x.balance} {x.unit}</b><em>{mr?'कमी':'Low'}</em></div>)}</div>}<div className="stock-section good-section"><div className="stock-section-head">{mr?'योग्य साठा':'Healthy Stock'}</div>{ok.map(x=><div className="stock-row" key={x.ingredient_id}><span>{mr?x.name_mr:x.name_en}</span><b>{x.balance} {x.unit}</b><em>{mr?'ठीक':'OK'}</em></div>)}{!ok.length&&<div className="stock-empty">{mr?'साठा माहिती उपलब्ध नाही.':'No stock information.'}</div>}</div></div>
  </section>

  <section className="dashboard-banners"><div className="nutrition-banner"><span>🌿</span><div><strong>{mr?'पोषणमय शाळा, निरोगी पिढी':'Nourished school, healthier generation'}</strong><small>PM POSHAN – {mr?'प्रत्येक मुलासाठी पौष्टिक आहार, प्रत्येक दिवस उज्ज्वल उद्यासाठी':'nutritious meals for every child'}</small></div></div><div className="community-banner"><span>👥</span><b>{mr?'शाळा':'School'}</b><i>•</i><b>{mr?'पालक':'Parents'}</b><i>•</i><b>{mr?'शिक्षक':'Teachers'}</b><i>•</i><b>{mr?'समाज':'Community'}</b></div></section>
 </main>
}
