import { CapacitorSQLite, SQLiteConnection, type SQLiteDBConnection } from '@capacitor-community/sqlite';
import { androidApiFetch } from './androidRuntime';

const DB_NAME = 'pmposhan';
const DB_VERSION = 1;
const sqlite = new SQLiteConnection(CapacitorSQLite);
let dbPromise: Promise<SQLiteDBConnection> | null = null;

type LocalUser = {
  id: string;
  username: string;
  role: 'SYSTEM_ADMIN' | 'HEADMASTER' | 'TEACHER';
};

function uuid(): string { return crypto.randomUUID(); }
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: {'Content-Type':'application/json'} });
}
async function bodyJson(init: RequestInit): Promise<any> {
  if (!init.body) return {};
  if (typeof init.body === 'string') return JSON.parse(init.body || '{}');
  throw new Error('ANDROID_BODY_TYPE_UNSUPPORTED');
}
function boolValue(value: unknown): number { return value ? 1 : 0; }
function intValue(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : 0;
}
function isIsoDate(value: string): boolean { return /^\d{4}-\d{2}-\d{2}$/.test(value); }

async function getDb(): Promise<SQLiteDBConnection> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const consistent = (await sqlite.checkConnectionsConsistency()).result;
      const exists = (await sqlite.isConnection(DB_NAME, false)).result;
      const db = consistent && exists
        ? await sqlite.retrieveConnection(DB_NAME, false)
        : await sqlite.createConnection(DB_NAME, false, 'no-encryption', DB_VERSION, false);
      try { await db.open(); } catch { /* existing shared connection may already be open */ }
      await ensureSchema(db);
      return db;
    })();
  }
  return dbPromise;
}

async function ensureSchema(db: SQLiteDBConnection): Promise<void> {
  await db.execute(`
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS menu_schedules (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      menu_date TEXT NOT NULL,
      menu_id TEXT NOT NULL REFERENCES menus(id) ON DELETE RESTRICT,
      remarks TEXT,
      active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
      created_by TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,menu_date)
    );
    CREATE TABLE IF NOT EXISTS daily_attendance (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      meal_date TEXT NOT NULL,
      class_1_5_enrolled INTEGER NOT NULL DEFAULT 0,
      class_1_5_present INTEGER NOT NULL DEFAULT 0,
      class_6_8_enrolled INTEGER NOT NULL DEFAULT 0,
      class_6_8_present INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','SUBMITTED','VERIFIED')),
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
      menu_id TEXT NOT NULL REFERENCES menus(id) ON DELETE RESTRICT,
      meals_class_1_5 INTEGER NOT NULL DEFAULT 0,
      meals_class_6_8 INTEGER NOT NULL DEFAULT 0,
      total_meals INTEGER NOT NULL DEFAULT 0,
      tasting_done INTEGER NOT NULL DEFAULT 0 CHECK(tasting_done IN (0,1)),
      hygiene_ok INTEGER NOT NULL DEFAULT 0 CHECK(hygiene_ok IN (0,1)),
      remarks TEXT,
      status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','SUBMITTED','VERIFIED')),
      entered_by_subject TEXT,
      entered_by_username TEXT,
      verified_by_subject TEXT,
      verified_by_username TEXT,
      verified_at TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,meal_date)
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
    CREATE INDEX IF NOT EXISTS ix_android_stock_school_ingredient ON stock_transactions(school_id,ingredient_id);
    CREATE INDEX IF NOT EXISTS ix_android_stock_reference ON stock_transactions(reference_type,reference_id,transaction_type);
  `);
}

async function requireUser(init: RequestInit): Promise<{response?:Response; user?:LocalUser}> {
  const probe = await androidApiFetch('/me', {headers:init.headers || {}});
  if (!probe.ok) return {response:probe};
  const me = await probe.json();
  return { user: {id:String(me.sub || ''), username:String(me.username || ''), role:String(me.role || me.roles?.[0] || '') as LocalUser['role']} };
}

