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
import HelpManual from './pages/HelpManual';
import SystemAdministration from './pages/SystemAdministration';
import { Lang } from './i18n/translations';
import { apiFetch, isStandaloneMode, keycloak, realmRoles, standaloneLogout } from './auth';
import './styles.css';
import './professional-ui.css';

type School = { id:string; code:string; udise_code:string; name_en:string; name_mr:string; village?:string|null; class_1_5_strength:number; class_6_8_strength:number };
type MeResponse = {username:string;email?:string|null;roles:string[];school_access:{school_id:string|null;school_name_en?:string|null;school_name_mr?:string|null;role:string;preferred_language:string}[]};
type Page='dashboard'|'schoolProfile'|'menuPlanner'|'dailyMeal'|'stockReceipt'|'stockRegister'|'stockControls'|'monthlyVerification'|'adminDashboard'|'schoolCalendar'|'masterData'|'customReports'|'workbookRegisters'|'reports'|'branding'|'help'|'systemAdministration';
type NavItem={id:Page;icon:string;en:string;mr:string;adminOnly?:boolean;management?:boolean};
type NavGroup={en:string;mr:string;items:NavItem[]};
const groups:NavGroup[]=[
 {en:'',mr:'',items:[{id:'dashboard',icon:'⌂',en:'Dashboard',mr:'मुख्य पृष्ठ'}]},
 {en:'SCHOOL OPERATIONS',mr:'शाळा कामकाज',items:[{id:'schoolCalendar',icon:'▣',en:'School Calendar',mr:'शाळा दिनदर्शिका'},{id:'dailyMeal',icon:'☑',en:'Daily Meal Entry',mr:'दैनिक आहार नोंद'},{id:'menuPlanner',icon:'◉',en:'Menu Planner',mr:'दिवसनिहाय मेनू'},{id:'workbookRegisters',icon:'▤',en:'Ration & Requirements',mr:'राशन व गरज'}]},
 {en:'FOOD & STOCK',mr:'आहार व साठा',items:[{id:'stockReceipt',icon:'↓',en:'Stock Receipt',mr:'साठा प्राप्ती'},{id:'stockRegister',icon:'⬡',en:'Stock Management',mr:'साठा व्यवस्थापन'},{id:'stockControls',icon:'✓',en:'Stock Controls',mr:'साठा नियंत्रण'}]},
 {en:'MASTERS & MANAGEMENT',mr:'मास्टर्स व व्यवस्थापन',items:[{id:'masterData',icon:'▧',en:'Master Data',mr:'मास्टर डेटा',adminOnly:true},{id:'monthlyVerification',icon:'◆',en:'Monthly Verification',mr:'मासिक पडताळणी'},{id:'adminDashboard',icon:'▥',en:'Administrative Dashboard',mr:'प्रशासकीय डॅशबोर्ड',management:true},{id:'reports',icon:'▤',en:'Registers & Reports',mr:'नोंदवही व अहवाल'},{id:'customReports',icon:'▧',en:'Custom Excel Reports',mr:'सानुकूल Excel अहवाल',management:true}]},
 {en:'SETTINGS',mr:'सेटिंग्ज',items:[{id:'systemAdministration',icon:'⚿',en:'System Administration',mr:'सिस्टम प्रशासन',adminOnly:true},{id:'schoolProfile',icon:'⚙',en:'School Profile',mr:'शाळा माहिती'},{id:'help',icon:'?',en:'Help & User Manual',mr:'मदत व वापरकर्ता मार्गदर्शिका'},{id:'branding',icon:'◈',en:'Branding & Logos',mr:'ब्रँडिंग व लोगो',adminOnly:true}]}
];
export default function App(){
 const [lang,setLang]=useState<Lang>((localStorage.getItem('pmposhan.lang') as Lang)||'mr');const [me,setMe]=useState<MeResponse|null>(null);const [schools,setSchools]=useState<School[]>([]);const [schoolId,setSchoolId]=useState('');const [page,setPage]=useState<Page>('dashboard');const [apiError,setApiError]=useState('');const [navOpen,setNavOpen]=useState(false);const [brandTick,setBrandTick]=useState(0);
 useEffect(()=>localStorage.setItem('pmposhan.lang',lang),[lang]);useEffect(()=>{const h=()=>setBrandTick(x=>x+1);window.addEventListener('pmposhan-branding-changed',h);return()=>window.removeEventListener('pmposhan-branding-changed',h)},[]);useEffect(()=>{Promise.all([apiFetch('/me').then(async r=>{if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);return r.json()}),apiFetch('/schools').then(async r=>{if(!r.ok)throw new Error(`${r.status} ${await r.text()}`);return r.json()})]).then(([meData,schoolData])=>{setMe(meData);setSchools(schoolData);if(schoolData[0])setSchoolId(schoolData[0].id);const preferred=meData.school_access?.[0]?.preferred_language;if((preferred==='mr'||preferred==='en')&&!localStorage.getItem('pmposhan.lang'))setLang(preferred)}).catch(e=>setApiError(String(e)))},[]);
 const roles=realmRoles().filter(r=>['TEACHER','HEADMASTER','CLUSTER_OFFICER','BLOCK_OFFICER','DISTRICT_OFFICER','SYSTEM_ADMIN'].includes(r));const isSystem=roles.includes('SYSTEM_ADMIN');const managementRoles=['HEADMASTER','CLUSTER_OFFICER','BLOCK_OFFICER','DISTRICT_OFFICER','SYSTEM_ADMIN'];const canManage=roles.some(r=>managementRoles.includes(r));const activeSchool=schools.find(s=>s.id===schoolId)||schools[0];
 const schoolLogo=localStorage.getItem('pmposhan.brand.schoolLogo')||'';const districtLogo=localStorage.getItem('pmposhan.brand.districtLogo')||'';const districtName=localStorage.getItem('pmposhan.brand.districtName')||'District / जिल्हा';const departmentName=localStorage.getItem('pmposhan.brand.departmentName')||'School Education & Sports Department';void brandTick;void departmentName;
 const visibleGroups=useMemo(()=>groups.map(g=>({...g,items:g.items.filter(i=>!i.adminOnly||isSystem).filter(i=>!i.management||canManage)})).filter(g=>g.items.length),[isSystem,canManage]);function go(p:string){setPage(p as Page);setNavOpen(false)}
 const logout=async()=>{if(isStandaloneMode()){await standaloneLogout();window.location.reload();return;}await keycloak.logout({redirectUri:window.location.origin});};
 let body:any;if(page==='dashboard')body=<Dashboard lang={lang} schoolId={schoolId} school={activeSchool} onNavigate={go}/>;else if(page==='schoolProfile')body=<SchoolProfile lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='menuPlanner')body=<MenuPlanner lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='dailyMeal')body=<DailyMeal lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='stockReceipt')body=<StockReceipt lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='stockRegister')body=<StockRegister lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='stockControls')body=<StockControls lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='monthlyVerification')body=<HierarchyDashboard lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;else if(page==='adminDashboard')body=<AdminDashboard lang={lang}/>;else if(page==='schoolCalendar')body=<SchoolCalendar lang={lang} schoolId={schoolId}/>;else if(page==='masterData')body=<MasterData lang={lang}/>;else if(page==='customReports')body=<CustomReports lang={lang}/>;else if(page==='systemAdministration')body=<SystemAdministration lang={lang}/>;else if(page==='reports' || page==='workbookRegisters')
  body=<WorkbookRegisters
    lang={lang}
    schools={schools}
    schoolId={schoolId}
    setSchoolId={setSchoolId}
