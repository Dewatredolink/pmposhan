import { useEffect, useMemo, useState } from 'react';
import { apiFetch, realmRoles } from '../auth';
import { Lang } from '../i18n/translations';

type School = { id:string; name_en:string; name_mr:string; class_1_5_strength:number; class_6_8_strength:number };
type Menu = { id:string; code:string; name_en:string; name_mr:string; week_pattern:string; day_of_week:number };
type RecipeItem = { ingredient_id:string; code:string; name_en:string; name_mr:string; unit:string; qty_per_student_class_1_5:number; qty_per_student_class_6_8:number; required_class_1_5:number; required_class_6_8:number; required_total:number };
type Props = { lang:Lang; schools:School[]; schoolId:string; setSchoolId:(id:string)=>void };

const today = new Date().toISOString().slice(0,10);

function fmt(v:number){
  if (!Number.isFinite(v)) return '0';
  return v.toLocaleString(undefined,{maximumFractionDigits:4});
}

export default function MenuPlanner({lang,schools,schoolId,setSchoolId}:Props){
  const [date,setDate] = useState(today);
  const [menus,setMenus] = useState<Menu[]>([]);
  const [menuId,setMenuId] = useState('');
  const [remarks,setRemarks] = useState('');
  const [items,setItems] = useState<RecipeItem[]>([]);
  const [message,setMessage] = useState('');
  const [busy,setBusy] = useState(false);
  const school = schools.find(s=>s.id===schoolId);
  const canEdit = realmRoles().some(r=>r==='HEADMASTER'||r==='SYSTEM_ADMIN');
  const c15 = school?.class_1_5_strength || 0;
  const c68 = school?.class_6_8_strength || 0;

  useEffect(()=>{ apiFetch('/menus').then(async r=>{if(!r.ok) throw new Error(await r.text()); return r.json()}).then(setMenus).catch(e=>setMessage(String(e))); },[]);

  async function loadPlan(){
    if(!schoolId||!date) return;
    setMessage('');
    try{
      const r=await apiFetch(`/menu-plan?school_id=${encodeURIComponent(schoolId)}&menu_date=${date}`);
      if(!r.ok) throw new Error(await r.text());
      const d=await r.json();
      if(d.plan){ setMenuId(d.plan.menu_id); setRemarks(d.plan.remarks||''); }
      else { setMenuId(''); setRemarks(''); setItems([]); }
    }catch(e){setMessage(String(e));}
  }

  useEffect(()=>{ void loadPlan(); },[schoolId,date]);

  useEffect(()=>{
    if(!menuId||!date){setItems([]); return;}
    apiFetch(`/menus/${encodeURIComponent(menuId)}/recipe-preview?on_date=${date}&class_1_5=${c15}&class_6_8=${c68}`)
      .then(async r=>{if(!r.ok) throw new Error(await r.text()); return r.json()})
      .then(d=>setItems(Array.isArray(d.items)?d.items:[]))
      .catch(e=>{setItems([]);setMessage(String(e));});
  },[menuId,date,c15,c68]);

  const suggested = useMemo(()=>{
    const dow=new Date(`${date}T12:00:00`).getDay();
    return menus.filter(m=>m.day_of_week===dow);
  },[menus,date]);

  async function save(){
    if(!schoolId||!date||!menuId){setMessage(lang==='mr'?'शाळा, दिनांक आणि मेनू निवडा.':'Select school, date and menu.');return;}
    setBusy(true);setMessage('');
    try{
      const r=await apiFetch('/menu-plan',{method:'PUT',body:JSON.stringify({school_id:schoolId,menu_date:date,menu_id:menuId,remarks})});
      if(!r.ok) throw new Error(await r.text());
      await loadPlan();
      setMessage(lang==='mr'?'त्या दिवसासाठी मेनू जतन झाला.':'Menu saved for the selected date.');
    }catch(e){setMessage(String(e));}finally{setBusy(false);}
  }

  return <main className="content">
    <div className="page-title"><div><h2>{lang==='mr'?'दिवसनिहाय मेनू नियोजन':'Date-wise Menu Planner'}</h2><p>{lang==='mr'?'विशिष्ट दिवशी कोणता मेनू द्यायचा ते ठरवा आणि आवश्यक साहित्याचे प्रमाण पहा.':'Assign a menu to a specific date and view required ingredients and quantities.'}</p></div></div>
    <section className="panel form-grid compact">
      <label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></label>
      <label>{lang==='mr'?'दिनांक':'Date'}<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label>
      <label className="span-2">{lang==='mr'?'त्या दिवसाचा मेनू':'Menu for the selected date'}<select value={menuId} onChange={e=>setMenuId(e.target.value)}><option value="">-- {lang==='mr'?'मेनू निवडा':'Select menu'} --</option>{(suggested.length?suggested:menus).map(m=><option key={m.id} value={m.id}>{lang==='mr'?m.name_mr:m.name_en} ({m.code})</option>)}</select></label>
      <label className="span-2">{lang==='mr'?'शेरा':'Remarks'}<textarea value={remarks} onChange={e=>setRemarks(e.target.value)}/></label>
    </section>

    <section className="panel">
      <h3>{lang==='mr'?'मेनूमधील आवश्यक साहित्य व प्रमाण':'Required ingredients and quantities'}</h3>
      <p>{lang==='mr'?`शाळेच्या सध्याच्या विद्यार्थी संख्येवर अंदाज: इ.1-5 = ${c15}, इ.6-8 = ${c68}`:`Estimate using current school strength: Class 1-5 = ${c15}, Class 6-8 = ${c68}`}</p>
      {!menuId && <div className="notice">{lang==='mr'?'प्रमाण पाहण्यासाठी मेनू निवडा.':'Select a menu to see quantities.'}</div>}
      {menuId && items.length===0 && <div className="notice">{lang==='mr'?'या मेनूसाठी सक्रिय Recipe Master उपलब्ध नाही.':'No active Recipe Master is configured for this menu.'}</div>}
      {items.length>0 && <div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'साहित्य':'Ingredient'}</th><th>{lang==='mr'?'इ.1-5 प्रति विद्यार्थी':'1-5 / student'}</th><th>{lang==='mr'?'इ.6-8 प्रति विद्यार्थी':'6-8 / student'}</th><th>{lang==='mr'?'इ.1-5 आवश्यक':'1-5 required'}</th><th>{lang==='mr'?'इ.6-8 आवश्यक':'6-8 required'}</th><th>{lang==='mr'?'एकूण आवश्यक':'Total required'}</th></tr></thead><tbody>{items.map(x=><tr key={x.ingredient_id}><td>{lang==='mr'?x.name_mr:x.name_en}<small style={{display:'block'}}>{x.code}</small></td><td>{fmt(x.qty_per_student_class_1_5)} {x.unit}</td><td>{fmt(x.qty_per_student_class_6_8)} {x.unit}</td><td>{fmt(x.required_class_1_5)} {x.unit}</td><td>{fmt(x.required_class_6_8)} {x.unit}</td><td><strong>{fmt(x.required_total)} {x.unit}</strong></td></tr>)}</tbody></table></div>}
    </section>
    {message&&<div className="notice">{message}</div>}
    {canEdit&&<div className="action-row"><button className="primary" disabled={busy||!menuId} onClick={save}>{lang==='mr'?'दिवसाचा मेनू जतन करा':'Save Date Menu'}</button></div>}
  </main>
}
