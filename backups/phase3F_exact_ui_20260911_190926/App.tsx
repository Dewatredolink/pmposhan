import { useEffect, useMemo, useState } from 'react';
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
import MasterData from './pages/MasterData';
import CustomReports from './pages/CustomReports';
import WorkbookRegisters from './pages/WorkbookRegisters';
import BrandingSettings from './pages/BrandingSettings';
import { Lang, t } from './i18n/translations';
import { apiFetch, keycloak, realmRoles } from './auth';
import './styles.css';
import './professional-ui.css';

type School = { id:string; code:string; udise_code:string; name_en:string; name_mr:string; village?:string|null; class_1_5_strength:number; class_6_8_strength:number };
type MeResponse = {username:string;email?:string|null;roles:string[];school_access:{school_id:string|null;school_name_en?:string|null;school_name_mr?:string|null;role:string;preferred_language:string}[]};
type Page='dashboard'|'schoolProfile'|'menuPlanner'|'dailyMeal'|'stockReceipt'|'stockRegister'|'stockControls'|'monthlyVerification'|'adminDashboard'|'schoolCalendar'|'masterData'|'customReports'|'workbookRegisters'|'reports'|'branding';

type NavItem={id:Page;icon:string;en:string;mr:string;adminOnly?:boolean;management?:boolean};
type NavGroup={en:string;mr:string;items:NavItem[]};

const groups:NavGroup[]=[
 {en:'OVERVIEW',mr:'आढावा',items:[{id:'dashboard',icon:'⌂',en:'Dashboard',mr:'मुख्य पृष्ठ'}]},
 {en:'SCHOOL OPERATIONS',mr:'शाळा कामकाज',items:[
   {id:'schoolCalendar',icon:'▣',en:'School Calendar',mr:'शाळा दिनदर्शिका'},
   {id:'menuPlanner',icon:'◉',en:'Menu Planner',mr:'दिवसनिहाय मेनू'},
   {id:'dailyMeal',icon:'◫',en:'Daily Meal Entry',mr:'दैनिक आहार नोंद'}]},
 {en:'FOOD & STOCK',mr:'आहार व साठा',items:[
   {id:'stockReceipt',icon:'↓',en:'Stock Receipt',mr:'साठा प्राप्ती'},
   {id:'stockRegister',icon:'▦',en:'Stock Register',mr:'साठा नोंदवही'},
   {id:'stockControls',icon:'✓',en:'Stock Controls',mr:'साठा नियंत्रण'},
   {id:'workbookRegisters',icon:'▤',en:'Registers & Ration',mr:'नोंदवही व राशन'}]},
 {en:'MONITORING & REPORTS',mr:'निरीक्षण व अहवाल',items:[
   {id:'monthlyVerification',icon:'◆',en:'Monthly Verification',mr:'मासिक पडताळणी'},
   {id:'adminDashboard',icon:'▥',en:'Administrative Dashboard',mr:'प्रशासकीय डॅशबोर्ड',management:true},
   {id:'reports',icon:'▧',en:'Reports',mr:'अहवाल'},
   {id:'customReports',icon:'⇩',en:'Custom Excel Reports',mr:'सानुकूल Excel अहवाल',management:true}]},
 {en:'ADMINISTRATION',mr:'प्रशासन',items:[
   {id:'schoolProfile',icon:'⌂',en:'School Profile',mr:'शाळा माहिती'},
   {id:'masterData',icon:'⚙',en:'Master Data',mr:'मास्टर डेटा',adminOnly:true},
   {id:'branding',icon:'◈',en:'Branding & Logos',mr:'ब्रँडिंग व लोगो',adminOnly:true}]}
];

