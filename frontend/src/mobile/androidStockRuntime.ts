import type { SQLiteDBConnection } from '@capacitor-community/sqlite';
import { androidApiFetch } from './androidRuntime';
import { getSharedAndroidDb } from './androidSharedDb';

type LocalUser = {
  id: string;
  username: string;
  role: 'SYSTEM_ADMIN' | 'HEADMASTER' | 'TEACHER';
};

type PhysicalLineInput = { ingredient_id: string; physical_quantity: number };
type ReceiptLineInput = { ingredient_id: string; quantity: number; unit_cost?: number | null };

const EPSILON = 0.000000001;

function uuid(): string { return crypto.randomUUID(); }
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: {'Content-Type':'application/json'} });
}
function isIsoDate(value: string): boolean { return /^\d{4}-\d{2}-\d{2}$/.test(value); }
function num(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}
async function bodyJson(init: RequestInit): Promise<any> {
  if (!init.body) return {};
  if (typeof init.body === 'string') return JSON.parse(init.body || '{}');
  throw new Error('ANDROID_BODY_TYPE_UNSUPPORTED');
}

async function ensureSchema(db: SQLiteDBConnection): Promise<void> {
  await db.execute(`
    PRAGMA foreign_keys=ON;
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
    CREATE INDEX IF NOT EXISTS ix_android_stock_school_ingredient
      ON stock_transactions(school_id,ingredient_id);
    CREATE INDEX IF NOT EXISTS ix_android_stock_reference
      ON stock_transactions(reference_type,reference_id,transaction_type);

    CREATE TABLE IF NOT EXISTS stock_receipts (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      receipt_date TEXT NOT NULL,
      receipt_no TEXT NOT NULL,
      source_name TEXT,
      remarks TEXT,
      entered_by_subject TEXT,
      entered_by_username TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,receipt_no)
    );
    CREATE TABLE IF NOT EXISTS stock_receipt_lines (
      id TEXT PRIMARY KEY,
      receipt_id TEXT NOT NULL REFERENCES stock_receipts(id) ON DELETE CASCADE,
      ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
      quantity REAL NOT NULL,
      unit_cost REAL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(receipt_id,ingredient_id)
    );

    CREATE TABLE IF NOT EXISTS stock_adjustments (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      adjustment_date TEXT NOT NULL,
      adjustment_no TEXT NOT NULL,
      ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
      quantity REAL NOT NULL,
      reason_code TEXT NOT NULL,
      remarks TEXT,
      entered_by_subject TEXT,
      entered_by_username TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,adjustment_no)
    );

    CREATE TABLE IF NOT EXISTS physical_stock_verifications (
      id TEXT PRIMARY KEY,
      school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
      verification_date TEXT NOT NULL,
      verification_no TEXT NOT NULL,
      remarks TEXT,
      entered_by_subject TEXT,
      entered_by_username TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(school_id,verification_no)
    );
    CREATE TABLE IF NOT EXISTS physical_stock_verification_lines (
      id TEXT PRIMARY KEY,
      verification_id TEXT NOT NULL REFERENCES physical_stock_verifications(id) ON DELETE CASCADE,
      ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
      system_quantity REAL NOT NULL,
      physical_quantity REAL NOT NULL,
      variance_quantity REAL NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(verification_id,ingredient_id)
    );
  `);
}

async function requireUser(init: RequestInit): Promise<{response?:Response; user?:LocalUser}> {
  const r = await androidApiFetch('/me', {headers:init.headers || {}});
  if (!r.ok) return {response:r};
  const me = await r.json();
  return {
    user: {
      id:String(me.sub || ''),
      username:String(me.username || me.preferred_username || ''),
      role:String(me.role || me.roles?.[0] || '') as LocalUser['role'],
    },
  };
}

