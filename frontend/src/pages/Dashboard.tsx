import { useEffect, useState } from 'react';
import { apiFetch } from '../auth';
import { Lang, t } from '../i18n/translations';

type Props = { lang: Lang; schoolId:string };
export default function Dashboard({lang,schoolId}: Props) {
  const tr = (k: keyof typeof t) => t[k][lang];
  const [s,setS]=useState({students:0,present_today:0,meals_today:0,meals_month:0,attendance_status:'NOT_ENTERED',meal_status:'NOT_ENTERED'});
  useEffect(()=>{ if(schoolId) apiFetch(`/dashboard-summary?school_id=${schoolId}`).then(r=>r.json()).then(setS).catch(()=>{}); },[schoolId]);
  const cards = [[tr('students'),String(s.students)],[tr('presentToday'),String(s.present_today)],[tr('mealsToday'),String(s.meals_today)],[tr('mealsMonth'),String(s.meals_month)]];
  return <main className="content">
    <section className="cards">{cards.map(([label,value]) => <article className="card" key={label}><span>{label}</span><strong>{value}</strong></article>)}</section>
    <section className="panel"><h2>{lang==='mr'?'आजची नोंद स्थिती':'Today’s Entry Status'}</h2><div className="status-row"><div><span>{lang==='mr'?'उपस्थिती':'Attendance'}</span><strong className={`status ${s.attendance_status.toLowerCase()}`}>{s.attendance_status}</strong></div><div><span>{lang==='mr'?'भोजन':'Meal'}</span><strong className={`status ${s.meal_status.toLowerCase()}`}>{s.meal_status}</strong></div></div></section>
    <section className="panel"><h2>{tr('alerts')}</h2><p>{s.attendance_status==='NOT_ENTERED'||s.meal_status==='NOT_ENTERED' ? (lang==='mr'?'आजची दैनिक नोंद अद्याप पूर्ण झालेली नाही.':'Today’s daily entry is not complete yet.') : (lang==='mr'?'सध्या कोणतीही सूचना नाही.':'No alerts at present.')}</p></section>
  </main>
}