/>;else if(page==='branding')body=<BrandingSettings lang={lang}/>;else if(page==='help')body=<HelpManual lang={lang}/>;else body=<Reports lang={lang} schools={schools} schoolId={schoolId} setSchoolId={setSchoolId}/>;
 return <div className="app professional-ui exact-ui">
  <header className="gov-header exact-header">
   <button className="mobile-menu" onClick={()=>setNavOpen(v=>!v)}>☰</button>
   <div className="maha-lockup"><div className="maha-emblem">◉</div><div><strong>{lang==='mr'?'महाराष्ट्र शासन':'Government of Maharashtra'}</strong><span>{lang==='mr'?'शालेय शिक्षण व क्रीडा विभाग':'School Education & Sports Department'}</span></div></div>
   <div className="pm-center"><b>PM POSHAN</b><strong>{lang==='mr'?'प्रधानमंत्री पोषण शक्ती निर्माण':'School Meal Management System'}</strong><small>Healthy Children &nbsp;|&nbsp; Brighter Minds &nbsp;|&nbsp; Stronger India</small><em>{lang==='mr'?'संतुलित आहार, उज्ज्वल भविष्य':'Balanced nutrition, brighter future'}</em></div>
   <div className="district-lockup">{districtLogo?<img src={districtLogo}/>:<span className="round-logo">जि.प.</span>}<div><strong>{districtName}</strong><small>{lang==='mr'?'शिक्षण • पोषण • समृद्ध समाज':'Education • Nutrition • Community'}</small></div></div>
  </header>
  {apiError&&<div className="api-error">API authentication error: {apiError}</div>}
  <div className="shell professional-shell">
   <aside className={navOpen?'open':''}>
    <div className="sidebar-brand">{districtLogo?<img src={districtLogo}/>:<span>◉</span>}<div><b>PM POSHAN</b><small>School Meal Management</small></div></div>
    <div className="school-brand-card">{schoolLogo?<div className="school-logo-wrap"><img src={schoolLogo}/></div>:<div className="school-logo-wrap">🏫</div>}<div><strong>{activeSchool?(lang==='mr'?activeSchool.name_mr:activeSchool.name_en):(lang==='mr'?'शाळा':'School')}</strong><small>{activeSchool?.udise_code?`UDISE: ${activeSchool.udise_code}`:''}</small><small>{districtName}</small></div></div>
    <nav>{visibleGroups.map(g=><div className="nav-group" key={g.en||'main'}>{g.en&&<div className="nav-group-title">{lang==='mr'?g.mr:g.en}</div>}{g.items.map(i=><button key={i.id} className={page===i.id?'active':''} onClick={()=>go(i.id)}><span className="nav-icon">{i.icon}</span><span className="nav-copy"><b>{lang==='mr'?i.mr:i.en}</b>{lang==='mr'&&<small>{i.en}</small>}</span><strong className="chev">›</strong></button>)}</div>)}</nav>
    <div className="sidebar-footer">PM POSHAN v1.0 &nbsp;|&nbsp; Build 2026.09<br/><span className="online-dot"></span>{lang==='mr'?'ऑफलाइन तयार':'Offline Ready'}</div>
   </aside>
   <section className="main-stage">
    <div className="top-userbar">
     <div className="school-context">
      <div className="school-select-wrap"><span>🏫</span><select value={schoolId} onChange={e=>setSchoolId(e.target.value)}>{schools.map(s=><option value={s.id} key={s.id}>{lang==='mr'?s.name_mr:s.name_en}</option>)}</select></div>
      <span className="context-sep"></span><b>UDISE: {activeSchool?.udise_code||'—'}</b><span className="context-sep"></span><b>{districtName}</b>
     </div>
     <div className="top-actions-right"><span className="bell">🔔<b>3</b></span><div className="user-chip"><span className="avatar-dot">●</span><span><strong>{me?.username||keycloak.tokenParsed?.preferred_username||'User'}</strong><small>{roles.join(' • ')}</small></span></div><div className="lang"><button className={lang==='mr'?'active':''} onClick={()=>setLang('mr')}>मराठी</button><button className={lang==='en'?'active':''} onClick={()=>setLang('en')}>EN</button></div><button className="logout" onClick={logout}>{lang==='mr'?'बाहेर':'Logout'}</button></div>
    </div>
    {body}
    <footer className="app-footer"><span>© 2026 PM POSHAN – Government of Maharashtra</span><span>Support: pmposhan@maharashtra.gov.in &nbsp; | &nbsp; Help Desk &nbsp; | &nbsp; Privacy &nbsp; | &nbsp; Terms</span></footer>
   </section>
  </div>
 </div>
}
