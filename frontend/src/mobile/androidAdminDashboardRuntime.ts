import type { SQLiteDBConnection } from '@capacitor-community/sqlite';
import { androidApiFetch } from './androidRuntime';
import { getSharedAndroidDb } from './androidSharedDb';

type LocalUser={id:string;username:string;role:string};

type SchoolSnapshot={
  school_id:string;
  school_name_en:string;
  school_name_mr:string;
  udise_code:string;
  cluster_id:string|null;
  cluster_name_en:string|null;
  cluster_name_mr:string|null;
  block_id:string|null;
  block_name_en:string|null;
  block_name_mr:string|null;
  district_id:string|null;
  district_name_en:string|null;
  district_name_mr:string|null;
  return_id:string|null;
  status:string;
  recorded_days:number;
  verified_days:number;
  attendance:number;
  meals:number;
  coverage_pct:number;
  exceptions:number;
  low_stock_items:number;
  has_low_stock:boolean;
};

function jsonResponse(body:unknown,status=200):Response{
  return new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
}
function num(v:unknown):number{const n=Number(v);return Number.isFinite(n)?n:0;}
function validPeriod(year:number,month:number):boolean{return Number.isInteger(year)&&year>=2000&&year<=2200&&Number.isInteger(month)&&month>=1&&month<=12;}

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

async function ensureSchema(db:SQLiteDBConnection):Promise<void>{
  await db.execute(`
    PRAGMA foreign_keys=ON;
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
    CREATE TABLE IF NOT EXISTS stock_transactions (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
      transaction_date TEXT NOT NULL,
      transaction_type TEXT NOT NULL,
      quantity REAL NOT NULL,
      reference_type TEXT,
      reference_id TEXT,
      reference_no TEXT,
      remarks TEXT,
      entered_by_subject TEXT,
      entered_by_username TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
  `);
}

async function stockBalance(db:SQLiteDBConnection,schoolId:string,ingredientId:string):Promise<number>{
  const q=await db.query('SELECT COALESCE(SUM(quantity),0) AS balance FROM stock_transactions WHERE school_id=? AND ingredient_id=?',[schoolId,ingredientId]);
  return num(q.values?.[0]?.balance);
}

async function adminSchoolSnapshot(db:SQLiteDBConnection,init:RequestInit,year:number,month:number):Promise<{response?:Response;rows?:SchoolSnapshot[]}>{
  const access=await accessibleSchoolIds(init); if(access.response)return {response:access.response};
  const schoolIds=access.ids||[]; if(!schoolIds.length)return {rows:[]};

  const rq=await db.query('SELECT * FROM monthly_school_returns WHERE year=? AND month=?',[year,month]);
  const returnBySchool=new Map<string,any>((rq.values||[]).map((r:any)=>[String(r.school_id),r]));
  const iq=await db.query('SELECT id,reorder_level FROM ingredients WHERE active=1 AND track_inventory=1');
  const ingredients=iq.values||[];
  const rows:SchoolSnapshot[]=[];

  for(const schoolId of schoolIds){
    const sq=await db.query(`SELECT s.id AS school_id,s.udise_code,s.name_en AS school_name_en,s.name_mr AS school_name_mr,
      c.id AS cluster_id,c.name_en AS cluster_name_en,c.name_mr AS cluster_name_mr,
      b.id AS block_id,b.name_en AS block_name_en,b.name_mr AS block_name_mr,
      d.id AS district_id,d.name_en AS district_name_en,d.name_mr AS district_name_mr
      FROM schools s
      LEFT JOIN clusters c ON c.id=s.cluster_id
      LEFT JOIN blocks b ON b.id=c.block_id
      LEFT JOIN districts d ON d.id=b.district_id
      WHERE s.id=? AND s.active=1`,[schoolId]);
    const school=sq.values?.[0]; if(!school)continue;
    const ret=returnBySchool.get(schoolId);
    let lowItems=0;
    for(const ing of ingredients){
      const reorder=num(ing.reorder_level); if(reorder<=0)continue;
      if(await stockBalance(db,schoolId,String(ing.id))<=reorder)lowItems+=1;
    }
    const attendance=ret?num(ret.attendance_class_1_5)+num(ret.attendance_class_6_8):0;
    const meals=ret?num(ret.total_meals):0;
    const exceptions=ret?num(ret.incomplete_days)+num(ret.tasting_exception_days)+num(ret.hygiene_exception_days):0;
    rows.push({
      school_id:schoolId,
      school_name_en:String(school.school_name_en||''),school_name_mr:String(school.school_name_mr||''),udise_code:String(school.udise_code||''),
      cluster_id:school.cluster_id?String(school.cluster_id):null,cluster_name_en:school.cluster_name_en||null,cluster_name_mr:school.cluster_name_mr||null,
      block_id:school.block_id?String(school.block_id):null,block_name_en:school.block_name_en||null,block_name_mr:school.block_name_mr||null,
      district_id:school.district_id?String(school.district_id):null,district_name_en:school.district_name_en||null,district_name_mr:school.district_name_mr||null,
      return_id:ret?String(ret.id):null,status:ret?String(ret.status):'MISSING',recorded_days:ret?num(ret.recorded_days):0,verified_days:ret?num(ret.verified_days):0,
      attendance,meals,coverage_pct:attendance>0?Math.round((meals*10000)/attendance)/100:0,
      exceptions,low_stock_items:lowItems,has_low_stock:lowItems>0,
    });
  }
  rows.sort((a,b)=>a.school_name_en.localeCompare(b.school_name_en));
  return {rows};
}

