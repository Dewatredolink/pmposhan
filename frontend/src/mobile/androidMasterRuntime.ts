import { CapacitorSQLite, SQLiteConnection, type SQLiteDBConnection } from '@capacitor-community/sqlite';
import { androidApiFetch } from './androidRuntime';

const DB_NAME = 'pmposhan';
const DB_VERSION = 1;
const GOV_EFFECTIVE_FROM = '2024-06-11';

const sqlite = new SQLiteConnection(CapacitorSQLite);
let dbPromise: Promise<SQLiteDBConnection> | null = null;

const STANDARD_INGREDIENTS = [
  ['RICE','Rice','तांदूळ','CEREAL_PULSE','KG',1],
  ['MOONGDAL','Moong Dal','मुगडाळ','CEREAL_PULSE','KG',1],
  ['TURDAL','Tur Dal','तूरडाळ','CEREAL_PULSE','KG',1],
  ['MASOORDAL','Masoor Dal','मसूरडाळ','CEREAL_PULSE','KG',1],
  ['MATKI','Matki','मटकी','SPROUT','KG',1],
  ['MOONG','Moong','मूग','SPROUT','KG',1],
  ['CHAWLI','Chawli','चवळी','SPROUT','KG',1],
  ['HARBHARA','Harbhara','हरभरा','SPROUT','KG',1],
  ['VATANA','Peas','वाटाणा','SPROUT','KG',1],
  ['SOYA','Soyabean','सोयाबीन','SPROUT','KG',1],
  ['CUMIN','Cumin','जिरे','SPICE','KG',1],
  ['MUSTARD','Mustard','मोहरी','SPICE','KG',1],
  ['TURMERIC','Turmeric','हळद','SPICE','KG',1],
  ['GARAM','Garam Masala','गरम मसाला','SPICE','KG',1],
  ['OIL','Cooking Oil','खाद्यतेल','CONSUMABLE','KG',1],
  ['SALT','Salt','मीठ','CONSUMABLE','KG',1],
  ['SUGAR','Sugar/Jaggery','साखर/गुळ','CONSUMABLE','KG',1],
  ['MILK','Milk Powder','दूध पावडर','CONSUMABLE','KG',1],
  ['RAGI','Ragi','नाचणी','CONSUMABLE','KG',1],
  ['EGG','Eggs','अंडी','OTHER','EA',1],
  ['VEGETABLE','Vegetable Cost','भाजीपाला खर्च','OTHER','INR',0],
  ['FUEL','Fuel Cost','इंधन खर्च','OTHER','INR',0],
  ['VEGQTY','Vegetables','भाजीपाला','VEGETABLE','KG',0],
  ['RICEFLOUR','Rice Flour','तांदळाचे पीठ','CEREAL_PULSE','KG',1],
] as const;

const STANDARD_MENUS = [
  ['VPUL-W13-MON','Vegetable Pulao','व्हेज पुलाव','W13',1],
  ['MDKH-W13-TUE','Moong Dal Khichdi','मुगडाळ खिचडी','W13',2],
  ['CHPUL-W13-WED','Chana Pulao','चना पुलाव','W13',3],
  ['MBHAT-W13-THU','Masale Bhat','मसाले भात','W13',4],
  ['CHKH-W13-FRI','Chawli Khichdi','चवळी खिचडी','W13',5],
  ['MUSAL-W13-SAT','Matki Usal','मटकी उसळ','W13',6],
  ['MTPUL-W24-MON','Matar Pulao','मटर पुलाव','W24',1],
  ['MDVB-W24-TUE','Moong Drumstick Varan Bhat','मुग शेवगा वरणभात','W24',2],
  ['SOYP-W24-WED','Soya Pulao','सोया पुलाव','W24',3],
  ['VPUL-W24-THU','Vegetable Pulao','व्हेज पुलाव','W24',4],
  ['MDKH-W24-FRI','Moong Dal Khichdi','मुगडाळ खिचडी','W24',5],
  ['MASP-W24-SAT','Masoor Pulao','मसुरी पुलाव','W24',6],
] as const;

