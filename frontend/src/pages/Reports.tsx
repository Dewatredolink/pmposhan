import { useEffect, useState } from 'react';
import { apiFetch } from '../auth';
import { Lang } from '../i18n/translations';

type School={id:string;name_en:string;name_mr:string};
type Item={ingredient_id:string;code:string;name_en:string;name_mr:string;unit:string;opening:number;receipts:number;consumption:number;adjustments:number;closing:number;reorder_level:number;low_stock:boolean};
type Props={lang:Lang;schools:School[];schoolId:string;setSchoolId:(id:string)=>void};

export default function Reports({lang,schools,schoolId,setSchoolId}:Props){
  const now=new Date(); const [year,setYear]=useState(now.getFullYear()); const [month,setMonth]=useState(now.getMonth()+1);
  const [items,setItems]=useState<Item[]>([]); const [message,setMessage]=useState('');
  async function load(){if(!schoolId)return;setMessage('');try{const r=await apiFetch(`/stock/monthly-summary?school_id=${encodeURIComponent(schoolId)}&year=${year}&month=${month}`);if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);const d=await r.json();setItems(d.items);}catch(e){setMessage(String(e));}}
  useEffect(()=>{void load();},[schoolId,year,month]);
  const school=schools.find(s=>s.id===schoolId); const low=items.filter(x=>x.low_stock).length;
  return <main className="content report-page">
    <div className="page-title no-print"><div><h2>{lang==='mr'?'मासिक साठा अहवाल':'Monthly Stock Report'}</h2><p>{lang==='mr'?'उघडता साठा, प्राप्ती, वापर, समायोजन आणि बंद साठा.':'Opening, receipts, consumption, adjustments and closing stock.'}</p></div><div className="action-row report-actions"><button className="secondary standalone" onClick={load}>{lang==='mr'?'रीफ्रेश':'Refresh'}</button><button className="primary standalone" onClick={()=>window.print()}>{lang==='mr'?'प्रिंट / PDF':'Print / PDF'}</button></div></div>
    <section className="panel form-grid compact no-print"><label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></label><div className="month-controls"><label>{lang==='mr'?'वर्ष':'Year'}<input type="number" value={year} onChange={e=>setYear(Number(e.target.value))}/></label><label>{lang==='mr'?'महिना':'Month'}<select value={month} onChange={e=>setMonth(Number(e.target.value))}>{Array.from({length:12},(_,i)=><option key={i+1} value={i+1}>{i+1}</option>)}</select></label></div></section>
    <section className="panel printable-report"><div className="report-heading"><h2>{lang==='mr'?'पीएम पोषण - मासिक साठा अहवाल':'PM POSHAN - Monthly Stock Report'}</h2><p><strong>{lang==='mr'?'शाळा':'School'}:</strong> {school?(lang==='mr'?school.name_mr:school.name_en):'-'} &nbsp; <strong>{lang==='mr'?'कालावधी':'Period'}:</strong> {String(month).padStart(2,'0')}/{year}</p></div>
      <div className="cards stock-cards report-cards"><article className="card"><span>{lang==='mr'?'वस्तू':'Items'}</span><strong>{items.length}</strong></article><article className="card"><span>{lang==='mr'?'कमी साठा':'Low Stock'}</span><strong>{low}</strong></article><article className="card"><span>{lang==='mr'?'अहवाल महिना':'Report Month'}</span><strong>{String(month).padStart(2,'0')}/{year}</strong></article></div>
      <div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'वस्तू':'Ingredient'}</th><th>{lang==='mr'?'उघडता':'Opening'}</th><th>{lang==='mr'?'प्राप्ती':'Receipts'}</th><th>{lang==='mr'?'वापर':'Consumption'}</th><th>{lang==='mr'?'समायोजन':'Adjustments'}</th><th>{lang==='mr'?'बंद':'Closing'}</th><th>{lang==='mr'?'स्थिती':'Status'}</th></tr></thead><tbody>{items.map(x=><tr key={x.ingredient_id}><td>{lang==='mr'?x.name_mr:x.name_en}<div className="tiny">{x.code}</div></td><td>{x.opening.toFixed(3)} {x.unit}</td><td>{x.receipts.toFixed(3)} {x.unit}</td><td>{x.consumption.toFixed(3)} {x.unit}</td><td className={x.adjustments<0?'qty-out':x.adjustments>0?'qty-in':''}>{x.adjustments.toFixed(3)} {x.unit}</td><td><strong>{x.closing.toFixed(3)} {x.unit}</strong></td><td>{x.low_stock?<span className="status low">{lang==='mr'?'कमी':'LOW'}</span>:<span className="status verified">OK</span>}</td></tr>)}</tbody></table></div>
      <div className="report-signatures"><div>{lang==='mr'?'आहार प्रभारी सही':'Meal In-charge Signature'}</div><div>{lang==='mr'?'मुख्याध्यापक सही':'Headmaster Signature'}</div></div>
    </section>{message&&<div className="notice no-print">{message}</div>}
  </main>
}
