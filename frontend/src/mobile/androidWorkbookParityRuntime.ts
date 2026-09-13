import type { SQLiteDBConnection } from '@capacitor-community/sqlite';
import { androidApiFetch } from './androidRuntime';
import { tryAndroidMasterApiFetch } from './androidMasterRuntime';
import { tryAndroidOperationsApiFetch } from './androidOperationsRuntime';
import { tryAndroidStockApiFetch } from './androidStockRuntime';
import { getSharedAndroidDb } from './androidSharedDb';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: {'Content-Type':'application/json'} });
}
function uuid():string{return crypto.randomUUID();}
function num(v:unknown):number{const n=Number(v);return Number.isFinite(n)?n:0;}
function pad(v:number):string{return String(v).padStart(2,'0');}
function isIsoDate(value: string): boolean { return /^\d{4}-\d{2}-\d{2}$/.test(value); }
function nonNegativeInt(value: string | null, fallback: number): number { if (value === null || value === '') return Math.max(0, Math.trunc(Number(fallback) || 0)); const n = Number(value); return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : Math.max(0, Math.trunc(Number(fallback) || 0)); }
function xmlEscape(v:unknown):string{return String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&apos;');}
function monthRange(year:number,month:number):[string,string]{const last=new Date(Date.UTC(year,month,0)).getUTCDate();return [`${year}-${pad(month)}-01`,`${year}-${pad(month)}-${pad(last)}`];}
function validPeriod(year:number,month:number):boolean{return Number.isInteger(year)&&year>=2000&&year<=2200&&Number.isInteger(month)&&month>=1&&month<=12;}

async function bodyJson(init:RequestInit):Promise<any>{if(!init.body)return {};if(typeof init.body==='string')return JSON.parse(init.body||'{}');throw new Error('ANDROID_BODY_TYPE_UNSUPPORTED');}
async function requireUser(init:RequestInit):Promise<{response?:Response;user?:any}>{const r=await androidApiFetch('/me',{headers:init.headers||{}});if(!r.ok)return {response:r};return {user:await r.json()};}
async function requireSchool(init:RequestInit,schoolId:string):Promise<{response?:Response;school?:any}>{const r=await androidApiFetch('/schools',{headers:init.headers||{}});if(!r.ok)return {response:r};const rows=await r.json();const school=Array.isArray(rows)?rows.find((x:any)=>String(x.id)===schoolId):null;return school?{school}:{response:jsonResponse({detail:'NO_SCHOOL_ACCESS'},403)};}

async function ensureSchema(db:SQLiteDBConnection):Promise<void>{
  await db.execute(`
    CREATE TABLE IF NOT EXISTS stock_loans (
      id TEXT PRIMARY KEY,school_id TEXT NOT NULL,loan_date TEXT NOT NULL,loan_no TEXT NOT NULL,direction TEXT NOT NULL,
      counterparty_name TEXT NOT NULL,ingredient_id TEXT NOT NULL,quantity REAL NOT NULL,remarks TEXT,
      entered_by_subject TEXT,entered_by_username TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS bmi_records (
      id TEXT PRIMARY KEY,school_id TEXT NOT NULL,measurement_date TEXT NOT NULL,student_identifier TEXT,student_name TEXT NOT NULL,
      class_name TEXT,gender TEXT,height_cm REAL NOT NULL,weight_kg REAL NOT NULL,bmi REAL NOT NULL,remarks TEXT,
      entered_by_subject TEXT,entered_by_username TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS school_calendar_days (
      id TEXT PRIMARY KEY,school_id TEXT NOT NULL,calendar_date TEXT NOT NULL,day_type TEXT NOT NULL DEFAULT 'WORKING',reason TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(school_id,calendar_date)
    );
    CREATE TABLE IF NOT EXISTS stock_transactions (
      id TEXT PRIMARY KEY,school_id TEXT NOT NULL,ingredient_id TEXT NOT NULL,transaction_date TEXT NOT NULL,transaction_type TEXT NOT NULL,quantity REAL NOT NULL,
      reference_type TEXT,reference_id TEXT,reference_no TEXT,remarks TEXT,entered_by_subject TEXT,entered_by_username TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
  `);
}

async function rationPreview(path:string,init:RequestInit):Promise<Response>{
  const url=new URL(path,'https://local.pmposhan.invalid');
  const schoolId=String(url.searchParams.get('school_id')||''); const rationDate=String(url.searchParams.get('ration_date')||'');
  if(!schoolId||!isIsoDate(rationDate))return jsonResponse({detail:'RATION_PREVIEW_FIELDS_INVALID'},400);
  const access=await requireSchool(init,schoolId);if(access.response)return access.response;const school=access.school;
  const class15=nonNegativeInt(url.searchParams.get('class_1_5'),Number(school.class_1_5_strength||0));const class68=nonNegativeInt(url.searchParams.get('class_6_8'),Number(school.class_6_8_strength||0));
  const planResponse=await tryAndroidOperationsApiFetch(`/menu-plan?school_id=${encodeURIComponent(schoolId)}&menu_date=${rationDate}`,init);if(!planResponse)return jsonResponse({detail:'ANDROID_MENU_PLAN_UNAVAILABLE'},501);if(!planResponse.ok)return planResponse;const planData=await planResponse.json();const plan=planData?.plan;if(!plan?.menu_id)return jsonResponse({detail:'No menu planned for this date'},404);
  const previewResponse=await tryAndroidMasterApiFetch(`/menus/${encodeURIComponent(String(plan.menu_id))}/recipe-preview?on_date=${rationDate}&class_1_5=${class15}&class_6_8=${class68}`,init);if(!previewResponse)return jsonResponse({detail:'ANDROID_RECIPE_PREVIEW_UNAVAILABLE'},501);if(!previewResponse.ok)return previewResponse;const preview=await previewResponse.json();
  const balanceResponse=await tryAndroidStockApiFetch(`/stock/balances?school_id=${encodeURIComponent(schoolId)}`,init);if(!balanceResponse)return jsonResponse({detail:'ANDROID_STOCK_BALANCE_UNAVAILABLE'},501);if(!balanceResponse.ok)return balanceResponse;const balances=await balanceResponse.json();const balanceMap=new Map<string,number>((Array.isArray(balances)?balances:[]).map((x:any)=>[String(x.ingredient_id),Number(x.balance||0)]));
  const items=(Array.isArray(preview?.items)?preview.items:[]).map((x:any)=>{const required=Number(x.required_total||0);const available=Number(balanceMap.get(String(x.ingredient_id))||0);return {...x,required_total:required,available,shortage:Math.max(0,required-available)};});
  return jsonResponse({school_id:schoolId,ration_date:rationDate,menu:{id:String(plan.menu_id),code:plan.menu_code||null,name_en:plan.menu_name_en||null,name_mr:plan.menu_name_mr||null},class_1_5:class15,class_6_8:class68,items});
}

async function saveLoan(db:SQLiteDBConnection,init:RequestInit,user:any):Promise<Response>{
  if(!['HEADMASTER','SYSTEM_ADMIN'].includes(String(user.role||user.roles?.[0]||'')))return jsonResponse({detail:'HEADMASTER_OR_ADMIN_REQUIRED'},403);
  const p=await bodyJson(init);const schoolId=String(p.school_id||'');const ingredientId=String(p.ingredient_id||'');const date=String(p.loan_date||'');const direction=String(p.direction||'').toUpperCase();const qty=num(p.quantity);
  if(!schoolId||!ingredientId||!isIsoDate(date)||!['RECEIVED','GIVEN'].includes(direction)||qty<=0||!String(p.loan_no||'').trim()||!String(p.counterparty_name||'').trim())return jsonResponse({detail:'LOAN_FIELDS_INVALID'},422);
  const access=await requireSchool(init,schoolId);if(access.response)return access.response;
  const ing=await db.query('SELECT id FROM ingredients WHERE id=? AND active=1',[ingredientId]);if(!ing.values?.length)return jsonResponse({detail:'Ingredient not found'},404);
  if(direction==='GIVEN'){const q=await db.query('SELECT COALESCE(SUM(quantity),0) AS balance FROM stock_transactions WHERE school_id=? AND ingredient_id=?',[schoolId,ingredientId]);if(num(q.values?.[0]?.balance)<qty)return jsonResponse({detail:'Insufficient stock for loan given'},409);}
  const id=uuid();await db.run(`INSERT INTO stock_loans (id,school_id,loan_date,loan_no,direction,counterparty_name,ingredient_id,quantity,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?,?)`,[id,schoolId,date,String(p.loan_no).trim(),direction,String(p.counterparty_name).trim(),ingredientId,qty,String(p.remarks||''),String(user.sub||''),String(user.username||'')]);
  const signed=direction==='RECEIVED'?qty:-qty;await db.run(`INSERT INTO stock_transactions (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`,[uuid(),schoolId,ingredientId,date,signed>0?'LOAN_IN':'LOAN_OUT',signed,'STOCK_LOAN',id,String(p.loan_no).trim(),`${direction}: ${String(p.counterparty_name).trim()}`,String(user.sub||''),String(user.username||'')]);
  return jsonResponse({ok:true,id});
}

async function saveBmi(db:SQLiteDBConnection,init:RequestInit,user:any):Promise<Response>{
  if(!['TEACHER','HEADMASTER','SYSTEM_ADMIN'].includes(String(user.role||user.roles?.[0]||'')))return jsonResponse({detail:'ROLE_NOT_ALLOWED'},403);
  const p=await bodyJson(init);const schoolId=String(p.school_id||'');const date=String(p.measurement_date||'');const h=num(p.height_cm),w=num(p.weight_kg);if(!schoolId||!isIsoDate(date)||!String(p.student_name||'').trim()||h<=0||w<=0)return jsonResponse({detail:'BMI_FIELDS_INVALID'},422);const access=await requireSchool(init,schoolId);if(access.response)return access.response;const bmi=Math.round((w/((h/100)*(h/100)))*100)/100;const id=uuid();await db.run(`INSERT INTO bmi_records (id,school_id,measurement_date,student_identifier,student_name,class_name,gender,height_cm,weight_kg,bmi,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,[id,schoolId,date,String(p.student_identifier||''),String(p.student_name).trim(),String(p.class_name||''),String(p.gender||''),h,w,bmi,String(p.remarks||''),String(user.sub||''),String(user.username||'')]);return jsonResponse({ok:true,id,bmi});
}

function excelXml(title:string,headers:string[],rows:unknown[][]):string{
  const cell=(v:unknown)=>`<Cell><Data ss:Type="${typeof v==='number'?'Number':'String'}">${xmlEscape(v)}</Data></Cell>`;
  const heading=`<Row><Cell ss:MergeAcross="${Math.max(0,headers.length-1)}"><Data ss:Type="String">${xmlEscape(title)}</Data></Cell></Row>`;
  const header=`<Row>${headers.map(cell).join('')}</Row>`;const body=rows.map(r=>`<Row>${r.map(cell).join('')}</Row>`).join('');
  return `<?xml version="1.0" encoding="UTF-8"?><?mso-application progid="Excel.Sheet"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="Report"><Table>${heading}${header}${body}</Table></Worksheet></Workbook>`;
}
function excelResponse(title:string,headers:string[],rows:unknown[][],filename:string):Response{const xml=excelXml(title,headers,rows);return new Response(xml,{status:200,headers:{'Content-Type':'application/vnd.ms-excel; charset=utf-8','Content-Disposition':`attachment; filename="${filename}"`,'X-PMPoshan-Filename':filename}});}

async function exportReport(db:SQLiteDBConnection,url:URL,init:RequestInit,marathi:boolean,exact=false):Promise<Response>{
  const schoolId=String(url.searchParams.get('school_id')||'');const year=Number(url.searchParams.get('year'));const month=Number(url.searchParams.get('month'));if(!schoolId||!validPeriod(year,month))return jsonResponse({detail:'Invalid school/year/month'},400);const access=await requireSchool(init,schoolId);if(access.response)return access.response;const school=access.school;const [first,last]=monthRange(year,month);let report=exact?String(url.searchParams.get('format')||''):String(url.searchParams.get('report_type')||'');if(report==='MONTHLY_CENTER')report='MONTHLY';if(report==='DAILY_PART2')report='PART2';report=report.toUpperCase();let headers:string[]=[];let rows:unknown[][]=[];
  if(report==='PART1'){
    headers=marathi?['दिनांक','पटसंख्या','उपस्थित','तांदूळ प्राप्त','उसणवार प्राप्त','तांदूळ वापर','शिल्लक']:['Date','Enrolment','Present','Rice Received','Loan In','Rice Consumed','Closing Rice'];const rice=await db.query("SELECT id FROM ingredients WHERE code='RICE' LIMIT 1");const iid=String(rice.values?.[0]?.id||'');let balance=0;if(iid){const pre=await db.query('SELECT COALESCE(SUM(quantity),0) AS q FROM stock_transactions WHERE school_id=? AND ingredient_id=? AND transaction_date<?',[schoolId,iid,first]);balance=num(pre.values?.[0]?.q);}for(let d=1;d<=Number(last.slice(8));d++){const dt=`${year}-${pad(month)}-${pad(d)}`;const a=await db.query('SELECT * FROM daily_attendance WHERE school_id=? AND meal_date=?',[schoolId,dt]);const ar=a.values?.[0];let rec=0,loan=0,con=0;if(iid){const t=await db.query('SELECT transaction_type,quantity FROM stock_transactions WHERE school_id=? AND ingredient_id=? AND transaction_date=?',[schoolId,iid,dt]);for(const x of t.values||[]){const q=num(x.quantity);balance+=q;if(q>0&&x.transaction_type!=='LOAN_IN')rec+=q;if(x.transaction_type==='LOAN_IN')loan+=q;if(x.transaction_type==='CONSUMPTION')con+=Math.abs(q);}}rows.push([dt,num(ar?.class_1_5_enrolled)+num(ar?.class_6_8_enrolled),num(ar?.class_1_5_present)+num(ar?.class_6_8_present),rec,loan,con,balance]);}
  }else if(report==='PART2'){
    headers=marathi?['दिनांक','मेनू','उपस्थित','भोजन','चव तपासणी','स्वच्छता','स्थिती']:['Date','Menu','Present','Meals','Tasting','Hygiene','Status'];const q=await db.query(`SELECT m.meal_date,m.meals_class_1_5,m.meals_class_6_8,m.tasting_done,m.hygiene_ok,m.status,mu.name_en,mu.name_mr,a.class_1_5_present,a.class_6_8_present FROM daily_meal_entries m LEFT JOIN menus mu ON mu.id=m.menu_id LEFT JOIN daily_attendance a ON a.school_id=m.school_id AND a.meal_date=m.meal_date WHERE m.school_id=? AND m.meal_date BETWEEN ? AND ? ORDER BY m.meal_date`,[schoolId,first,last]);rows=(q.values||[]).map((r:any)=>[r.meal_date,marathi?(r.name_mr||r.name_en||''):(r.name_en||r.name_mr||''),num(r.class_1_5_present)+num(r.class_6_8_present),num(r.meals_class_1_5)+num(r.meals_class_6_8),Number(r.tasting_done)?(marathi?'होय':'Yes'):(marathi?'नाही':'No'),Number(r.hygiene_ok)?(marathi?'होय':'Yes'):(marathi?'नाही':'No'),r.status]);
  }else if(report==='RATION'){
    headers=marathi?['दिनांक','मेनू','घटक','एकक','इ.1-5 मात्रा','इ.6-8 मात्रा','एकूण आवश्यक']:['Date','Menu','Ingredient','Unit','Class 1-5 Qty','Class 6-8 Qty','Required Total'];const q=await db.query(`SELECT ms.menu_date,m.name_en AS menu_en,m.name_mr AS menu_mr,i.name_en AS ing_en,i.name_mr AS ing_mr,i.base_unit,r.student_group,r.qty_per_student FROM menu_schedules ms JOIN menus m ON m.id=ms.menu_id JOIN recipes r ON r.menu_id=ms.menu_id JOIN ingredients i ON i.id=r.ingredient_id WHERE ms.school_id=? AND ms.menu_date BETWEEN ? AND ? AND r.active=1 ORDER BY ms.menu_date,m.code,i.code,r.student_group`,[schoolId,first,last]);const grouped=new Map<string,any>();for(const r of q.values||[]){const k=`${r.menu_date}|${r.menu_en}|${r.ing_en}`;const g=grouped.get(k)||{date:r.menu_date,menu:marathi?(r.menu_mr||r.menu_en):(r.menu_en||r.menu_mr),ing:marathi?(r.ing_mr||r.ing_en):(r.ing_en||r.ing_mr),unit:r.base_unit,q15:0,q68:0};if(r.student_group==='CLASS_1_5')g.q15+=num(r.qty_per_student)*num(school.class_1_5_strength);else if(r.student_group==='CLASS_6_8')g.q68+=num(r.qty_per_student)*num(school.class_6_8_strength);grouped.set(k,g);}rows=[...grouped.values()].map(g=>[g.date,g.menu,g.ing,g.unit,g.q15,g.q68,g.q15+g.q68]);
  }else if(report==='MONTHLY'||report==='SUMMARY'){
    headers=marathi?['वर्ष','महिना','नोंद दिवस','पडताळलेले दिवस','अपूर्ण दिवस','उपस्थिती 1-5','उपस्थिती 6-8','भोजन 1-5','भोजन 6-8','एकूण भोजन','स्थिती']:['Year','Month','Recorded Days','Verified Days','Incomplete Days','Attendance 1-5','Attendance 6-8','Meals 1-5','Meals 6-8','Total Meals','Status'];const q=await db.query('SELECT * FROM monthly_school_returns WHERE school_id=? AND year=? AND month=?',[schoolId,year,month]);rows=(q.values||[]).map((r:any)=>[r.year,r.month,r.recorded_days,r.verified_days,r.incomplete_days,r.attendance_class_1_5,r.attendance_class_6_8,r.meals_class_1_5,r.meals_class_6_8,r.total_meals,r.status]);
  }else if(report==='UTILIZATION'){
    headers=marathi?['घटक','एकक','उघडता','प्राप्ती','वापर','समायोजन','बंद']:['Ingredient','Unit','Opening','Receipts','Consumption','Adjustments','Closing'];const iq=await db.query('SELECT id,name_en,name_mr,base_unit FROM ingredients WHERE active=1 AND track_inventory=1 ORDER BY name_en');for(const ing of iq.values||[]){const pre=await db.query('SELECT COALESCE(SUM(quantity),0) AS q FROM stock_transactions WHERE school_id=? AND ingredient_id=? AND transaction_date<?',[schoolId,ing.id,first]);const pq=await db.query('SELECT transaction_type,COALESCE(SUM(quantity),0) AS q FROM stock_transactions WHERE school_id=? AND ingredient_id=? AND transaction_date BETWEEN ? AND ? GROUP BY transaction_type',[schoolId,ing.id,first,last]);const by=new Map<string,number>((pq.values||[]).map((x:any)=>[String(x.transaction_type),num(x.q)]));let total=0;for(const v of by.values())total+=v;const opening=num(pre.values?.[0]?.q)+(by.get('OPENING')||0);const receipts=(by.get('RECEIPT')||0)+(by.get('LOAN_IN')||0);const consumption=Math.abs(by.get('CONSUMPTION')||0)+Math.abs(Math.min(0,by.get('LOAN_OUT')||0));const adjustments=(by.get('ADJUSTMENT')||0)+(by.get('PHYSICAL_ADJUSTMENT')||0);rows.push([marathi?(ing.name_mr||ing.name_en):(ing.name_en||ing.name_mr),ing.base_unit,opening,receipts,consumption,adjustments,num(pre.values?.[0]?.q)+total]);}
  }else if(report==='BMI'){
    headers=marathi?['दिनांक','विद्यार्थी ID','विद्यार्थ्याचे नाव','इयत्ता','लिंग','उंची सेमी','वजन कि.ग्रॅ.','BMI','शेरा']:['Date','Student ID','Student Name','Class','Gender','Height cm','Weight kg','BMI','Remarks'];const q=await db.query('SELECT * FROM bmi_records WHERE school_id=? AND measurement_date BETWEEN ? AND ? ORDER BY measurement_date,student_name',[schoolId,first,last]);rows=(q.values||[]).map((r:any)=>[r.measurement_date,r.student_identifier,r.student_name,r.class_name,r.gender,r.height_cm,r.weight_kg,r.bmi,r.remarks]);
  }else if(report==='LOANS'){
    headers=marathi?['दिनांक','क्रमांक','प्रकार','समोरील संस्था','घटक','मात्रा','शेरा']:['Date','Loan No','Direction','Counterparty','Ingredient','Quantity','Remarks'];const q=await db.query(`SELECT l.*,i.name_en,i.name_mr FROM stock_loans l LEFT JOIN ingredients i ON i.id=l.ingredient_id WHERE l.school_id=? AND l.loan_date BETWEEN ? AND ? ORDER BY l.loan_date`,[schoolId,first,last]);rows=(q.values||[]).map((r:any)=>[r.loan_date,r.loan_no,r.direction,r.counterparty_name,marathi?(r.name_mr||r.name_en):(r.name_en||r.name_mr),r.quantity,r.remarks]);
  }else if(report==='SPECIAL_DAYS'){
    headers=marathi?['दिनांक','दिवस प्रकार','कारण']:['Date','Day Type','Reason'];const q=await db.query("SELECT calendar_date,day_type,reason FROM school_calendar_days WHERE school_id=? AND calendar_date BETWEEN ? AND ? AND day_type<>'WORKING' ORDER BY calendar_date",[schoolId,first,last]);rows=(q.values||[]).map((r:any)=>[r.calendar_date,r.day_type,r.reason]);
  }else return jsonResponse({detail:'Unknown workbook report type'},422);
  const name=`PM_POSHAN_${report}_${year}_${pad(month)}.xls`;const title=`PM POSHAN - ${marathi?'अहवाल':'Report'} - ${report} - ${marathi?(school.name_mr||school.name_en):(school.name_en||school.name_mr)} - ${pad(month)}/${year}`;return excelResponse(title,headers,rows,name);
}

export async function tryAndroidWorkbookParityApiFetch(path: string, init: RequestInit = {}): Promise<Response | null> {
  const method=String(init.method||'GET').toUpperCase();const url=new URL(path,'https://local.pmposhan.invalid');const route=url.pathname;
  const relevant=route==='/workbook-parity/ration-preview'||route==='/workbook-parity/loans'||route==='/workbook-parity/bmi'||route==='/workbook-parity/register/export'||route==='/workbook-parity/register/export-marathi'||route==='/workbook-parity/exact-report/export';if(!relevant)return null;
  try{
    const auth=await requireUser(init);if(auth.response)return auth.response;const db=await getSharedAndroidDb();await ensureSchema(db);
    if(route==='/workbook-parity/ration-preview'&&method==='GET')return rationPreview(path,init);
    if(route==='/workbook-parity/loans'&&method==='POST')return saveLoan(db,init,auth.user);
    if(route==='/workbook-parity/bmi'&&method==='POST')return saveBmi(db,init,auth.user);
    if(route==='/workbook-parity/register/export'&&method==='GET')return exportReport(db,url,init,false,false);
    if(route==='/workbook-parity/register/export-marathi'&&method==='GET')return exportReport(db,url,init,true,false);
    if(route==='/workbook-parity/exact-report/export'&&method==='GET')return exportReport(db,url,init,true,true);
    return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);
  }catch(error){return jsonResponse({detail:error instanceof Error?error.message:String(error)},400);}
}