const MENU_COMPONENTS: Record<string, Array<[string, number, number]>> = {
  'VPUL-W13-MON': [['VATANA',0.020,0.030]],
  'MDKH-W13-TUE': [['MOONGDAL',0.020,0.030]],
  'CHPUL-W13-WED': [['HARBHARA',0.020,0.030],['RICEFLOUR',0.020,0.015]],
  'MBHAT-W13-THU': [['VATANA',0.020,0.030]],
  'CHKH-W13-FRI': [['CHAWLI',0.020,0.030]],
  'MUSAL-W13-SAT': [['MATKI',0.020,0.030]],
  'MTPUL-W24-MON': [['VATANA',0.020,0.030]],
  'MDVB-W24-TUE': [['MOONG',0.010,0.015],['TURDAL',0.010,0.015]],
  'SOYP-W24-WED': [['SOYA',0.020,0.030]],
  'VPUL-W24-THU': [['VATANA',0.020,0.030]],
  'MDKH-W24-FRI': [['MOONGDAL',0.020,0.030]],
  'MASP-W24-SAT': [['MASOORDAL',0.020,0.030],['SUGAR',0.006,0.009]],
};

function uuid(): string { return crypto.randomUUID(); }
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: {'Content-Type':'application/json'} });
}
function boolValue(v: unknown, fallback = true): number {
  if (v === undefined || v === null) return fallback ? 1 : 0;
  return v ? 1 : 0;
}
function rowsWithBooleans(rows: any[]): any[] {
  return rows.map(r => ({...r, active: !!Number(r.active), ...(Object.prototype.hasOwnProperty.call(r,'track_inventory') ? {track_inventory: !!Number(r.track_inventory)} : {})}));
}
async function bodyJson(init: RequestInit): Promise<any> {
  if (!init.body) return {};
  if (typeof init.body === 'string') return JSON.parse(init.body || '{}');
  throw new Error('ANDROID_BODY_TYPE_UNSUPPORTED');
}

async function getDb(): Promise<SQLiteDBConnection> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const consistent = (await sqlite.checkConnectionsConsistency()).result;
      const exists = (await sqlite.isConnection(DB_NAME, false)).result;
      const db = consistent && exists
        ? await sqlite.retrieveConnection(DB_NAME, false)
        : await sqlite.createConnection(DB_NAME, false, 'no-encryption', DB_VERSION, false);
      try { await db.open(); } catch { /* already open */ }
      await ensureSchema(db);
      await seedGovernmentMasters(db);
      return db;
    })();
  }
  return dbPromise;
}

async function ensureSchema(db: SQLiteDBConnection): Promise<void> {
  await db.execute(`
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS ingredients (
      id TEXT PRIMARY KEY,
      code TEXT NOT NULL UNIQUE,
      name_en TEXT NOT NULL,
      name_mr TEXT NOT NULL,
      category TEXT NOT NULL DEFAULT 'CONSUMABLE',
      base_unit TEXT NOT NULL DEFAULT 'KG',
      reorder_level REAL NOT NULL DEFAULT 0,
      safety_stock REAL NOT NULL DEFAULT 0,
      track_inventory INTEGER NOT NULL DEFAULT 1 CHECK(track_inventory IN (0,1)),
      active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS menus (
      id TEXT PRIMARY KEY,
      code TEXT NOT NULL UNIQUE,
      name_en TEXT NOT NULL,
      name_mr TEXT NOT NULL,
      week_pattern TEXT NOT NULL DEFAULT 'CUSTOM',
      day_of_week INTEGER NOT NULL DEFAULT 1,
      active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS recipes (
      id TEXT PRIMARY KEY,
      menu_id TEXT NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
      ingredient_id TEXT NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
      student_group TEXT NOT NULL CHECK(student_group IN ('CLASS_1_5','CLASS_6_8')),
      qty_per_student REAL NOT NULL DEFAULT 0,
      measurement_unit TEXT NOT NULL DEFAULT 'KG',
      effective_from TEXT NOT NULL,
      effective_to TEXT,
      version INTEGER NOT NULL DEFAULT 1,
      active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(menu_id,ingredient_id,student_group,effective_from)
    );
  `);
}

