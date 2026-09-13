import type { SQLiteDBConnection } from '@capacitor-community/sqlite';
import { androidApiFetch } from './androidRuntime';
import { getSharedAndroidDb } from './androidSharedDb';

type LocalUser={id:string;username:string;role:string};

type Metrics={
  recorded_days:number;
  verified_days:number;
  incomplete_days:number;
  attendance_class_1_5:number;
  attendance_class_6_8:number;
  meals_class_1_5:number;
  meals_class_6_8:number;
  total_meals:number;
  tasting_exception_days:number;
  hygiene_exception_days:number;
};

const ALLOWED_DAY_TYPES=new Set(['WORKING','SUNDAY','PUBLIC_HOLIDAY','SCHOOL_HOLIDAY','LOCAL_HOLIDAY','CLOSURE','EXAM_NON_MEAL']);
const RETURN_STATUSES=['DRAFT','SUBMITTED','CLUSTER_REVIEWED','BLOCK_APPROVED','RETURNED'];

function uuid():string{return crypto.randomUUID();}
function jsonResponse(body:unknown,status=200):Response{return new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});}
function pad(n:number):string{return String(n).padStart(2,'0');}
function isoDate(year:number,month:number,day:number):string{return `${year}-${pad(month)}-${pad(day)}`;}
function daysInMonth(year:number,month:number):number{return new Date(Date.UTC(year,month,0)).getUTCDate();}
function isSunday(year:number,month:number,day:number):boolean{return new Date(Date.UTC(year,month-1,day)).getUTCDay()===0;}
function validPeriod(year:number,month:number):boolean{return Number.isInteger(year)&&year>=2000&&year<=2200&&Number.isInteger(month)&&month>=1&&month<=12;}
function bool(v:unknown):boolean{return Number(v)===1||v===true;}
function num(v:unknown):number{const n=Number(v);return Number.isFinite(n)?n:0;}
function nowIso():string{return new Date().toISOString();}

async function bodyJson(init:RequestInit):Promise<any>{
  if(!init.body)return {};
  if(typeof init.body==='string')return JSON.parse(init.body||'{}');
  throw new Error('ANDROID_BODY_TYPE_UNSUPPORTED');
}

async function requireUser(init:RequestInit):Promise<{response?:Response;user?:LocalUser}>{
  const r=await androidApiFetch('/me',{headers:init.headers||{}});
  if(!r.ok)return {response:r};
  const me=await r.json();
  return {user:{id:String(me.sub||''),username:String(me.username||me.preferred_username||''),role:String(me.role||me.roles?.[0]||'')}};
}

async function accessibleSchoolIds(init:RequestInit):Promise<{response?:Response;ids?:string[]}>{
  const r=await androidApiFetch('/schools',{headers:init.headers||{}});
  if(!r.ok)return {response:r};
  const rows=await r.json();
  return {ids:Array.isArray(rows)?rows.map((x:any)=>String(x.id)):[]};
}

async function assertSchoolAccess(init:RequestInit,schoolId:string):Promise<Response|null>{
  const a=await accessibleSchoolIds(init);
  if(a.response)return a.response;
  return a.ids?.includes(schoolId)?null:jsonResponse({detail:'NO_SCHOOL_ACCESS'},403);
}