async function assertSchoolAccess(init: RequestInit, schoolId: string): Promise<Response | null> {
  const r = await androidApiFetch('/schools', {headers:init.headers || {}});
  if (!r.ok) return r;
  const schools = await r.json();
  if (!Array.isArray(schools) || !schools.some((s:any)=>String(s.id)===schoolId)) {
    return jsonResponse({detail:'NO_SCHOOL_ACCESS'},403);
  }
  return null;
}

async function inventoryIngredient(db:SQLiteDBConnection, ingredientId:string): Promise<any|null> {
  const q = await db.query(
    'SELECT id,code,name_en,name_mr,category,base_unit,reorder_level,safety_stock,track_inventory,active FROM ingredients WHERE id=? AND active=1 AND track_inventory=1',
    [ingredientId],
  );
  return q.values?.[0] || null;
}

async function balance(db:SQLiteDBConnection, schoolId:string, ingredientId:string): Promise<number> {
  const q=await db.query(
    'SELECT COALESCE(SUM(quantity),0) AS balance FROM stock_transactions WHERE school_id=? AND ingredient_id=?',
    [schoolId,ingredientId],
  );
  return num(q.values?.[0]?.balance);
}

async function listIngredients(db:SQLiteDBConnection): Promise<Response> {
  const q=await db.query(`SELECT id,code,name_en,name_mr,category,base_unit,track_inventory
    FROM ingredients WHERE active=1 ORDER BY name_en,code`);
  return jsonResponse((q.values || []).map((x:any)=>({...x,track_inventory:!!Number(x.track_inventory)})));
}

async function stockBalances(db:SQLiteDBConnection, schoolId:string): Promise<Response> {
  const q=await db.query(`
    SELECT i.id AS ingredient_id,i.code,i.name_en,i.name_mr,i.base_unit AS unit,
           i.reorder_level,
           COALESCE(SUM(t.quantity),0) AS balance
    FROM ingredients i
    LEFT JOIN stock_transactions t ON t.ingredient_id=i.id AND t.school_id=?
    WHERE i.active=1 AND i.track_inventory=1
    GROUP BY i.id,i.code,i.name_en,i.name_mr,i.base_unit,i.reorder_level
    ORDER BY i.name_en,i.code`,[schoolId]);
  const rows=(q.values || []).map((x:any)=>{
    const current=num(x.balance); const reorder=num(x.reorder_level);
    return {...x,balance:current,reorder_level:reorder,low_stock:reorder>0 ? current<=reorder : false};
  });
  return jsonResponse(rows);
}

async function stockLedger(db:SQLiteDBConnection, url:URL, schoolId:string): Promise<Response> {
  const ingredientId=String(url.searchParams.get('ingredient_id')||'');
  const fromDate=String(url.searchParams.get('from_date')||'');
  const toDate=String(url.searchParams.get('to_date')||'');
  const where=['t.school_id=?']; const args:any[]=[schoolId];
  if (ingredientId) { where.push('t.ingredient_id=?'); args.push(ingredientId); }
  if (fromDate) { if(!isIsoDate(fromDate)) return jsonResponse({detail:'FROM_DATE_INVALID'},400); where.push('t.transaction_date>=?'); args.push(fromDate); }
  if (toDate) { if(!isIsoDate(toDate)) return jsonResponse({detail:'TO_DATE_INVALID'},400); where.push('t.transaction_date<=?'); args.push(toDate); }
  const q=await db.query(`SELECT t.id,t.transaction_date,t.transaction_type,t.ingredient_id,
      i.code AS ingredient_code,i.name_en AS ingredient_name_en,i.name_mr AS ingredient_name_mr,
      i.base_unit AS unit,t.quantity,t.reference_type,t.reference_no,t.remarks,t.entered_by_username
    FROM stock_transactions t JOIN ingredients i ON i.id=t.ingredient_id
    WHERE ${where.join(' AND ')}
    ORDER BY t.transaction_date DESC,t.created_at DESC`,args);
  return jsonResponse((q.values || []).map((x:any)=>({...x,quantity:num(x.quantity)})));
}