async function seedGovernmentMasters(db: SQLiteDBConnection): Promise<void> {
  for (const [code,nameEn,nameMr,category,unit,track] of STANDARD_INGREDIENTS) {
    const found = await db.query('SELECT id FROM ingredients WHERE code=?',[code]);
    if (!found.values?.length) {
      await db.run(`INSERT INTO ingredients
        (id,code,name_en,name_mr,category,base_unit,reorder_level,safety_stock,track_inventory,active)
        VALUES (?,?,?,?,?,?,0,0,?,1)`,[uuid(),code,nameEn,nameMr,category,unit,track]);
    }
  }
  for (const [code,nameEn,nameMr,weekPattern,day] of STANDARD_MENUS) {
    const found = await db.query('SELECT id FROM menus WHERE code=?',[code]);
    if (!found.values?.length) {
      await db.run(`INSERT INTO menus (id,code,name_en,name_mr,week_pattern,day_of_week,active)
        VALUES (?,?,?,?,?,?,1)`,[uuid(),code,nameEn,nameMr,weekPattern,day]);
    }
  }

  const ingredientRows = await db.query('SELECT id,code FROM ingredients');
  const menuRows = await db.query('SELECT id,code FROM menus');
  const ingredientIds = new Map((ingredientRows.values || []).map((r:any)=>[String(r.code),String(r.id)]));
  const menuIds = new Map((menuRows.values || []).map((r:any)=>[String(r.code),String(r.id)]));

  const common: Array<[string,number,number]> = [
    ['RICE',0.100,0.150],
    ['OIL',0.005,0.0075],
    ['VEGQTY',0.050,0.075],
  ];
  for (const [menuCode, components] of Object.entries(MENU_COMPONENTS)) {
    const menuId = menuIds.get(menuCode);
    if (!menuId) continue;
    for (const [ingredientCode,q15,q68] of [...common,...components]) {
      const ingredientId = ingredientIds.get(ingredientCode);
      if (!ingredientId) continue;
      for (const [group,qty] of [['CLASS_1_5',q15],['CLASS_6_8',q68]] as const) {
        await db.run(`INSERT INTO recipes
          (id,menu_id,ingredient_id,student_group,qty_per_student,measurement_unit,effective_from,version,active)
          VALUES (?,?,?,?,?,'KG',?,1,1)
          ON CONFLICT(menu_id,ingredient_id,student_group,effective_from)
          DO UPDATE SET qty_per_student=excluded.qty_per_student,measurement_unit='KG',active=1,updated_at=CURRENT_TIMESTAMP`,
          [uuid(),menuId,ingredientId,group,qty,GOV_EFFECTIVE_FROM]);
      }
    }
  }
  await db.run(`INSERT INTO app_metadata (key,value,updated_at) VALUES ('maharashtra_pm_poshan_standard',?,CURRENT_TIMESTAMP)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP`,
    [JSON.stringify({authority:'Government of Maharashtra',scheme:'PM POSHAN',gr_number:'शापोआ-2022/प्र.क्र.117/एस.डी.3',gr_date:'2024-06-11',effective_from:GOV_EFFECTIVE_FROM})]);
}

async function requireUser(init: RequestInit): Promise<{response?:Response; user?:any}> {
  const probe = await androidApiFetch('/me',{headers:init.headers || {}});
  if (!probe.ok) return {response:probe};
  return {user:await probe.json()};
}

