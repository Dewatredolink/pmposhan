import { useEffect, useMemo, useState } from 'react';
import { apiFetch, realmRoles } from '../auth';
import { Lang } from '../i18n/translations';

type School={id:string;name_en:string;name_mr:string};
type Props={lang:Lang;schools:School[];schoolId:string;setSchoolId:(id:string)=>void};
type Summary={total_schools:number;returns_generated:number;missing_returns:number;status_counts:Record<string,number>;total_meals:number;exception_returns:number};
type ScopeSchool={school_id:string;school_name_en:string;school_name_mr:string;cluster_name_en?:string|null;cluster_name_mr?:string|null;block_name_en?:string|null;block_name_mr?:string|null;district_name_en?:string|null;district_name_mr?:string|null};
type ReturnRow={id:string;school_id:string;school_name_en:string;school_name_mr:string;udise_code:string;cluster_name_en?:string|null;cluster_name_mr?:string|null;block_name_en?:string|null;block_name_mr?:string|null;district_name_en?:string|null;district_name_mr?:string|null;year:number;month:number;recorded_days:number;verified_days:number;incomplete_days:number;attendance_class_1_5:number;attendance_class_6_8:number;meals_class_1_5:number;meals_class_6_8:number;total_meals:number;tasting_exception_days:number;hygiene_exception_days:number;status:string;return_reason?:string|null;submitted_by_username?:string|null;cluster_reviewed_by?:string|null;block_approved_by?:string|null};

const now=new Date();