async function ensureSchema(db:SQLiteDBConnection):Promise<void>{
  await db.execute(`
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS school_calendar_days (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      calendar_date TEXT NOT NULL,
      day_type TEXT NOT NULL DEFAULT 'WORKING',
      meal_required INTEGER NOT NULL DEFAULT 1 CHECK(meal_required IN (0,1)),
      title_en TEXT,
      title_mr TEXT,
      remarks TEXT,
      created_by TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,calendar_date)
    );
    CREATE INDEX IF NOT EXISTS ix_android_calendar_school_date ON school_calendar_days(school_id,calendar_date);

    CREATE TABLE IF NOT EXISTS daily_attendance (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      meal_date TEXT NOT NULL,
      class_1_5_enrolled INTEGER NOT NULL DEFAULT 0,
      class_1_5_present INTEGER NOT NULL DEFAULT 0,
      class_6_8_enrolled INTEGER NOT NULL DEFAULT 0,
      class_6_8_present INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'DRAFT',
      entered_by_subject TEXT,
      entered_by_username TEXT,
      verified_by_subject TEXT,
      verified_by_username TEXT,
      verified_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,meal_date)
    );
    CREATE TABLE IF NOT EXISTS daily_meal_entries (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      meal_date TEXT NOT NULL,
      menu_id TEXT NOT NULL,
      meals_class_1_5 INTEGER NOT NULL DEFAULT 0,
      meals_class_6_8 INTEGER NOT NULL DEFAULT 0,
      total_meals INTEGER NOT NULL DEFAULT 0,
      tasting_done INTEGER NOT NULL DEFAULT 0,
      hygiene_ok INTEGER NOT NULL DEFAULT 0,
      remarks TEXT,
      status TEXT NOT NULL DEFAULT 'DRAFT',
      entered_by_subject TEXT,
      entered_by_username TEXT,
      verified_by_subject TEXT,
      verified_by_username TEXT,
      verified_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,meal_date)
    );

    CREATE TABLE IF NOT EXISTS monthly_school_returns (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      year INTEGER NOT NULL,
      month INTEGER NOT NULL,
      recorded_days INTEGER NOT NULL DEFAULT 0,
      verified_days INTEGER NOT NULL DEFAULT 0,
      incomplete_days INTEGER NOT NULL DEFAULT 0,
      attendance_class_1_5 INTEGER NOT NULL DEFAULT 0,
      attendance_class_6_8 INTEGER NOT NULL DEFAULT 0,
      meals_class_1_5 INTEGER NOT NULL DEFAULT 0,
      meals_class_6_8 INTEGER NOT NULL DEFAULT 0,
      total_meals INTEGER NOT NULL DEFAULT 0,
      tasting_exception_days INTEGER NOT NULL DEFAULT 0,
      hygiene_exception_days INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'DRAFT',
      generated_by_subject TEXT NOT NULL,
      generated_by_username TEXT NOT NULL,
      generated_at TEXT NOT NULL,
      submitted_by_subject TEXT,
      submitted_by_username TEXT,
      submitted_at TEXT,
      cluster_reviewed_by TEXT,
      cluster_reviewed_at TEXT,
      block_approved_by TEXT,
      block_approved_at TEXT,
      return_reason TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,year,month)
    );
    CREATE INDEX IF NOT EXISTS ix_android_monthly_period ON monthly_school_returns(year,month,status);
    CREATE TABLE IF NOT EXISTS monthly_return_actions (
      id TEXT PRIMARY KEY,
      monthly_return_id TEXT NOT NULL REFERENCES monthly_school_returns(id) ON DELETE CASCADE,
      action TEXT NOT NULL,
      from_status TEXT,
      to_status TEXT NOT NULL,
      actor_subject TEXT NOT NULL,
      actor_username TEXT NOT NULL,
      actor_role TEXT NOT NULL,
      remarks TEXT,
      acted_at TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
  `);
}

async function calendarMonth(db:SQLiteDBConnection,url:URL,init:RequestInit):Promise<Response>{
  const schoolId=String(url.searchParams.get('school_id')||'');
  const year=Number(url.searchParams.get('year')); const month=Number(url.searchParams.get('month'));
  if(!schoolId||!validPeriod(year,month))return jsonResponse({detail:'Invalid school/year/month'},400);
  const access=await assertSchoolAccess(init,schoolId); if(access)return access;
  const first=isoDate(year,month,1),last=isoDate(year,month,daysInMonth(year,month));
  const q=await db.query('SELECT * FROM school_calendar_days WHERE school_id=? AND calendar_date>=? AND calendar_date<=? ORDER BY calendar_date',[schoolId,first,last]);
  const by=new Map<string,any>((q.values||[]).map((r:any)=>[String(r.calendar_date),r]));
  const out:any[]=[];
  for(let day=1;day<=daysInMonth(year,month);day+=1){
    const date=isoDate(year,month,day); const row=by.get(date); const sunday=isSunday(year,month,day);
    out.push({date,day_type:row?.day_type||(sunday?'SUNDAY':'WORKING'),meal_required:row?bool(row.meal_required):!sunday,title_en:row?.title_en||null,title_mr:row?.title_mr||null,remarks:row?.remarks||null,configured:!!row});
  }
  return jsonResponse(out);
}