async function listTable(db: SQLiteDBConnection, table: string): Promise<Response> {
  const order = table === 'menus' ? 'day_of_week,code' : table === 'schools' ? 'name_en,code' : 'code';
  const q = await db.query(`SELECT * FROM ${table} ORDER BY ${order}`);
  return jsonResponse(rowsWithBooleans(q.values || []));
}

async function saveMaster(db: SQLiteDBConnection, kind: string, id: string | null, data: any): Promise<Response> {
  const editing = !!id;
  if (kind === 'districts') {
    const values=[String(data.code||'').trim(),String(data.name_en||'').trim(),String(data.name_mr||'').trim(),boolValue(data.active)];
    if (!values[0] || !values[1] || !values[2]) return jsonResponse({detail:'MASTER_FIELDS_REQUIRED'},400);
    if (editing) await db.run('UPDATE districts SET code=?,name_en=?,name_mr=?,active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[...values,id]);
    else { id=uuid(); await db.run('INSERT INTO districts (id,code,name_en,name_mr,active) VALUES (?,?,?,?,?)',[id,...values]); }
  } else if (kind === 'blocks') {
    const values=[String(data.code||'').trim(),String(data.district_id||'').trim(),String(data.name_en||'').trim(),String(data.name_mr||'').trim(),boolValue(data.active)];
    if (!values[0] || !values[1] || !values[2] || !values[3]) return jsonResponse({detail:'MASTER_FIELDS_REQUIRED'},400);
    if (editing) await db.run('UPDATE blocks SET code=?,district_id=?,name_en=?,name_mr=?,active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[...values,id]);
    else { id=uuid(); await db.run('INSERT INTO blocks (id,code,district_id,name_en,name_mr,active) VALUES (?,?,?,?,?,?)',[id,...values]); }
  } else if (kind === 'clusters') {
    const values=[String(data.code||'').trim(),String(data.block_id||'').trim(),String(data.name_en||'').trim(),String(data.name_mr||'').trim(),boolValue(data.active)];
    if (!values[0] || !values[1] || !values[2] || !values[3]) return jsonResponse({detail:'MASTER_FIELDS_REQUIRED'},400);
    if (editing) await db.run('UPDATE clusters SET code=?,block_id=?,name_en=?,name_mr=?,active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[...values,id]);
    else { id=uuid(); await db.run('INSERT INTO clusters (id,code,block_id,name_en,name_mr,active) VALUES (?,?,?,?,?,?)',[id,...values]); }
  } else if (kind === 'schools') {
    const values=[String(data.code||'').trim(),String(data.udise_code||'').trim(),String(data.cluster_id||'').trim(),String(data.name_en||'').trim(),String(data.name_mr||'').trim(),String(data.village||'').trim(),Number(data.class_1_5_strength||0),Number(data.class_6_8_strength||0),boolValue(data.active)];
    if (!values[0] || !values[1] || !values[2] || !values[3] || !values[4]) return jsonResponse({detail:'MASTER_FIELDS_REQUIRED'},400);
    if (editing) await db.run('UPDATE schools SET code=?,udise_code=?,cluster_id=?,name_en=?,name_mr=?,village=?,class_1_5_strength=?,class_6_8_strength=?,active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[...values,id]);
    else { id=uuid(); await db.run('INSERT INTO schools (id,code,udise_code,cluster_id,name_en,name_mr,village,class_1_5_strength,class_6_8_strength,active) VALUES (?,?,?,?,?,?,?,?,?,?)',[id,...values]); }
  } else if (kind === 'ingredients') {
    const values=[String(data.code||'').trim().toUpperCase(),String(data.name_en||'').trim(),String(data.name_mr||'').trim(),String(data.category||'CONSUMABLE').trim(),String(data.base_unit||'KG').trim().toUpperCase(),Number(data.reorder_level||0),Number(data.safety_stock||0),boolValue(data.track_inventory),boolValue(data.active)];
    if (!values[0] || !values[1] || !values[2]) return jsonResponse({detail:'MASTER_FIELDS_REQUIRED'},400);
    if (editing) await db.run('UPDATE ingredients SET code=?,name_en=?,name_mr=?,category=?,base_unit=?,reorder_level=?,safety_stock=?,track_inventory=?,active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[...values,id]);
    else { id=uuid(); await db.run('INSERT INTO ingredients (id,code,name_en,name_mr,category,base_unit,reorder_level,safety_stock,track_inventory,active) VALUES (?,?,?,?,?,?,?,?,?,?)',[id,...values]); }
  } else if (kind === 'menus') {
    const values=[String(data.code||'').trim().toUpperCase(),String(data.name_en||'').trim(),String(data.name_mr||'').trim(),String(data.week_pattern||'CUSTOM').trim(),Number(data.day_of_week||1),boolValue(data.active)];
    if (!values[0] || !values[1] || !values[2]) return jsonResponse({detail:'MASTER_FIELDS_REQUIRED'},400);
    if (editing) await db.run('UPDATE menus SET code=?,name_en=?,name_mr=?,week_pattern=?,day_of_week=?,active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[...values,id]);
    else { id=uuid(); await db.run('INSERT INTO menus (id,code,name_en,name_mr,week_pattern,day_of_week,active) VALUES (?,?,?,?,?,?,?)',[id,...values]); }
  } else return jsonResponse({detail:'MASTER_KIND_INVALID'},404);
  return jsonResponse({ok:true,id});
}

async function recipeStandard(db: SQLiteDBConnection, menuId: string, onDate: string): Promise<Response> {
  const q = await db.query(`
    SELECT i.id AS ingredient_id,i.code,i.name_en,i.name_mr,i.base_unit,
      COALESCE((SELECT r.qty_per_student FROM recipes r WHERE r.menu_id=? AND r.ingredient_id=i.id AND r.student_group='CLASS_1_5' AND r.active=1 AND r.effective_from<=? ORDER BY r.effective_from DESC,r.version DESC LIMIT 1),0) AS qty_class_1_5,
      COALESCE((SELECT r.qty_per_student FROM recipes r WHERE r.menu_id=? AND r.ingredient_id=i.id AND r.student_group='CLASS_6_8' AND r.active=1 AND r.effective_from<=? ORDER BY r.effective_from DESC,r.version DESC LIMIT 1),0) AS qty_class_6_8,
      COALESCE((SELECT r.measurement_unit FROM recipes r WHERE r.menu_id=? AND r.ingredient_id=i.id AND r.active=1 AND r.effective_from<=? ORDER BY r.effective_from DESC,r.version DESC LIMIT 1),i.base_unit) AS unit
    FROM ingredients i WHERE i.active=1 ORDER BY i.name_en,i.code`,[menuId,onDate,menuId,onDate,menuId,onDate]);
  return jsonResponse({menu_id:menuId,on_date:onDate,items:q.values || []});
}

async function saveRecipeStandard(db: SQLiteDBConnection, menuId: string, data: any): Promise<Response> {
  const effectiveFrom=String(data.effective_from || GOV_EFFECTIVE_FROM);
  const items=Array.isArray(data.items)?data.items:[];
  for (const x of items) {
    const ingredientId=String(x.ingredient_id||''); if(!ingredientId) continue;
    const unit=String(x.unit||'KG').toUpperCase();
    for (const [group,qty] of [['CLASS_1_5',Number(x.qty_class_1_5)||0],['CLASS_6_8',Number(x.qty_class_6_8)||0]] as const) {
      await db.run(`INSERT INTO recipes (id,menu_id,ingredient_id,student_group,qty_per_student,measurement_unit,effective_from,version,active)
        VALUES (?,?,?,?,?,?,?,1,1)
        ON CONFLICT(menu_id,ingredient_id,student_group,effective_from)
        DO UPDATE SET qty_per_student=excluded.qty_per_student,measurement_unit=excluded.measurement_unit,active=1,updated_at=CURRENT_TIMESTAMP`,
        [uuid(),menuId,ingredientId,group,qty,unit,effectiveFrom]);
    }
  }
  return jsonResponse({ok:true,menu_id:menuId,effective_from:effectiveFrom,items_saved:items.length});
}

async function recipePreview(db: SQLiteDBConnection, menuId: string, date: string, c15: number, c68: number): Promise<Response> {
  const standard = await recipeStandard(db,menuId,date);
  const data:any = await standard.json();
  const items=(data.items || []).filter((x:any)=>Number(x.qty_class_1_5)>0 || Number(x.qty_class_6_8)>0).map((x:any)=>{
    const q15=Number(x.qty_class_1_5)||0, q68=Number(x.qty_class_6_8)||0;
    const r15=q15*c15, r68=q68*c68;
    return {ingredient_id:x.ingredient_id,code:x.code,name_en:x.name_en,name_mr:x.name_mr,unit:x.unit,qty_per_student_class_1_5:q15,qty_per_student_class_6_8:q68,required_class_1_5:r15,required_class_6_8:r68,required_total:r15+r68};
  });
  return jsonResponse({menu_id:menuId,on_date:date,class_1_5:c15,class_6_8:c68,items});
}

export async function tryAndroidMasterApiFetch(path: string, init: RequestInit = {}): Promise<Response | null> {
  const method=String(init.method||'GET').toUpperCase();
  const url=new URL(path,'https://local.pmposhan.invalid');
  const route=url.pathname;
  const masterMatch=route.match(/^\/master\/(districts|blocks|clusters|schools|ingredients|menus)(?:\/([^/]+))?$/);
  const recipeMatch=route.match(/^\/master\/menus\/([^/]+)\/recipe-standard$/);
  const previewMatch=route.match(/^\/menus\/([^/]+)\/recipe-preview$/);
  const activeMenus=route==='/menus';
  if (!masterMatch && !recipeMatch && !previewMatch && !activeMenus) return null;

  const auth=await requireUser(init);
  if (auth.response) return auth.response;
  const db=await getDb();

  try {
    if (activeMenus && method==='GET') {
      const q=await db.query('SELECT * FROM menus WHERE active=1 ORDER BY day_of_week,code');
      return jsonResponse(rowsWithBooleans(q.values || []));
    }
    if (previewMatch && method==='GET') {
      return recipePreview(db,decodeURIComponent(previewMatch[1]),url.searchParams.get('on_date') || new Date().toISOString().slice(0,10),Number(url.searchParams.get('class_1_5')||0),Number(url.searchParams.get('class_6_8')||0));
    }
    if (recipeMatch) {
      const menuId=decodeURIComponent(recipeMatch[1]);
      if (method==='GET') return recipeStandard(db,menuId,url.searchParams.get('on_date') || new Date().toISOString().slice(0,10));
      if (method==='PUT') {
        if (!auth.user?.roles?.includes('SYSTEM_ADMIN')) return jsonResponse({detail:'SYSTEM_ADMIN_REQUIRED'},403);
        return saveRecipeStandard(db,menuId,await bodyJson(init));
      }
      return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);
    }
    if (masterMatch) {
      const kind=masterMatch[1];
      const id=masterMatch[2] ? decodeURIComponent(masterMatch[2]) : null;
      if (method==='GET' && !id) return listTable(db,kind);
      if (!auth.user?.roles?.includes('SYSTEM_ADMIN')) return jsonResponse({detail:'SYSTEM_ADMIN_REQUIRED'},403);
      if (method==='POST' && !id) return saveMaster(db,kind,null,await bodyJson(init));
      if (method==='PUT' && id) return saveMaster(db,kind,id,await bodyJson(init));
      return jsonResponse({detail:'METHOD_NOT_ALLOWED'},405);
    }
    return null;
  } catch (error) {
    return jsonResponse({detail:error instanceof Error ? error.message : String(error)},400);
  }
}
