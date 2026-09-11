import { useEffect, useState } from 'react';
import Dashboard from './pages/Dashboard';
import DailyMeal from './pages/DailyMeal';
import MenuPlanner from './pages/MenuPlanner';
import SchoolProfile from './pages/SchoolProfile';
import StockReceipt from './pages/StockReceipt';
import StockRegister from './pages/StockRegister';
import StockControls from './pages/StockControls';
import Reports from './pages/Reports';
import HierarchyDashboard from './pages/HierarchyDashboard';
import AdminDashboard from './pages/AdminDashboard';
import SchoolCalendar from './pages/SchoolCalendar';
import { Lang, t } from './i18n/translations';
import { apiFetch, keycloak, realmRoles } from './auth';
import './styles.css';

type School = { id:string; code:string; udise_code:string; name_en:string; name_mr:string; village?:string|null; class_1_5_strength:number; class_6_8_strength:number };
type MeResponse = {
  username: string;
  email?: string | null;
  roles: string[];
  school_access: { school_id: string | null; school_name_en?:string|null; school_name_mr?:string|null; role: string; preferred_language: string }[];
};

type Page = 'dashboard'|'schoolProfile'|'menuPlanner'|'dailyMeal'|'stockReceipt'|'stockRegister'|'stockControls'|'monthlyVerification'|'adminDashboard'|'schoolCalendar'|'reports';

export default function App(){
  const [lang,setLang] = useState<Lang>((localStorage.getItem('pmposhan.lang') as Lang) || 'mr');
  const [me,setMe] = useState<MeResponse | null>(null);
  const [schools,setSchools] = useState<School[]>([]);
  const [schoolId,setSchoolId] = useState('');
  const [page,setPage] = useState<Page>('dashboard');
  const [apiError,setApiError] = useState('');

  useEffect(()=>localStorage.setItem('pmposhan.lang',lang),[lang]);
  useEffect(()=>{
    Promise.all([
      apiFetch('/me').then(async r=>{if(!r.ok) throw new Error(`${r.status} ${await r.text()}`); return r.json()}),
      apiFetch('/schools').then(async r=>{if(!r.ok) throw new Error(`${r.status} ${await r.text()}`); return r.json()}),
    ]).then(([meData,schoolData])=>{
      setMe(meData); setSchools(schoolData); if(schoolData[0]) setSchoolId(schoolData[0].id);
      const preferred = meData.school_access?.[0]?.preferred_language;
      if ((preferred === 'mr' || preferred === 'en') && !localStorage.getItem('pmposhan.lang')) setLang(preferred);
    }).catch(e => setApiError(String(e)));
  },[]);

  const tr=(k:keyof typeof t)=>t[k][lang];
  const navBase:[Page,keyof typeof t,string][]=[['dashboard','dashboard','🏠'],['schoolProfile','schoolProfile','🏫'],['menuPlanner','menuPlanner','📅'],['dailyMeal','dailyMeal','🍲'],['stockReceipt','stockReceipt','📦'],['stockRegister','stockRegister','📊'],['stockControls','stockControls','🧾'],['monthlyVerification','monthlyVerification','✅'],['adminDashboard','adminDashboard','📈'],['schoolCalendar','schoolCalendar','🗓️'],['reports','reports','📄']];
  const adminRoles=['HEADMASTER','CLUSTER_OFFICER','BLOCK_OFFICER','DISTRICT_OFFICER','SYSTEM_ADMIN'];
  const nav=navBase.filter(([id])=>id!=='adminDashboard'||realmRoles().some(r=>adminRoles.includes(r))); 
  const roles = realmRoles().filter(r => ['TEACHER','HEADMASTER','CLUSTER_OFFICER','BLOCK_OFFICER','DISTRICT_OFFICER','SYSTEM_ADMIN'].includes(r));

  const placeholder = (title:string,phase:string)=><main className="content"><section className="panel"><h2>{title}</h2><p>{lang==='mr'?`${phase} मध्ये हा मॉड्यूल जोडला जाईल.`:`This module will be added in ${phase}.`}</p></section></main>;
  let body:any;
  if(page==='dashboard') body=<Dashboard lang={lang} schoolId={schoolId}/>;
  else if(page==='schoolProfile') body=<SchoolProfile lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
  else if(page==='menuPlanner') body=<MenuPlanner lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
  else if(page==='dailyMeal') body=<DailyMeal lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
  else if(page==='stockReceipt') body=<StockReceipt lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
  else if(page==='stockRegister') body=<StockRegister lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
  else if(page==='stockControls') body=<StockControls lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
  else if(page==='monthlyVerification') body=<HierarchyDashboard lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
  else if(page==='adminDashboard') body=<AdminDashboard lang={lang}/>;
  else if(page==='schoolCalendar') body=<SchoolCalendar lang={lang} schoolId={schoolId}/>;
  else body=<Reports lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;

  return <div className="app">
    <header>
      <div><h1>{tr('title')}</h1><p>{tr('subtitle')}</p></div>
      <div className="top-actions">
        <div className="userbox"><strong>{me?.username || keycloak.tokenParsed?.preferred_username || 'User'}</strong><span>{roles.join(', ')}</span></div>
        <div className="lang"><button className={lang==='mr'?'active':''} onClick={()=>setLang('mr')}>मराठी</button><button className={lang==='en'?'active':''} onClick={()=>setLang('en')}>English</button></div>
        <button className="logout" onClick={()=>keycloak.logout({redirectUri: window.location.origin})}>{lang==='mr'?'बाहेर पडा':'Logout'}</button>
      </div>
    </header>
    {apiError && <div className="api-error">API authentication error: {apiError}</div>}
    <div className="shell"><aside>{nav.map(([id,key,icon])=><button className={page===id?'active':''} key={id} onClick={()=>setPage(id)}>{icon}<span>{tr(key)}</span></button>)}</aside>{body}</div>
  </div>
}