async function calendarDay(db:SQLiteDBConnection,init:RequestInit,user:LocalUser):Promise<Response>{
  if(!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role))return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
  const body=await bodyJson(init); const schoolId=String(body.school_id||''); const date=String(body.date||'');
  const dayType=String(body.day_type||'WORKING').toUpperCase();
  if(!schoolId||!/^\d{4}-\d{2}-\d{2}$/.test(date))return jsonResponse({detail:'Invalid calendar date'},400);
  if(!ALLOWED_DAY_TYPES.has(dayType))return jsonResponse({detail:'Invalid day type'},422);
  const access=await assertSchoolAccess(init,schoolId); if(access)return access;
  const mealRequired=body.meal_required===undefined?dayType==='WORKING':!!body.meal_required;
  await db.run(`INSERT INTO school_calendar_days
    (id,school_id,calendar_date,day_type,meal_required,title_en,title_mr,remarks,created_by,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(school_id,calendar_date) DO UPDATE SET
      day_type=excluded.day_type,meal_required=excluded.meal_required,title_en=excluded.title_en,title_mr=excluded.title_mr,remarks=excluded.remarks,updated_at=CURRENT_TIMESTAMP`,
    [uuid(),schoolId,date,dayType,mealRequired?1:0,body.title_en||null,body.title_mr||null,body.remarks||null,user.username]);
  return jsonResponse({status:'saved',date});
}

async function calendarDefaults(db:SQLiteDBConnection,init:RequestInit,user:LocalUser):Promise<Response>{
  if(!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role))return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
  const body=await bodyJson(init); const schoolId=String(body.school_id||''); const year=Number(body.year),month=Number(body.month);
  if(!schoolId||!validPeriod(year,month))return jsonResponse({detail:'Invalid school/year/month'},400);
  const access=await assertSchoolAccess(init,schoolId); if(access)return access;
  let created=0;
  for(let day=1;day<=daysInMonth(year,month);day+=1){
    const date=isoDate(year,month,day);
    const exists=await db.query('SELECT id FROM school_calendar_days WHERE school_id=? AND calendar_date=?',[schoolId,date]);
    if(exists.values?.length)continue;
    const sunday=isSunday(year,month,day);
    await db.run('INSERT INTO school_calendar_days (id,school_id,calendar_date,day_type,meal_required,created_by) VALUES (?,?,?,?,?,?)',[uuid(),schoolId,date,sunday?'SUNDAY':'WORKING',sunday?0:1,user.username]);
    created+=1;
  }
  return jsonResponse({status:'ok',created});
}

async function complianceMonth(db:SQLiteDBConnection,url:URL,init:RequestInit):Promise<Response>{
  const schoolId=String(url.searchParams.get('school_id')||''); const year=Number(url.searchParams.get('year')),month=Number(url.searchParams.get('month'));
  if(!schoolId||!validPeriod(year,month))return jsonResponse({detail:'Invalid school/year/month'},400);
  const access=await assertSchoolAccess(init,schoolId); if(access)return access;
  const first=isoDate(year,month,1),last=isoDate(year,month,daysInMonth(year,month));
  const cal=await db.query('SELECT calendar_date,meal_required FROM school_calendar_days WHERE school_id=? AND calendar_date>=? AND calendar_date<=?',[schoolId,first,last]);
  const required=new Set<string>((cal.values||[]).filter((r:any)=>bool(r.meal_required)).map((r:any)=>String(r.calendar_date)));
  const meals=await db.query('SELECT meal_date,status FROM daily_meal_entries WHERE school_id=? AND meal_date>=? AND meal_date<=?',[schoolId,first,last]);
  const atts=await db.query('SELECT meal_date,status FROM daily_attendance WHERE school_id=? AND meal_date>=? AND meal_date<=?',[schoolId,first,last]);
  const mealStatus=new Map<string,string>((meals.values||[]).map((r:any)=>[String(r.meal_date),String(r.status)]));
  const attStatus=new Map<string,string>((atts.values||[]).map((r:any)=>[String(r.meal_date),String(r.status)]));
  const complete=[...required].filter(d=>mealStatus.get(d)==='VERIFIED'&&attStatus.get(d)==='VERIFIED');
  const missing=[...required].filter(d=>!complete.includes(d)).sort();
  const pct=required.size?Math.round((complete.length*10000)/required.size)/100:100;
  return jsonResponse({required_days:required.size,complete_days:complete.length,missing_days:missing.length,compliance_percent:pct,missing_dates:missing});
}