async function accessibleSchool(init: RequestInit, schoolId: string): Promise<Response | null> {
  const r = await androidApiFetch('/schools', {headers:init.headers || {}});
  if (!r.ok) return r;
  const schools = await r.json();
  return Array.isArray(schools) && schools.some((s:any)=>String(s.id)===schoolId)
    ? null
    : jsonResponse({detail:'NO_SCHOOL_ACCESS'},403);
}

async function activeMenu(db: SQLiteDBConnection, menuId: string): Promise<any | null> {
  const q = await db.query('SELECT id,code,name_en,name_mr,week_pattern,day_of_week FROM menus WHERE id=? AND active=1',[menuId]);
  return q.values?.[0] || null;
}

function menuPlanDict(row: any | null): any | null {
  if (!row) return null;
  return {
    id: row.id,
    school_id: row.school_id,
    menu_date: row.menu_date,
    menu_id: row.menu_id,
    menu_code: row.menu_code || null,
    menu_name_en: row.menu_name_en || null,
    menu_name_mr: row.menu_name_mr || null,
    remarks: row.remarks || null,
    active: !!Number(row.active),
  };
}

async function getMenuPlan(db: SQLiteDBConnection, schoolId: string, menuDate: string): Promise<any | null> {
  const q = await db.query(`SELECT ms.*,m.code AS menu_code,m.name_en AS menu_name_en,m.name_mr AS menu_name_mr
    FROM menu_schedules ms JOIN menus m ON m.id=ms.menu_id
    WHERE ms.school_id=? AND ms.menu_date=? AND ms.active=1 LIMIT 1`,[schoolId,menuDate]);
  return menuPlanDict(q.values?.[0] || null);
}

async function recipePreview(db: SQLiteDBConnection, menuId: string, onDate: string, class15: number, class68: number): Promise<any[]> {
  const q = await db.query(`SELECT r.ingredient_id,r.student_group,r.qty_per_student,r.measurement_unit,
      i.code,i.name_en,i.name_mr,i.base_unit
    FROM recipes r JOIN ingredients i ON i.id=r.ingredient_id
    WHERE r.menu_id=? AND r.active=1 AND r.effective_from<=?
      AND (r.effective_to IS NULL OR r.effective_to>=?)
    ORDER BY i.name_en,r.student_group`,[menuId,onDate,onDate]);
  const grouped = new Map<string,any>();
  for (const r of q.values || []) {
    const id=String(r.ingredient_id);
    if (!grouped.has(id)) grouped.set(id,{
      ingredient_id:id, code:r.code, name_en:r.name_en, name_mr:r.name_mr,
      unit:r.measurement_unit || r.base_unit,
      p15:0, p68:0,
    });
    const x=grouped.get(id)!;
    if (r.student_group==='CLASS_1_5') x.p15 += Number(r.qty_per_student || 0);
    else if (r.student_group==='CLASS_6_8') x.p68 += Number(r.qty_per_student || 0);
    else if (r.student_group==='ALL') { x.p15 += Number(r.qty_per_student || 0); x.p68 += Number(r.qty_per_student || 0); }
  }
  return [...grouped.values()].map(x=>({
    ingredient_id:x.ingredient_id, code:x.code, name_en:x.name_en, name_mr:x.name_mr, unit:x.unit,
    qty_per_student_class_1_5:x.p15,
    qty_per_student_class_6_8:x.p68,
    required_class_1_5:x.p15*class15,
    required_class_6_8:x.p68*class68,
    required_total:(x.p15*class15)+(x.p68*class68),
  }));
}

function attendanceDict(row:any|null): any|null {
  if (!row) return null;
  return {
    id:row.id, school_id:row.school_id, meal_date:row.meal_date,
    class_1_5_enrolled:Number(row.class_1_5_enrolled||0), class_1_5_present:Number(row.class_1_5_present||0),
    class_6_8_enrolled:Number(row.class_6_8_enrolled||0), class_6_8_present:Number(row.class_6_8_present||0),
    total_present:Number(row.class_1_5_present||0)+Number(row.class_6_8_present||0),
    status:row.status, entered_by_username:row.entered_by_username||null,
    verified_by_username:row.verified_by_username||null, verified_at:row.verified_at||null,
  };
}