async function postOpening(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {
  if (!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role)) return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
  const body=await bodyJson(init);
  const schoolId=String(body.school_id||''); const openingDate=String(body.opening_date||'');
  const ingredientId=String(body.ingredient_id||''); const quantity=num(body.quantity);
  if(!schoolId||!ingredientId||!isIsoDate(openingDate)||quantity<=0) return jsonResponse({detail:'OPENING_BALANCE_FIELDS_INVALID'},400);
  const access=await assertSchoolAccess(init,schoolId); if(access) return access;
  const ing=await inventoryIngredient(db,ingredientId); if(!ing) return jsonResponse({detail:'Invalid inventory ingredient'},400);
  const count=await db.query('SELECT COUNT(*) AS n FROM stock_transactions WHERE school_id=? AND ingredient_id=?',[schoolId,ingredientId]);
  if(num(count.values?.[0]?.n)>0) return jsonResponse({detail:'Opening balance is allowed only before any transaction exists for this ingredient'},409);
  const id=uuid();
  await db.run(`INSERT INTO stock_transactions
    (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username)
    VALUES (?,?,?,?, 'OPENING', ?, 'OPENING_BALANCE', ?, 'OPENING', ?, ?, ?)`,
    [id,schoolId,ingredientId,openingDate,quantity,`${schoolId}:${ingredientId}`,String(body.remarks||'').slice(0,1000)||null,user.id,user.username]);
  return jsonResponse({ok:true,id,quantity,unit:ing.base_unit});
}

async function listReceipts(db:SQLiteDBConnection, schoolId:string): Promise<Response> {
  const h=await db.query(`SELECT * FROM stock_receipts WHERE school_id=? ORDER BY receipt_date DESC,created_at DESC`,[schoolId]);
  const out:any[]=[];
  for(const row of h.values || []) {
    const l=await db.query(`SELECT l.ingredient_id,i.name_en AS ingredient_name_en,i.name_mr AS ingredient_name_mr,
        i.base_unit AS unit,l.quantity,l.unit_cost
      FROM stock_receipt_lines l JOIN ingredients i ON i.id=l.ingredient_id
      WHERE l.receipt_id=? ORDER BY i.name_en`,[row.id]);
    out.push({...row,lines:(l.values||[]).map((x:any)=>({...x,quantity:num(x.quantity),unit_cost:x.unit_cost===null||x.unit_cost===undefined?null:num(x.unit_cost)}))});
  }
  return jsonResponse(out);
}

