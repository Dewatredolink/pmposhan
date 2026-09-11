import { useEffect, useMemo, useState } from 'react';
import { apiFetch, realmRoles } from '../auth';
import { Lang } from '../i18n/translations';

type School={id:string;name_en:string;name_mr:string};
type Ingredient={id:string;code:string;name_en:string;name_mr:string;base_unit:string;track_inventory:boolean};
type Line={ingredient_id:string;quantity:number;unit_cost:string};
type Props={lang:Lang;schools:School[];schoolId:string;setSchoolId:(id:string)=>void};
const today=new Date().toISOString().slice(0,10);

export default function StockReceipt({lang,schools,schoolId,setSchoolId}:Props){
  const [ingredients,setIngredients]=useState<Ingredient[]>([]);
  const [receiptDate,setReceiptDate]=useState(today);
  const [receiptNo,setReceiptNo]=useState('');
  const [source,setSource]=useState('');
  const [remarks,setRemarks]=useState('');
  const [lines,setLines]=useState<Line[]>([{ingredient_id:'',quantity:0,unit_cost:''}]);
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  const [openingIngredient,setOpeningIngredient]=useState(''); const [openingQty,setOpeningQty]=useState(0); const [openingDate,setOpeningDate]=useState(today);
  const canOpening=realmRoles().includes('HEADMASTER')||realmRoles().includes('SYSTEM_ADMIN');
  useEffect(()=>{apiFetch('/ingredients').then(r=>r.json()).then((x:Ingredient[])=>setIngredients(x.filter(i=>i.track_inventory))).catch(()=>setIngredients([]));},[]);
  const school=schools.find(s=>s.id===schoolId);
  const totalLines=useMemo(()=>lines.filter(x=>x.ingredient_id&&x.quantity>0).length,[lines]);
  const addLine=()=>setLines([...lines,{ingredient_id:'',quantity:0,unit_cost:''}]);
  const removeLine=(idx:number)=>setLines(lines.filter((_,i)=>i!==idx));
  const update=(idx:number,patch:Partial<Line>)=>setLines(lines.map((x,i)=>i===idx?{...x,...patch}:x));
  async function submit(){
    setMessage('');
    const valid=lines.filter(x=>x.ingredient_id&&x.quantity>0);
    if(!schoolId||!receiptNo.trim()||valid.length===0){setMessage(lang==='mr'?'शाळा, प्राप्ती क्रमांक आणि किमान एक वस्तू आवश्यक आहे.':'School, receipt number and at least one item are required.');return;}
    if(new Set(valid.map(x=>x.ingredient_id)).size!==valid.length){setMessage(lang==='mr'?'एकाच वस्तूची पुनरावृत्ती काढा.':'Remove duplicate ingredient lines.');return;}
    setBusy(true);
    try{
      const r=await apiFetch('/stock/receipts',{method:'POST',body:JSON.stringify({school_id:schoolId,receipt_date:receiptDate,receipt_no:receiptNo.trim(),source_name:source||null,remarks:remarks||null,lines:valid.map(x=>({ingredient_id:x.ingredient_id,quantity:x.quantity,unit_cost:x.unit_cost===''?null:+x.unit_cost}))})});
      if(!r.ok) throw new Error(await r.text());
      setReceiptNo('');setSource('');setRemarks('');setLines([{ingredient_id:'',quantity:0,unit_cost:''}]);
      setMessage(lang==='mr'?'साठा प्राप्ती यशस्वीरीत्या नोंदवली.':'Stock receipt posted successfully.');
    }catch(e){setMessage(String(e));}finally{setBusy(false);}
  }

  async function postOpening(){
    if(!schoolId||!openingIngredient||openingQty<=0){setMessage(lang==='mr'?'वस्तू आणि प्रारंभिक प्रमाण निवडा.':'Select ingredient and opening quantity.');return;}
    setBusy(true);setMessage('');
    try{const r=await apiFetch('/stock/opening-balance',{method:'POST',body:JSON.stringify({school_id:schoolId,opening_date:openingDate,ingredient_id:openingIngredient,quantity:openingQty,remarks:'Opening balance entered from Phase 2B UI'})});if(!r.ok)throw new Error(await r.text());setOpeningIngredient('');setOpeningQty(0);setMessage(lang==='mr'?'प्रारंभिक साठा जतन झाला.':'Opening balance posted.');}catch(e){setMessage(String(e));}finally{setBusy(false);}
  }
  return <main className="content">
    <div className="page-title"><div><h2>{lang==='mr'?'साठा प्राप्ती':'Stock Receipt'}</h2><p>{lang==='mr'?'शाळेला मिळालेला धान्य व इतर साहित्य साठ्यात जमा करा.':'Post grain and ingredient receipts into school inventory.'}</p></div></div>
    <section className="panel form-grid compact">
      <label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></label>
      <label>{lang==='mr'?'प्राप्ती दिनांक':'Receipt Date'}<input type="date" value={receiptDate} onChange={e=>setReceiptDate(e.target.value)}/></label>
      <label>{lang==='mr'?'प्राप्ती / चलन क्रमांक':'Receipt / Challan No.'}<input value={receiptNo} onChange={e=>setReceiptNo(e.target.value)} placeholder="e.g. CH-2026-001"/></label>
      <label>{lang==='mr'?'पुरवठा स्रोत':'Source / Supplier'}<input value={source} onChange={e=>setSource(e.target.value)}/></label>
      <label className="span-2">{lang==='mr'?'शेरा':'Remarks'}<input value={remarks} onChange={e=>setRemarks(e.target.value)}/></label>
    </section>
    {canOpening&&<section className="panel"><h3>{lang==='mr'?'प्रारंभिक साठा':'Opening Balance'}</h3><p className="muted">{lang==='mr'?'ही नोंद त्या वस्तूवर कोणताही व्यवहार होण्यापूर्वी फक्त एकदाच करता येईल.':'Allowed once per ingredient before any transaction exists.'}</p><div className="form-grid"><label>{lang==='mr'?'वस्तू':'Ingredient'}<select value={openingIngredient} onChange={e=>setOpeningIngredient(e.target.value)}><option value="">-- {lang==='mr'?'वस्तू निवडा':'Select'} --</option>{ingredients.map(i=><option key={i.id} value={i.id}>{lang==='mr'?i.name_mr:i.name_en} ({i.base_unit})</option>)}</select></label><label>{lang==='mr'?'दिनांक':'Date'}<input type="date" value={openingDate} onChange={e=>setOpeningDate(e.target.value)}/></label><label>{lang==='mr'?'प्रमाण':'Quantity'}<input type="number" min="0" step="0.001" value={openingQty||''} onChange={e=>setOpeningQty(+e.target.value)}/></label></div><div className="action-row"><button className="secondary" disabled={busy||!openingIngredient||openingQty<=0} onClick={postOpening}>{lang==='mr'?'प्रारंभिक साठा जतन करा':'Post Opening Balance'}</button></div></section>}
    <section className="panel"><h3>{lang==='mr'?'प्राप्त वस्तू':'Received Items'}</h3><div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'वस्तू':'Ingredient'}</th><th>{lang==='mr'?'एकक':'Unit'}</th><th>{lang==='mr'?'प्रमाण':'Quantity'}</th><th>{lang==='mr'?'दर (ऐच्छिक)':'Unit Cost (optional)'}</th><th></th></tr></thead><tbody>{lines.map((ln,idx)=>{const ing=ingredients.find(i=>i.id===ln.ingredient_id);return <tr key={idx}><td><select value={ln.ingredient_id} onChange={e=>update(idx,{ingredient_id:e.target.value})}><option value="">-- {lang==='mr'?'वस्तू निवडा':'Select'} --</option>{ingredients.map(i=><option key={i.id} value={i.id}>{lang==='mr'?i.name_mr:i.name_en} ({i.code})</option>)}</select></td><td>{ing?.base_unit||'-'}</td><td><input type="number" min="0" step="0.001" value={ln.quantity||''} onChange={e=>update(idx,{quantity:+e.target.value})}/></td><td><input type="number" min="0" step="0.01" value={ln.unit_cost} onChange={e=>update(idx,{unit_cost:e.target.value})}/></td><td>{lines.length>1&&<button className="table-button danger" onClick={()=>removeLine(idx)}>×</button>}</td></tr>})}</tbody></table></div><div className="action-row"><button className="secondary" onClick={addLine}>{lang==='mr'?'+ वस्तू जोडा':'+ Add Item'}</button></div></section>
    {message&&<div className="notice">{message}</div>}
    <div className="action-row"><span className="muted">{school ? (lang==='mr'?school.name_mr:school.name_en):''} · {totalLines} {lang==='mr'?'वस्तू':'items'}</span><button className="primary" disabled={busy||totalLines===0} onClick={submit}>{lang==='mr'?'साठा प्राप्ती जतन करा':'Post Stock Receipt'}</button></div>
  </main>
}