async function monthlyMetrics(db:SQLiteDBConnection,schoolId:string,year:number,month:number):Promise<Metrics>{
  const first=isoDate(year,month,1),last=isoDate(year,month,daysInMonth(year,month));
  const aq=await db.query('SELECT * FROM daily_attendance WHERE school_id=? AND meal_date>=? AND meal_date<=?',[schoolId,first,last]);
  const mq=await db.query('SELECT * FROM daily_meal_entries WHERE school_id=? AND meal_date>=? AND meal_date<=?',[schoolId,first,last]);
  const attendance=aq.values||[],meals=mq.values||[];
  const byA=new Map<string,any>(attendance.map((r:any)=>[String(r.meal_date),r])); const byM=new Map<string,any>(meals.map((r:any)=>[String(r.meal_date),r]));
  const recorded=new Set<string>([...byA.keys(),...byM.keys()]);
  const cq=await db.query('SELECT calendar_date,meal_required FROM school_calendar_days WHERE school_id=? AND calendar_date>=? AND calendar_date<=?',[schoolId,first,last]);
  const calendar=cq.values||[];
  const required=calendar.length?new Set<string>(calendar.filter((r:any)=>bool(r.meal_required)).map((r:any)=>String(r.calendar_date))):new Set<string>(recorded);
  const verified=[...recorded].filter(d=>byA.get(d)?.status==='VERIFIED'&&byM.get(d)?.status==='VERIFIED');
  return {
    recorded_days:recorded.size,
    verified_days:verified.length,
    incomplete_days:[...required].filter(d=>!verified.includes(d)).length,
    attendance_class_1_5:verified.reduce((s,d)=>s+num(byA.get(d)?.class_1_5_present),0),
    attendance_class_6_8:verified.reduce((s,d)=>s+num(byA.get(d)?.class_6_8_present),0),
    meals_class_1_5:verified.reduce((s,d)=>s+num(byM.get(d)?.meals_class_1_5),0),
    meals_class_6_8:verified.reduce((s,d)=>s+num(byM.get(d)?.meals_class_6_8),0),
    total_meals:verified.reduce((s,d)=>s+num(byM.get(d)?.total_meals),0),
    tasting_exception_days:meals.filter((r:any)=>!bool(r.tasting_done)).length,
    hygiene_exception_days:meals.filter((r:any)=>!bool(r.hygiene_ok)).length,
  };
}

async function hierarchyForSchool(db:SQLiteDBConnection,schoolId:string):Promise<any|null>{
  const q=await db.query(`SELECT s.id AS school_id,s.code AS school_code,s.udise_code,s.name_en AS school_name_en,s.name_mr AS school_name_mr,
    c.id AS cluster_id,c.name_en AS cluster_name_en,c.name_mr AS cluster_name_mr,
    b.id AS block_id,b.name_en AS block_name_en,b.name_mr AS block_name_mr,
    d.id AS district_id,d.name_en AS district_name_en,d.name_mr AS district_name_mr
    FROM schools s LEFT JOIN clusters c ON c.id=s.cluster_id LEFT JOIN blocks b ON b.id=c.block_id LEFT JOIN districts d ON d.id=b.district_id WHERE s.id=?`,[schoolId]);
  return q.values?.[0]||null;
}

