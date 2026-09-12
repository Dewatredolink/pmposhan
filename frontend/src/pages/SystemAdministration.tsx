import { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../auth';
import type { Lang } from '../i18n/translations';

type Props={lang:Lang};
type School={id:string;name_en:string;name_mr:string;udise_code:string};
type UserRow={id:string;username:string;display_name?:string;role:string;active:boolean;school_ids:string[];school_access?:{school_id:string;name_en:string;name_mr:string}[];last_login_at?:string|null};
type DeviceInfo={installation_id:string;app_version:string;schema_version:number;data_dir:string;license:any};
type GovernmentStandard={
  ok:boolean;
  imported:boolean;
  source:{authority:string;scheme:string;gr_number:string;gr_date:string;effective_from:string;basis:string};
  imported_metadata?:any;
  active_ingredients:number;
  active_menus:number;
  menus_standardized:number;
  government_recipe_rows:number;
  oil_inventory_unit?:string|null;
  norms:{
    class_1_5:{rice_g:number;pulse_g:number;vegetables_g:number;oil_g:number};
    class_6_8:{rice_g:number;pulse_g:number;vegetables_g:number;oil_g:number};
  };
};
type Tab='users'|'device'|'masters';

async function jsonReq(path:string,opts?:RequestInit){
  const r=await apiFetch(path,opts);
  const body=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(body.detail||JSON.stringify(body)||`HTTP ${r.status}`);
  return body;
}

export default function SystemAdministration({lang}:Props){
 const mr=lang==='mr';
 const [tab,setTab]=useState<Tab>('users');
 const [users,setUsers]=useState<UserRow[]>([]);
 const [schools,setSchools]=useState<School[]>([]);
 const [device,setDevice]=useState<DeviceInfo|null>(null);
 const [government,setGovernment]=useState<GovernmentStandard|null>(null);
 const [msg,setMsg]=useState('');
 const [err,setErr]=useState('');
 const [busy,setBusy]=useState(false);
 const [form,setForm]=useState({username:'',display_name:'',password:'',role:'HEADMASTER',school_ids:[] as string[],preferred_language:'mr'});
 const [edit,setEdit]=useState<UserRow|null>(null);
 const [resetFor,setResetFor]=useState<UserRow|null>(null);
 const [resetPassword,setResetPassword]=useState('');

 const reload=async()=>{
   try{
     setErr('');
     const [u,s,d,g]=await Promise.all([
       jsonReq('/admin/users'),
       jsonReq('/schools'),
       jsonReq('/admin/device'),
       jsonReq('/admin/government-standard'),
     ]);
     setUsers(u);setSchools(s);setDevice(d);setGovernment(g);
   }catch(e){setErr(String(e))}
 };
 useEffect(()=>{void reload()},[]);

 const roleLabel=(r:string)=>r==='SYSTEM_ADMIN'?(mr?'सिस्टम प्रशासक':'System Admin'):r==='HEADMASTER'?(mr?'मुख्याध्यापक':'Headmaster'):(mr?'शिक्षक':'Teacher');
 const schoolMap=useMemo(()=>Object.fromEntries(schools.map(s=>[s.id,s])),[schools]);
 const toggleSchool=(id:string,current:string[],set:(v:string[])=>void)=>set(current.includes(id)?current.filter(x=>x!==id):[...current,id]);
 const clearMessages=()=>{setErr('');setMsg('')};

 const createUser=async()=>{
   try{
     clearMessages();setBusy(true);
     await jsonReq('/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form)});
     setForm({username:'',display_name:'',password:'',role:'HEADMASTER',school_ids:[],preferred_language:'mr'});
     setMsg(mr?'वापरकर्ता तयार केला':'User account created');
     await reload();
   }catch(e){setErr(String(e))}finally{setBusy(false)}
 };
 const saveEdit=async()=>{
   if(!edit)return;
   try{
     clearMessages();setBusy(true);
     await jsonReq(`/admin/users/${edit.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:edit.display_name||'',role:edit.role,active:edit.active,school_ids:edit.school_ids})});
     setEdit(null);setMsg(mr?'वापरकर्ता अद्ययावत केला':'User updated');await reload();
   }catch(e){setErr(String(e))}finally{setBusy(false)}
 };
 const toggleActive=async(u:UserRow)=>{
   try{
     clearMessages();setBusy(true);
     await jsonReq(`/admin/users/${u.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({active:!u.active})});
     setMsg(mr?'स्थिती बदलली':'Account status updated');await reload();
   }catch(e){setErr(String(e))}finally{setBusy(false)}
 };
 const doReset=async()=>{
   if(!resetFor)return;
   try{
     clearMessages();setBusy(true);
     await jsonReq(`/admin/users/${resetFor.id}/reset-password`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:resetPassword})});
     setResetFor(null);setResetPassword('');setMsg(mr?'पासवर्ड रीसेट केला':'Password reset');
   }catch(e){setErr(String(e))}finally{setBusy(false)}
 };
 const restoreMasters=async()=>{
   if(!confirm(mr?'मानक साहित्य व मेनू यादी पुनर्संचयित करायची? विद्यमान कोड हटवले जाणार नाहीत.':'Restore the standard ingredient and menu lists? Existing coded rows will not be deleted.'))return;
   try{
     clearMessages();setBusy(true);
     const r=await jsonReq('/admin/restore-standard-masters',{method:'POST'});
     setMsg(mr?`पुनर्संचयित पूर्ण: साहित्य ${r.ingredients_total}, मेनू ${r.menus_total}`:`Restore complete: ${r.ingredients_total} ingredients and ${r.menus_total} menus available`);
     await reload();
   }catch(e){setErr(String(e))}finally{setBusy(false)}
 };
 const importGovernmentStandard=async()=>{
   if(!confirm(mr?'महाराष्ट्र शासन PM POSHAN प्रति-विद्यार्थी प्रमाण आयात/अद्ययावत करायचे? बदलापूर्वी आपोआप बॅकअप घेतला जाईल.':'Import/update the Maharashtra Government PM POSHAN per-student standards? A backup will be created automatically before changes.'))return;
   try{
     clearMessages();setBusy(true);
     const r=await jsonReq('/admin/government-standard/import',{method:'POST'});
     setGovernment(r);
     const backup=(r.backup_created||'').split(/[\\/]/).pop();
     setMsg(mr?`शासकीय प्रमाण अद्ययावत झाले. ${r.menus_standardized} मेनू, ${r.government_recipe_rows} recipe rows. बॅकअप: ${backup}`:`Government standards updated: ${r.menus_standardized} menus, ${r.government_recipe_rows} recipe rows. Backup: ${backup}`);
     await reload();
   }catch(e){setErr(String(e))}finally{setBusy(false)}
 };
 const copyActivationRequest=async()=>{
   if(!device)return;
   const request={product:'PM_POSHAN',request_type:'DEVICE_ACTIVATION',installation_id:device.installation_id,app_version:device.app_version,current_license:device.license?.license?.license_id||null,udise:device.license?.license?.udise||schools[0]?.udise_code||null};
   await navigator.clipboard.writeText(JSON.stringify(request,null,2));
   setMsg(mr?'डिव्हाइस विनंती कॉपी केली':'Device authorization request copied');
 };

 const userForm=(editing:boolean)=>{
   const data:any=editing?edit:form;if(!data)return null;
   const setData=(next:any)=>editing?setEdit(next):setForm(next);
   return <div className="master-form">
     {!editing&&<label>{mr?'यूजर आयडी':'User ID'}<input value={data.username} onChange={e=>setData({...data,username:e.target.value})}/></label>}
     <label>{mr?'नाव':'Display Name'}<input value={data.display_name||''} onChange={e=>setData({...data,display_name:e.target.value})}/></label>
     {!editing&&<label>{mr?'तात्पुरता पासवर्ड':'Initial Password'}<input type="password" value={data.password} onChange={e=>setData({...data,password:e.target.value})} placeholder={mr?'किमान 10 अक्षरे':'Minimum 10 characters'}/></label>}
     <label>{mr?'भूमिका':'Role'}<select value={data.role} onChange={e=>setData({...data,role:e.target.value})}><option value="HEADMASTER">Headmaster / मुख्याध्यापक</option><option value="TEACHER">Teacher / शिक्षक</option><option value="SYSTEM_ADMIN">System Admin / सिस्टम प्रशासक</option></select></label>
     {editing&&<label className="checkline"><input type="checkbox" checked={!!data.active} onChange={e=>setData({...data,active:e.target.checked})}/>{mr?'खाते सक्रिय':'Account active'}</label>}
     {data.role!=='SYSTEM_ADMIN'&&<div style={{gridColumn:'1 / -1'}}><b>{mr?'शाळा प्रवेश':'School access'}</b><div className="check-grid">{schools.map(s=><label className="checkline" key={s.id}><input type="checkbox" checked={(data.school_ids||[]).includes(s.id)} onChange={()=>toggleSchool(s.id,data.school_ids||[],v=>setData({...data,school_ids:v}))}/>{mr?s.name_mr:s.name_en} ({s.udise_code})</label>)}</div></div>}
     <button disabled={busy} onClick={editing?saveEdit:createUser}>{editing?(mr?'बदल जतन करा':'Save changes'):(mr?'वापरकर्ता तयार करा':'Create user')}</button>
     {editing&&<button className="secondary" onClick={()=>setEdit(null)}>{mr?'रद्द':'Cancel'}</button>}
   </div>
 };

 const normRow=(label:string,n:any)=><tr><td><b>{label}</b></td><td>{n.rice_g} g</td><td>{n.pulse_g} g</td><td>{n.vegetables_g} g</td><td>{n.oil_g} g</td></tr>;

 return <main className="content">
  <section className="panel">
   <h2>{mr?'सिस्टम प्रशासन':'System Administration'}</h2>
   <p>{mr?'वापरकर्ता खाती, डिव्हाइस परवाना, शासकीय PM POSHAN प्रमाण आणि मास्टर डेटा नियंत्रित करा.':'Manage local user accounts, device licensing, Government PM POSHAN standards and master recovery.'}</p>
   {err&&<div className="api-error">{err}</div>}{msg&&<div className="success-box">{msg}</div>}
   <div className="master-tabs">
    <button className={tab==='users'?'active':''} onClick={()=>setTab('users')}>{mr?'वापरकर्ता खाती':'User Accounts'}</button>
    <button className={tab==='device'?'active':''} onClick={()=>setTab('device')}>{mr?'डिव्हाइस व परवाना':'Device & License'}</button>
    <button className={tab==='masters'?'active':''} onClick={()=>setTab('masters')}>{mr?'मास्टर व शासकीय प्रमाण':'Masters & Govt Standards'}</button>
   </div>
  </section>

  {tab==='users'&&<>
   <section className="panel"><h3>{mr?'नवीन खाते तयार करा':'Create Headmaster / Teacher / Admin Account'}</h3>{userForm(false)}</section>
   <section className="panel"><h3>{mr?'वापरकर्ता यादी':'User Accounts'}</h3><div className="table-scroll"><table><thead><tr><th>{mr?'यूजर आयडी':'User ID'}</th><th>{mr?'नाव':'Name'}</th><th>{mr?'भूमिका':'Role'}</th><th>{mr?'शाळा':'School'}</th><th>{mr?'स्थिती':'Status'}</th><th>{mr?'शेवटचा लॉगिन':'Last Login'}</th><th></th></tr></thead><tbody>{users.map(u=><tr key={u.id}><td><b>{u.username}</b></td><td>{u.display_name||'—'}</td><td>{roleLabel(u.role)}</td><td>{u.role==='SYSTEM_ADMIN'?(mr?'सर्व शाळा':'All schools'):(u.school_ids||[]).map(id=>mr?schoolMap[id]?.name_mr:schoolMap[id]?.name_en).filter(Boolean).join(', ')||'—'}</td><td>{u.active?(mr?'सक्रिय':'Active'):(mr?'बंद':'Disabled')}</td><td>{u.last_login_at?new Date(u.last_login_at).toLocaleString():'—'}</td><td><button onClick={()=>setEdit({...u,school_ids:[...(u.school_ids||[])]})}>{mr?'संपादित':'Edit'}</button> <button onClick={()=>{setResetFor(u);setResetPassword('')}}>{mr?'पासवर्ड':'Password'}</button> <button onClick={()=>toggleActive(u)}>{u.active?(mr?'बंद करा':'Disable'):(mr?'सक्रिय करा':'Enable')}</button></td></tr>)}</tbody></table></div></section>
   {edit&&<section className="panel"><h3>{mr?'वापरकर्ता संपादित करा':'Edit User'}</h3>{userForm(true)}</section>}
   {resetFor&&<section className="panel"><h3>{mr?'पासवर्ड रीसेट':'Reset Password'} — {resetFor.username}</h3><div className="master-form"><label>{mr?'नवीन पासवर्ड':'New password'}<input type="password" value={resetPassword} onChange={e=>setResetPassword(e.target.value)} placeholder={mr?'किमान 10 अक्षरे':'Minimum 10 characters'}/></label><button disabled={busy} onClick={doReset}>{mr?'पासवर्ड बदला':'Reset password'}</button><button className="secondary" onClick={()=>setResetFor(null)}>{mr?'रद्द':'Cancel'}</button></div></section>}
  </>}

  {tab==='device'&&<section className="panel">
   <h3>{mr?'डिव्हाइस माहिती':'Device Authorization'}</h3>
   {device?<div className="summary-grid"><div><small>Installation ID</small><strong style={{wordBreak:'break-all'}}>{device.installation_id}</strong></div><div><small>{mr?'अॅप आवृत्ती':'App Version'}</small><strong>{device.app_version}</strong></div><div><small>{mr?'परवाना':'License'}</small><strong>{device.license?.active?'ACTIVE':'INACTIVE'} — {device.license?.reason}</strong></div><div><small>{mr?'परवाना आयडी':'License ID'}</small><strong>{device.license?.license?.license_id||'—'}</strong></div><div><small>{mr?'वैध पर्यंत':'Valid Until'}</small><strong>{device.license?.license?.valid_until||'—'}</strong></div><div><small>{mr?'डेटा फोल्डर':'Data Folder'}</small><strong style={{wordBreak:'break-all'}}>{device.data_dir}</strong></div></div>:<p>Loading…</p>}
   <p>{mr?'नवीन डिव्हाइस अधिकृत करण्यासाठी खालील विनंती कॉपी करा आणि License Authority Dashboard मध्ये पेस्ट करा. खाजगी signing key या शाळेच्या app मध्ये कधीही ठेवली जात नाही.':'For a new device, copy the authorization request and paste it into the separate License Authority Dashboard. The private signing key is never stored in the school application.'}</p>
   <button onClick={copyActivationRequest}>{mr?'डिव्हाइस विनंती कॉपी करा':'Copy Device Authorization Request'}</button>
  </section>}

  {tab==='masters'&&<>
   <section className="panel">
    <h3>{mr?'मानक साहित्य व मेनू पुनर्प्राप्त करा':'Restore Standard Ingredients & Menus'}</h3>
    <p>{mr?'मूळ demo seed मधून 22 साहित्य आणि 12 साप्ताहिक मेनू पुन्हा आणले जातील. Demo शाळा किंवा demo users तयार होणार नाहीत. विद्यमान साठा, शाळा आणि व्यवहार हटवले जाणार नाहीत.':'Restores the original 22 ingredient masters and 12 weekly menu masters from the PM POSHAN demo seed. It does not recreate demo schools or demo users, and it does not delete existing stock, schools or transactions.'}</p>
    <button disabled={busy} onClick={restoreMasters}>{mr?'मानक यादी पुनर्संचयित करा':'Restore Standard Master Lists'}</button>
   </section>

   <section className="panel">
    <div className="page-title"><div><h3>{mr?'महाराष्ट्र शासन PM POSHAN प्रमाण':'Maharashtra Government PM POSHAN Standard'}</h3><p>{mr?'प्रति विद्यार्थी प्रति भोजन मानक प्रमाण आणि मेनू recipe standards.':'Per-student, per-meal food norms and menu recipe standards.'}</p></div>{government&&<span className={`status ${government.imported?'verified':'low'}`}>{government.imported?(mr?'आयात केले':'IMPORTED'):(mr?'आयात बाकी':'NOT IMPORTED')}</span>}</div>
    {government?<>
      <div className="summary-grid">
       <div><small>{mr?'शासन':'Authority'}</small><strong>{government.source.authority}</strong></div>
       <div><small>GR</small><strong>{government.source.gr_number}</strong></div>
       <div><small>{mr?'GR दिनांक':'GR Date'}</small><strong>{government.source.gr_date}</strong></div>
       <div><small>{mr?'लागू दिनांक':'Effective From'}</small><strong>{government.source.effective_from}</strong></div>
       <div><small>{mr?'मानकीकृत मेनू':'Standardized Menus'}</small><strong>{government.menus_standardized} / 12</strong></div>
       <div><small>{mr?'शासकीय Recipe Rows':'Government Recipe Rows'}</small><strong>{government.government_recipe_rows}</strong></div>
       <div><small>{mr?'सक्रिय साहित्य':'Active Ingredients'}</small><strong>{government.active_ingredients}</strong></div>
       <div><small>{mr?'तेल साठा एकक':'Oil Inventory Unit'}</small><strong>{government.oil_inventory_unit||'—'}</strong></div>
      </div>
      <h4 style={{marginTop:20}}>{mr?'प्रति विद्यार्थी प्रमाण':'Per-student Quantity'}</h4>
      <div className="table-scroll"><table><thead><tr><th>{mr?'गट':'Student Group'}</th><th>{mr?'तांदूळ':'Rice'}</th><th>{mr?'डाळ/कडधान्य':'Pulse'}</th><th>{mr?'भाजीपाला':'Vegetables'}</th><th>{mr?'तेल':'Oil'}</th></tr></thead><tbody>{normRow(mr?'इ. 1 ते 5':'Class 1–5',government.norms.class_1_5)}{normRow(mr?'इ. 6 ते 8':'Class 6–8',government.norms.class_6_8)}</tbody></table></div>
      <p style={{marginTop:14}}><strong>{mr?'आधार':'Basis'}:</strong> {government.source.basis}</p>
      <button disabled={busy} onClick={importGovernmentStandard}>{government.imported?(mr?'शासकीय प्रमाण अद्ययावत करा':'Update Government Standards'):(mr?'शासकीय प्रमाण आयात करा':'Import Government Standards')}</button>
      <p className="tiny" style={{marginTop:10}}>{mr?'प्रत्येक आयात/अद्ययावत करण्यापूर्वी स्थानिक डेटाबेसचा स्वयंचलित बॅकअप घेतला जातो.':'An automatic local database backup is created before every import/update.'}</p>
    </>:<p>Loading…</p>}
   </section>
  </>}
 </main>;
}
