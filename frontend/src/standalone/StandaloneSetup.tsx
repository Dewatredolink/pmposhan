import React, { useState } from 'react';
import { publicApiFetch } from '../auth';

export async function fetchStandaloneSetupStatus(){
  const r=await publicApiFetch('/setup/status');
  if(!r.ok) throw new Error(`Setup status HTTP ${r.status}`);
  return r.json();
}

export default function StandaloneSetup({onCreated}:{onCreated:()=>void}){
  const [username,setUsername]=useState('system.admin');
  const [displayName,setDisplayName]=useState('System Admin');
  const [password,setPassword]=useState('');
  const [confirm,setConfirm]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);

  async function submit(e:React.FormEvent){
    e.preventDefault(); setMessage('');
    if(password.length<12){setMessage('Password must be at least 12 characters.');return}
    if(password!==confirm){setMessage('Passwords do not match.');return}
    setBusy(true);
    try{
      const r=await publicApiFetch('/setup/admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password,display_name:displayName})});
      const body=await r.json().catch(()=>({}));
      if(!r.ok) throw new Error(body.detail||`Setup HTTP ${r.status}`);
      onCreated();
    }catch(err:any){setMessage(err?.message||'Setup failed')}finally{setBusy(false)}
  }

  return <div style={{minHeight:'100vh',display:'grid',placeItems:'center',background:'#f3f6fb',padding:24,fontFamily:'system-ui'}}>
    <form onSubmit={submit} style={{width:'min(460px,100%)',background:'#fff',padding:28,borderRadius:16,boxShadow:'0 10px 30px rgba(0,0,0,.12)'}}>
      <div style={{fontSize:13,fontWeight:800,color:'#1e3a8a'}}>PM POSHAN • FIRST RUN</div>
      <h2>Create Local Administrator</h2>
      <p>प्रथम वापरासाठी स्थानिक प्रशासक खाते तयार करा.</p>
      <label>Username</label><input value={username} onChange={e=>setUsername(e.target.value)} style={{width:'100%',boxSizing:'border-box',padding:10,margin:'6px 0 12px'}} />
      <label>Display name</label><input value={displayName} onChange={e=>setDisplayName(e.target.value)} style={{width:'100%',boxSizing:'border-box',padding:10,margin:'6px 0 12px'}} />
      <label>Password</label><input type="password" value={password} onChange={e=>setPassword(e.target.value)} style={{width:'100%',boxSizing:'border-box',padding:10,margin:'6px 0 12px'}} />
      <label>Confirm password</label><input type="password" value={confirm} onChange={e=>setConfirm(e.target.value)} style={{width:'100%',boxSizing:'border-box',padding:10,margin:'6px 0 14px'}} />
      <button disabled={busy||!username.trim()||!password} style={{padding:'10px 18px',fontWeight:700}}>{busy?'Creating…':'Create administrator'}</button>
      {message&&<p style={{color:'#b91c1c'}}>{message}</p>}
    </form>
  </div>
}