async function hierarchyScope(db:SQLiteDBConnection,init:RequestInit,user:LocalUser):Promise<Response>{
  const a=await accessibleSchoolIds(init); if(a.response)return a.response;
  const schools:any[]=[];
  for(const id of a.ids||[]){const row=await hierarchyForSchool(db,id); if(row)schools.push(row);}
  schools.sort((x,y)=>String(x.school_name_en||'').localeCompare(String(y.school_name_en||'')));
  return jsonResponse({roles:[user.role],school_count:schools.length,schools,org_access:[]});
}

async function returnDict(db:SQLiteDBConnection,row:any):Promise<any>{
  const school=await hierarchyForSchool(db,String(row.school_id));
  const aq=await db.query('SELECT action,from_status,to_status,actor_username,actor_role,remarks,acted_at FROM monthly_return_actions WHERE monthly_return_id=? ORDER BY acted_at',[row.id]);
  return {...row,
    school_code:school?.school_code||null,udise_code:school?.udise_code||null,school_name_en:school?.school_name_en||null,school_name_mr:school?.school_name_mr||null,
    cluster_name_en:school?.cluster_name_en||null,cluster_name_mr:school?.cluster_name_mr||null,block_name_en:school?.block_name_en||null,block_name_mr:school?.block_name_mr||null,district_name_en:school?.district_name_en||null,district_name_mr:school?.district_name_mr||null,
    actions:aq.values||[]};
}

async function appendAction(db:SQLiteDBConnection,rowId:string,user:LocalUser,action:string,fromStatus:string|null,toStatus:string,remarks:string|null):Promise<void>{
  await db.run('INSERT INTO monthly_return_actions (id,monthly_return_id,action,from_status,to_status,actor_subject,actor_username,actor_role,remarks,acted_at) VALUES (?,?,?,?,?,?,?,?,?,?)',[uuid(),rowId,action,fromStatus,toStatus,user.id,user.username,user.role,remarks,nowIso()]);
}

async function listMonthly(db:SQLiteDBConnection,url:URL,init:RequestInit):Promise<Response>{
  const year=Number(url.searchParams.get('year')),month=Number(url.searchParams.get('month')); const requested=String(url.searchParams.get('school_id')||'');
  if(!validPeriod(year,month))return jsonResponse({detail:'Invalid year/month'},400);
  const a=await accessibleSchoolIds(init); if(a.response)return a.response;
  let ids=a.ids||[]; if(requested){if(!ids.includes(requested))return jsonResponse({detail:'NO_SCHOOL_ACCESS'},403);ids=[requested];}
  if(!ids.length)return jsonResponse([]);
  const q=await db.query('SELECT * FROM monthly_school_returns WHERE year=? AND month=? ORDER BY status,school_id',[year,month]);
  const out:any[]=[]; for(const row of q.values||[]){if(ids.includes(String(row.school_id)))out.push(await returnDict(db,row));}
  return jsonResponse(out);
}

async function monthlySummary(db:SQLiteDBConnection,url:URL,init:RequestInit):Promise<Response>{
  const year=Number(url.searchParams.get('year')),month=Number(url.searchParams.get('month')); if(!validPeriod(year,month))return jsonResponse({detail:'Invalid year/month'},400);
  const a=await accessibleSchoolIds(init); if(a.response)return a.response; const ids=a.ids||[];
  const q=await db.query('SELECT * FROM monthly_school_returns WHERE year=? AND month=?',[year,month]); const rows=(q.values||[]).filter((r:any)=>ids.includes(String(r.school_id)));
  const counts:Record<string,number>=Object.fromEntries(RETURN_STATUSES.map(s=>[s,0])); let totalMeals=0,exceptions=0;
  for(const r of rows){counts[String(r.status)]=(counts[String(r.status)]||0)+1;totalMeals+=num(r.total_meals);if(num(r.incomplete_days)>0||num(r.tasting_exception_days)>0||num(r.hygiene_exception_days)>0)exceptions+=1;}
  return jsonResponse({year,month,total_schools:ids.length,returns_generated:rows.length,missing_returns:Math.max(0,ids.length-rows.length),status_counts:counts,total_meals:totalMeals,exception_returns:exceptions});
}

