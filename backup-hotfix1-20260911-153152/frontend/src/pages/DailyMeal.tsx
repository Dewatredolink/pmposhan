import { useEffect, useMemo, useState } from 'react';
import { apiFetch, realmRoles } from '../auth';
import { Lang } from '../i18n/translations';

type School = { id:string; name_en:string; name_mr:string; class_1_5_strength:number; class_6_8_strength:number };
type Menu = { id:string; code:string; name_en:string; name_mr:string; week_pattern:string; day_of_week:number };
type DailyData = {
  attendance: null | { class_1_5_enrolled:number; class_1_5_present:number; class_6_8_enrolled:number; class_6_8_present:number; status:string; verified_by_username?:string|null };
  meal: null | { menu_id:string; meals_class_1_5:number; meals_class_6_8:number; tasting_done:boolean; hygiene_ok:boolean; remarks?:string|null; status:string; verified_by_username?:string|null };
};

type Props = { lang:Lang; schools:School[]; schoolId:string; setSchoolId:(id:string)=>void };
const today = new Date().toISOString().slice(0,10);

export default function DailyMeal({lang, schools, schoolId, setSchoolId}:Props){
  const [date,setDate] = useState(today);
  const [menus,setMenus] = useState<Menu[]>([]);
  const [message,setMessage] = useState('');
  const [busy,setBusy] = useState(false);
  const school = schools.find(s=>s.id===schoolId);
  const [a,setA] = useState({e15:0,p15:0,e68:0,p68:0,status:'DRAFT'});
  const [m,setM] = useState({menu_id:'',m15:0,m68:0,tasting:false,hygiene:false,remarks:'',status:'DRAFT'});
  const roles = realmRoles();
  const canVerify = roles.includes('HEADMASTER') || roles.includes('SYSTEM_ADMIN');
  const totalPresent = a.p15 + a.p68;
  const totalMeals = m.m15 + m.m68;

  useEffect(()=>{ apiFetch('/menus').then(r=>r.json()).then(setMenus).catch(()=>setMenus([])); },[]);
  useEffect(()=>{
    if (!schoolId || !date) return;
    setMessage('');
    apiFetch(`/daily-operations?school_id=${encodeURIComponent(schoolId)}&meal_date=${date}`)
      .then(async r=>{ if(!r.ok) throw new Error(await r.text()); return r.json(); })
      .then((d:DailyData)=>{
        setA(d.attendance ? {e15:d.attendance.class_1_5_enrolled,p15:d.attendance.class_1_5_present,e68:d.attendance.class_6_8_enrolled,p68:d.attendance.class_6_8_present,status:d.attendance.status} : {e15:school?.class_1_5_strength||0,p15:0,e68:school?.class_6_8_strength||0,p68:0,status:'DRAFT'});
        setM(d.meal ? {menu_id:d.meal.menu_id,m15:d.meal.meals_class_1_5,m68:d.meal.meals_class_6_8,tasting:d.meal.tasting_done,hygiene:d.meal.hygiene_ok,remarks:d.meal.remarks||'',status:d.meal.status} : {menu_id:'',m15:0,m68:0,tasting:false,hygiene:false,remarks:'',status:'DRAFT'});
      })
      .catch(e=>setMessage(String(e)));
  },[schoolId,date,school?.class_1_5_strength,school?.class_6_8_strength]);

  const suggestedMenus = useMemo(()=>{
    const dow = new Date(`${date}T12:00:00`).getDay(); // 1 Mon..6 Sat
    return menus.filter(x=>x.day_of_week===dow);
  },[menus,date]);

  async function save(status:'DRAFT'|'SUBMITTED'){
    if(!schoolId || !m.menu_id){ setMessage(lang==='mr'?'शाळा आणि मेनू निवडा.':'Select school and menu.'); return; }
    setBusy(true); setMessage('');
    try{
      const ar = await apiFetch('/daily-attendance',{method:'PUT',body:JSON.stringify({school_id:schoolId,meal_date:date,class_1_5_enrolled:a.e15,class_1_5_present:a.p15,class_6_8_enrolled:a.e68,class_6_8_present:a.p68,status})});
      if(!ar.ok) throw new Error(await ar.text());
      const mr = await apiFetch('/daily-meal',{method:'PUT',body:JSON.stringify({school_id:schoolId,meal_date:date,menu_id:m.menu_id,meals_class_1_5:m.m15,meals_class_6_8:m.m68,tasting_done:m.tasting,hygiene_ok:m.hygiene,remarks:m.remarks,status})});
      if(!mr.ok) throw new Error(await mr.text());
      setA({...a,status}); setM({...m,status});
      setMessage(status==='SUBMITTED' ? (lang==='mr'?'नोंद पडताळणीसाठी सादर केली.':'Entry submitted for verification.') : (lang==='mr'?'मसुदा जतन झाला.':'Draft saved.'));
    }catch(e){ setMessage(String(e)); } finally{ setBusy(false); }
  }

  async function verify(){
    setBusy(true); setMessage('');
    try{
      const r = await apiFetch('/daily-operations/verify',{method:'POST',body:JSON.stringify({school_id:schoolId,meal_date:date})});
      if(!r.ok) throw new Error(await r.text());
      setA({...a,status:'VERIFIED'}); setM({...m,status:'VERIFIED'});
      setMessage(lang==='mr'?'मुख्याध्यापक पडताळणी पूर्ण.':'Headmaster verification completed.');
    }catch(e){ setMessage(String(e)); } finally{ setBusy(false); }
  }

  const locked = a.status==='VERIFIED' || m.status==='VERIFIED';
  return <main className="content">
    <div className="page-title"><div><h2>{lang==='mr'?'दैनिक उपस्थिती व आहार नोंद':'Daily Attendance & Meal Entry'}</h2><p>{lang==='mr'?'एकाच दिवसाची उपस्थिती, मेनू आणि भोजन संख्या नोंदवा.':'Record attendance, menu and meals served for the day.'}</p></div><span className={`status ${m.status.toLowerCase()}`}>{m.status}</span></div>
    <section className="panel form-grid compact">
      <label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></label>
      <label>{lang==='mr'?'दिनांक':'Date'}<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label>
    </section>

    <section className="panel"><h3>{lang==='mr'?'1. उपस्थिती':'1. Attendance'}</h3><div className="form-grid">
      <label>{lang==='mr'?'इ. 1-5 नोंदणी':'Class 1-5 Enrolled'}<input type="number" min="0" disabled={locked} value={a.e15} onChange={e=>setA({...a,e15:+e.target.value})}/></label>
      <label>{lang==='mr'?'इ. 1-5 उपस्थित':'Class 1-5 Present'}<input type="number" min="0" disabled={locked} value={a.p15} onChange={e=>setA({...a,p15:+e.target.value})}/></label>
      <label>{lang==='mr'?'इ. 6-8 नोंदणी':'Class 6-8 Enrolled'}<input type="number" min="0" disabled={locked} value={a.e68} onChange={e=>setA({...a,e68:+e.target.value})}/></label>
      <label>{lang==='mr'?'इ. 6-8 उपस्थित':'Class 6-8 Present'}<input type="number" min="0" disabled={locked} value={a.p68} onChange={e=>setA({...a,p68:+e.target.value})}/></label>
    </div><div className="metric-line"><strong>{lang==='mr'?'एकूण उपस्थित':'Total present'}: {totalPresent}</strong></div></section>

    <section className="panel"><h3>{lang==='mr'?'2. भोजन नोंद':'2. Meal Entry'}</h3><div className="form-grid">
      <label className="span-2">{lang==='mr'?'आजचा मेनू':'Today’s Menu'}<select disabled={locked} value={m.menu_id} onChange={e=>setM({...m,menu_id:e.target.value})}><option value="">-- {lang==='mr'?'मेनू निवडा':'Select menu'} --</option>{(suggestedMenus.length?suggestedMenus:menus).map(x=><option key={x.id} value={x.id}>{lang==='mr'?x.name_mr:x.name_en} ({x.code})</option>)}</select></label>
      <label>{lang==='mr'?'इ. 1-5 भोजन':'Meals Class 1-5'}<input type="number" min="0" disabled={locked} value={m.m15} onChange={e=>setM({...m,m15:+e.target.value})}/></label>
      <label>{lang==='mr'?'इ. 6-8 भोजन':'Meals Class 6-8'}<input type="number" min="0" disabled={locked} value={m.m68} onChange={e=>setM({...m,m68:+e.target.value})}/></label>
      <label className="check"><input type="checkbox" disabled={locked} checked={m.tasting} onChange={e=>setM({...m,tasting:e.target.checked})}/>{lang==='mr'?'भोजन चव तपासणी पूर्ण':'Meal tasting completed'}</label>
      <label className="check"><input type="checkbox" disabled={locked} checked={m.hygiene} onChange={e=>setM({...m,hygiene:e.target.checked})}/>{lang==='mr'?'स्वच्छता तपासणी समाधानकारक':'Hygiene check satisfactory'}</label>
      <label className="span-2">{lang==='mr'?'शेरा':'Remarks'}<textarea disabled={locked} value={m.remarks} onChange={e=>setM({...m,remarks:e.target.value})}/></label>
    </div><div className="metric-line"><strong>{lang==='mr'?'एकूण भोजन':'Total meals'}: {totalMeals}</strong><span>{totalMeals>totalPresent ? (lang==='mr'?'⚠ भोजन संख्या उपस्थितीपेक्षा जास्त आहे':'⚠ Meals exceed attendance') : ''}</span></div></section>

    {message && <div className="notice">{message}</div>}
    <div className="action-row">
      {!locked && <><button className="secondary" disabled={busy} onClick={()=>save('DRAFT')}>{lang==='mr'?'मसुदा जतन करा':'Save Draft'}</button><button className="primary" disabled={busy || totalMeals>totalPresent} onClick={()=>save('SUBMITTED')}>{lang==='mr'?'पडताळणीसाठी सादर करा':'Submit for Verification'}</button></>}
      {canVerify && a.status==='SUBMITTED' && m.status==='SUBMITTED' && <button className="success" disabled={busy} onClick={verify}>{lang==='mr'?'मुख्याध्यापक पडताळणी':'Headmaster Verify'}</button>}
    </div>
  </main>
}