export default function App(){
 const [lang,setLang]=useState<Lang>((localStorage.getItem('pmposhan.lang') as Lang)||'mr');
 const [me,setMe]=useState<MeResponse|null>(null);const [schools,setSchools]=useState<School[]>([]);const [schoolId,setSchoolId]=useState('');const [page,setPage]=useState<Page>('dashboard');const [apiError,setApiError]=useState('');const [navOpen,setNavOpen]=useState(false);const [brandTick,setBrandTick]=useState(0);
 useEffect(()=>localStorage.setItem('pmposhan.lang',lang),[lang]);
 useEffect(()=>{const h=()=>setBrandTick(x=>x+1);window.addEventListener('pmposhan-branding-changed',h);return()=>window.removeEventListener('pmposhan-branding-changed',h)},[]);
 useEffect(()=>{Promise.all([apiFetch('/me').then(async r=>{if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);return r.json()}),apiFetch('/schools').then(async r=>{if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);return r.json()})]).then(([meData,schoolData])=>{setMe(meData);setSchools(schoolData);if(schoolData[0])setSchoolId(schoolData[0].id);const preferred=meData.school_access?.[0]?.preferred_language;if((preferred==='mr'||preferred==='en')&&!localStorage.getItem('pmposhan.lang'))setLang(preferred)}).catch(e=>setApiError(String(e)))},[]);
 const roles=realmRoles().filter(r=>['TEACHER','HEADMASTER','CLUSTER_OFFICER','BLOCK_OFFICER','DISTRICT_OFFICER','SYSTEM_ADMIN'].includes(r));const isSystem=roles.includes('SYSTEM_ADMIN');const managementRoles=['HEADMASTER','CLUSTER_OFFICER','BLOCK_OFFICER','DISTRICT_OFFICER','SYSTEM_ADMIN'];const canManage=roles.some(r=>managementRoles.includes(r));
 const activeSchool=schools.find(s=>s.id===schoolId)||schools[0];
 const schoolLogo=localStorage.getItem('pmposhan.brand.schoolLogo')||'';const districtLogo=localStorage.getItem('pmposhan.brand.districtLogo')||'';const districtName=localStorage.getItem('pmposhan.brand.districtName')||'District / जिल्हा';const departmentName=localStorage.getItem('pmposhan.brand.departmentName')||'School Education & Sports Department';void brandTick;
 const visibleGroups=useMemo(()=>groups.map(g=>({...g,items:g.items.filter(i=>!i.adminOnly||isSystem).filter(i=>!i.management||canManage)})).filter(g=>g.items.length),[isSystem,canManage]);
 function go(p:Page){setPage(p);setNavOpen(false)}
 let body:any;if(page==='dashboard')body=<Dashboard lang={lang} schoolId={schoolId}/>;else if(page==='schoolProfile')body=<SchoolProfile lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='menuPlanner')body=<MenuPlanner lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='dailyMeal')body=<DailyMeal lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='stockReceipt')body=<StockReceipt lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='stockRegister')body=<StockRegister lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='stockControls')body=<StockControls lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='monthlyVerification')body=<HierarchyDashboard lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='adminDashboard')body=<AdminDashboard lang={lang}/>;else if(page==='schoolCalendar')body=<SchoolCalendar lang={lang} schoolId={schoolId}/>;else if(page==='masterData')body=<MasterData lang={lang}/>;else if(page==='customReports')body=<CustomReports lang={lang}/>;else if(page==='workbookRegisters')body=<WorkbookRegisters lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='branding')body=<BrandingSettings lang={lang}/>;else body=<Reports lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
 return <div className="app professional-ui">
   <header className="gov-header">
    <button className="mobile-menu" onClick={()=>setNavOpen(v=>!v)}>☰</button>
    <div className="brand-lockup"><div className="brand-emblem">◉</div><div><h1>PM POSHAN</h1><p>{lang==='mr'?'प्रधानमंत्री पोषण शक्ती निर्माण':'School Meal Management System'}</p></div></div>
    <div className="header-center"><strong>{lang==='mr'?'महाराष्ट्र शासन':'Government of Maharashtra'}</strong><span>{departmentName}</span></div>
    <div className="header-right">
      <div className="org-logos">{districtLogo?<img src={districtLogo} alt="District logo"/>:<span className="logo-fallback">जि.प.</span>}{schoolLogo?<img src={schoolLogo} alt="School logo"/>:<span className="logo-fallback">शाळा</span>}</div>
      <div className="lang"><button className={lang==='mr'?'active':''} onClick={()=>setLang('mr')}>मराठी</button><button className={lang==='en'?'active':''} onClick={()=>setLang('en')}>EN</button></div>
      <div className="userbox"><strong>{me?.username||keycloak.tokenParsed?.preferred_username||'User'}</strong><span>{roles.join(' • ')}</span></div>
      <button className="logout" onClick={()=>keycloak.logout({redirectUri:window.location.origin})}>{lang==='mr'?'बाहेर':'Logout'}</button>
    </div>
   </header>
   {apiError&&<div className="api-error">API authentication error: {apiError}</div>}
   <div className="shell professional-shell">
    <aside className={navOpen?'open':''}>
      <div className="school-brand-card"><div className="school-logo-wrap">{schoolLogo?<img src={schoolLogo}/>:<span>🏫</span>}</div><div><strong>{activeSchool?(lang==='mr'?activeSchool.name_mr:activeSchool.name_en):(lang==='mr'?'शाळा':'School')}</strong><small>{activeSchool?.udise_code?`UDISE: ${activeSchool.udise_code}`:''}</small><small>{districtName}</small></div></div>
      <nav>{visibleGroups.map(g=><div className="nav-group" key={g.en}><div className="nav-group-title">{lang==='mr'?g.mr:g.en}</div>{g.items.map(i=><button key={i.id} className={page===i.id?'active':''} onClick={()=>go(i.id)}><span className="nav-icon">{i.icon}</span><span>{lang==='mr'?i.mr:i.en}</span><b>›</b></button>)}</div>)}</nav>
      <div className="sidebar-footer"><span className="online-dot"></span>{lang==='mr'?'ऑनलाइन':'Online'}<small>PM POSHAN • 2026</small></div>
    </aside>
    <section className="main-stage"><div className="context-bar"><div><strong>{activeSchool?(lang==='mr'?activeSchool.name_mr:activeSchool.name_en):(lang==='mr'?'शाळा निवडा':'Select school')}</strong><span>{districtName}</span></div>{schools.length>1&&<select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option value={s.id} key={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select>}</div>{body}</section>
   </div>
 </div>
}