function aggregate(rows:SchoolSnapshot[],level:string,parentId:string|null):any[]{
  if(level==='school'){
    const filtered=parentId?rows.filter(r=>r.cluster_id===parentId):rows;
    return filtered.map(r=>({
      id:r.school_id,name_en:r.school_name_en,name_mr:r.school_name_mr,code:r.udise_code,school_count:1,
      returns_generated:r.status==='MISSING'?0:1,missing_returns:r.status==='MISSING'?1:0,approved_returns:r.status==='BLOCK_APPROVED'?1:0,
      pending_returns:!['MISSING','BLOCK_APPROVED'].includes(r.status)?1:0,attendance:r.attendance,meals:r.meals,coverage_pct:r.coverage_pct,
      exception_schools:r.exceptions>0?1:0,low_stock_schools:r.has_low_stock?1:0,status:r.status,exceptions:r.exceptions,low_stock_items:r.low_stock_items,next_level:null,
    })).sort((a,b)=>String(a.name_en).localeCompare(String(b.name_en)));
  }

  const spec:Record<string,{id:keyof SchoolSnapshot,en:keyof SchoolSnapshot,mr:keyof SchoolSnapshot,parent:keyof SchoolSnapshot|null,next:string}>={
    district:{id:'district_id',en:'district_name_en',mr:'district_name_mr',parent:null,next:'block'},
    block:{id:'block_id',en:'block_name_en',mr:'block_name_mr',parent:'district_id',next:'cluster'},
    cluster:{id:'cluster_id',en:'cluster_name_en',mr:'cluster_name_mr',parent:'block_id',next:'school'},
  };
  const s=spec[level]; if(!s)return [];
  const filtered=s.parent&&parentId?rows.filter(r=>String(r[s.parent!]||'')===parentId):rows;
  const groups=new Map<string,any>();
  for(const r of filtered){
    const gid=String(r[s.id]||''); if(!gid)continue;
    let g=groups.get(gid);
    if(!g){g={id:gid,name_en:String(r[s.en]||''),name_mr:String(r[s.mr]||''),code:null,school_count:0,returns_generated:0,missing_returns:0,approved_returns:0,pending_returns:0,attendance:0,meals:0,exception_schools:0,low_stock_schools:0,next_level:s.next};groups.set(gid,g);}
    g.school_count+=1;
    if(r.status==='MISSING')g.missing_returns+=1; else {g.returns_generated+=1;if(r.status==='BLOCK_APPROVED')g.approved_returns+=1;else g.pending_returns+=1;}
    g.attendance+=r.attendance;g.meals+=r.meals;g.exception_schools+=r.exceptions>0?1:0;g.low_stock_schools+=r.has_low_stock?1:0;
  }
  const out=[...groups.values()];
  for(const g of out)g.coverage_pct=g.attendance>0?Math.round((g.meals*10000)/g.attendance)/100:0;
  return out.sort((a,b)=>String(a.name_en).localeCompare(String(b.name_en)));
}

