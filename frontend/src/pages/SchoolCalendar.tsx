import {useEffect,useState} from 'react';
import {apiFetch, realmRoles} from '../auth';

type Day={date:string;day_type:string;meal_required:boolean;title_en?:string;title_mr?:string;configured:boolean};
type Compliance={required_days:number;complete_days:number;missing_days:number;compliance_percent:number;missing_dates:string[]};

async function readJson<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || '';
  let body: any = null;
  if (contentType.includes('application/json')) {
    body = await response.json();
  } else {
    const text = await response.text();
    body = text ? {detail: text} : null;
  }
  if (!response.ok) {
    const detail = body?.detail || body?.message || `${response.status} ${response.statusText}`;
    throw new Error(String(detail));
  }
  return body as T;
}

export default function SchoolCalendar({lang,schoolId}:{lang:'mr'|'en';schoolId:string}){
 const now=new Date();
 const [year,setYear]=useState(now.getFullYear());
 const [month,setMonth]=useState(now.getMonth()+1);
 const [days,setDays]=useState<Day[]>([]);
 const [comp,setComp]=useState<Compliance|null>(null);
 const [msg,setMsg]=useState('');
 const [loading,setLoading]=useState(false);
 const canEdit=realmRoles().some(r=>['HEADMASTER','SYSTEM_ADMIN'].includes(r));

 const load=async()=>{
   if(!schoolId){setDays([]);setComp(null);setMsg(lang==='mr'?'शाळा निवडलेली नाही':'No school selected');return;}
   setLoading(true); setMsg('');
   try{
     const calendarResponse = await apiFetch(`/calendar/month?school_id=${schoolId}&year=${year}&month=${month}`);
     const calendarData = await readJson<unknown>(calendarResponse);
     if(!Array.isArray(calendarData)) throw new Error(lang==='mr'?'कॅलेंडर API कडून चुकीचा प्रतिसाद मिळाला':'Calendar API returned an invalid response');
     setDays(calendarData as Day[]);

     const complianceResponse = await apiFetch(`/compliance/month?school_id=${schoolId}&year=${year}&month=${month}`);
     const complianceData = await readJson<Compliance>(complianceResponse);
     setComp(complianceData);
   }catch(e:any){
     setDays([]); setComp(null); setMsg(e?.message || String(e));
   }finally{setLoading(false);}
 };

 useEffect(()=>{load()},[schoolId,year,month]);

 const defaults=async()=>{
   try{
     setMsg('');
     const response=await apiFetch('/calendar/month/defaults',{method:'POST',body:JSON.stringify({school_id:schoolId,year,month})});
     await readJson(response);
     setMsg(lang==='mr'?'महिन्याचे डीफॉल्ट कॅलेंडर तयार केले':'Default month calendar created');
     await load();
   }catch(e:any){setMsg(e?.message || String(e));}
 };

 const change=async(d:Day,type:string)=>{
   try{
     setMsg('');
     const meal=type==='WORKING';
     const response=await apiFetch('/calendar/day',{method:'PUT',body:JSON.stringify({school_id:schoolId,date:d.date,day_type:type,meal_required:meal})});
     await readJson(response);
     await load();
   }catch(e:any){setMsg(e?.message || String(e));}
 };

 return <div className="page"><div className="page-head"><div><h2>{lang==='mr'?'शाळा कॅलेंडर व अनुपालन':'School Calendar & Compliance'}</h2><p>{lang==='mr'?'कामकाज, सुट्ट्या आणि भोजन आवश्यक दिवस':'Working days, holidays and meal-required days'}</p></div></div>
 <div className="card form-grid"><label>{lang==='mr'?'वर्ष':'Year'}<input type="number" value={year} onChange={e=>setYear(+e.target.value)}/></label><label>{lang==='mr'?'महिना':'Month'}<input type="number" min="1" max="12" value={month} onChange={e=>setMonth(+e.target.value)}/></label>{canEdit&&<button onClick={defaults} disabled={loading}>{lang==='mr'?'महिना तयार करा':'Create Month Defaults'}</button>}</div>
 {comp&&<div className="stats-row"><div className="stat-card"><b>{comp.required_days}</b><span>{lang==='mr'?'भोजन आवश्यक दिवस':'Meal-required days'}</span></div><div className="stat-card"><b>{comp.complete_days}</b><span>{lang==='mr'?'पूर्ण':'Complete'}</span></div><div className="stat-card"><b>{comp.missing_days}</b><span>{lang==='mr'?'प्रलंबित':'Missing'}</span></div><div className="stat-card"><b>{comp.compliance_percent}%</b><span>{lang==='mr'?'अनुपालन':'Compliance'}</span></div></div>}
 {msg&&<div className="notice">{msg}</div>}
 <div className="card table-wrap"><table><thead><tr><th>{lang==='mr'?'दिनांक':'Date'}</th><th>{lang==='mr'?'दिवस प्रकार':'Day type'}</th><th>{lang==='mr'?'भोजन आवश्यक':'Meal required'}</th><th>{lang==='mr'?'स्थिती':'Status'}</th></tr></thead><tbody>{loading?<tr><td colSpan={4}>{lang==='mr'?'लोड होत आहे...':'Loading...'}</td></tr>:days.length===0?<tr><td colSpan={4}>{lang==='mr'?'नोंदी उपलब्ध नाहीत':'No calendar rows available'}</td></tr>:days.map(d=><tr key={d.date}><td>{d.date}</td><td>{canEdit?<select value={d.day_type} onChange={e=>change(d,e.target.value)}><option value="WORKING">WORKING</option><option value="SUNDAY">SUNDAY</option><option value="PUBLIC_HOLIDAY">PUBLIC HOLIDAY</option><option value="SCHOOL_HOLIDAY">SCHOOL HOLIDAY</option><option value="LOCAL_HOLIDAY">LOCAL HOLIDAY</option><option value="CLOSURE">CLOSURE</option><option value="EXAM_NON_MEAL">EXAM NON-MEAL</option></select>:d.day_type}</td><td>{d.meal_required?'✓':'—'}</td><td>{comp?.missing_dates?.includes(d.date)?(lang==='mr'?'नोंद प्रलंबित':'Entry missing'):(d.meal_required?(lang==='mr'?'ठीक/तपासा':'OK/Check'):(lang==='mr'?'लागू नाही':'N/A'))}</td></tr>)}</tbody></table></div></div>
}
