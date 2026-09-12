import React, { useState } from 'react';
import { standaloneLogin } from '../auth';

export default function StandaloneLogin({onLoggedIn}:{onLoggedIn:()=>void}){
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);

  async function submit(e:React.FormEvent){
    e.preventDefault(); setMessage(''); setBusy(true);
    try{
      await standaloneLogin(username,password);
      onLoggedIn();
    }catch(err:any){
      setMessage(err?.message || 'Login failed');
    }finally{setBusy(false)}
  }

  return <div style={{minHeight:'100vh',display:'grid',placeItems:'center',background:'#f3f6fb',padding:24,fontFamily:'system-ui'}}>
    <form onSubmit={submit} style={{width:'min(420px,100%)',background:'#fff',padding:28,borderRadius:16,boxShadow:'0 10px 30px rgba(0,0,0,.12)'}}>
      <div style={{fontSize:13,fontWeight:800,color:'#1e3a8a'}}>PM POSHAN • STANDALONE</div>
      <h2>Local Login / स्थानिक लॉगिन</h2>
      <label>Username</label>
      <input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" style={{width:'100%',boxSizing:'border-box',padding:10,margin:'6px 0 14px'}} />
      <label>Password</label>
      <input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" style={{width:'100%',boxSizing:'border-box',padding:10,margin:'6px 0 14px'}} />
      <button disabled={busy||!username.trim()||!password} style={{padding:'10px 18px',fontWeight:700}}>{busy?'Signing in…':'Login'}</button>
      {message && <p style={{color:'#b91c1c'}}>{message}</p>}
    </form>
  </div>
}