async function generateMonthly(db:SQLiteDBConnection,init:RequestInit,user:LocalUser):Promise<Response>{
  if(!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role))return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
  const body=await bodyJson(init); const schoolId=String(body.school_id||''),year=Number(body.year),month=Number(body.month);
  if(!schoolId||!validPeriod(year,month))return jsonResponse({detail:'Invalid school/year/month'},400);
  const access=await assertSchoolAccess(init,schoolId); if(access)return access;
  const eq=await db.query('SELECT * FROM monthly_school_returns WHERE school_id=? AND year=? AND month=?',[schoolId,year,month]); const existing=eq.values?.[0];
  if(existing&&!['DRAFT','RETURNED'].includes(String(existing.status)))return jsonResponse({detail:'Submitted/reviewed return cannot be regenerated'},409);
  const metrics=await monthlyMetrics(db,schoolId,year,month); const timestamp=nowIso(); const id=existing?String(existing.id):uuid(); const previous=existing?String(existing.status):null;
  if(existing){
    await db.run(`UPDATE monthly_school_returns SET recorded_days=?,verified_days=?,incomplete_days=?,attendance_class_1_5=?,attendance_class_6_8=?,meals_class_1_5=?,meals_class_6_8=?,total_meals=?,tasting_exception_days=?,hygiene_exception_days=?,status='DRAFT',generated_by_subject=?,generated_by_username=?,generated_at=?,return_reason=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?`,
      [metrics.recorded_days,metrics.verified_days,metrics.incomplete_days,metrics.attendance_class_1_5,metrics.attendance_class_6_8,metrics.meals_class_1_5,metrics.meals_class_6_8,metrics.total_meals,metrics.tasting_exception_days,metrics.hygiene_exception_days,user.id,user.username,timestamp,id]);
  }else{
    await db.run(`INSERT INTO monthly_school_returns (id,school_id,year,month,recorded_days,verified_days,incomplete_days,attendance_class_1_5,attendance_class_6_8,meals_class_1_5,meals_class_6_8,total_meals,tasting_exception_days,hygiene_exception_days,status,generated_by_subject,generated_by_username,generated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'DRAFT',?,?,?)`,
      [id,schoolId,year,month,metrics.recorded_days,metrics.verified_days,metrics.incomplete_days,metrics.attendance_class_1_5,metrics.attendance_class_6_8,metrics.meals_class_1_5,metrics.meals_class_6_8,metrics.total_meals,metrics.tasting_exception_days,metrics.hygiene_exception_days,user.id,user.username,timestamp]);
  }
  await appendAction(db,id,user,existing?'REGENERATE':'GENERATE',previous,'DRAFT',null);
  const rq=await db.query('SELECT * FROM monthly_school_returns WHERE id=?',[id]); return jsonResponse(await returnDict(db,rq.values?.[0]));
}

