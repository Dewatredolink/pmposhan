import { useEffect, useMemo, useState } from 'react';
import { apiFetch, realmRoles } from '../auth';
import { Lang } from '../i18n/translations';

type School={id:string;name_en:string;name_mr:string};
type Ingredient={id:string;name_en:string;name_mr:string;base_unit:string;track_inventory:boolean};
type Balance={ingredient_id:string;name_en:string;name_mr:string;unit:string;balance:number};
type Adjustment={id:string;adjustment_date:string;adjustment_no:string;ingredient_name_en:string;ingredient_name_mr:string;unit:string;quantity:number;reason_code:string;remarks?:string|null;entered_by_username:string};
type Verification={id:string;verification_date:string;verification_no:string;remarks?:string|null;entered_by_username:string;lines:{ingredient_id:string;ingredient_name_en:string;ingredient_name_mr:string;unit:string;system_quantity:number;physical_quantity:number;variance_quantity:number}[]};
type Props={lang:Lang;schools:School[];schoolId:string;setSchoolId:(id:string)=>void};

const today=()=>new Date().toISOString().slice(0,10);
const ref=(prefix:string)=>`${prefix}-${new Date().toISOString().replace(/[-:TZ.]/g,'').slice(0,14)}`;

export default function StockControls({lang,schools,schoolId,setSchoolId}:Props){
  const [ingredients,setIngredients]=useState<Ingredient[]>([]);
  const [balances,setBalances]=useState<Balance[]>([]);
  const [adjustments,setAdjustments]=useState<Adjustment[]>([]);
  const [verifications,setVerifications]=useState<Verification[]>([]);
  const [message,setMessage]=useState('');
  const [adjustment,setAdjustment]=useState({adjustment_date:today(),adjustment_no:ref('ADJ'),ingredient_id:'',quantity:'',reason_code:'DAMAGE',remarks:''});
  const [verification,setVerification]=useState({verification_date:today(),verification_no:ref('PHY'),remarks:''});
  const [physical,setPhysical]=useState<Record<string,string>>({});
  const roles=realmRoles(); const canPost=roles.includes('HEADMASTER')||roles.includes('SYSTEM_ADMIN');

  async function load(){
    if(!schoolId)return; setMessage('');
    try{
      const [i,b,a,v]=await Promise.all([
        apiFetch('/ingredients'), apiFetch(`/stock/balances?school_id=${encodeURIComponent(schoolId)}`),
        apiFetch(`/stock/adjustments?school_id=${encodeURIComponent(schoolId)}`), apiFetch(`/stock/physical-verifications?school_id=${encodeURIComponent(schoolId)}`)
      ]);
      for(const r of [i,b,a,v]) if(!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      const idata=(await i.json()).filter((x:Ingredient)=>x.track_inventory); const bdata=await b.json();
      setIngredients(idata); setBalances(bdata); setAdjustments(await a.json()); setVerifications(await v.json());
      if(!adjustment.ingredient_id&&idata[0])setAdjustment(x=>({...x,ingredient_id:idata[0].id}));
      const map:Record<string,string>={}; bdata.forEach((x:Balance)=>map[x.ingredient_id]=String(x.balance)); setPhysical(map);
    }catch(e){setMessage(String(e));}
  }
  useEffect(()=>{void load();},[schoolId]);
  const balMap=useMemo(()=>Object.fromEntries(balances.map(x=>[x.ingredient_id,x])),[balances]);

  async function postAdjustment(){
    try{
      setMessage('');
      const r=await apiFetch('/stock/adjustments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...adjustment,school_id:schoolId,quantity:Number(adjustment.quantity)})});
      if(!r.ok)throw new Error(`${r.status} ${await r.text()}`); const data=await r.json();
      setMessage(lang==='mr'?`समायोजन नोंदवले: ${data.adjustment_no}`:`Adjustment posted: ${data.adjustment_no}`);
      setAdjustment(x=>({...x,adjustment_no:ref('ADJ'),quantity:'',remarks:''})); await load();
    }catch(e){setMessage(String(e));}
  }

  async function postPhysical(){
    try{
      setMessage('');
      const lines=balances.map(x=>({ingredient_id:x.ingredient_id,physical_quantity:Number(physical[x.ingredient_id]??x.balance)}));
      const r=await apiFetch('/stock/physical-verifications',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...verification,school_id:schoolId,lines})});
      if(!r.ok)throw new Error(`${r.status} ${await r.text()}`); const data=await r.json();
      setMessage(lang==='mr'?`भौतिक पडताळणी नोंदवली. फरक असलेल्या वस्तू: ${data.variance_lines}`:`Physical verification posted. Variance items: ${data.variance_lines}`);
      setVerification(x=>({...x,verification_no:ref('PHY'),remarks:''})); await load();
    }catch(e){setMessage(String(e));}
  }

  return <main className="content">
    <div className="page-title"><div><h2>{lang==='mr'?'साठा नियंत्रण':'Stock Controls'}</h2><p>{lang==='mr'?'समायोजन, नुकसान/तूट आणि भौतिक पडताळणी ऑडिट ट्रेलसह नोंदवा.':'Record adjustments, shortages/damage and physical verification with an audit trail.'}</p></div><button className="secondary standalone" onClick={load}>{lang==='mr'?'रीफ्रेश':'Refresh'}</button></div>
    <section className="panel form-grid compact"><label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></label><div className="muted">{canPost?(lang==='mr'?'मुख्याध्यापक/प्रशासक नियंत्रण सक्षम':'Headmaster/Admin controls enabled'):(lang==='mr'?'फक्त पाहण्याची परवानगी':'Read-only access')}</div></section>

    <section className="panel"><h3>{lang==='mr'?'साठा समायोजन':'Stock Adjustment'}</h3><div className="form-grid">
      <label>{lang==='mr'?'दिनांक':'Date'}<input type="date" value={adjustment.adjustment_date} onChange={e=>setAdjustment({...adjustment,adjustment_date:e.target.value})}/></label>
      <label>{lang==='mr'?'समायोजन क्रमांक':'Adjustment No.'}<input value={adjustment.adjustment_no} onChange={e=>setAdjustment({...adjustment,adjustment_no:e.target.value})}/></label>
      <label>{lang==='mr'?'वस्तू':'Ingredient'}<select value={adjustment.ingredient_id} onChange={e=>setAdjustment({...adjustment,ingredient_id:e.target.value})}>{ingredients.map(x=><option key={x.id} value={x.id}>{lang==='mr'?x.name_mr:x.name_en} ({x.base_unit})</option>)}</select></label>
      <label>{lang==='mr'?'प्रमाण (+ वाढ / - घट)':'Quantity (+ add / - reduce)'}<input type="number" step="0.001" value={adjustment.quantity} onChange={e=>setAdjustment({...adjustment,quantity:e.target.value})}/></label>
      <label>{lang==='mr'?'कारण':'Reason'}<select value={adjustment.reason_code} onChange={e=>setAdjustment({...adjustment,reason_code:e.target.value})}><option value="DAMAGE">{lang==='mr'?'नुकसान':'Damage'}</option><option value="SHORTAGE">{lang==='mr'?'तूट':'Shortage'}</option><option value="EXCESS">{lang==='mr'?'जादा साठा':'Excess'}</option><option value="CORRECTION">{lang==='mr'?'दुरुस्ती':'Correction'}</option><option value="OTHER">{lang==='mr'?'इतर':'Other'}</option></select></label>
      <label>{lang==='mr'?'चालू शिल्लक':'Current Balance'}<input disabled value={adjustment.ingredient_id?`${balMap[adjustment.ingredient_id]?.balance?.toFixed(3)??'0.000'} ${balMap[adjustment.ingredient_id]?.unit??''}`:''}/></label>
      <label className="span-2">{lang==='mr'?'तपशील':'Remarks'}<textarea value={adjustment.remarks} onChange={e=>setAdjustment({...adjustment,remarks:e.target.value})}/></label>
    </div><div className="action-row"><button className="primary" disabled={!canPost||!adjustment.quantity||!adjustment.adjustment_no} onClick={postAdjustment}>{lang==='mr'?'समायोजन नोंदवा':'Post Adjustment'}</button></div></section>

    <section className="panel"><h3>{lang==='mr'?'भौतिक साठा पडताळणी':'Physical Stock Verification'}</h3><div className="form-grid"><label>{lang==='mr'?'दिनांक':'Date'}<input type="date" value={verification.verification_date} onChange={e=>setVerification({...verification,verification_date:e.target.value})}/></label><label>{lang==='mr'?'पडताळणी क्रमांक':'Verification No.'}<input value={verification.verification_no} onChange={e=>setVerification({...verification,verification_no:e.target.value})}/></label></div>
      <div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'वस्तू':'Ingredient'}</th><th>{lang==='mr'?'प्रणाली शिल्लक':'System Qty'}</th><th>{lang==='mr'?'प्रत्यक्ष शिल्लक':'Physical Qty'}</th><th>{lang==='mr'?'फरक':'Variance'}</th></tr></thead><tbody>{balances.map(x=>{const ph=Number(physical[x.ingredient_id]??x.balance); const variance=ph-x.balance; return <tr key={x.ingredient_id}><td>{lang==='mr'?x.name_mr:x.name_en}</td><td>{x.balance.toFixed(3)} {x.unit}</td><td><input type="number" min="0" step="0.001" value={physical[x.ingredient_id]??''} onChange={e=>setPhysical({...physical,[x.ingredient_id]:e.target.value})}/></td><td className={variance<0?'qty-out':variance>0?'qty-in':''}>{variance.toFixed(3)} {x.unit}</td></tr>})}</tbody></table></div>
      <div className="form-grid"><label className="span-2">{lang==='mr'?'तपशील':'Remarks'}<textarea value={verification.remarks} onChange={e=>setVerification({...verification,remarks:e.target.value})}/></label></div>
      <div className="action-row"><button className="success" disabled={!canPost||!verification.verification_no} onClick={postPhysical}>{lang==='mr'?'भौतिक पडताळणी पोस्ट करा':'Post Physical Verification'}</button></div>
    </section>

    <section className="panel"><h3>{lang==='mr'?'अलीकडील समायोजन':'Recent Adjustments'}</h3><div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'दिनांक':'Date'}</th><th>{lang==='mr'?'क्रमांक':'No.'}</th><th>{lang==='mr'?'वस्तू':'Ingredient'}</th><th>{lang==='mr'?'प्रमाण':'Qty'}</th><th>{lang==='mr'?'कारण':'Reason'}</th><th>{lang==='mr'?'नोंद करणारा':'Entered By'}</th></tr></thead><tbody>{adjustments.slice(0,20).map(x=><tr key={x.id}><td>{x.adjustment_date}</td><td>{x.adjustment_no}</td><td>{lang==='mr'?x.ingredient_name_mr:x.ingredient_name_en}</td><td className={x.quantity<0?'qty-out':'qty-in'}>{x.quantity>0?'+':''}{x.quantity.toFixed(3)} {x.unit}</td><td>{x.reason_code}</td><td>{x.entered_by_username}</td></tr>)}</tbody></table></div></section>
    <section className="panel"><h3>{lang==='mr'?'भौतिक पडताळणी इतिहास':'Physical Verification History'}</h3><div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'दिनांक':'Date'}</th><th>{lang==='mr'?'क्रमांक':'No.'}</th><th>{lang==='mr'?'वस्तू':'Items'}</th><th>{lang==='mr'?'फरक असलेल्या वस्तू':'Variance Items'}</th><th>{lang==='mr'?'नोंद करणारा':'Entered By'}</th></tr></thead><tbody>{verifications.slice(0,20).map(x=><tr key={x.id}><td>{x.verification_date}</td><td>{x.verification_no}</td><td>{x.lines.length}</td><td>{x.lines.filter(l=>Math.abs(l.variance_quantity)>0.0001).length}</td><td>{x.entered_by_username}</td></tr>)}</tbody></table></div></section>
    {message&&<div className="notice">{message}</div>}
  </main>
}
