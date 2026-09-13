import type { SQLiteDBConnection } from '@capacitor-community/sqlite';
import { androidApiFetch } from './androidRuntime';
import { getSharedAndroidDb } from './androidSharedDb';

type LocalUser={id:string;username:string;role:string};
type ReportColumn={key:string;label_en:string;label_mr:string};
type ReportDefinition={title_en:string;title_mr:string;columns:ReportColumn[]};

const REPORT_DEFS:Record<string,ReportDefinition>={
  SCHOOL_MASTER:{
    title_en:'School Master',title_mr:'शाळा मास्टर',
    columns:[
      {key:'district',label_en:'District',label_mr:'जिल्हा'},{key:'block',label_en:'Taluka / Block',label_mr:'तालुका'},{key:'cluster',label_en:'Cluster',label_mr:'केंद्र'},
      {key:'school_code',label_en:'School Code',label_mr:'शाळा कोड'},{key:'udise_code',label_en:'UDISE Code',label_mr:'UDISE कोड'},{key:'school_name',label_en:'School Name',label_mr:'शाळेचे नाव'},
      {key:'village',label_en:'Village',label_mr:'गाव'},{key:'class_1_5_strength',label_en:'Class 1-5 Strength',label_mr:'इ. 1-5 पटसंख्या'},{key:'class_6_8_strength',label_en:'Class 6-8 Strength',label_mr:'इ. 6-8 पटसंख्या'},{key:'active',label_en:'Active',label_mr:'सक्रिय'},
    ],
  },
  MENU_RECIPES:{
    title_en:'Menu & Standard Ingredient Quantities',title_mr:'मेनू व प्रमाणित साहित्य मात्रा',
    columns:[
      {key:'menu_code',label_en:'Menu Code',label_mr:'मेनू कोड'},{key:'menu_name',label_en:'Menu Name',label_mr:'मेनू नाव'},{key:'ingredient_code',label_en:'Ingredient Code',label_mr:'साहित्य कोड'},
      {key:'ingredient_name',label_en:'Ingredient',label_mr:'साहित्य'},{key:'class_1_5_qty',label_en:'Qty/Student Class 1-5',label_mr:'इ.1-5 प्रति विद्यार्थी मात्रा'},{key:'class_6_8_qty',label_en:'Qty/Student Class 6-8',label_mr:'इ.6-8 प्रति विद्यार्थी मात्रा'},
      {key:'unit',label_en:'Unit',label_mr:'एकक'},{key:'effective_from',label_en:'Effective From',label_mr:'लागू दिनांक'},
    ],
  },
  DAILY_MEALS:{
    title_en:'Daily Meals',title_mr:'दैनिक आहार',
    columns:[
      {key:'date',label_en:'Date',label_mr:'दिनांक'},{key:'district',label_en:'District',label_mr:'जिल्हा'},{key:'block',label_en:'Taluka / Block',label_mr:'तालुका'},{key:'cluster',label_en:'Cluster',label_mr:'केंद्र'},
      {key:'school_name',label_en:'School',label_mr:'शाळा'},{key:'udise_code',label_en:'UDISE',label_mr:'UDISE'},{key:'menu_name',label_en:'Menu',label_mr:'मेनू'},
      {key:'present_1_5',label_en:'Present 1-5',label_mr:'उपस्थित 1-5'},{key:'present_6_8',label_en:'Present 6-8',label_mr:'उपस्थित 6-8'},
      {key:'meals_1_5',label_en:'Meals 1-5',label_mr:'भोजन 1-5'},{key:'meals_6_8',label_en:'Meals 6-8',label_mr:'भोजन 6-8'},{key:'total_meals',label_en:'Total Meals',label_mr:'एकूण भोजन'},
      {key:'tasting_done',label_en:'Tasting',label_mr:'चव तपासणी'},{key:'hygiene_ok',label_en:'Hygiene',label_mr:'स्वच्छता'},{key:'status',label_en:'Status',label_mr:'स्थिती'},
    ],
  },
  STOCK_LEDGER:{
    title_en:'Stock Ledger',title_mr:'साठा नोंदवही',
    columns:[
      {key:'date',label_en:'Date',label_mr:'दिनांक'},{key:'district',label_en:'District',label_mr:'जिल्हा'},{key:'block',label_en:'Taluka / Block',label_mr:'तालुका'},{key:'cluster',label_en:'Cluster',label_mr:'केंद्र'},
      {key:'school_name',label_en:'School',label_mr:'शाळा'},{key:'ingredient',label_en:'Ingredient',label_mr:'साहित्य'},{key:'transaction_type',label_en:'Transaction Type',label_mr:'व्यवहार प्रकार'},
      {key:'quantity',label_en:'Quantity',label_mr:'मात्रा'},{key:'unit',label_en:'Unit',label_mr:'एकक'},{key:'reference_no',label_en:'Reference No.',label_mr:'संदर्भ क्र.'},{key:'remarks',label_en:'Remarks',label_mr:'शेरा'},
    ],
  },
  MONTHLY_RETURNS:{
    title_en:'Monthly School Returns',title_mr:'मासिक शाळा परतावा',
    columns:[
      {key:'year',label_en:'Year',label_mr:'वर्ष'},{key:'month',label_en:'Month',label_mr:'महिना'},{key:'district',label_en:'District',label_mr:'जिल्हा'},{key:'block',label_en:'Taluka / Block',label_mr:'तालुका'},{key:'cluster',label_en:'Cluster',label_mr:'केंद्र'},
      {key:'school_name',label_en:'School',label_mr:'शाळा'},{key:'udise_code',label_en:'UDISE',label_mr:'UDISE'},{key:'recorded_days',label_en:'Recorded Days',label_mr:'नोंद दिवस'},{key:'verified_days',label_en:'Verified Days',label_mr:'पडताळलेले दिवस'},
      {key:'incomplete_days',label_en:'Incomplete Days',label_mr:'अपूर्ण दिवस'},{key:'attendance_1_5',label_en:'Attendance 1-5',label_mr:'उपस्थिती 1-5'},{key:'attendance_6_8',label_en:'Attendance 6-8',label_mr:'उपस्थिती 6-8'},
      {key:'meals_1_5',label_en:'Meals 1-5',label_mr:'भोजन 1-5'},{key:'meals_6_8',label_en:'Meals 6-8',label_mr:'भोजन 6-8'},{key:'total_meals',label_en:'Total Meals',label_mr:'एकूण भोजन'},{key:'status',label_en:'Status',label_mr:'स्थिती'},
    ],
  },
};

