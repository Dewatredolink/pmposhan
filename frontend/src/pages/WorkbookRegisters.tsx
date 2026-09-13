import { useEffect, useState } from 'react';
import { apiFetch, realmRoles } from '../auth';
import { Lang } from '../i18n/translations';
import { saveBlobToDevice } from '../mobile/nativeFile';
import { printCurrentView } from '../mobile/nativePrint';

type School={id:string;name_en:string;name_mr:string;class_1_5_strength:number;class_6_8_strength:number};
type Ingredient={id:string;code:string;name_en:string;name_mr:string;base_unit:string};
type RationItem={ingredient_id:string;name_en:string;name_mr:string;unit:string;required_total:number;available:number;shortage:number};
type Props={lang:Lang;schools:School[];schoolId:string;setSchoolId:(v:string)=>void};
const today=new Date().toISOString().slice(0,10);
function filenameFromResponse(r:Response,fallback:string){const explicit=r.headers.get('X-PMPoshan-Filename');if(explicit)return explicit;const cd=r.headers.get('Content-Disposition')||'';const m=cd.match(/filename="?([^";]+)"?/i);return m?.[1]||fallback;}

export default function WorkbookRegisters({lang,schools,schoolId,setSchoolId}:Props){
  const [date,setDate]=useState(today);
  const [year,setYear]=useState(new Date().getFullYear());
  const [month,setMonth]=useState(new Date().getMonth()+1);
  const [ings,setIngs]=useState<Ingredient[]>([]);
  const [ration,setRation]=useState<any>(null);
  const [msg,setMsg]=useState('');
  const [loan,setLoan]=useState({loan_no:'',direction:'RECEIVED',counterparty_name:'',ingredient_id:'',quantity:'',remarks:''});
  const [bmi,setBmi]=useState({student_identifier:'',student_name:'',class_name:'',gender:'',height_cm:'',weight_kg:'',remarks:''});

  const canEdit=realmRoles().some(r=>['TEACHER','HEADMASTER','SYSTEM_ADMIN'].includes(r));
  const canStock=realmRoles().some(r=>['HEADMASTER','SYSTEM_ADMIN'].includes(r));

  useEffect(()=>{
    apiFetch('/master-data/ingredients')
      .then(r=>r.ok?r.json():[])
      .then(x=>setIngs(Array.isArray(x)?x:[]))
      .catch(()=>setIngs([]));
  },[]);

  async function loadRation(){
    setMsg(''); setRation(null);
    try{const r=await apiFetch(`/workbook-parity/ration-preview?school_id=${encodeURIComponent(schoolId)}&ration_date=${date}`);if(!r.ok)throw new Error(await r.text());setRation(await r.json())}catch(e){setMsg(String(e))}
  }

  async function saveLoan(){
    try{const r=await apiFetch('/workbook-parity/loans',{method:'POST',body:JSON.stringify({school_id:schoolId,loan_date:date,...loan,quantity:Number(loan.quantity)})});if(!r.ok)throw new Error(await r.text());setMsg(lang==='mr'?'उसणवार नोंद जतन झाली.':'Loan stock saved.');setLoan({...loan,loan_no:'',counterparty_name:'',quantity:'',remarks:''})}catch(e){setMsg(String(e))}
  }

  async function saveBmi(){
    try{const r=await apiFetch('/workbook-parity/bmi',{method:'POST',body:JSON.stringify({school_id:schoolId,measurement_date:date,...bmi,height_cm:Number(bmi.height_cm),weight_kg:Number(bmi.weight_kg)})});if(!r.ok)throw new Error(await r.text());const d=await r.json();setMsg(`${lang==='mr'?'BMI जतन झाला':'BMI saved'}: ${d.bmi}`);setBmi({...bmi,student_identifier:'',student_name:'',height_cm:'',weight_kg:'',remarks:''})}catch(e){setMsg(String(e))}
  }

  async function download(rt:string){
    setMsg('');
    try{
      const exportPath=lang==='mr'?'/workbook-parity/register/export-marathi':'/workbook-parity/register/export';
      const r=await apiFetch(`${exportPath}?report_type=${rt}&school_id=${encodeURIComponent(schoolId)}&year=${year}&month=${month}`);
      if(!r.ok)throw new Error(await r.text());
      const b=await r.blob();const fallback=`PM_POSHAN_${rt}_${year}_${String(month).padStart(2,'0')}.xls`;const filename=filenameFromResponse(r,fallback);const saved=await saveBlobToDevice(b,filename);setMsg(lang==='mr'?`फाईल जतन झाली: ${saved.location||filename}`:`File saved: ${saved.location||filename}`);
    }catch(e){setMsg(String(e))}
  }

  async function downloadExact(fmt:string){
    setMsg('');
    try{
      const r=await apiFetch(`/workbook-parity/exact-report/export?format=${fmt}&school_id=${encodeURIComponent(schoolId)}&year=${year}&month=${month}`);
      if(!r.ok)throw new Error(await r.text());
      const b=await r.blob();const fallback=fmt==='MONTHLY_CENTER'?`PM_POSHAN_Monthly_Centre_Report_${year}_${String(month).padStart(2,'0')}.xls`:`PM_POSHAN_Daily_Expense_Part2_${year}_${String(month).padStart(2,'0')}.xls`;const filename=filenameFromResponse(r,fallback);const saved=await saveBlobToDevice(b,filename);setMsg(lang==='mr'?`फाईल जतन झाली: ${saved.location||filename}`:`File saved: ${saved.location||filename}`);
    }catch(e){setMsg(String(e))}
  }

  return <main className="content">
    <section className="panel">
      <h2>{lang==='mr'?'नोंदवही व अधिकृत अहवाल':'Registers & Workbook Reports'}</h2>
      <div className="form-grid">
        <label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?(s.name_mr||s.name_en):(s.name_en||s.name_mr)}</option>)}</select></label>
        <label>{lang==='mr'?'दिनांक':'Date'}<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label>
        <label>{lang==='mr'?'वर्ष':'Year'}<input type="number" value={year} onChange={e=>setYear(Number(e.target.value))}/></label>
        <label>{lang==='mr'?'महिना':'Month'}<input type="number" min="1" max="12" value={month} onChange={e=>setMonth(Number(e.target.value))}/></label>
      </div>
      <div className="action-row"><button className="primary standalone" onClick={()=>void printCurrentView(lang==='mr'?'PM POSHAN - नोंदवही व अहवाल':'PM POSHAN - Registers & Reports')}>{lang==='mr'?'प्रिंट / PDF':'Print / PDF'}</button></div>
      {msg&&<p>{msg}</p>}
    </section>

    <section className="panel"><h3>{lang==='mr'?'राशन — निवडलेल्या दिवसाची आवश्यक मात्रा':'Ration requirement for selected day'}</h3><button onClick={loadRation}>{lang==='mr'?'राशन गणना दाखवा':'Show ration calculation'}</button>{ration&&<><p><b>{lang==='mr'?'मेनू':'Menu'}:</b> {lang==='mr'?(ration.menu.name_mr||ration.menu.name_en):(ration.menu.name_en||ration.menu.name_mr)} | 1-5: {ration.class_1_5} | 6-8: {ration.class_6_8}</p><div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'घटक':'Ingredient'}</th><th>{lang==='mr'?'एकक':'Unit'}</th><th>{lang==='mr'?'आवश्यक':'Required'}</th><th>{lang==='mr'?'उपलब्ध':'Available'}</th><th>{lang==='mr'?'तूट':'Shortage'}</th></tr></thead><tbody>{ration.items.map((x:RationItem)=><tr key={x.ingredient_id}><td>{lang==='mr'?(x.name_mr||x.name_en):(x.name_en||x.name_mr)}</td><td>{x.unit}</td><td>{x.required_total}</td><td>{x.available}</td><td>{x.shortage}</td></tr>)}</tbody></table></div></>}</section>

    {canStock&&<section className="panel"><h3>{lang==='mr'?'उसणवार साठा':'Borrowed / Loan Stock'}</h3><div className="form-grid"><label>{lang==='mr'?'क्रमांक':'Loan No'}<input value={loan.loan_no} onChange={e=>setLoan({...loan,loan_no:e.target.value})}/></label><label>{lang==='mr'?'प्रकार':'Direction'}<select value={loan.direction} onChange={e=>setLoan({...loan,direction:e.target.value})}><option value="RECEIVED">RECEIVED / प्राप्त</option><option value="GIVEN">GIVEN / दिले</option></select></label><label>{lang==='mr'?'समोरील शाळा/संस्था':'Counterparty'}<input value={loan.counterparty_name} onChange={e=>setLoan({...loan,counterparty_name:e.target.value})}/></label><label>{lang==='mr'?'घटक':'Ingredient'}<select value={loan.ingredient_id} onChange={e=>setLoan({...loan,ingredient_id:e.target.value})}><option value="">--</option>{ings.map(i=><option key={i.id} value={i.id}>{lang==='mr'?(i.name_mr||i.name_en):(i.name_en||i.name_mr)}</option>)}</select></label><label>{lang==='mr'?'मात्रा':'Quantity'}<input type="number" step="0.001" value={loan.quantity} onChange={e=>setLoan({...loan,quantity:e.target.value})}/></label></div><button onClick={saveLoan}>{lang==='mr'?'उसणवार जतन करा':'Save loan stock'}</button></section>}

    {canEdit&&<section className="panel"><h3>BMI</h3><div className="form-grid"><label>ID<input value={bmi.student_identifier} onChange={e=>setBmi({...bmi,student_identifier:e.target.value})}/></label><label>{lang==='mr'?'विद्यार्थ्याचे नाव':'Student name'}<input value={bmi.student_name} onChange={e=>setBmi({...bmi,student_name:e.target.value})}/></label><label>{lang==='mr'?'इयत्ता':'Class'}<input value={bmi.class_name} onChange={e=>setBmi({...bmi,class_name:e.target.value})}/></label><label>{lang==='mr'?'लिंग':'Gender'}<input value={bmi.gender} onChange={e=>setBmi({...bmi,gender:e.target.value})}/></label><label>{lang==='mr'?'उंची सेमी':'Height cm'}<input type="number" step="0.1" value={bmi.height_cm} onChange={e=>setBmi({...bmi,height_cm:e.target.value})}/></label><label>{lang==='mr'?'वजन कि.ग्रॅ.':'Weight kg'}<input type="number" step="0.1" value={bmi.weight_kg} onChange={e=>setBmi({...bmi,weight_kg:e.target.value})}/></label></div><button onClick={saveBmi}>{lang==='mr'?'BMI जतन करा':'Save BMI'}</button><p className="muted">{lang==='mr'?'ॲप BMI संख्या मोजते; वैद्यकीय वर्गीकरण आपोआप करत नाही.':'The app calculates the BMI number; it does not automatically assign a medical category.'}</p></section>}

    <section className="panel official-report-panel"><h3>{lang==='mr'?'दिलेल्या नमुन्याप्रमाणे अधिकृत अहवाल':'Official reports matching supplied formats'}</h3><p className="muted">{lang==='mr'?'हे Excel अहवाल दिलेल्या नमुन्याची मांडणी, 1 ते 5 / 6 ते 8 विभाग, साठा व वापर आकडे आणि प्रिंट सेटिंग वापरतात.':'These Excel reports follow the supplied layout, separate 1-5 / 6-8 sections, stock/consumption figures and print settings.'}</p><div className="button-row"><button onClick={()=>downloadExact('MONTHLY_CENTER')}>{lang==='mr'?'मासिक केंद्र अहवाल — नमुना 1':'Monthly Centre Report — Format 1'}</button><button onClick={()=>downloadExact('DAILY_PART2')}>{lang==='mr'?'दैनंदिन खर्च नोंदवही भाग 2 — नमुना 2':'Daily Expense Register Part 2 — Format 2'}</button></div></section>

    <section className="panel"><h3>{lang==='mr'?'Excel नोंदवही डाउनलोड':'Download Excel registers'}</h3><div className="button-row">{[['PART1','भाग 1'],['PART2','भाग 2'],['RATION','राशन'],['MONTHLY','मासिक प्रपत्र'],['SUMMARY','गोषवारा'],['UTILIZATION','उपयोगिता'],['BMI','BMI'],['LOANS','उसणवार'],['SPECIAL_DAYS','विशेषदिन']].map(([k,l])=><button key={k} onClick={()=>download(k)}>{lang==='mr'?l:k}</button>)}</div></section>
  </main>
}