async function mealDict(db:SQLiteDBConnection,row:any|null): Promise<any|null> {
  if (!row) return null;
  const menu=await activeMenu(db,String(row.menu_id));
  return {
    id:row.id, school_id:row.school_id, meal_date:row.meal_date, menu_id:row.menu_id,
    menu_code:menu?.code||null, menu_name_en:menu?.name_en||null, menu_name_mr:menu?.name_mr||null,
    meals_class_1_5:Number(row.meals_class_1_5||0), meals_class_6_8:Number(row.meals_class_6_8||0),
    total_meals:Number(row.total_meals||0), tasting_done:!!Number(row.tasting_done), hygiene_ok:!!Number(row.hygiene_ok),
    remarks:row.remarks||null, status:row.status, entered_by_username:row.entered_by_username||null,
    verified_by_username:row.verified_by_username||null, verified_at:row.verified_at||null,
  };
}

async function mealConsumption(db:SQLiteDBConnection, meal:any): Promise<Array<{ingredient_id:string;required:number;ingredient:any}>> {
  const items=await recipePreview(db,String(meal.menu_id),String(meal.meal_date),Number(meal.meals_class_1_5||0),Number(meal.meals_class_6_8||0));
  const out:Array<{ingredient_id:string;required:number;ingredient:any}>=[];
  for (const item of items) {
    const ingQ=await db.query('SELECT * FROM ingredients WHERE id=?',[item.ingredient_id]);
    const ingredient=ingQ.values?.[0];
    if (ingredient && Number(ingredient.track_inventory)===1 && Number(item.required_total)>0) {
      out.push({ingredient_id:String(item.ingredient_id),required:Number(item.required_total),ingredient});
    }
  }
  return out;
}

async function currentBalance(db:SQLiteDBConnection,schoolId:string,ingredientId:string): Promise<number> {
  const q=await db.query('SELECT COALESCE(SUM(quantity),0) AS balance FROM stock_transactions WHERE school_id=? AND ingredient_id=?',[schoolId,ingredientId]);
  return Number(q.values?.[0]?.balance || 0);
}