async function monthlyAction(db:SQLiteDBConnection,route:string,init:RequestInit,user:LocalUser):Promise<Response>{
  const m=route.match(/^\/monthly-returns\/([^/]+)\/(submit|cluster-review|block-approve|return)$/); if(!m)return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);
  const id=decodeURIComponent(m[1]),action=m[2]; const body=await bodyJson(init); const q=await db.query('SELECT * FROM monthly_school_returns WHERE id=?',[id]); const row=q.values?.[0];
  if(!row)return jsonResponse({detail:'Monthly return not found'},404); const access=await assertSchoolAccess(init,String(row.school_id)); if(access)return access;
  const previous=String(row.status),timestamp=nowIso(); let next='',event='';
  if(action==='submit'){
    if(!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role))return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
    if(!['DRAFT','RETURNED'].includes(previous))return jsonResponse({detail:'Only draft/returned monthly return can be submitted'},409);
    if(num(row.verified_days)<=0)return jsonResponse({detail:'At least one verified daily operation is required'},400);
    if(num(row.incomplete_days)>0||num(row.tasting_exception_days)>0||num(row.hygiene_exception_days)>0)return jsonResponse({detail:'Resolve incomplete daily entries and tasting/hygiene exceptions before submission'},409);
    next='SUBMITTED';event='SUBMIT';
    await db.run('UPDATE monthly_school_returns SET status=?,submitted_by_subject=?,submitted_by_username=?,submitted_at=?,return_reason=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?',[next,user.id,user.username,timestamp,id]);
  }else if(action==='cluster-review'){
    if(!['CLUSTER_OFFICER','SYSTEM_ADMIN'].includes(user.role))return jsonResponse({detail:'CLUSTER_OFFICER_OR_SYSTEM_ADMIN_REQUIRED'},403);
    if(previous!=='SUBMITTED')return jsonResponse({detail:'Return must be SUBMITTED before cluster review'},409);
    next='CLUSTER_REVIEWED';event='CLUSTER_REVIEW'; await db.run('UPDATE monthly_school_returns SET status=?,cluster_reviewed_by=?,cluster_reviewed_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[next,user.username,timestamp,id]);
  }else if(action==='block-approve'){
    if(!['BLOCK_OFFICER','SYSTEM_ADMIN'].includes(user.role))return jsonResponse({detail:'BLOCK_OFFICER_OR_SYSTEM_ADMIN_REQUIRED'},403);
    if(previous!=='CLUSTER_REVIEWED')return jsonResponse({detail:'Return must be CLUSTER_REVIEWED before block approval'},409);
    next='BLOCK_APPROVED';event='BLOCK_APPROVE'; await db.run('UPDATE monthly_school_returns SET status=?,block_approved_by=?,block_approved_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[next,user.username,timestamp,id]);
  }else{
    if(!['CLUSTER_OFFICER','BLOCK_OFFICER','SYSTEM_ADMIN'].includes(user.role))return jsonResponse({detail:'REVIEWER_OR_SYSTEM_ADMIN_REQUIRED'},403);
    if(!['SUBMITTED','CLUSTER_REVIEWED'].includes(previous))return jsonResponse({detail:'Only submitted/reviewed return can be returned'},409);
    const reason=String(body.remarks||'').trim(); if(!reason)return jsonResponse({detail:'Return reason is required'},400);
    next='RETURNED';event='RETURN'; await db.run('UPDATE monthly_school_returns SET status=?,return_reason=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[next,reason,id]);
  }
  await appendAction(db,id,user,event,previous,next,body.remarks?String(body.remarks):null); const rq=await db.query('SELECT * FROM monthly_school_returns WHERE id=?',[id]); return jsonResponse(await returnDict(db,rq.values?.[0]));
}

export async function tryAndroidCalendarMonthlyApiFetch(path:string,init:RequestInit={}):Promise<Response|null>{
  const method=String(init.method||'GET').toUpperCase(); const url=new URL(path,'https://local.pmposhan.invalid'); const route=url.pathname;
  const relevant=route==='/calendar/month'||route==='/calendar/day'||route==='/calendar/month/defaults'||route==='/compliance/month'||route==='/hierarchy/scope'||route==='/monthly-returns'||route==='/monthly-returns/summary'||route==='/monthly-returns/generate'||/^\/monthly-returns\/[^/]+\/(submit|cluster-review|block-approve|return)$/.test(route);
  if(!relevant)return null;
  try{
    const auth=await requireUser(init); if(auth.response)return auth.response; const user=auth.user!; const db=await getSharedAndroidDb(); await ensureSchema(db);
    if(route==='/calendar/month'&&method==='GET')return calendarMonth(db,url,init);
    if(route==='/calendar/day'&&method==='PUT')return calendarDay(db,init,user);
    if(route==='/calendar/month/defaults'&&method==='POST')return calendarDefaults(db,init,user);
    if(route==='/compliance/month'&&method==='GET')return complianceMonth(db,url,init);
    if(route==='/hierarchy/scope'&&method==='GET')return hierarchyScope(db,init,user);
    if(route==='/monthly-returns'&&method==='GET')return listMonthly(db,url,init);
    if(route==='/monthly-returns/summary'&&method==='GET')return monthlySummary(db,url,init);
    if(route==='/monthly-returns/generate'&&method==='POST')return generateMonthly(db,init,user);
    if(method==='POST'&&route.startsWith('/monthly-returns/'))return monthlyAction(db,route,init,user);
    return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);
  }catch(error){return jsonResponse({detail:error instanceof Error?error.message:String(error)},400);}
}
