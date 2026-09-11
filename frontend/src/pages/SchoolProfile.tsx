import { useEffect, useState } from 'react';
import { apiFetch, realmRoles } from '../auth';
import { Lang } from '../i18n/translations';

type School = { id:string; name_en:string; name_mr:string };
type Props = { lang:Lang; schools:School[]; schoolId:string; setSchoolId:(id:string)=>void };

export default function SchoolProfile({lang,schools,schoolId,setSchoolId}:Props){
  const [data,setData] = useState<any>(null);
  const [form,setForm] = useState({kitchen_type:'SCHOOL_KITCHEN',cooking_agency:'',headmaster_name:'',meal_incharge_name:'',contact_mobile:''});
  const [message,setMessage] = useState('');
  const canEdit = realmRoles().some(r=>['HEADMASTER','SYSTEM_ADMIN'].includes(r));
  function load(){
    if(!schoolId) return;
    apiFetch(`/school-profiles/${schoolId}`).then(async r=>{if(!r.ok) throw new Error(await r.text());return r.json()}).then(d=>{
      setData(d); const p=d.profile||{}; setForm({kitchen_type:p.kitchen_type||'SCHOOL_KITCHEN',cooking_agency:p.cooking_agency||'',headmaster_name:p.headmaster_name||'',meal_incharge_name:p.meal_incharge_name||'',contact_mobile:p.contact_mobile||''});
    }).catch(e=>setMessage(String(e)));
  }
  useEffect(load,[schoolId]);
  async function save(){
    setMessage(''); const r=await apiFetch(`/school-profiles/${schoolId}`,{method:'PUT',body:JSON.stringify(form)}); if(!r.ok){setMessage(await r.text());return;} setMessage(lang==='mr'?'शाळा प्रोफाइल जतन झाले.':'School profile saved.'); load();
  }
  return <main className="content"><div className="page-title"><div><h2>{lang==='mr'?'शाळा प्रोफाइल व वापरकर्ता प्रवेश':'School Profile & User Access'}</h2><p>{lang==='mr'?'PM POSHAN शाळेची मूलभूत माहिती आणि नियुक्त वापरकर्ते.':'Core PM POSHAN school details and assigned users.'}</p></div></div>
    <section className="panel form-grid compact"><label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></label></section>
    {data && <><section className="panel"><h3>{lang==='mr'?'शाळा माहिती':'School Information'}</h3><div className="info-grid"><div><span>UDISE</span><strong>{data.school.udise_code}</strong></div><div><span>{lang==='mr'?'गाव':'Village'}</span><strong>{data.school.village||'—'}</strong></div><div><span>{lang==='mr'?'इ. 1-5 पटसंख्या':'Class 1-5 Strength'}</span><strong>{data.school.class_1_5_strength}</strong></div><div><span>{lang==='mr'?'इ. 6-8 पटसंख्या':'Class 6-8 Strength'}</span><strong>{data.school.class_6_8_strength}</strong></div></div></section>
    <section className="panel"><h3>{lang==='mr'?'PM POSHAN प्रोफाइल':'PM POSHAN Profile'}</h3><div className="form-grid"><label>{lang==='mr'?'स्वयंपाकघर प्रकार':'Kitchen Type'}<select disabled={!canEdit} value={form.kitchen_type} onChange={e=>setForm({...form,kitchen_type:e.target.value})}><option value="SCHOOL_KITCHEN">School Kitchen</option><option value="CENTRAL_KITCHEN">Central Kitchen</option></select></label><label>{lang==='mr'?'स्वयंपाक संस्था':'Cooking Agency'}<input disabled={!canEdit} value={form.cooking_agency} onChange={e=>setForm({...form,cooking_agency:e.target.value})}/></label><label>{lang==='mr'?'मुख्याध्यापक':'Headmaster'}<input disabled={!canEdit} value={form.headmaster_name} onChange={e=>setForm({...form,headmaster_name:e.target.value})}/></label><label>{lang==='mr'?'आहार प्रभारी':'Meal In-charge'}<input disabled={!canEdit} value={form.meal_incharge_name} onChange={e=>setForm({...form,meal_incharge_name:e.target.value})}/></label><label>{lang==='mr'?'मोबाईल':'Mobile'}<input disabled={!canEdit} value={form.contact_mobile} onChange={e=>setForm({...form,contact_mobile:e.target.value})}/></label></div>{canEdit&&<div className="action-row"><button className="primary" onClick={save}>{lang==='mr'?'जतन करा':'Save Profile'}</button></div>}</section>
    <section className="panel"><h3>{lang==='mr'?'नियुक्त वापरकर्ते':'Assigned Users'}</h3><div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'वापरकर्ता':'User'}</th><th>{lang==='mr'?'भूमिका':'Role'}</th><th>{lang==='mr'?'भाषा':'Language'}</th></tr></thead><tbody>{data.assignments.map((x:any)=><tr key={x.id}><td>{x.username}</td><td>{x.role}</td><td>{x.preferred_language.toUpperCase()}</td></tr>)}</tbody></table></div></section></>}
    {message&&<div className="notice">{message}</div>}
  </main>
}
