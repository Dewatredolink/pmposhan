import { useEffect, useState } from 'react';
import Dashboard from './pages/Dashboard';
import { Lang, t } from './i18n/translations';
import { apiFetch, keycloak, realmRoles } from './auth';
import './styles.css';

type MeResponse = {
  username: string;
  email?: string | null;
  roles: string[];
  school_access: { school_id: string | null; role: string; preferred_language: string }[];
};

export default function App(){
  const [lang,setLang] = useState<Lang>((localStorage.getItem('pmposhan.lang') as Lang) || 'mr');
  const [me,setMe] = useState<MeResponse | null>(null);
  const [apiError,setApiError] = useState('');

  useEffect(()=>localStorage.setItem('pmposhan.lang',lang),[lang]);
  useEffect(()=>{
    apiFetch('/me')
      .then(async r => {
        if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
        return r.json();
      })
      .then(data => {
        setMe(data);
        const preferred = data.school_access?.[0]?.preferred_language;
        if ((preferred === 'mr' || preferred === 'en') && !localStorage.getItem('pmposhan.lang')) {
          setLang(preferred);
        }
      })
      .catch(e => setApiError(String(e)));
  },[]);

  const tr=(k:keyof typeof t)=>t[k][lang];
  const nav:[keyof typeof t,string][]=[['dashboard','🏠'],['dailyMeal','🍲'],['stockReceipt','📦'],['stockRegister','📊'],['monthlyVerification','✅'],['reports','📄']];
  const roles = realmRoles().filter(r => ['TEACHER','HEADMASTER','CLUSTER_OFFICER','BLOCK_OFFICER','DISTRICT_OFFICER','SYSTEM_ADMIN'].includes(r));

  return <div className="app">
    <header>
      <div><h1>{tr('title')}</h1><p>{tr('subtitle')}</p></div>
      <div className="top-actions">
        <div className="userbox">
          <strong>{me?.username || keycloak.tokenParsed?.preferred_username || 'User'}</strong>
          <span>{roles.join(', ')}</span>
        </div>
        <div className="lang"><button className={lang==='mr'?'active':''} onClick={()=>setLang('mr')}>मराठी</button><button className={lang==='en'?'active':''} onClick={()=>setLang('en')}>English</button></div>
        <button className="logout" onClick={()=>keycloak.logout({redirectUri: window.location.origin})}>{lang==='mr'?'बाहेर पडा':'Logout'}</button>
      </div>
    </header>
    {apiError && <div className="api-error">API authentication error: {apiError}</div>}
    <div className="shell"><aside>{nav.map(([key,icon])=><button key={key}>{icon}<span>{tr(key)}</span></button>)}</aside><Dashboard lang={lang}/></div>
  </div>
}
