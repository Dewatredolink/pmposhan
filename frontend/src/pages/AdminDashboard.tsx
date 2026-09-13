import { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../auth';
import { Lang } from '../i18n/translations';
import { printCurrentView } from '../mobile/nativePrint';

type Props={lang:Lang};
type Summary={year:number;month:number;total_schools:number;returns_generated:number;missing_returns:number;approved_returns:number;pending_returns:number;total_attendance:number;total_meals:number;meal_coverage_pct:number;exception_schools:number;low_stock_schools:number;status_counts:Record<string,number>};
type DrillRow={id:string;name_en:string;name_mr:string;code?:string|null;school_count:number;returns_generated:number;missing_returns:number;approved_returns:number;pending_returns:number;attendance:number;meals:number;coverage_pct:number;exception_schools:number;low_stock_schools:number;status?:string;exceptions?:number;low_stock_items?:number;next_level?:string|null};
type SchoolRow={school_id:string;school_name_en:string;school_name_mr:string;udise_code:string;cluster_name_en?:string|null;cluster_name_mr?:string|null;block_name_en?:string|null;block_name_mr?:string|null;district_name_en?:string|null;district_name_mr?:string|null;status:string;recorded_days:number;verified_days:number;attendance:number;meals:number;coverage_pct:number;exceptions:number;low_stock_items:number;has_low_stock:boolean};
type Crumb={level:string;id?:string;name:string};
const now=new Date();

export default function AdminDashboard({lang}:Props){
  const [year,setYear]=useState(now.getFullYear());
  const [month,setMonth]=useState(now.getMonth()+1);
  const [summary,setSummary]=useState<Summary|null>(null);
  const [level,setLevel]=useState('district');
  const [parentId,setParentId]=useState<string|undefined>(undefined);
  const [rows,setRows]=useState<DrillRow[]>([]);
  const [schools,setSchools]=useState<SchoolRow[]>([]);
  const [crumbs,setCrumbs]=useState<Crumb[]>([{level:'district',name:lang==='mr'?'जिल्हा':'District'}]);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');

  async function load(lvl=level,pid=parentId){
    try{
      setBusy(true); setMessage('');
      const qs=`year=${year}&month=${month}`;
      const drill=`${qs}&level=${encodeURIComponent(lvl)}${pid?`&parent_id=${encodeURIComponent(pid)}`:''}`;
      const [a,b,c]=await Promise.all([
        apiFetch(`/admin-dashboard/summary?${qs}`),
        apiFetch(`/admin-dashboard/drilldown?${drill}`),
        apiFetch(`/admin-dashboard/schools?${qs}`),
      ]);
      for(const r of [a,b,c]) if(!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      setSummary(await a.json());
      const d=await b.json(); setRows(d.rows||[]);
      setSchools(await c.json());
    }catch(e){setMessage(String(e));}finally{setBusy(false);}
  }
  useEffect(()=>{setLevel('district');setParentId(undefined);setCrumbs([{level:'district',name:lang==='mr'?'जिल्हा':'District'}]);void load('district',undefined);},[year,month]);
  useEffect(()=>{setCrumbs(c=>c.map((x,i)=>i===0?{...x,name:lang==='mr'?'जिल्हा':'District'}:x));},[lang]);

  function drill(r:DrillRow){
    if(!r.next_level)return;
    setLevel(r.next_level); setParentId(r.id);
    setCrumbs(c=>[...c,{level:r.next_level!,id:r.id,name:lang==='mr'?r.name_mr:r.name_en}]);
    void load(r.next_level,r.id);
  }
  function goCrumb(i:number){
    const next=crumbs.slice(0,i+1); const c=next[next.length-1];
    setCrumbs(next); setLevel(c.level); setParentId(c.id); void load(c.level,c.id);
  }
  const statusLabel=(s:string)=>({DRAFT:lang==='mr'?'मसुदा':'Draft',SUBMITTED:lang==='mr'?'सादर':'Submitted',CLUSTER_REVIEWED:lang==='mr'?'क्लस्टर पडताळले':'Cluster Reviewed',BLOCK_APPROVED:lang==='mr'?'ब्लॉक मंजूर':'Block Approved',RETURNED:lang==='mr'?'परत':'Returned',MISSING:lang==='mr'?'परतावा नाही':'Missing'} as Record<string,string>)[s]||s;
  const attention=useMemo(()=>schools.filter(s=>s.status==='MISSING'||s.status==='RETURNED'||s.exceptions>0||s.has_low_stock),[schools]);

  function exportCsv(){
    const head=['UDISE','School','Cluster','Block','District','Status','Recorded Days','Verified Days','Attendance','Meals','Coverage %','Exceptions','Low Stock Items'];
    const escape=(v:any)=>`"${String(v??'').replaceAll('"','""')}"`;
    const body=schools.map(s=>[s.udise_code,lang==='mr'?s.school_name_mr:s.school_name_en,lang==='mr'?s.cluster_name_mr:s.cluster_name_en,lang==='mr'?s.block_name_mr:s.block_name_en,lang==='mr'?s.district_name_mr:s.district_name_en,statusLabel(s.status),s.recorded_days,s.verified_days,s.attendance,s.meals,s.coverage_pct,s.exceptions,s.low_stock_items].map(escape).join(','));
    const blob=new Blob(['\ufeff'+[head.join(','),...body].join('\n')],{type:'text/csv;charset=utf-8'});
    const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`pmposhan-consolidated-${year}-${String(month).padStart(2,'0')}.csv`;a.click();URL.revokeObjectURL(a.href);
  }

  const printReport=()=>void printCurrentView(`PM POSHAN - ${lang==='mr'?'एकत्रित प्रशासकीय अहवाल':'Consolidated Administrative Report'} ${String(month).padStart(2,'0')}-${year}`);

  return <main className="content admin-report-page">
    <div className="page-title no-print"><div><h2>{lang==='mr'?'प्रशासकीय डॅशबोर्ड व एकत्रित अहवाल':'Administrative Dashboard & Consolidated Reporting'}</h2><p>{lang==='mr'?'जिल्हा → ब्लॉक → क्लस्टर → शाळा ड्रिल-डाउन, परतावा स्थिती, आहार कव्हरेज आणि अपवाद.':'District → Block → Cluster → School drill-down, return status, meal coverage and exceptions.'}</p></div><div className="admin-actions"><button className="secondary standalone" disabled={busy} onClick={()=>load()}>{lang==='mr'?'रीफ्रेश':'Refresh'}</button><button className="secondary standalone" onClick={exportCsv}>CSV</button><button className="primary standalone" onClick={printReport}>{lang==='mr'?'प्रिंट / PDF':'Print / PDF'}</button></div></div>

    <section className="panel form-grid compact no-print"><div className="month-controls"><label>{lang==='mr'?'वर्ष':'Year'}<input type="number" min="2000" max="2200" value={year} onChange={e=>setYear(Number(e.target.value))}/></label><label>{lang==='mr'?'महिना':'Month'}<select value={month} onChange={e=>setMonth(Number(e.target.value))}>{Array.from({length:12},(_,i)=><option key={i+1} value={i+1}>{i+1}</option>)}</select></label></div></section>

    <div className="report-heading print-only"><h2>{lang==='mr'?'पीएम पोषण - एकत्रित प्रशासकीय अहवाल':'PM POSHAN - Consolidated Administrative Report'}</h2><p>{month}/{year}</p></div>

    <div className="cards admin-cards">
      <div className="card"><span>{lang==='mr'?'कार्यक्षेत्रातील शाळा':'Schools in Scope'}</span><strong>{summary?.total_schools??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'ब्लॉक मंजूर परतावे':'Block Approved'}</span><strong>{summary?.approved_returns??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'परतावा बाकी':'Missing Returns'}</span><strong>{summary?.missing_returns??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'एकूण भोजन':'Total Meals'}</span><strong>{summary?.total_meals??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'आहार कव्हरेज':'Meal Coverage'}</span><strong>{summary?.meal_coverage_pct??0}%</strong></div>
      <div className="card"><span>{lang==='mr'?'अपवाद शाळा':'Exception Schools'}</span><strong>{summary?.exception_schools??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'कमी साठा शाळा':'Low-stock Schools'}</span><strong>{summary?.low_stock_schools??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'प्रलंबित कार्यप्रवाह':'Pending Workflow'}</span><strong>{summary?.pending_returns??0}</strong></div>
    </div>

    <section className="panel"><h3>{lang==='mr'?'परतावा कार्यप्रवाह स्थिती':'Return Workflow Status'}</h3><div className="status-grid admin-status-grid">{['DRAFT','SUBMITTED','CLUSTER_REVIEWED','BLOCK_APPROVED','RETURNED','MISSING'].map(s=><div key={s}><span>{statusLabel(s)}</span><strong>{summary?.status_counts?.[s]??0}</strong></div>)}</div></section>

    <section className="panel"><div className="page-title"><div><h3>{lang==='mr'?'प्रशासकीय ड्रिल-डाउन':'Administrative Drill-down'}</h3><div className="breadcrumb">{crumbs.map((c,i)=><span key={`${c.level}-${i}`}><button disabled={i===crumbs.length-1} onClick={()=>goCrumb(i)}>{c.name}</button>{i<crumbs.length-1&&<b>→</b>}</span>)}</div></div></div>
      <div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'युनिट':'Unit'}</th><th>{lang==='mr'?'शाळा':'Schools'}</th><th>{lang==='mr'?'मंजूर':'Approved'}</th><th>{lang==='mr'?'बाकी':'Missing'}</th><th>{lang==='mr'?'उपस्थिती':'Attendance'}</th><th>{lang==='mr'?'भोजन':'Meals'}</th><th>{lang==='mr'?'कव्हरेज':'Coverage'}</th><th>{lang==='mr'?'अपवाद':'Exceptions'}</th><th>{lang==='mr'?'कमी साठा':'Low Stock'}</th></tr></thead><tbody>
        {rows.length===0?<tr><td colSpan={9}>{lang==='mr'?'डेटा उपलब्ध नाही.':'No data available.'}</td></tr>:rows.map(r=><tr key={r.id} className={r.next_level?'drill-row':''} onClick={()=>r.next_level&&drill(r)}><td><strong>{lang==='mr'?r.name_mr:r.name_en}</strong>{r.code&&<div className="tiny">{r.code}</div>}</td><td>{r.school_count}</td><td>{r.approved_returns}</td><td className={r.missing_returns?'qty-out':''}>{r.missing_returns}</td><td>{r.attendance}</td><td>{r.meals}</td><td>{r.coverage_pct}%</td><td className={r.exception_schools?'qty-out':'qty-in'}>{r.exception_schools}</td><td className={r.low_stock_schools?'qty-out':'qty-in'}>{r.low_stock_schools}</td></tr>)}
      </tbody></table></div>
    </section>

    <section className="panel printable-report"><h3>{lang==='mr'?'लक्ष देण्याची गरज असलेल्या शाळा':'Schools Requiring Attention'}</h3><div className="table-wrap"><table><thead><tr><th>UDISE</th><th>{lang==='mr'?'शाळा':'School'}</th><th>{lang==='mr'?'ब्लॉक / क्लस्टर':'Block / Cluster'}</th><th>{lang==='mr'?'स्थिती':'Status'}</th><th>{lang==='mr'?'कव्हरेज':'Coverage'}</th><th>{lang==='mr'?'अपवाद':'Exceptions'}</th><th>{lang==='mr'?'कमी साठा आयटम':'Low-stock Items'}</th></tr></thead><tbody>
      {attention.length===0?<tr><td colSpan={7}>{lang==='mr'?'कोणताही महत्त्वाचा अपवाद नाही.':'No material exceptions.'}</td></tr>:attention.map(s=><tr key={s.school_id}><td>{s.udise_code}</td><td>{lang==='mr'?s.school_name_mr:s.school_name_en}</td><td>{lang==='mr'?`${s.block_name_mr||''} / ${s.cluster_name_mr||''}`:`${s.block_name_en||''} / ${s.cluster_name_en||''}`}</td><td><span className={`status ${s.status.toLowerCase()}`}>{statusLabel(s.status)}</span></td><td>{s.coverage_pct}%</td><td className={s.exceptions?'qty-out':'qty-in'}>{s.exceptions}</td><td className={s.low_stock_items?'qty-out':'qty-in'}>{s.low_stock_items}</td></tr>)}
      </tbody></table></div></section>
    {message&&<div className="notice">{message}</div>}
  </main>
}