import { useEffect, useState } from 'react';
import { apiFetch } from '../auth';
import { Lang } from '../i18n/translations';

type School={id:string;name_en:string;name_mr:string};
type Balance={ingredient_id:string;code:string;name_en:string;name_mr:string;unit:string;balance:number;reorder_level:number;low_stock:boolean};
type Ledger={id:string;transaction_date:string;transaction_type:string;ingredient_id:string;ingredient_name_en:string;ingredient_name_mr:string;unit:string;quantity:number;reference_no?:string|null;remarks?:string|null;entered_by_username:string};
type Props={lang:Lang;schools:School[];schoolId:string;setSchoolId:(id:string)=>void};

export default function StockRegister({lang,schools,schoolId,setSchoolId}:Props){
  const [balances,setBalances]=useState<Balance[]>([]); const [ledger,setLedger]=useState<Ledger[]>([]);
  const [ingredientId,setIngredientId]=useState(''); const [message,setMessage]=useState('');
  async function load(){if(!schoolId)return;setMessage('');try{const [b,l]=await Promise.all([apiFetch(`/stock/balances?school_id=${encodeURIComponent(schoolId)}`),apiFetch(`/stock/ledger?school_id=${encodeURIComponent(schoolId)}${ingredientId?`&ingredient_id=${encodeURIComponent(ingredientId)}`:''}`)]);if(!b.ok)throw new Error(await b.text());if(!l.ok)throw new Error(await l.text());setBalances(await b.json());setLedger(await l.json());}catch(e){setMessage(String(e));}}
  useEffect(()=>{void load();},[schoolId,ingredientId]);
  const low=balances.filter(x=>x.low_stock).length;
  return <main className="content">
    <div className="page-title"><div><h2>{lang==='mr'?'साठा नोंदवही':'Stock Register'}</h2><p>{lang==='mr'?'प्राप्ती, स्वयंचलित वापर आणि चालू शिल्लक तपासा.':'Review receipts, automatic consumption and current balances.'}</p></div><button className="secondary standalone" onClick={load}>{lang==='mr'?'रीफ्रेश':'Refresh'}</button></div>
    <section className="panel form-grid compact"><label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></label><label>{lang==='mr'?'लेजर वस्तू फिल्टर':'Ledger Ingredient Filter'}<select value={ingredientId} onChange={e=>setIngredientId(e.target.value)}><option value="">{lang==='mr'?'सर्व वस्तू':'All ingredients'}</option>{balances.map(x=><option key={x.ingredient_id} value={x.ingredient_id}>{lang==='mr'?x.name_mr:x.name_en}</option>)}</select></label></section>
    <section className="cards stock-cards"><article className="card"><span>{lang==='mr'?'साठा वस्तू':'Inventory Items'}</span><strong>{balances.length}</strong></article><article className="card"><span>{lang==='mr'?'कमी साठा सूचना':'Low Stock Alerts'}</span><strong>{low}</strong></article><article className="card"><span>{lang==='mr'?'लेजर नोंदी':'Ledger Entries'}</span><strong>{ledger.length}</strong></article></section>
    <section className="panel"><h3>{lang==='mr'?'चालू शिल्लक':'Current Balances'}</h3><div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'वस्तू':'Ingredient'}</th><th>{lang==='mr'?'कोड':'Code'}</th><th>{lang==='mr'?'शिल्लक':'Balance'}</th><th>{lang==='mr'?'पुनर्भरण पातळी':'Reorder Level'}</th><th>{lang==='mr'?'स्थिती':'Status'}</th></tr></thead><tbody>{balances.map(x=><tr key={x.ingredient_id}><td>{lang==='mr'?x.name_mr:x.name_en}</td><td>{x.code}</td><td><strong>{x.balance.toFixed(3)} {x.unit}</strong></td><td>{x.reorder_level.toFixed(3)} {x.unit}</td><td>{x.low_stock?<span className="status low">{lang==='mr'?'कमी साठा':'LOW'}</span>:<span className="status verified">OK</span>}</td></tr>)}</tbody></table></div></section>
    <section className="panel"><h3>{lang==='mr'?'साठा लेजर':'Stock Ledger'}</h3><div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'दिनांक':'Date'}</th><th>{lang==='mr'?'वस्तू':'Ingredient'}</th><th>{lang==='mr'?'प्रकार':'Type'}</th><th>{lang==='mr'?'प्रमाण':'Qty'}</th><th>{lang==='mr'?'संदर्भ':'Reference'}</th><th>{lang==='mr'?'नोंद करणारा':'Entered By'}</th></tr></thead><tbody>{ledger.map(x=><tr key={x.id}><td>{x.transaction_date}</td><td>{lang==='mr'?x.ingredient_name_mr:x.ingredient_name_en}</td><td>{x.transaction_type}</td><td className={x.quantity<0?'qty-out':'qty-in'}>{x.quantity>0?'+':''}{x.quantity.toFixed(3)} {x.unit}</td><td>{x.reference_no||'-'}</td><td>{x.entered_by_username}</td></tr>)}</tbody></table></div></section>
    {message&&<div className="notice">{message}</div>}
  </main>
}