export async function tryAndroidOperationsApiFetch(path:string, init:RequestInit={}): Promise<Response|null> {
  const method=String(init.method||'GET').toUpperCase();
  const url=new URL(path,'https://local.pmposhan.invalid');
  const route=url.pathname;
  const relevant = route==='/menus' || route==='/menu-plan' || route==='/daily-operations' || route==='/daily-attendance' || route==='/daily-meal' || route==='/daily-operations/verify' || /^\/menus\/[^/]+\/recipe-preview$/.test(route);
  if (!relevant) return null;

  try {
    const auth=await requireUser(init);
    if (auth.response) return auth.response;
    const user=auth.user!;
    const db=await getDb();

    if (method==='GET' && route==='/menus') {
      const q=await db.query('SELECT id,code,name_en,name_mr,week_pattern,day_of_week FROM menus WHERE active=1 ORDER BY day_of_week,code');
      return jsonResponse(q.values || []);
    }

    const recipeMatch=route.match(/^\/menus\/([^/]+)\/recipe-preview$/);
    if (method==='GET' && recipeMatch) {
      const menuId=decodeURIComponent(recipeMatch[1]);
      const menu=await activeMenu(db,menuId);
      if (!menu) return jsonResponse({detail:'Menu not found'},404);
      const onDate=url.searchParams.get('on_date')||new Date().toISOString().slice(0,10);
      if (!isIsoDate(onDate)) return jsonResponse({detail:'LICENSE_DATE_INVALID'},400);
      const c15=Math.max(0,intValue(url.searchParams.get('class_1_5')));
      const c68=Math.max(0,intValue(url.searchParams.get('class_6_8')));
      return jsonResponse({menu,on_date:onDate,class_1_5:c15,class_6_8:c68,items:await recipePreview(db,menuId,onDate,c15,c68)});
    }

    if (route==='/menu-plan') {
      if (method==='GET') {
        const schoolId=String(url.searchParams.get('school_id')||'');
        const menuDate=String(url.searchParams.get('menu_date')||'');
        if (!schoolId || !isIsoDate(menuDate)) return jsonResponse({detail:'MENU_PLAN_FIELDS_REQUIRED'},400);
        const access=await accessibleSchool(init,schoolId); if (access) return access;
        return jsonResponse({plan:await getMenuPlan(db,schoolId,menuDate)});
      }
      if (method==='PUT') {
        if (!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role)) return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
        const body=await bodyJson(init);
        const schoolId=String(body.school_id||''); const menuDate=String(body.menu_date||''); const menuId=String(body.menu_id||'');
        if (!schoolId || !menuId || !isIsoDate(menuDate)) return jsonResponse({detail:'MENU_PLAN_FIELDS_REQUIRED'},400);
        const access=await accessibleSchool(init,schoolId); if (access) return access;
        if (!await activeMenu(db,menuId)) return jsonResponse({detail:'Menu not found'},404);
        const found=await db.query('SELECT id FROM menu_schedules WHERE school_id=? AND menu_date=?',[schoolId,menuDate]);
        const id=String(found.values?.[0]?.id || uuid());
        if (found.values?.length) await db.run('UPDATE menu_schedules SET menu_id=?,remarks=?,active=1,updated_at=CURRENT_TIMESTAMP WHERE id=?',[menuId,String(body.remarks||'')||null,id]);
        else await db.run('INSERT INTO menu_schedules (id,school_id,menu_date,menu_id,remarks,active,created_by) VALUES (?,?,?,?,?,1,?)',[id,schoolId,menuDate,menuId,String(body.remarks||'')||null,user.username]);
        return jsonResponse({ok:true,plan:await getMenuPlan(db,schoolId,menuDate)});
      }
    }

    if (method==='GET' && route==='/daily-operations') {
      const schoolId=String(url.searchParams.get('school_id')||''); const mealDate=String(url.searchParams.get('meal_date')||'');
      if (!schoolId || !isIsoDate(mealDate)) return jsonResponse({detail:'DAILY_FIELDS_REQUIRED'},400);
      const access=await accessibleSchool(init,schoolId); if (access) return access;
      const s=await db.query('SELECT id,name_en,name_mr FROM schools WHERE id=? AND active=1',[schoolId]);
      if (!s.values?.length) return jsonResponse({detail:'School not found'},404);
      const aq=await db.query('SELECT * FROM daily_attendance WHERE school_id=? AND meal_date=?',[schoolId,mealDate]);
      const mq=await db.query('SELECT * FROM daily_meal_entries WHERE school_id=? AND meal_date=?',[schoolId,mealDate]);
      return jsonResponse({school:s.values[0],attendance:attendanceDict(aq.values?.[0]||null),meal:await mealDict(db,mq.values?.[0]||null),planned_menu:await getMenuPlan(db,schoolId,mealDate)});
    }

    if (method==='PUT' && route==='/daily-attendance') {
      if (!['TEACHER','HEADMASTER','SYSTEM_ADMIN'].includes(user.role)) return jsonResponse({detail:'ROLE_CANNOT_EDIT_SCHOOL_OPERATIONS'},403);
      const body=await bodyJson(init); const schoolId=String(body.school_id||''); const mealDate=String(body.meal_date||''); const status=String(body.status||'DRAFT').toUpperCase();
      if (!schoolId || !isIsoDate(mealDate) || !['DRAFT','SUBMITTED'].includes(status)) return jsonResponse({detail:'ATTENDANCE_FIELDS_INVALID'},400);
      const access=await accessibleSchool(init,schoolId); if (access) return access;
      const e15=Math.max(0,intValue(body.class_1_5_enrolled)), p15=Math.max(0,intValue(body.class_1_5_present)), e68=Math.max(0,intValue(body.class_6_8_enrolled)), p68=Math.max(0,intValue(body.class_6_8_present));
      if (p15>e15) return jsonResponse({detail:'Class 1-5 present count cannot exceed enrolled count'},400);
      if (p68>e68) return jsonResponse({detail:'Class 6-8 present count cannot exceed enrolled count'},400);
      const found=await db.query('SELECT id,status FROM daily_attendance WHERE school_id=? AND meal_date=?',[schoolId,mealDate]);
      if (found.values?.[0]?.status==='VERIFIED') return jsonResponse({detail:'Verified attendance cannot be edited'},409);
      const id=String(found.values?.[0]?.id || uuid());
      if (found.values?.length) await db.run(`UPDATE daily_attendance SET class_1_5_enrolled=?,class_1_5_present=?,class_6_8_enrolled=?,class_6_8_present=?,status=?,entered_by_subject=?,entered_by_username=?,updated_at=CURRENT_TIMESTAMP WHERE id=?`,[e15,p15,e68,p68,status,user.id,user.username,id]);
      else await db.run(`INSERT INTO daily_attendance (id,school_id,meal_date,class_1_5_enrolled,class_1_5_present,class_6_8_enrolled,class_6_8_present,status,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?)`,[id,schoolId,mealDate,e15,p15,e68,p68,status,user.id,user.username]);
      const out=await db.query('SELECT * FROM daily_attendance WHERE id=?',[id]);
      return jsonResponse(attendanceDict(out.values?.[0]||null));
    }

    if (method==='PUT' && route==='/daily-meal') {
      if (!['TEACHER','HEADMASTER','SYSTEM_ADMIN'].includes(user.role)) return jsonResponse({detail:'ROLE_CANNOT_EDIT_SCHOOL_OPERATIONS'},403);
      const body=await bodyJson(init); const schoolId=String(body.school_id||''); const mealDate=String(body.meal_date||''); const menuId=String(body.menu_id||''); const status=String(body.status||'DRAFT').toUpperCase();
      if (!schoolId || !menuId || !isIsoDate(mealDate) || !['DRAFT','SUBMITTED'].includes(status)) return jsonResponse({detail:'MEAL_FIELDS_INVALID'},400);
      const access=await accessibleSchool(init,schoolId); if (access) return access;
      if (!await activeMenu(db,menuId)) return jsonResponse({detail:'Menu not found'},404);
      const m15=Math.max(0,intValue(body.meals_class_1_5)), m68=Math.max(0,intValue(body.meals_class_6_8));
      const aq=await db.query('SELECT * FROM daily_attendance WHERE school_id=? AND meal_date=?',[schoolId,mealDate]); const attendance=aq.values?.[0];
      if (attendance && (m15>Number(attendance.class_1_5_present||0) || m68>Number(attendance.class_6_8_present||0))) return jsonResponse({detail:'Meals served cannot exceed present students'},400);
      if (status==='SUBMITTED' && (!body.tasting_done || !body.hygiene_ok)) return jsonResponse({detail:'Complete both meal tasting and hygiene checks before submitting'},400);
      const found=await db.query('SELECT id,status FROM daily_meal_entries WHERE school_id=? AND meal_date=?',[schoolId,mealDate]);
      if (found.values?.[0]?.status==='VERIFIED') return jsonResponse({detail:'Verified meal entry cannot be edited'},409);
      const id=String(found.values?.[0]?.id || uuid());
      const remarks=String(body.remarks||'').slice(0,1000)||null;
      if (found.values?.length) await db.run(`UPDATE daily_meal_entries SET menu_id=?,meals_class_1_5=?,meals_class_6_8=?,total_meals=?,tasting_done=?,hygiene_ok=?,remarks=?,status=?,entered_by_subject=?,entered_by_username=?,updated_at=CURRENT_TIMESTAMP WHERE id=?`,[menuId,m15,m68,m15+m68,boolValue(body.tasting_done),boolValue(body.hygiene_ok),remarks,status,user.id,user.username,id]);
      else await db.run(`INSERT INTO daily_meal_entries (id,school_id,meal_date,menu_id,meals_class_1_5,meals_class_6_8,total_meals,tasting_done,hygiene_ok,remarks,status,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,[id,schoolId,mealDate,menuId,m15,m68,m15+m68,boolValue(body.tasting_done),boolValue(body.hygiene_ok),remarks,status,user.id,user.username]);
      const out=await db.query('SELECT * FROM daily_meal_entries WHERE id=?',[id]);
      return jsonResponse(await mealDict(db,out.values?.[0]||null));
    }

    if (method==='POST' && route==='/daily-operations/verify') {
      if (!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role)) return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
      const body=await bodyJson(init); const schoolId=String(body.school_id||''); const mealDate=String(body.meal_date||'');
      if (!schoolId || !isIsoDate(mealDate)) return jsonResponse({detail:'DAILY_FIELDS_REQUIRED'},400);
      const access=await accessibleSchool(init,schoolId); if (access) return access;
      const aq=await db.query('SELECT * FROM daily_attendance WHERE school_id=? AND meal_date=?',[schoolId,mealDate]); const attendance=aq.values?.[0];
      const mq=await db.query('SELECT * FROM daily_meal_entries WHERE school_id=? AND meal_date=?',[schoolId,mealDate]); const meal=mq.values?.[0];
      if (!attendance || !meal) return jsonResponse({detail:'Attendance and meal entry are both required'},400);
      if (attendance.status!=='SUBMITTED' || meal.status!=='SUBMITTED') return jsonResponse({detail:'Both records must be submitted before verification'},400);
      if (!Number(meal.tasting_done) || !Number(meal.hygiene_ok)) return jsonResponse({detail:'Tasting and hygiene checks must be complete'},400);
      const existing=await db.query(`SELECT id FROM stock_transactions WHERE school_id=? AND reference_type='DAILY_MEAL' AND reference_id=? AND transaction_type='CONSUMPTION'`,[schoolId,meal.id]);
      let posted=Number(existing.values?.length || 0);
      if (!posted) {
        const consumption=await mealConsumption(db,meal);
        if (!consumption.length) return jsonResponse({detail:'No active recipe is configured for the selected menu/date'},400);
        const shortages:string[]=[];
        for (const x of consumption) {
          const available=await currentBalance(db,schoolId,x.ingredient_id);
          if (available+1e-9<x.required) shortages.push(`${x.ingredient.name_en}: required ${x.required} ${x.ingredient.base_unit}, available ${available} ${x.ingredient.base_unit}`);
        }
        if (shortages.length) return jsonResponse({detail:`Insufficient stock - ${shortages.join('; ')}`},409);
        for (const x of consumption) {
          await db.run(`INSERT INTO stock_transactions (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?, 'CONSUMPTION', ?, 'DAILY_MEAL', ?, ?, ?, ?, ?)`,[uuid(),schoolId,x.ingredient_id,mealDate,-x.required,meal.id,`MEAL-${mealDate}`,`Auto consumption for ${Number(meal.total_meals||0)} verified meals`,user.id,user.username]);
          posted += 1;
        }
      }
      const now=new Date().toISOString();
      await db.run(`UPDATE daily_attendance SET status='VERIFIED',verified_by_subject=?,verified_by_username=?,verified_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?`,[user.id,user.username,now,attendance.id]);
      await db.run(`UPDATE daily_meal_entries SET status='VERIFIED',verified_by_subject=?,verified_by_username=?,verified_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?`,[user.id,user.username,now,meal.id]);
      return jsonResponse({ok:true,status:'VERIFIED',verified_by:user.username,verified_at:now,stock_consumption_transactions:posted});
    }

    return null;
  } catch (error) {
    const message=error instanceof Error ? error.message : String(error);
    return jsonResponse({detail:message},400);
  }
}
