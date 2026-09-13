import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, '..', 'src', 'mobile');

const sqliteModule = "@capacitor-community/sqlite";
const typeImport = `import type { SQLiteDBConnection } from '${sqliteModule}';`;
const sharedImport = `import { getSharedAndroidDb } from './androidSharedDb';`;

function normalizeSharedImports(text) {
  text = text.replace(
    /import\s+\{[^\n]*CapacitorSQLite[^\n]*\}\s+from\s+['"]@capacitor-community\/sqlite['"];?\r?\n?/,
    '',
  );
  text = text.replace(
    /import\s+type\s+\{\s*SQLiteDBConnection\s*\}\s+from\s+['"]@capacitor-community\/sqlite['"];?\r?\n?/g,
    '',
  );
  text = text.replace(
    /import\s+\{\s*getSharedAndroidDb\s*\}\s+from\s+['"]\.\/androidSharedDb['"];?\r?\n?/g,
    '',
  );
  return `${typeImport}\n${sharedImport}\n${text}`;
}

function replaceFunctionBlock(text, startMarker, endMarker, replacement, fileName) {
  const start = text.indexOf(startMarker);
  if (start < 0) throw new Error(`${fileName}: ${startMarker} not found`);
  const end = text.indexOf(endMarker, start);
  if (end < 0) throw new Error(`${fileName}: ${endMarker} not found`);
  return text.slice(0, start) + replacement.trimEnd() + '\n\n' + text.slice(end);
}

function writeIfChanged(fileName, transform) {
  const filePath = path.join(src, fileName);
  const before = fs.readFileSync(filePath, 'utf8');
  const after = transform(before);
  if (after !== before) {
    fs.writeFileSync(filePath, after, 'utf8');
    console.log(`PATCHED ${fileName}`);
  } else {
    console.log(`OK      ${fileName}`);
  }
}

const runtimeOpen = `async function openDb(): Promise<SQLiteDBConnection> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const db = await getSharedAndroidDb();
      await db.execute(BOOTSTRAP_SCHEMA);
      const state = await db.query('SELECT installation_id FROM installation_state WHERE id=1');
      if (!state.values?.length) {
        await db.run(
          'INSERT INTO installation_state (id,installation_id,app_version,schema_version) VALUES (1,?,?,?)',
          [uuid(), '1.0-android-dev', DB_VERSION],
        );
      }
      return db;
    })().catch(error => {
      dbPromise = null;
      throw error;
    });
  }
  return dbPromise;
}`;

const masterOpen = `async function getDb(): Promise<SQLiteDBConnection> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const db = await getSharedAndroidDb();
      await ensureSchema(db);
      await seedGovernmentMasters(db);
      return db;
    })().catch(error => {
      dbPromise = null;
      throw error;
    });
  }
  return dbPromise;
}`;

const operationsOpen = `async function getDb(): Promise<SQLiteDBConnection> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const db = await getSharedAndroidDb();
      await ensureSchema(db);
      return db;
    })().catch(error => {
      dbPromise = null;
      throw error;
    });
  }
  return dbPromise;
}`;

const stockReceipt = `async function postReceipt(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {
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
    if(!await inventoryIngredient(db,String(line.ingredient_id))) return jsonResponse({detail:\`Invalid inventory ingredient: \${line.ingredient_id}\`},400);
  }

  const receiptId=uuid();
  const tasks:any[]=[{
    statement:'INSERT INTO stock_receipts (id,school_id,receipt_date,receipt_no,source_name,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?)',
    values:[receiptId,schoolId,receiptDate,receiptNo,String(body.source_name||'').slice(0,200)||null,String(body.remarks||'').slice(0,1000)||null,user.id,user.username],
  }];
  for(const line of lines) {
    const quantity=num(line.quantity);
    tasks.push({
      statement:'INSERT INTO stock_receipt_lines (id,receipt_id,ingredient_id,quantity,unit_cost) VALUES (?,?,?,?,?)',
      values:[uuid(),receiptId,String(line.ingredient_id),quantity,line.unit_cost===undefined||line.unit_cost===null?null:num(line.unit_cost)],
    });
    tasks.push({
      statement:'INSERT INTO stock_transactions (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
      values:[uuid(),schoolId,String(line.ingredient_id),receiptDate,'RECEIPT',quantity,'STOCK_RECEIPT',receiptId,receiptNo,String(body.remarks||body.source_name||'').slice(0,1000)||null,user.id,user.username],
    });
  }
  await db.executeTransaction(tasks);
  return jsonResponse({ok:true,id:receiptId,receipt_no:receiptNo,lines:lines.length});
}`;

const stockAdjustment = `async function postAdjustment(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {
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
  if(quantity<0 && available+quantity < -EPSILON) return jsonResponse({detail:\`Adjustment would create negative stock. Available \${available} \${ing.base_unit}\`},409);

  const id=uuid();
  const tasks:any[]=[
    {
      statement:'INSERT INTO stock_adjustments (id,school_id,adjustment_date,adjustment_no,ingredient_id,quantity,reason_code,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?)',
      values:[id,schoolId,date,adjustmentNo,ingredientId,quantity,reasonCode,String(body.remarks||'').slice(0,1000)||null,user.id,user.username],
    },
    {
      statement:'INSERT INTO stock_transactions (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
      values:[uuid(),schoolId,ingredientId,date,'ADJUSTMENT',quantity,'STOCK_ADJUSTMENT',id,adjustmentNo,String(body.remarks||reasonCode).slice(0,1000),user.id,user.username],
    },
  ];
  await db.executeTransaction(tasks);
  return jsonResponse({ok:true,id,adjustment_no:adjustmentNo,quantity,unit:ing.base_unit,balance_after:available+quantity});
}`;

const stockPhysical = `async function postPhysical(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {
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
    if(!await inventoryIngredient(db,String(line.ingredient_id))) return jsonResponse({detail:\`Invalid inventory ingredient: \${line.ingredient_id}\`},400);
  }

  const id=uuid();
  let varianceCount=0;
  const prepared:any[]=[];
  for(const line of lines) {
    const ingredientId=String(line.ingredient_id);
    const systemQty=await balance(db,schoolId,ingredientId);
    const physicalQty=num(line.physical_quantity);
    const variance=physicalQty-systemQty;
    if(Math.abs(variance)>EPSILON) varianceCount += 1;
    prepared.push({ingredientId,systemQty,physicalQty,variance});
  }

  const tasks:any[]=[{
    statement:'INSERT INTO physical_stock_verifications (id,school_id,verification_date,verification_no,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?)',
    values:[id,schoolId,date,verificationNo,String(body.remarks||'').slice(0,1000)||null,user.id,user.username],
  }];
  for(const item of prepared) {
    tasks.push({
      statement:'INSERT INTO physical_stock_verification_lines (id,verification_id,ingredient_id,system_quantity,physical_quantity,variance_quantity) VALUES (?,?,?,?,?,?)',
      values:[uuid(),id,item.ingredientId,item.systemQty,item.physicalQty,item.variance],
    });
    if(Math.abs(item.variance)>EPSILON) {
      tasks.push({
        statement:'INSERT INTO stock_transactions (id,school_id,ingredient_id,transaction_date,transaction_type,quantity,reference_type,reference_id,reference_no,remarks,entered_by_subject,entered_by_username) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        values:[uuid(),schoolId,item.ingredientId,date,'PHYSICAL_ADJUSTMENT',item.variance,'PHYSICAL_VERIFICATION',id,verificationNo,String(body.remarks||'Physical stock verification variance').slice(0,1000),user.id,user.username],
      });
    }
  }
  await db.executeTransaction(tasks);
  return jsonResponse({ok:true,id,verification_no:verificationNo,variance_lines:varianceCount});
}`;

writeIfChanged('androidRuntime.ts', text => {
  text = normalizeSharedImports(text);
  text = text.replace(/const sqlite = new SQLiteConnection\(CapacitorSQLite\);\r?\n?/g, '');
  text = text.replace(/const DB_NAME = 'pmposhan';\r?\n?/g, '');
  text = replaceFunctionBlock(
    text,
    'async function openDb(): Promise<SQLiteDBConnection> {',
    'async function installationId(): Promise<string> {',
    runtimeOpen,
    'androidRuntime.ts',
  );
  return text;
});

writeIfChanged('androidMasterRuntime.ts', text => {
  text = normalizeSharedImports(text);
  text = text.replace(/const sqlite = new SQLiteConnection\(CapacitorSQLite\);\r?\n?/g, '');
  text = text.replace(/const DB_NAME = 'pmposhan';\r?\n?/g, '');
  text = text.replace(/const DB_VERSION = 1;\r?\n?/g, '');
  text = replaceFunctionBlock(
    text,
    'async function getDb(): Promise<SQLiteDBConnection> {',
    'async function ensureSchema(db: SQLiteDBConnection): Promise<void> {',
    masterOpen,
    'androidMasterRuntime.ts',
  );
  return text;
});

writeIfChanged('androidOperationsRuntime.ts', text => {
  text = normalizeSharedImports(text);
  text = text.replace(/const sqlite = new SQLiteConnection\(CapacitorSQLite\);\r?\n?/g, '');
  text = text.replace(/const DB_NAME = 'pmposhan';\r?\n?/g, '');
  text = text.replace(/const DB_VERSION = 1;\r?\n?/g, '');
  text = replaceFunctionBlock(
    text,
    'async function getDb(): Promise<SQLiteDBConnection> {',
    'async function ensureSchema(db: SQLiteDBConnection): Promise<void> {',
    operationsOpen,
    'androidOperationsRuntime.ts',
  );
  return text;
});

writeIfChanged('androidStockRuntime.ts', text => {
  text = replaceFunctionBlock(
    text,
    'async function postReceipt(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {',
    'async function listAdjustments(db:SQLiteDBConnection, schoolId:string): Promise<Response> {',
    stockReceipt,
    'androidStockRuntime.ts',
  );
  text = replaceFunctionBlock(
    text,
    'async function postAdjustment(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {',
    'async function listPhysical(db:SQLiteDBConnection, schoolId:string): Promise<Response> {',
    stockAdjustment,
    'androidStockRuntime.ts',
  );
  text = replaceFunctionBlock(
    text,
    'async function postPhysical(db:SQLiteDBConnection, init:RequestInit, user:LocalUser): Promise<Response> {',
    'export async function tryAndroidStockApiFetch(path:string, init:RequestInit={}): Promise<Response|null> {',
    stockPhysical,
    'androidStockRuntime.ts',
  );
  return text;
});

for (const fileName of ['androidRuntime.ts','androidMasterRuntime.ts','androidOperationsRuntime.ts']) {
  const text = fs.readFileSync(path.join(src, fileName), 'utf8');
  if (!text.includes("getSharedAndroidDb")) throw new Error(`${fileName}: shared DB import missing after patch`);
  if (text.includes('new SQLiteConnection(') || text.includes('CapacitorSQLite')) {
    throw new Error(`${fileName}: direct SQLite connection owner remains after patch`);
  }
}

const stockText = fs.readFileSync(path.join(src, 'androidStockRuntime.ts'), 'utf8');
for (const forbidden of ['beginTransaction()', 'commitTransaction()', 'rollbackTransaction()']) {
  if (stockText.includes(forbidden)) {
    throw new Error(`androidStockRuntime.ts: manual stock transaction remains after patch: ${forbidden}`);
  }
}
const atomicCount = (stockText.match(/executeTransaction\(tasks\)/g) || []).length;
if (atomicCount < 3) {
  throw new Error(`androidStockRuntime.ts: expected 3 atomic stock write paths, found ${atomicCount}`);
}

console.log('ANDROID_SQLITE_SINGLE_CONNECTION_PATCH_OK');
console.log('ANDROID_STOCK_ATOMIC_TRANSACTION_PATCH_OK');