async function postReceipt(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {
  if (!['TEACHER','HEADMASTER','SYSTEM_ADMIN'].includes(user.role)) return jsonResponse({detail:'ROLE_CANNOT_POST_STOCK_RECEIPT'},403);
  const body=await bodyJson(init);
  const schoolId=String(body.school_id||''); const receiptDate=String(body.receipt_date||'');
  const receiptNo=String(body.receipt_no||'').trim().slice(0,80); const lines:Array<ReceiptLineInput>=Array.isArray(body.lines)?body.lines:[];
  if(!schoolId||!isIsoDate(receiptDate)||!receiptNo||!lines.length) return jsonResponse({detail:'STOCK_RECEIPT_FIELDS_INVALID'},400);
  const access=await assertSchoolAccess(init,schoolId); if(access) return access;
  const ids=lines.map(x=>String(x.ingredient_id||''));
  if(ids.some(x=>!x)||new Set(ids).size!==ids.length) return jsonResponse({detail:'Duplicate or invalid ingredient lines are not allowed'},400);
  const duplicate=await db.query('SELECT id FROM stock_receipts WHERE school_id=? AND receipt_no=?',[schoolId,receiptNo]);
  if(duplicate.values?.length) return jsonResponse({detail:'Receipt number already exists for this school'},409);
  for(const line of lines) {
    if(num(line.quantity)<=0) return jsonResponse({detail:'Stock receipt quantity must be greater than zero'},400);
    if(line.unit_cost!==undefined && line.unit_cost!==null && num(line.unit_cost)<0) return jsonResponse({detail:'Unit cost cannot be negative'},400);
    if(!await inventoryIngredient(db,String(line.ingredient_id))) return jsonResponse({detail:`Invalid inventory ingredient: ${line.ingredient_id}`},400);
  }
  const receiptId=uuid();
  await db.beginTransaction();
  try {
    await db.run(`INSERT INTO stock_receipts (id,school_id,receipt_date,receipt_no,source_name,remarks,entered_by_subject,entered_by_username)
      VALUES (?,?,?,?,?,?,?,?)`,[receiptId,schoolId,receiptDate,receiptNo,String(body.source_name||'').slice(0,200)||null,String(body.remarks||'').slice(0,1000)||null,user.id,user.username]);
    for(const line of lines) {
      const quantity=num(line.quantity);
      await db.run('INSERT INTO stock_receipt_lines (id,receipt_id,ingredient_id,quantity,unit_cost) VALUES (?,?,?,?,?)',
        [uuid(),receiptId,String(line.ingredient_id),quantity,line.unit_cost===undefined||line.unit_cost===null?null:num(line.unit_cost)]);
      await db.run(`INSERT INTO stock_transactions
        (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username)
        VALUES (?,?,?,?, 'RECEIPT', ?, 'STOCK_RECEIPT', ?, ?, ?, ?, ?)`,
        [uuid(),schoolId,String(line.ingredient_id),receiptDate,quantity,receiptId,receiptNo,String(body.remarks||body.source_name||'').slice(0,1000)||null,user.id,user.username]);
    }
    await db.commitTransaction();
  } catch(error) {
    try { await db.rollbackTransaction(); } catch { /* ignore */ }
    throw error;
  }
  return jsonResponse({ok:true,id:receiptId,receipt_no:receiptNo,lines:lines.length});
}

async function listAdjustments(db:SQLiteDBConnection, schoolId:string): Promise<Response> {
  const q=await db.query(`SELECT a.id,a.adjustment_date,a.adjustment_no,a.ingredient_id,
      i.name_en AS ingredient_name_en,i.name_mr AS ingredient_name_mr,i.base_unit AS unit,
      a.quantity,a.reason_code,a.remarks,a.entered_by_username
    FROM stock_adjustments a JOIN ingredients i ON i.id=a.ingredient_id
    WHERE a.school_id=? ORDER BY a.adjustment_date DESC,a.created_at DESC`,[schoolId]);
  return jsonResponse((q.values||[]).map((x:any)=>({...x,quantity:num(x.quantity)})));
}

async function postAdjustment(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {
  if (!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role)) return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
  const body=await bodyJson(init);
  const schoolId=String(body.school_id||''); const date=String(body.adjustment_date||'');
  const adjustmentNo=String(body.adjustment_no||'').trim().slice(0,80); const ingredientId=String(body.ingredient_id||'');
  const quantity=num(body.quantity); const reasonCode=String(body.reason_code||'').trim().slice(0,40);
  if(!schoolId||!ingredientId||!isIsoDate(date)||!adjustmentNo||!reasonCode||Math.abs(quantity)<EPSILON) return jsonResponse({detail:'STOCK_ADJUSTMENT_FIELDS_INVALID'},400);
  const access=await assertSchoolAccess(init,schoolId); if(access) return access;
  const ing=await inventoryIngredient(db,ingredientId); if(!ing) return jsonResponse({detail:'Invalid inventory ingredient'},400);
  const duplicate=await db.query('SELECT id FROM stock_adjustments WHERE school_id=? AND adjustment_no=?',[schoolId,adjustmentNo]);
  if(duplicate.values?.length) return jsonResponse({detail:'Adjustment number already exists for this school'},409);
  const available=await balance(db,schoolId,ingredientId);
  if(quantity<0 && available+quantity < -EPSILON) return jsonResponse({detail:`Adjustment would create negative stock. Available ${available} ${ing.base_unit}`},409);
  const id=uuid();
  await db.beginTransaction();
  try {
    await db.run(`INSERT INTO stock_adjustments
      (id,school_id,adjustment_date,adjustment_no,ingredient_id,quantity,reason_code,remarks,entered_by_subject,entered_by_username)
      VALUES (?,?,?,?,?,?,?,?,?,?)`,[id,schoolId,date,adjustmentNo,ingredientId,quantity,reasonCode,String(body.remarks||'').slice(0,1000)||null,user.id,user.username]);
    await db.run(`INSERT INTO stock_transactions
      (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username)
      VALUES (?,?,?,?, 'ADJUSTMENT', ?, 'STOCK_ADJUSTMENT', ?, ?, ?, ?, ?)`,
      [uuid(),schoolId,ingredientId,date,quantity,id,adjustmentNo,String(body.remarks||reasonCode).slice(0,1000),user.id,user.username]);
    await db.commitTransaction();
  } catch(error) {
    try { await db.rollbackTransaction(); } catch { /* ignore */ }
    throw error;
  }
  return jsonResponse({ok:true,id,adjustment_no:adjustmentNo,quantity,unit:ing.base_unit,balance_after:available+quantity});
}

async function listPhysical(db:SQLiteDBConnection, schoolId:string): Promise<Response> {
  const h=await db.query('SELECT * FROM physical_stock_verifications WHERE school_id=? ORDER BY verification_date DESC,created_at DESC',[schoolId]);
  const out:any[]=[];
  for(const row of h.values || []) {
    const l=await db.query(`SELECT l.ingredient_id,i.name_en AS ingredient_name_en,i.name_mr AS ingredient_name_mr,i.base_unit AS unit,
        l.system_quantity,l.physical_quantity,l.variance_quantity
      FROM physical_stock_verification_lines l JOIN ingredients i ON i.id=l.ingredient_id
      WHERE l.verification_id=? ORDER BY i.name_en`,[row.id]);
    out.push({...row,lines:(l.values||[]).map((x:any)=>({...x,system_quantity:num(x.system_quantity),physical_quantity:num(x.physical_quantity),variance_quantity:num(x.variance_quantity)}))});
  }
  return jsonResponse(out);
}

async function postPhysical(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {
  if (!['HEADMASTER','SYSTEM_ADMIN'].includes(user.role)) return jsonResponse({detail:'HEADMASTER_OR_SYSTEM_ADMIN_REQUIRED'},403);
  const body=await bodyJson(init);
  const schoolId=String(body.school_id||''); const date=String(body.verification_date||'');
  const verificationNo=String(body.verification_no||'').trim().slice(0,80); const lines:Array<PhysicalLineInput>=Array.isArray(body.lines)?body.lines:[];
  if(!schoolId||!isIsoDate(date)||!verificationNo||!lines.length) return jsonResponse({detail:'PHYSICAL_VERIFICATION_FIELDS_INVALID'},400);
  const access=await assertSchoolAccess(init,schoolId); if(access) return access;
  const ids=lines.map(x=>String(x.ingredient_id||''));
  if(ids.some(x=>!x)||new Set(ids).size!==ids.length) return jsonResponse({detail:'Duplicate or invalid ingredient lines are not allowed'},400);
  const duplicate=await db.query('SELECT id FROM physical_stock_verifications WHERE school_id=? AND verification_no=?',[schoolId,verificationNo]);
  if(duplicate.values?.length) return jsonResponse({detail:'Verification number already exists for this school'},409);
  for(const line of lines) {
    if(num(line.physical_quantity)<0) return jsonResponse({detail:'Physical quantity cannot be negative'},400);
    if(!await inventoryIngredient(db,String(line.ingredient_id))) return jsonResponse({detail:`Invalid inventory ingredient: ${line.ingredient_id}`},400);
  }
  const id=uuid(); let varianceCount=0;
  await db.beginTransaction();
  try {
    await db.run(`INSERT INTO physical_stock_verifications
      (id,school_id,verification_date,verification_no,remarks,entered_by_subject,entered_by_username)
      VALUES (?,?,?,?,?,?,?)`,[id,schoolId,date,verificationNo,String(body.remarks||'').slice(0,1000)||null,user.id,user.username]);
    for(const line of lines) {
      const ingredientId=String(line.ingredient_id); const systemQty=await balance(db,schoolId,ingredientId);
      const physicalQty=num(line.physical_quantity); const variance=physicalQty-systemQty;
      await db.run(`INSERT INTO physical_stock_verification_lines
        (id,verification_id,ingredient_id,system_quantity,physical_quantity,variance_quantity)
        VALUES (?,?,?,?,?,?)`,[uuid(),id,ingredientId,systemQty,physicalQty,variance]);
      if(Math.abs(variance)>EPSILON) {
        varianceCount += 1;
        await db.run(`INSERT INTO stock_transactions
          (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username)
          VALUES (?,?,?,?, 'PHYSICAL_ADJUSTMENT', ?, 'PHYSICAL_VERIFICATION', ?, ?, ?, ?, ?)`,
          [uuid(),schoolId,ingredientId,date,variance,id,verificationNo,String(body.remarks||'Physical stock verification variance').slice(0,1000),user.id,user.username]);
      }
    }
    await db.commitTransaction();
  } catch(error) {
    try { await db.rollbackTransaction(); } catch { /* ignore */ }
    throw error;
  }
  return jsonResponse({ok:true,id,verification_no:verificationNo,variance_lines:varianceCount});
}

export async function tryAndroidStockApiFetch(path:string, init:RequestInit={}): Promise<Response|null> {
  const method=String(init.method||'GET').toUpperCase();
  const url=new URL(path,'https://local.pmposhan.invalid');
  const route=url.pathname;
  const relevant = route==='/ingredients' || route==='/stock/opening-balance' || route==='/stock/balances' ||
    route==='/stock/ledger' || route==='/stock/receipts' || route==='/stock/adjustments' || route==='/stock/physical-verifications';
  if(!relevant) return null;

  try {
    const auth=await requireUser(init);
    if(auth.response) return auth.response;
    const user=auth.user!;
    const db=await getSharedAndroidDb();
    await ensureSchema(db);

    if(method==='GET' && route==='/ingredients') return listIngredients(db);

    if(route.startsWith('/stock/')) {
      const schoolId = method==='GET' ? String(url.searchParams.get('school_id')||'') : '';
      if(method==='GET') {
        if(!schoolId) return jsonResponse({detail:'SCHOOL_ID_REQUIRED'},400);
        const access=await assertSchoolAccess(init,schoolId); if(access) return access;
      }
      if(method==='GET' && route==='/stock/balances') return stockBalances(db,schoolId);
      if(method==='GET' && route==='/stock/ledger') return stockLedger(db,url,schoolId);
      if(method==='GET' && route==='/stock/receipts') return listReceipts(db,schoolId);
      if(method==='GET' && route==='/stock/adjustments') return listAdjustments(db,schoolId);
      if(method==='GET' && route==='/stock/physical-verifications') return listPhysical(db,schoolId);
      if(method==='POST' && route==='/stock/opening-balance') return postOpening(db,init,user);
      if(method==='POST' && route==='/stock/receipts') return postReceipt(db,init,user);
      if(method==='POST' && route==='/stock/adjustments') return postAdjustment(db,init,user);
      if(method==='POST' && route==='/stock/physical-verifications') return postPhysical(db,init,user);
    }

    return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);
  } catch(error) {
    return jsonResponse({detail:error instanceof Error ? error.message : String(error)},400);
  }
}