async function summary(db:SQLiteDBConnection,url:URL,init:RequestInit):Promise<Response>{
  const year=Number(url.searchParams.get('year')),month=Number(url.searchParams.get('month'));
  if(!validPeriod(year,month))return jsonResponse({detail:'Invalid period'},400);
  const snap=await adminSchoolSnapshot(db,init,year,month); if(snap.response)return snap.response; const rows=snap.rows||[];
  const statuses:Record<string,number>={DRAFT:0,SUBMITTED:0,CLUSTER_REVIEWED:0,BLOCK_APPROVED:0,RETURNED:0,MISSING:0};
  for(const r of rows)statuses[r.status]=(statuses[r.status]||0)+1;
  const attendance=rows.reduce((s,r)=>s+r.attendance,0),meals=rows.reduce((s,r)=>s+r.meals,0);
  return jsonResponse({year,month,total_schools:rows.length,returns_generated:rows.filter(r=>r.status!=='MISSING').length,missing_returns:rows.filter(r=>r.status==='MISSING').length,
    approved_returns:rows.filter(r=>r.status==='BLOCK_APPROVED').length,pending_returns:rows.filter(r=>!['MISSING','BLOCK_APPROVED'].includes(r.status)).length,
    total_attendance:attendance,total_meals:meals,meal_coverage_pct:attendance>0?Math.round((meals*10000)/attendance)/100:0,
    exception_schools:rows.filter(r=>r.exceptions>0).length,low_stock_schools:rows.filter(r=>r.has_low_stock).length,status_counts:statuses});
}

async function drilldown(db:SQLiteDBConnection,url:URL,init:RequestInit):Promise<Response>{
  const year=Number(url.searchParams.get('year')),month=Number(url.searchParams.get('month')),level=String(url.searchParams.get('level')||'district'),parentId=url.searchParams.get('parent_id');
  if(!validPeriod(year,month))return jsonResponse({detail:'Invalid period'},400);
  if(!['district','block','cluster','school'].includes(level))return jsonResponse({detail:'level must be district, block, cluster or school'},400);
  const snap=await adminSchoolSnapshot(db,init,year,month); if(snap.response)return snap.response;
  return jsonResponse({level,parent_id:parentId,rows:aggregate(snap.rows||[],level,parentId)});
}

async function schools(db:SQLiteDBConnection,url:URL,init:RequestInit):Promise<Response>{
  const year=Number(url.searchParams.get('year')),month=Number(url.searchParams.get('month'));
  if(!validPeriod(year,month))return jsonResponse({detail:'Invalid period'},400);
  const snap=await adminSchoolSnapshot(db,init,year,month); if(snap.response)return snap.response;
  return jsonResponse(snap.rows||[]);
}

export async function tryAndroidAdminDashboardApiFetch(path:string,init:RequestInit={}):Promise<Response|null>{
  const method=String(init.method||'GET').toUpperCase(); const url=new URL(path,'https://local.pmposhan.invalid'); const route=url.pathname;
  if(!['/admin-dashboard/summary','/admin-dashboard/drilldown','/admin-dashboard/schools'].includes(route))return null;
  if(method!=='GET')return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);
  try{
    const auth=await requireUser(init); if(auth.response)return auth.response; const user=auth.user!;
    if(!['SYSTEM_ADMIN','HEADMASTER'].includes(user.role))return jsonResponse({detail:'Administrative dashboard access denied'},403);
    const db=await getSharedAndroidDb(); await ensureSchema(db);
    if(route==='/admin-dashboard/summary')return summary(db,url,init);
    if(route==='/admin-dashboard/drilldown')return drilldown(db,url,init);
    return schools(db,url,init);
  }catch(error){return jsonResponse({detail:error instanceof Error?error.message:String(error)},400);}
}
