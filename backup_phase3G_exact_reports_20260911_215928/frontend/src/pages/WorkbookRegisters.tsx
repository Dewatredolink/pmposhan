import { useEffect, useState } from 'react';
import { apiFetch, realmRoles } from '../auth';
import { Lang } from '../i18n/translations';

type School={id:string;name_en:string;name_mr:string;class_1_5_strength:number;class_6_8_strength:number};
type Ingredient={id:string;code:string;name_en:string;name_mr:string;base_unit:string};
type RationItem={ingredient_id:string;name_en:string;name_mr:string;unit:string;required_total:number;available:number;shortage:number};
type Props={lang:Lang;schools:School[];schoolId:string;setSchoolId:(v:string)=>void};
const today=new Date().toISOString().slice(0,10);

export default function WorkbookRegisters({lang,schools,schoolId,setSchoolId}:Props){
  const [date,setDate]=useState(today); const [year,setYear]=useState(new Date().getFullYear()); const [month,setMonth]=useState(new Date().getMonth()+1);
  const [ings,setIngs]=useState<Ingredient[]>([]); const [ration,setRation]=useState<any>(null); const [msg,setMsg]=useState('');
  const [loan,setLoan]=useState({loan_no:'',direction:'RECEIVED',counterparty_name:'',ingredient_id:'',quantity:'',remarks:''});
  const [bmi,setBmi]=useState({student_identifier:'',student_name:'',class_name:'',gender:'',height_cm:'',weight_kg:'',remarks:''});
  const canEdit=realmRoles().some(r=>['TEACHER','HEADMASTER','SYSTEM_ADMIN'].includes(r));
  const canStock=realmRoles().some(r=>['HEADMASTER','SYSTEM_ADMIN'].includes(r));
  useEffect(()=>{apiFetch('/master-data/ingredients').then(r=>r.ok?r.json():[]).then(x=>setIngs(Array.isArray(x)?x:[])).catch(()=>setIngs([]));},[]);
  async function loadRation(){setMsg('');setRation(null);try{const r=await apiFetch(`/workbook-parity/ration-preview?school_id=${encodeURIComponent(schoolId)}&ration_date=${date}`);if(!r.ok)throw new Error(await r.text());setRation(await r.json())}catch(e){setMsg(String(e))}}
  async function saveLoan(){try{const r=await apiFetch('/workbook-parity/loans',{method:'POST',body:JSON.stringify({school_id:schoolId,loan_date:date,...loan,quantity:Number(loan.quantity)})});if(!r.ok)throw new Error(await r.text());setMsg(lang==='mr'?'à¤‰à¤¸à¤¨à¤µà¤¾à¤° à¤¨à¥‹à¤‚à¤¦ à¤œà¤¤à¤¨ à¤à¤¾à¤²à¥€.':'Loan stock saved.');setLoan({...loan,loan_no:'',counterparty_name:'',quantity:'',remarks:''})}catch(e){setMsg(String(e))}}
  async function saveBmi(){try{const r=await apiFetch('/workbook-parity/bmi',{method:'POST',body:JSON.stringify({school_id:schoolId,measurement_date:date,...bmi,height_cm:Number(bmi.height_cm),weight_kg:Number(bmi.weight_kg)})});if(!r.ok)throw new Error(await r.text());const d=await r.json();setMsg(`${lang==='mr'?'BMI à¤œà¤¤à¤¨ à¤à¤¾à¤²à¤¾':'BMI saved'}: ${d.bmi}`);setBmi({...bmi,student_identifier:'',student_name:'',height_cm:'',weight_kg:'',remarks:''})}catch(e){setMsg(String(e))}}
  async function download(rt:string){setMsg('');try{const r=await apiFetch(`/workbook-parity/register/export?report_type=${rt}&school_id=${encodeURIComponent(schoolId)}&year=${year}&month=${month}`);if(!r.ok)throw new Error(await r.text());const b=await r.blob();const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download=`PM_POSHAN_${rt}_${year}_${String(month).padStart(2,'0')}.xlsx`;a.click();URL.revokeObjectURL(u)}catch(e){setMsg(String(e))}}
  async function downloadExact(fmt:string){
    setMsg('');
    try{
      const r=await apiFetch(`/workbook-parity/exact-report/export?format=${fmt}&school_id=${encodeURIComponent(schoolId)}&year=${year}&month=${month}`);
      if(!r.ok)throw new Error(await r.text());
      const b=await r.blob();
      const u=URL.createObjectURL(b);
      const a=document.createElement('a');
      a.href=u;
      a.download=fmt==='MONTHLY_CENTER'
        ?`PM_POSHAN_Monthly_Centre_Report_${year}_${String(month).padStart(2,'0')}.xlsx`
        :`PM_POSHAN_Daily_Expense_Part2_${year}_${String(month).padStart(2,'0')}.xlsx`;
      a.click();
      URL.revokeObjectURL(u);
    }catch(e){setMsg(String(e))}
  }
  return <main className="content"><section className="panel"><h2>{lang==='mr'?'à¤¨à¥‹à¤‚à¤¦à¤µà¤¹à¥€ à¤µ à¤…à¤§à¤¿à¤•à¥ƒà¤¤ à¤…à¤¹à¤µà¤¾à¤²':'Registers & Workbook Reports'}</h2>
    <div className="form-grid"><label>{lang==='mr'?'à¤¶à¤¾à¤³à¤¾':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?(s.name_mr||s.name_en):(s.name_en||s.name_mr)}</option>)}</select></label><label>{lang==='mr'?'à¤¦à¤¿à¤¨à¤¾à¤‚à¤•':'Date'}<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label><label>{lang==='mr'?'à¤µà¤°à¥à¤·':'Year'}<input type="number" value={year} onChange={e=>setYear(Number(e.target.value))}/></label><label>{lang==='mr'?'à¤®à¤¹à¤¿à¤¨à¤¾':'Month'}<input type="number" min="1" max="12" value={month} onChange={e=>setMonth(Number(e.target.value))}/></label></div>{msg&&<p>{msg}</p>}
  </section>
  <section className="panel"><h3>{lang==='mr'?'à¤°à¤¾à¤¶à¤¨ â€” à¤¨à¤¿à¤µà¤¡à¤²à¥‡à¤²à¥à¤¯à¤¾ à¤¦à¤¿à¤µà¤¸à¤¾à¤šà¥€ à¤†à¤µà¤¶à¥à¤¯à¤• à¤®à¤¾à¤¤à¥à¤°à¤¾':'Ration requirement for selected day'}</h3><button onClick={loadRation}>{lang==='mr'?'à¤°à¤¾à¤¶à¤¨ à¤—à¤£à¤¨à¤¾ à¤¦à¤¾à¤–à¤µà¤¾':'Show ration calculation'}</button>{ration&&<><p><b>{lang==='mr'?'à¤®à¥‡à¤¨à¥‚':'Menu'}:</b> {lang==='mr'?(ration.menu.name_mr||ration.menu.name_en):(ration.menu.name_en||ration.menu.name_mr)} | 1-5: {ration.class_1_5} | 6-8: {ration.class_6_8}</p><div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'à¤˜à¤Ÿà¤•':'Ingredient'}</th><th>{lang==='mr'?'à¤à¤•à¤•':'Unit'}</th><th>{lang==='mr'?'à¤†à¤µà¤¶à¥à¤¯à¤•':'Required'}</th><th>{lang==='mr'?'à¤‰à¤ªà¤²à¤¬à¥à¤§':'Available'}</th><th>{lang==='mr'?'à¤¤à¥‚à¤Ÿ':'Shortage'}</th></tr></thead><tbody>{ration.items.map((x:RationItem)=><tr key={x.ingredient_id}><td>{lang==='mr'?(x.name_mr||x.name_en):(x.name_en||x.name_mr)}</td><td>{x.unit}</td><td>{x.required_total}</td><td>{x.available}</td><td>{x.shortage}</td></tr>)}</tbody></table></div></>}</section>
  {canStock&&<section className="panel"><h3>{lang==='mr'?'à¤‰à¤¸à¤¨à¤µà¤¾à¤° à¤¸à¤¾à¤ à¤¾':'Borrowed / Loan Stock'}</h3><div className="form-grid"><label>{lang==='mr'?'à¤•à¥à¤°à¤®à¤¾à¤‚à¤•':'Loan No'}<input value={loan.loan_no} onChange={e=>setLoan({...loan,loan_no:e.target.value})}/></label><label>{lang==='mr'?'à¤ªà¥à¤°à¤•à¤¾à¤°':'Direction'}<select value={loan.direction} onChange={e=>setLoan({...loan,direction:e.target.value})}><option value="RECEIVED">RECEIVED / à¤ªà¥à¤°à¤¾à¤ªà¥à¤¤</option><option value="GIVEN">GIVEN / à¤¦à¤¿à¤²à¥‡</option></select></label><label>{lang==='mr'?'à¤¸à¤®à¥‹à¤°à¥€à¤² à¤¶à¤¾à¤³à¤¾/à¤¸à¤‚à¤¸à¥à¤¥à¤¾':'Counterparty'}<input value={loan.counterparty_name} onChange={e=>setLoan({...loan,counterparty_name:e.target.value})}/></label><label>{lang==='mr'?'à¤˜à¤Ÿà¤•':'Ingredient'}<select value={loan.ingredient_id} onChange={e=>setLoan({...loan,ingredient_id:e.target.value})}><option value="">--</option>{ings.map(i=><option key={i.id} value={i.id}>{i.name_mr||i.name_en}</option>)}</select></label><label>{lang==='mr'?'à¤®à¤¾à¤¤à¥à¤°à¤¾':'Quantity'}<input type="number" step="0.001" value={loan.quantity} onChange={e=>setLoan({...loan,quantity:e.target.value})}/></label></div><button onClick={saveLoan}>{lang==='mr'?'à¤‰à¤¸à¤¨à¤µà¤¾à¤° à¤œà¤¤à¤¨ à¤•à¤°à¤¾':'Save loan stock'}</button></section>}
  {canEdit&&<section className="panel"><h3>BMI</h3><div className="form-grid"><label>ID<input value={bmi.student_identifier} onChange={e=>setBmi({...bmi,student_identifier:e.target.value})}/></label><label>{lang==='mr'?'à¤µà¤¿à¤¦à¥à¤¯à¤¾à¤°à¥à¤¥à¥à¤¯à¤¾à¤šà¥‡ à¤¨à¤¾à¤µ':'Student name'}<input value={bmi.student_name} onChange={e=>setBmi({...bmi,student_name:e.target.value})}/></label><label>{lang==='mr'?'à¤‡à¤¯à¤¤à¥à¤¤à¤¾':'Class'}<input value={bmi.class_name} onChange={e=>setBmi({...bmi,class_name:e.target.value})}/></label><label>{lang==='mr'?'à¤²à¤¿à¤‚à¤—':'Gender'}<input value={bmi.gender} onChange={e=>setBmi({...bmi,gender:e.target.value})}/></label><label>{lang==='mr'?'à¤‰à¤‚à¤šà¥€ à¤¸à¥‡à¤®à¥€':'Height cm'}<input type="number" step="0.1" value={bmi.height_cm} onChange={e=>setBmi({...bmi,height_cm:e.target.value})}/></label><label>{lang==='mr'?'à¤µà¤œà¤¨ à¤•à¤¿.à¤—à¥à¤°à¥….':'Weight kg'}<input type="number" step="0.1" value={bmi.weight_kg} onChange={e=>setBmi({...bmi,weight_kg:e.target.value})}/></label></div><button onClick={saveBmi}>Save BMI / BMI à¤œà¤¤à¤¨ à¤•à¤°à¤¾</button><p className="muted">{lang==='mr'?'à¤…à¥…à¤ª BMI à¤¸à¤‚à¤–à¥à¤¯à¤¾ à¤®à¥‹à¤œà¤¤à¥‹; à¤µà¥ˆà¤¦à¥à¤¯à¤•à¥€à¤¯ à¤µà¤°à¥à¤—à¥€à¤•à¤°à¤£ à¤†à¤ªà¥‹à¤†à¤ª à¤•à¤°à¤¤ à¤¨à¤¾à¤¹à¥€.':'The app calculates the BMI number; it does not automatically assign a medical category.'}</p></section>}
  <section className="panel official-report-panel">
    <h3>{lang==='mr'?'à¤¦à¤¿à¤²à¥‡à¤²à¥à¤¯à¤¾ à¤¨à¤®à¥à¤¨à¥à¤¯à¤¾à¤ªà¥à¤°à¤®à¤¾à¤£à¥‡ à¤…à¤§à¤¿à¤•à¥ƒà¤¤ à¤…à¤¹à¤µà¤¾à¤²':'Official reports matching supplied formats'}</h3>
    <p className="muted">{lang==='mr'?'à¤¹à¥‡ Excel à¤…à¤¹à¤µà¤¾à¤² à¤¦à¤¿à¤²à¥‡à¤²à¥à¤¯à¤¾ à¤¨à¤®à¥à¤¨à¥à¤¯à¤¾à¤šà¥€ à¤®à¤¾à¤‚à¤¡à¤£à¥€, 1 à¤¤à¥‡ 5 / 6 à¤¤à¥‡ 8 à¤µà¤¿à¤­à¤¾à¤—, à¤¸à¤¾à¤ à¤¾ à¤µ à¤µà¤¾à¤ªà¤° à¤†à¤•à¤¡à¥‡ à¤†à¤£à¤¿ à¤ªà¥à¤°à¤¿à¤‚à¤Ÿ à¤¸à¥‡à¤Ÿà¤¿à¤‚à¤— à¤µà¤¾à¤ªà¤°à¤¤à¤¾à¤¤.':'These Excel reports follow the supplied layout, separate 1â€“5 / 6â€“8 sections, stock/consumption figures and print settings.'}</p>
    <div className="button-row">
      <button onClick={()=>downloadExact('MONTHLY_CENTER')}>{lang==='mr'?'à¤®à¤¾à¤¸à¤¿à¤• à¤•à¥‡à¤‚à¤¦à¥à¤° à¤…à¤¹à¤µà¤¾à¤² â€” à¤¨à¤®à¥à¤¨à¤¾ 1':'Monthly Centre Report â€” Format 1'}</button>
      <button onClick={()=>downloadExact('DAILY_PART2')}>{lang==='mr'?'à¤¦à¥ˆà¤¨à¤‚à¤¦à¤¿à¤¨ à¤–à¤°à¥à¤š à¤¨à¥‹à¤‚à¤¦à¤µà¤¹à¥€ à¤­à¤¾à¤— 2 â€” à¤¨à¤®à¥à¤¨à¤¾ 2':'Daily Expense Register Part 2 â€” Format 2'}</button>
    </div>
  </section>
  <section className="panel"><h3>{lang==='mr'?'Excel à¤¨à¥‹à¤‚à¤¦à¤µà¤¹à¥€ à¤¡à¤¾à¤‰à¤¨à¤²à¥‹à¤¡':'Download Excel registers'}</h3><div className="button-row">{[['PART1','à¤­à¤¾à¤— 1'],['PART2','à¤­à¤¾à¤— 2'],['RATION','à¤°à¤¾à¤¶à¤¨'],['MONTHLY','à¤®à¤¾à¤¸à¤¿à¤• à¤ªà¥à¤°à¤ªà¤¤à¥à¤°'],['SUMMARY','à¤—à¥‹à¤·à¤µà¤¾à¤°à¤¾'],['UTILIZATION','à¤‰à¤ªà¤¯à¥‹à¤—à¤¿à¤¤à¤¾'],['BMI','BMI'],['LOANS','à¤‰à¤¸à¤¨à¤µà¤¾à¤°'],['SPECIAL_DAYS','à¤µà¤¿à¤¶à¥‡à¤·à¤¦à¤¿à¤¨']].map(([k,l])=><button key={k} onClick={()=>download(k)}>{l}</button>)}</div></section>
  </main>
}