function jsonResponse(body:unknown,status=200,headers:Record<string,string>={}):Response{return new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json',...headers}});}
function num(v:unknown):number{const n=Number(v);return Number.isFinite(n)?n:0;}
function bool(v:unknown):boolean{return v===true||Number(v)===1;}
function pad(n:number):string{return String(n).padStart(2,'0');}
function validPeriod(year:number,month:number):boolean{return Number.isInteger(year)&&year>=2000&&year<=2200&&Number.isInteger(month)&&month>=1&&month<=12;}
function daysInMonth(year:number,month:number):number{return new Date(Date.UTC(year,month,0)).getUTCDate();}
function isoDate(year:number,month:number,day:number):string{return `${year}-${pad(month)}-${pad(day)}`;}
function xmlEscape(value:unknown):string{return String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&apos;');}

async function bodyJson(init:RequestInit):Promise<any>{if(!init.body)return {};if(typeof init.body==='string')return JSON.parse(init.body||'{}');throw new Error('ANDROID_BODY_TYPE_UNSUPPORTED');}
async function requireUser(init:RequestInit):Promise<{response?:Response;user?:LocalUser}>{const r=await androidApiFetch('/me',{headers:init.headers||{}});if(!r.ok)return {response:r};const me=await r.json();return {user:{id:String(me.sub||''),username:String(me.username||me.preferred_username||''),role:String(me.role||me.roles?.[0]||'')}};}
async function accessibleIds(init:RequestInit):Promise<{response?:Response;ids?:string[]}>{const r=await androidApiFetch('/schools',{headers:init.headers||{}});if(!r.ok)return {response:r};const rows=await r.json();return {ids:Array.isArray(rows)?rows.map((x:any)=>String(x.id)):[]};}

async function ensureSchema(db:SQLiteDBConnection):Promise<void>{
  await db.execute(`
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS daily_attendance (
      id TEXT PRIMARY KEY,school_id TEXT NOT NULL,meal_date TEXT NOT NULL,
      class_1_5_enrolled INTEGER NOT NULL DEFAULT 0,class_1_5_present INTEGER NOT NULL DEFAULT 0,
      class_6_8_enrolled INTEGER NOT NULL DEFAULT 0,class_6_8_present INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'DRAFT',entered_by_subject TEXT,entered_by_username TEXT,
      verified_by_subject TEXT,verified_by_username TEXT,verified_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,meal_date)
    );
    CREATE TABLE IF NOT EXISTS daily_meal_entries (
      id TEXT PRIMARY KEY,school_id TEXT NOT NULL,meal_date TEXT NOT NULL,menu_id TEXT,
      meals_class_1_5 INTEGER NOT NULL DEFAULT 0,meals_class_6_8 INTEGER NOT NULL DEFAULT 0,total_meals INTEGER NOT NULL DEFAULT 0,
      tasting_done INTEGER NOT NULL DEFAULT 0,hygiene_ok INTEGER NOT NULL DEFAULT 0,remarks TEXT,status TEXT NOT NULL DEFAULT 'DRAFT',
      entered_by_subject TEXT,entered_by_username TEXT,verified_by_subject TEXT,verified_by_username TEXT,verified_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,meal_date)
    );
    CREATE TABLE IF NOT EXISTS stock_transactions (
      id TEXT PRIMARY KEY,school_id TEXT NOT NULL,ingredient_id TEXT NOT NULL,transaction_date TEXT NOT NULL,transaction_type TEXT NOT NULL,quantity REAL NOT NULL,
      reference_type TEXT,reference_id TEXT,reference_no TEXT,remarks TEXT,entered_by_subject TEXT,entered_by_username TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS monthly_school_returns (
      id TEXT PRIMARY KEY,school_id TEXT NOT NULL,year INTEGER NOT NULL,month INTEGER NOT NULL,
      recorded_days INTEGER NOT NULL DEFAULT 0,verified_days INTEGER NOT NULL DEFAULT 0,incomplete_days INTEGER NOT NULL DEFAULT 0,
      attendance_class_1_5 INTEGER NOT NULL DEFAULT 0,attendance_class_6_8 INTEGER NOT NULL DEFAULT 0,
      meals_class_1_5 INTEGER NOT NULL DEFAULT 0,meals_class_6_8 INTEGER NOT NULL DEFAULT 0,total_meals INTEGER NOT NULL DEFAULT 0,
      tasting_exception_days INTEGER NOT NULL DEFAULT 0,hygiene_exception_days INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'DRAFT',
      generated_by_subject TEXT,generated_by_username TEXT,generated_at TEXT,submitted_by_subject TEXT,submitted_by_username TEXT,submitted_at TEXT,
      cluster_reviewed_by TEXT,cluster_reviewed_at TEXT,block_approved_by TEXT,block_approved_at TEXT,return_reason TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(school_id,year,month)
    );
  `);
}

async function hierarchyRows(db:SQLiteDBConnection):Promise<any[]>{
  const q=await db.query(`SELECT s.id AS school_id,s.code AS school_code,s.udise_code,s.name_en AS school_name_en,s.name_mr AS school_name_mr,s.village,s.class_1_5_strength,s.class_6_8_strength,s.active,
    c.id AS cluster_id,c.name_en AS cluster_name_en,c.name_mr AS cluster_name_mr,
    b.id AS block_id,b.name_en AS block_name_en,b.name_mr AS block_name_mr,
    d.id AS district_id,d.name_en AS district_name_en,d.name_mr AS district_name_mr
    FROM schools s LEFT JOIN clusters c ON c.id=s.cluster_id LEFT JOIN blocks b ON b.id=c.block_id LEFT JOIN districts d ON d.id=b.district_id`);
  return q.values||[];
}

async function filteredSchools(db:SQLiteDBConnection,init:RequestInit,p:any):Promise<{response?:Response;rows?:any[]}>
{
  const a=await accessibleIds(init);if(a.response)return {response:a.response};const allowed=new Set(a.ids||[]);let rows=(await hierarchyRows(db)).filter(r=>allowed.has(String(r.school_id)));
  if(p.school_id)rows=rows.filter(r=>String(r.school_id)===String(p.school_id));
  if(p.cluster_id)rows=rows.filter(r=>String(r.cluster_id)===String(p.cluster_id));
  if(p.block_id)rows=rows.filter(r=>String(r.block_id)===String(p.block_id));
  if(p.district_id)rows=rows.filter(r=>String(r.district_id)===String(p.district_id));
  return {rows};
}

function orgNames(s:any,lang:string):{district:string;block:string;cluster:string;school:string}{
  return {district:String(lang==='mr'?s.district_name_mr||'':s.district_name_en||''),block:String(lang==='mr'?s.block_name_mr||'':s.block_name_en||''),cluster:String(lang==='mr'?s.cluster_name_mr||'':s.cluster_name_en||''),school:String(lang==='mr'?s.school_name_mr||'':s.school_name_en||'')};
}

async function reportRows(db:SQLiteDBConnection,init:RequestInit,p:any):Promise<{response?:Response;rows?:any[]}>
{
  const f=await filteredSchools(db,init,p);if(f.response)return {response:f.response};const schools=f.rows||[];const byId=new Map(schools.map(s=>[String(s.school_id),s]));const lang=String(p.language||'en');const rows:any[]=[];
  if(p.report_type==='SCHOOL_MASTER'){
    for(const s of schools){const o=orgNames(s,lang);rows.push({district:o.district,block:o.block,cluster:o.cluster,school_code:s.school_code,udise_code:s.udise_code,school_name:o.school,village:s.village||'',class_1_5_strength:num(s.class_1_5_strength),class_6_8_strength:num(s.class_6_8_strength),active:bool(s.active)});}
  }else if(p.report_type==='MENU_RECIPES'){
    const q=await db.query(`SELECT m.code AS menu_code,m.name_en AS menu_name_en,m.name_mr AS menu_name_mr,i.code AS ingredient_code,i.name_en AS ingredient_name_en,i.name_mr AS ingredient_name_mr,
      r.ingredient_id,r.effective_from,r.student_group,r.qty_per_student,r.measurement_unit,i.base_unit
      FROM recipes r JOIN menus m ON m.id=r.menu_id JOIN ingredients i ON i.id=r.ingredient_id WHERE r.active=1 AND m.active=1 ORDER BY m.code,i.code,r.effective_from,r.student_group`);
    const grouped=new Map<string,any>();
    for(const r of q.values||[]){const key=`${r.menu_code}|${r.ingredient_id}|${r.effective_from}`;const g=grouped.get(key)||{...r,q15:0,q68:0,qall:0};const qty=num(r.qty_per_student);if(r.student_group==='CLASS_1_5')g.q15+=qty;else if(r.student_group==='CLASS_6_8')g.q68+=qty;else if(r.student_group==='ALL')g.qall+=qty;grouped.set(key,g);}
    for(const g of grouped.values())rows.push({menu_code:g.menu_code,menu_name:lang==='mr'?g.menu_name_mr:g.menu_name_en,ingredient_code:g.ingredient_code,ingredient_name:lang==='mr'?g.ingredient_name_mr:g.ingredient_name_en,class_1_5_qty:g.q15+g.qall,class_6_8_qty:g.q68+g.qall,unit:g.measurement_unit||g.base_unit,effective_from:g.effective_from});
  }else if(p.report_type==='DAILY_MEALS'){
    const q=await db.query(`SELECT m.*,a.class_1_5_present,a.class_6_8_present,menu.name_en AS menu_name_en,menu.name_mr AS menu_name_mr
      FROM daily_meal_entries m LEFT JOIN daily_attendance a ON a.school_id=m.school_id AND a.meal_date=m.meal_date LEFT JOIN menus menu ON menu.id=m.menu_id ORDER BY m.meal_date,m.school_id`);
    for(const m of q.values||[]){const s=byId.get(String(m.school_id));if(!s)continue;if(p.date_from&&String(m.meal_date)<String(p.date_from))continue;if(p.date_to&&String(m.meal_date)>String(p.date_to))continue;const o=orgNames(s,lang);rows.push({date:m.meal_date,district:o.district,block:o.block,cluster:o.cluster,school_name:o.school,udise_code:s.udise_code,menu_name:lang==='mr'?m.menu_name_mr||'':m.menu_name_en||'',present_1_5:num(m.class_1_5_present),present_6_8:num(m.class_6_8_present),meals_1_5:num(m.meals_class_1_5),meals_6_8:num(m.meals_class_6_8),total_meals:num(m.total_meals),tasting_done:bool(m.tasting_done),hygiene_ok:bool(m.hygiene_ok),status:m.status});}
  }else if(p.report_type==='STOCK_LEDGER'){
    const q=await db.query(`SELECT t.*,i.name_en AS ingredient_name_en,i.name_mr AS ingredient_name_mr,i.base_unit FROM stock_transactions t LEFT JOIN ingredients i ON i.id=t.ingredient_id ORDER BY t.transaction_date,t.school_id`);
    for(const x of q.values||[]){const s=byId.get(String(x.school_id));if(!s)continue;if(p.date_from&&String(x.transaction_date)<String(p.date_from))continue;if(p.date_to&&String(x.transaction_date)>String(p.date_to))continue;const o=orgNames(s,lang);rows.push({date:x.transaction_date,district:o.district,block:o.block,cluster:o.cluster,school_name:o.school,ingredient:lang==='mr'?x.ingredient_name_mr||'':x.ingredient_name_en||'',transaction_type:x.transaction_type,quantity:num(x.quantity),unit:x.base_unit||'',reference_no:x.reference_no||'',remarks:x.remarks||''});}
  }else if(p.report_type==='MONTHLY_RETURNS'){
    const q=await db.query('SELECT * FROM monthly_school_returns ORDER BY year,month,school_id');
    for(const r of q.values||[]){const s=byId.get(String(r.school_id));if(!s)continue;if(p.year&&num(r.year)!==num(p.year))continue;if(p.month&&num(r.month)!==num(p.month))continue;const o=orgNames(s,lang);rows.push({year:num(r.year),month:num(r.month),district:o.district,block:o.block,cluster:o.cluster,school_name:o.school,udise_code:s.udise_code,recorded_days:num(r.recorded_days),verified_days:num(r.verified_days),incomplete_days:num(r.incomplete_days),attendance_1_5:num(r.attendance_class_1_5),attendance_6_8:num(r.attendance_class_6_8),meals_1_5:num(r.meals_class_1_5),meals_6_8:num(r.meals_class_6_8),total_meals:num(r.total_meals),status:r.status});}
  }else return {response:jsonResponse({detail:'Unknown report type'},422)};
  return {rows};
}

async function definitions():Promise<Response>{return jsonResponse(Object.entries(REPORT_DEFS).map(([report_type,v])=>({report_type,title_en:v.title_en,title_mr:v.title_mr,columns:v.columns})));}

async function preview(db:SQLiteDBConnection,init:RequestInit):Promise<Response>{
  const p=await bodyJson(init);const def=REPORT_DEFS[String(p.report_type||'')];if(!def)return jsonResponse({detail:'Unknown report type'},422);const allowed=def.columns.map(c=>c.key);const requested=Array.isArray(p.columns)?p.columns.map(String).filter((x:string)=>allowed.includes(x)):[];const selected=requested.length?requested:allowed;
  const result=await reportRows(db,init,p);if(result.response)return result.response;const all=result.rows||[];const limit=Math.max(1,Math.min(1000,num(p.max_preview_rows)||100));
  return jsonResponse({columns:selected.map(key=>({key,label:(def.columns.find(c=>c.key===key)?.[String(p.language||'en')==='mr'?'label_mr':'label_en'])||key})),rows:all.slice(0,limit).map(r=>Object.fromEntries(selected.map(k=>[k,r[k]]))),total_rows:all.length});
}

async function excel(db:SQLiteDBConnection,init:RequestInit):Promise<Response>{
  const p=await bodyJson(init);const def=REPORT_DEFS[String(p.report_type||'')];if(!def)return jsonResponse({detail:'Unknown report type'},422);const allowed=def.columns.map(c=>c.key);const requested=Array.isArray(p.columns)?p.columns.map(String).filter((x:string)=>allowed.includes(x)):[];const selected=requested.length?requested:allowed;
  const result=await reportRows(db,init,p);if(result.response)return result.response;const rows=result.rows||[];const mr=String(p.language||'en')==='mr';const labels=selected.map(k=>mr?(def.columns.find(c=>c.key===k)?.label_mr||k):(def.columns.find(c=>c.key===k)?.label_en||k));
  const cell=(v:unknown)=>`<Cell><Data ss:Type="${typeof v==='number'?'Number':'String'}">${xmlEscape(typeof v==='boolean'?(mr?(v?'होय':'नाही'):(v?'Yes':'No')):v)}</Data></Cell>`;
  const title=mr?def.title_mr:def.title_en;const sheetRows=[`<Row><Cell ss:MergeAcross="${Math.max(0,selected.length-1)}"><Data ss:Type="String">${xmlEscape(`PM POSHAN - ${title}`)}</Data></Cell></Row>`,`<Row>${labels.map(cell).join('')}</Row>`,...rows.map(r=>`<Row>${selected.map(k=>cell(r[k])).join('')}</Row>`)].join('');
  const xml=`<?xml version="1.0" encoding="UTF-8"?><?mso-application progid="Excel.Sheet"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Report"><Table>${sheetRows}</Table></Worksheet></Workbook>`;
  const filename=`PM_POSHAN_${String(p.report_type||'REPORT')}_${new Date().toISOString().replace(/[-:T]/g,'').slice(0,14)}.xls`;
  return new Response(xml,{status:200,headers:{'Content-Type':'application/vnd.ms-excel; charset=utf-8','Content-Disposition':`attachment; filename="${filename}"`,'X-PMPoshan-Filename':filename}});
}

async function districts(db:SQLiteDBConnection):Promise<Response>{const q=await db.query('SELECT id,code,name_en,name_mr,active FROM districts WHERE active=1 ORDER BY name_en');return jsonResponse(q.values||[]);}

async function stockMonthlySummary(db:SQLiteDBConnection,url:URL,init:RequestInit):Promise<Response>{
  const schoolId=String(url.searchParams.get('school_id')||'');const year=Number(url.searchParams.get('year'));const month=Number(url.searchParams.get('month'));if(!schoolId||!validPeriod(year,month))return jsonResponse({detail:'Invalid school/year/month'},400);
  const a=await accessibleIds(init);if(a.response)return a.response;if(!(a.ids||[]).includes(schoolId))return jsonResponse({detail:'NO_SCHOOL_ACCESS'},403);
  const first=isoDate(year,month,1),last=isoDate(year,month,daysInMonth(year,month));
  const iq=await db.query('SELECT id,code,name_en,name_mr,base_unit,reorder_level FROM ingredients WHERE active=1 AND track_inventory=1 ORDER BY name_en');const out:any[]=[];
  for(const ing of iq.values||[]){const oq=await db.query('SELECT COALESCE(SUM(quantity),0) AS q FROM stock_transactions WHERE school_id=? AND ingredient_id=? AND transaction_date<?',[schoolId,ing.id,first]);const openingBefore=num(oq.values?.[0]?.q);const pq=await db.query('SELECT transaction_type,COALESCE(SUM(quantity),0) AS q FROM stock_transactions WHERE school_id=? AND ingredient_id=? AND transaction_date>=? AND transaction_date<=? GROUP BY transaction_type',[schoolId,ing.id,first,last]);const by=new Map<string,number>((pq.values||[]).map((r:any)=>[String(r.transaction_type),num(r.q)]));const openingPeriod=by.get('OPENING')||0;const receipts=by.get('RECEIPT')||0;const rawConsumption=by.get('CONSUMPTION')||0;const adjustments=(by.get('ADJUSTMENT')||0)+(by.get('PHYSICAL_ADJUSTMENT')||0);let periodTotal=0;for(const v of by.values())periodTotal+=v;const closing=openingBefore+periodTotal;const reorder=num(ing.reorder_level);out.push({ingredient_id:ing.id,code:ing.code,name_en:ing.name_en,name_mr:ing.name_mr,unit:ing.base_unit,opening:openingBefore+openingPeriod,receipts,consumption:Math.abs(rawConsumption),adjustments,closing,reorder_level:reorder,low_stock:reorder>0?closing<=reorder:false});}
  return jsonResponse({school_id:schoolId,year,month,from_date:first,to_date:last,items:out});
}

export async function tryAndroidReportingApiFetch(path:string,init:RequestInit={}):Promise<Response|null>{
  const method=String(init.method||'GET').toUpperCase();const url=new URL(path,'https://local.pmposhan.invalid');const route=url.pathname;
  const relevant=route==='/districts'||route==='/stock/monthly-summary'||route==='/custom-reports/definitions'||route==='/custom-reports/preview'||route==='/custom-reports/excel';if(!relevant)return null;
  try{const auth=await requireUser(init);if(auth.response)return auth.response;const db=await getSharedAndroidDb();await ensureSchema(db);
    if(route==='/districts'&&method==='GET')return districts(db);
    if(route==='/stock/monthly-summary'&&method==='GET')return stockMonthlySummary(db,url,init);
    if(route==='/custom-reports/definitions'&&method==='GET')return definitions();
    if(route==='/custom-reports/preview'&&method==='POST')return preview(db,init);
    if(route==='/custom-reports/excel'&&method==='POST')return excel(db,init);
    return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);
  }catch(error){return jsonResponse({detail:error instanceof Error?error.message:String(error)},400);}
}