export default function HierarchyDashboard({lang,schools,schoolId,setSchoolId}:Props){
  const [year,setYear]=useState(now.getFullYear());
  const [month,setMonth]=useState(now.getMonth()+1);
  const [rows,setRows]=useState<ReturnRow[]>([]);
  const [summary,setSummary]=useState<Summary|null>(null);
  const [scope,setScope]=useState<ScopeSchool[]>([]);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  const roles=realmRoles();
  const canGenerate=roles.includes('HEADMASTER')||roles.includes('SYSTEM_ADMIN');
  const canClusterReview=roles.includes('CLUSTER_OFFICER')||roles.includes('SYSTEM_ADMIN');
  const canBlockApprove=roles.includes('BLOCK_OFFICER')||roles.includes('SYSTEM_ADMIN');
  const canReturn=roles.includes('CLUSTER_OFFICER')||roles.includes('BLOCK_OFFICER')||roles.includes('SYSTEM_ADMIN');

  async function load(){
    try{
      setMessage('');
      const [r1,r2,r3]=await Promise.all([
        apiFetch(`/monthly-returns?year=${year}&month=${month}`),
        apiFetch(`/monthly-returns/summary?year=${year}&month=${month}`),
        apiFetch('/hierarchy/scope'),
      ]);
      for(const r of [r1,r2,r3]) if(!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      setRows(await r1.json()); setSummary(await r2.json()); const sd=await r3.json(); setScope(sd.schools||[]);
    }catch(e){setMessage(String(e));}
  }
  useEffect(()=>{void load();},[year,month]);

  async function act(path:string, body:any={remarks:null}){
    try{
      setBusy(true); setMessage('');
      const r=await apiFetch(path,{method:'POST',body:JSON.stringify(body)});
      if(!r.ok) throw new Error(`${r.status} ${await r.text()}`);
      await load();
      setMessage(lang==='mr'?'कारवाई यशस्वी.':'Action completed successfully.');
    }catch(e){setMessage(String(e));}finally{setBusy(false);}
  }
  async function generate(){ if(!schoolId)return; await act('/monthly-returns/generate',{school_id:schoolId,year,month}); }
  async function returnForCorrection(id:string){
    const reason=window.prompt(lang==='mr'?'परत पाठवण्याचे कारण लिहा':'Enter reason for returning this monthly return');
    if(!reason)return; await act(`/monthly-returns/${id}/return`,{remarks:reason});
  }

  const selected=useMemo(()=>scope.find(x=>x.school_id===schoolId),[scope,schoolId]);
  const statusLabel=(s:string)=>({
    DRAFT:lang==='mr'?'मसुदा':'Draft',
    SUBMITTED:lang==='mr'?'सादर':'Submitted',
    CLUSTER_REVIEWED:lang==='mr'?'क्लस्टर पडताळले':'Cluster Reviewed',
    BLOCK_APPROVED:lang==='mr'?'ब्लॉक मंजूर':'Block Approved',
    RETURNED:lang==='mr'?'दुरुस्तीसाठी परत':'Returned',
  } as Record<string,string>)[s]||s;

  return <main className="content">
    <div className="page-title"><div><h2>{lang==='mr'?'प्रशासकीय श्रेणी व मासिक परतावा':'Hierarchy & Monthly Returns'}</h2><p>{lang==='mr'?'शाळा → क्लस्टर → ब्लॉक → जिल्हा कार्यप्रवाह, अपवाद आणि मंजुरी स्थिती.':'School → Cluster → Block → District workflow, exceptions and approval status.'}</p></div><button className="secondary standalone" onClick={load}>{lang==='mr'?'रीफ्रेश':'Refresh'}</button></div>

    <section className="panel form-grid compact">
      <label>{lang==='mr'?'शाळा':'School'}<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option key={s.id} value={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></label>
      <div className="month-controls"><label>{lang==='mr'?'वर्ष':'Year'}<input type="number" min="2000" max="2200" value={year} onChange={e=>setYear(Number(e.target.value))}/></label><label>{lang==='mr'?'महिना':'Month'}<select value={month} onChange={e=>setMonth(Number(e.target.value))}>{Array.from({length:12},(_,i)=><option key={i+1} value={i+1}>{i+1}</option>)}</select></label></div>
    </section>

    {selected&&<section className="panel"><h3>{lang==='mr'?'निवडलेल्या शाळेची प्रशासकीय श्रेणी':'Selected School Hierarchy'}</h3><div className="hierarchy-path"><span>{lang==='mr'?selected.school_name_mr:selected.school_name_en}</span><b>→</b><span>{lang==='mr'?selected.cluster_name_mr:selected.cluster_name_en}</span><b>→</b><span>{lang==='mr'?selected.block_name_mr:selected.block_name_en}</span><b>→</b><span>{lang==='mr'?selected.district_name_mr:selected.district_name_en}</span></div></section>}

    <div className="cards report-cards">
      <div className="card"><span>{lang==='mr'?'कार्यक्षेत्रातील शाळा':'Schools in Scope'}</span><strong>{summary?.total_schools??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'परतावे तयार':'Returns Generated'}</span><strong>{summary?.returns_generated??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'परतावा बाकी':'Missing Returns'}</span><strong>{summary?.missing_returns??0}</strong></div>
      <div className="card"><span>{lang==='mr'?'अपवाद असलेले परतावे':'Exception Returns'}</span><strong>{summary?.exception_returns??0}</strong></div>
    </div>

    <section className="panel"><div className="page-title"><div><h3>{lang==='mr'?'शाळेचा मासिक परतावा':'School Monthly Return'}</h3><p>{lang==='mr'?'फक्त पडताळलेले दैनिक रेकॉर्ड एकत्रित केले जातात.':'Only verified daily operations are aggregated.'}</p></div>{canGenerate&&<button className="primary standalone" disabled={busy||!schoolId} onClick={generate}>{lang==='mr'?'तयार / पुन्हा तयार करा':'Generate / Refresh Return'}</button>}</div>
      <div className="table-wrap"><table><thead><tr><th>{lang==='mr'?'शाळा':'School'}</th><th>{lang==='mr'?'स्थिती':'Status'}</th><th>{lang==='mr'?'नोंद दिवस':'Recorded Days'}</th><th>{lang==='mr'?'पडताळलेले दिवस':'Verified Days'}</th><th>{lang==='mr'?'अपूर्ण':'Incomplete'}</th><th>{lang==='mr'?'एकूण भोजन':'Total Meals'}</th><th>{lang==='mr'?'अपवाद':'Exceptions'}</th><th>{lang==='mr'?'कारवाई':'Action'}</th></tr></thead><tbody>
        {rows.length===0?<tr><td colSpan={8}>{lang==='mr'?'या कालावधीसाठी परतावा तयार केलेला नाही.':'No monthly return generated for this period.'}</td></tr>:rows.map(x=>{
          const exceptions=x.incomplete_days+x.tasting_exception_days+x.hygiene_exception_days;
          return <tr key={x.id}><td><strong>{lang==='mr'?x.school_name_mr:x.school_name_en}</strong><div className="tiny">UDISE: {x.udise_code}</div></td><td><span className={`status ${x.status.toLowerCase()}`}>{statusLabel(x.status)}</span>{x.return_reason&&<div className="tiny qty-out">{x.return_reason}</div>}</td><td>{x.recorded_days}</td><td>{x.verified_days}</td><td className={x.incomplete_days?'qty-out':''}>{x.incomplete_days}</td><td>{x.total_meals}</td><td className={exceptions?'qty-out':'qty-in'}>{exceptions}</td><td><div className="row-actions">
            {canGenerate&&x.status==='DRAFT'&&<button className="table-button" disabled={busy} onClick={()=>act(`/monthly-returns/${x.id}/submit`,{remarks:null})}>{lang==='mr'?'सादर करा':'Submit'}</button>}
            {canGenerate&&x.status==='RETURNED'&&<button className="table-button" disabled={busy} onClick={()=>act(`/monthly-returns/${x.id}/submit`,{remarks:null})}>{lang==='mr'?'पुन्हा सादर':'Resubmit'}</button>}
            {canClusterReview&&x.status==='SUBMITTED'&&<button className="table-button" disabled={busy} onClick={()=>act(`/monthly-returns/${x.id}/cluster-review`,{remarks:null})}>{lang==='mr'?'क्लस्टर पडताळणी':'Cluster Review'}</button>}
            {canBlockApprove&&x.status==='CLUSTER_REVIEWED'&&<button className="table-button" disabled={busy} onClick={()=>act(`/monthly-returns/${x.id}/block-approve`,{remarks:null})}>{lang==='mr'?'ब्लॉक मंजुरी':'Block Approve'}</button>}
            {canReturn&&['SUBMITTED','CLUSTER_REVIEWED'].includes(x.status)&&<button className="table-button danger" disabled={busy} onClick={()=>returnForCorrection(x.id)}>{lang==='mr'?'परत पाठवा':'Return'}</button>}
          </div></td></tr>
        })}
      </tbody></table></div>
    </section>

    <section className="panel"><h3>{lang==='mr'?'स्थिती सारांश':'Workflow Status Summary'}</h3><div className="status-grid">{['DRAFT','SUBMITTED','CLUSTER_REVIEWED','BLOCK_APPROVED','RETURNED'].map(s=><div key={s}><span>{statusLabel(s)}</span><strong>{summary?.status_counts?.[s]??0}</strong></div>)}</div></section>
    {message&&<div className="notice">{message}</div>}
  </main>
}
