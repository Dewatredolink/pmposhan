import { CapacitorSQLite, SQLiteConnection, type SQLiteDBConnection } from '@capacitor-community/sqlite';
import nacl from 'tweetnacl';

const DB_NAME = 'pmposhan';
const DB_VERSION = 1;
const PRODUCT = 'PM_POSHAN';
const LICENSE_PUBLIC_KEY_B64 = '3vsN+dDnufUGNaUnev+i4WMYqRU5OocDl2jXIUWvoFA=';

const sqlite = new SQLiteConnection(CapacitorSQLite);
let dbPromise: Promise<SQLiteDBConnection> | null = null;
const sessions = new Map<string, MobileUser>();

type MobileUser = {
  id: string;
  username: string;
  display_name?: string | null;
  role: 'SYSTEM_ADMIN' | 'HEADMASTER' | 'TEACHER';
};

const BOOTSTRAP_SCHEMA = `
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS app_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS local_users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  role TEXT NOT NULL CHECK (role IN ('SYSTEM_ADMIN','HEADMASTER','TEACHER')),
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS installation_state (
  id INTEGER PRIMARY KEY CHECK (id=1),
  installation_id TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  app_version TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS license_state (
  id INTEGER PRIMARY KEY CHECK (id=1),
  license_json TEXT,
  signature_b64 TEXT,
  activated_at TEXT,
  last_validated_at TEXT
);
CREATE TABLE IF NOT EXISTS districts (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS blocks (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  district_id TEXT NOT NULL REFERENCES districts(id) ON DELETE RESTRICT,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS clusters (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE RESTRICT,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS schools (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  udise_code TEXT NOT NULL UNIQUE,
  cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE RESTRICT,
  name_en TEXT NOT NULL,
  name_mr TEXT NOT NULL,
  village TEXT,
  class_1_5_strength INTEGER NOT NULL DEFAULT 0,
  class_6_8_strength INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS local_user_school_access (
  user_id TEXT NOT NULL REFERENCES local_users(id) ON DELETE CASCADE,
  school_id TEXT NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  preferred_language TEXT NOT NULL DEFAULT 'mr',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, school_id)
);
CREATE TABLE IF NOT EXISTS school_profiles (
  id TEXT PRIMARY KEY,
  school_id TEXT NOT NULL UNIQUE REFERENCES schools(id) ON DELETE CASCADE,
  kitchen_type TEXT NOT NULL DEFAULT 'SCHOOL_KITCHEN',
  cooking_agency TEXT,
  headmaster_name TEXT,
  meal_incharge_name TEXT,
  contact_mobile TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  user_id TEXT REFERENCES local_users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  details_json TEXT
);
`;

function uuid(): string {
  return crypto.randomUUID();
}

function utf8(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => [k, stable(v)]),
    );
  }
  return value;
}

function canonical(value: Record<string, unknown>): Uint8Array {
  return utf8(JSON.stringify(stable(value)));
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function openDb(): Promise<SQLiteDBConnection> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const consistent = (await sqlite.checkConnectionsConsistency()).result;
      const exists = (await sqlite.isConnection(DB_NAME, false)).result;
      const db = consistent && exists
        ? await sqlite.retrieveConnection(DB_NAME, false)
        : await sqlite.createConnection(DB_NAME, false, 'no-encryption', DB_VERSION, false);
      await db.open();
      await db.execute(BOOTSTRAP_SCHEMA);
      const state = await db.query('SELECT installation_id FROM installation_state WHERE id=1');
      if (!state.values?.length) {
        await db.run(
          'INSERT INTO installation_state (id,installation_id,app_version,schema_version) VALUES (1,?,?,?)',
          [uuid(), '1.0-android-dev', DB_VERSION],
        );
      }
      return db;
    })();
  }
  return dbPromise;
}

async function installationId(): Promise<string> {
  const db = await openDb();
  const rows = await db.query('SELECT installation_id FROM installation_state WHERE id=1');
  return String(rows.values?.[0]?.installation_id || '');
}

async function passwordHash(password: string, salt?: Uint8Array): Promise<string> {
  if (password.length < 10) throw new Error('PASSWORD_TOO_SHORT');
  const actualSalt = salt || crypto.getRandomValues(new Uint8Array(16));
  const key = await crypto.subtle.importKey('raw', utf8(password), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', hash: 'SHA-256', salt: actualSalt as BufferSource, iterations: 310000 },
    key,
    256,
  );
  return `pbkdf2_sha256$310000$${bytesToBase64(actualSalt)}$${bytesToBase64(new Uint8Array(bits))}`;
}

async function verifyPassword(password: string, encoded: string): Promise<boolean> {
  try {
    const [algo, rounds, saltB64, digestB64] = encoded.split('$');
    if (algo !== 'pbkdf2_sha256') return false;
    const salt = base64ToBytes(saltB64);
    const key = await crypto.subtle.importKey('raw', utf8(password), 'PBKDF2', false, ['deriveBits']);
    const bits = await crypto.subtle.deriveBits(
      { name: 'PBKDF2', hash: 'SHA-256', salt: salt as BufferSource, iterations: Number(rounds) },
      key,
      256,
    );
    const actual = new Uint8Array(bits);
    const expected = base64ToBytes(digestB64);
    if (actual.length !== expected.length) return false;
    let diff = 0;
    for (let i = 0; i < actual.length; i += 1) diff |= actual[i] ^ expected[i];
    return diff === 0;
  } catch {
    return false;
  }
}

async function validateLicense(payload: Record<string, unknown>, signatureB64: string): Promise<[boolean, string]> {
  const required = ['product','license_id','organization','installation_id','edition','valid_from','valid_until','max_schools'];
  if (!required.every(k => Object.prototype.hasOwnProperty.call(payload, k))) return [false, 'LICENSE_FIELDS_MISSING'];
  if (payload.product !== PRODUCT) return [false, 'LICENSE_PRODUCT_MISMATCH'];
  if (String(payload.installation_id) !== await installationId()) return [false, 'LICENSE_INSTALLATION_MISMATCH'];
  const today = new Date().toISOString().slice(0, 10);
  const from = String(payload.valid_from || '');
  const until = String(payload.valid_until || '');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(until)) return [false, 'LICENSE_DATE_INVALID'];
  if (today < from) return [false, 'LICENSE_NOT_YET_VALID'];
  if (today > until) return [false, 'LICENSE_EXPIRED'];
  const maxSchools = Number(payload.max_schools);
  if (!Number.isInteger(maxSchools) || maxSchools < 1) return [false, 'LICENSE_MAX_SCHOOLS_INVALID'];
  const db = await openDb();
  const count = await db.query('SELECT COUNT(*) AS n FROM schools');
  if (Number(count.values?.[0]?.n || 0) > maxSchools) return [false, 'LICENSE_SCHOOL_LIMIT_EXCEEDED'];
  const edition = String(payload.edition || '').toUpperCase();
  if (edition === 'SCHOOL' || edition === 'STANDALONE') {
    const udiseRows = await db.query("SELECT udise_code FROM schools WHERE udise_code IS NOT NULL AND TRIM(udise_code)<>''");
    const udises = (udiseRows.values || []).map(r => String(r.udise_code));
    if (udises.length) {
      const licensed = String(payload.udise || '').trim();
      if (!licensed) return [false, 'LICENSE_UDISE_REQUIRED'];
      if (!udises.includes(licensed)) return [false, 'LICENSE_UDISE_MISMATCH'];
    }
  }
  try {
    const ok = nacl.sign.detached.verify(canonical(payload), base64ToBytes(signatureB64), base64ToBytes(LICENSE_PUBLIC_KEY_B64));
    return ok ? [true, 'OK'] : [false, 'LICENSE_SIGNATURE_INVALID'];
  } catch {
    return [false, 'LICENSE_SIGNATURE_INVALID'];
  }
}

async function licenseStatus(): Promise<Record<string, unknown>> {
  const db = await openDb();
  const id = await installationId();
  const rows = await db.query('SELECT license_json,signature_b64,activated_at FROM license_state WHERE id=1');
  const row = rows.values?.[0];
  if (!row?.license_json || !row?.signature_b64) return { active: false, reason: 'LICENSE_REQUIRED', installation_id: id };
  try {
    const payload = JSON.parse(String(row.license_json));
    const [active, reason] = await validateLicense(payload, String(row.signature_b64));
    return { active, reason, installation_id: id, license: payload, activated_at: row.activated_at || null };
  } catch {
    return { active: false, reason: 'LICENSE_CORRUPT', installation_id: id };
  }
}

async function bearer(headers: Headers): Promise<MobileUser | null> {
  const raw = headers.get('Authorization') || '';
  if (!raw.toLowerCase().startsWith('bearer ')) return null;
  return sessions.get(raw.slice(7).trim()) || null;
}

async function schoolAccess(user: MobileUser): Promise<Record<string, unknown>[]> {
  const db = await openDb();
  if (user.role === 'SYSTEM_ADMIN') {
    const q = await db.query('SELECT id AS school_id,name_en AS school_name_en,name_mr AS school_name_mr FROM schools WHERE active=1 ORDER BY name_en');
    return (q.values || []).map(x => ({ ...x, role: 'SYSTEM_ADMIN', preferred_language: 'mr' }));
  }
  const q = await db.query(
    `SELECT a.school_id,s.name_en AS school_name_en,s.name_mr AS school_name_mr,u.role,a.preferred_language
     FROM local_user_school_access a JOIN local_users u ON u.id=a.user_id JOIN schools s ON s.id=a.school_id
     WHERE a.user_id=? AND a.active=1 AND s.active=1 ORDER BY s.name_en`,
    [user.id],
  );
  return q.values || [];
}

async function parseBody(init: RequestInit): Promise<any> {
  if (!init.body) return {};
  if (typeof init.body === 'string') return JSON.parse(init.body || '{}');
  throw new Error('ANDROID_BODY_TYPE_UNSUPPORTED');
}

export async function androidApiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const db = await openDb();
  const method = String(init.method || 'GET').toUpperCase();
  const url = new URL(path, 'https://local.pmposhan.invalid');
  const route = url.pathname;
  const headers = new Headers(init.headers || {});

  try {
    if (method === 'GET' && route === '/health') {
      return jsonResponse({ ok: true, mode: 'android-standalone', installation_id: await installationId(), app_version: '1.0-android-dev' });
    }

    if (method === 'GET' && route === '/license/status') return jsonResponse(await licenseStatus());

    if (method === 'POST' && route === '/license/activate') {
      const body = await parseBody(init);
      if (!body?.license || typeof body.signature !== 'string') return jsonResponse({ detail: 'Invalid license package' }, 400);
      const [ok, reason] = await validateLicense(body.license, body.signature);
      if (!ok) return jsonResponse({ detail: reason }, 400);
      const now = new Date().toISOString();
      await db.run(
        `INSERT INTO license_state (id,license_json,signature_b64,activated_at,last_validated_at) VALUES (1,?,?,?,?)
         ON CONFLICT(id) DO UPDATE SET license_json=excluded.license_json,signature_b64=excluded.signature_b64,activated_at=excluded.activated_at,last_validated_at=excluded.last_validated_at`,
        [JSON.stringify(body.license), body.signature, now, now],
      );
      return jsonResponse(await licenseStatus());
    }

    if (method === 'GET' && route === '/setup/status') {
      const users = await db.query('SELECT COUNT(*) AS n FROM local_users');
      const adminCreated = Number(users.values?.[0]?.n || 0) > 0;
      const license = await licenseStatus();
      return jsonResponse({
        installation_id: await installationId(),
        admin_created: adminCreated,
        needs_admin: !adminCreated,
        license_active: !!license.active,
        license_reason: license.reason,
        ready: adminCreated && !!license.active,
      });
    }

    if (method === 'POST' && route === '/setup/admin') {
      const count = await db.query('SELECT COUNT(*) AS n FROM local_users');
      if (Number(count.values?.[0]?.n || 0) > 0) return jsonResponse({ detail: 'FIRST_ADMIN_ALREADY_CREATED' }, 400);
      const body = await parseBody(init);
      const username = String(body.username || '').trim().toLowerCase();
      if (!username) return jsonResponse({ detail: 'USERNAME_REQUIRED' }, 400);
      const id = uuid();
      await db.run(
        `INSERT INTO local_users (id,username,password_hash,display_name,role,active,created_at,updated_at)
         VALUES (?,?,?,?, 'SYSTEM_ADMIN',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)`,
        [id, username, await passwordHash(String(body.password || '')), String(body.display_name || 'System Administrator').trim()],
      );
      return jsonResponse({ created: true, user_id: id });
    }

    if (method === 'POST' && route === '/auth/login') {
      const body = await parseBody(init);
      const username = String(body.username || '').trim().toLowerCase();
      const rows = await db.query('SELECT id,username,password_hash,display_name,role,active FROM local_users WHERE username=?', [username]);
      const row = rows.values?.[0];
      if (!row || !row.active || !(await verifyPassword(String(body.password || ''), String(row.password_hash)))) {
        return jsonResponse({ detail: 'INVALID_CREDENTIALS' }, 401);
      }
      const user: MobileUser = { id: String(row.id), username: String(row.username), display_name: row.display_name || null, role: row.role };
      const token = `${uuid()}${uuid().replaceAll('-', '')}`;
      sessions.set(token, user);
      await db.run('UPDATE local_users SET last_login_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?', [user.id]);
      return jsonResponse({ access_token: token, token_type: 'bearer', user });
    }

    if (method === 'POST' && route === '/auth/logout') {
      const raw = headers.get('Authorization') || '';
      if (raw.toLowerCase().startsWith('bearer ')) sessions.delete(raw.slice(7).trim());
      return jsonResponse({ ok: true });
    }

    const user = await bearer(headers);
    if (!user) return jsonResponse({ detail: 'AUTH_REQUIRED' }, 401);

    if (method === 'GET' && route === '/me') {
      return jsonResponse({
        sub: user.id,
        username: user.username,
        preferred_username: user.username,
        name: user.display_name || user.username,
        email: null,
        roles: [user.role],
        realm_roles: [user.role],
        role: user.role,
        school_access: await schoolAccess(user),
        mode: 'android-standalone',
      });
    }

    if (method === 'GET' && route === '/schools') {
      if (user.role === 'SYSTEM_ADMIN') {
        const q = await db.query('SELECT * FROM schools WHERE active=1 ORDER BY name_en');
        return jsonResponse(q.values || []);
      }
      const q = await db.query(
        `SELECT s.* FROM local_user_school_access a JOIN schools s ON s.id=a.school_id
         WHERE a.user_id=? AND a.active=1 AND s.active=1 ORDER BY s.name_en`,
        [user.id],
      );
      return jsonResponse(q.values || []);
    }

    if (method === 'GET' && route === '/installation') {
      if (user.role !== 'SYSTEM_ADMIN') return jsonResponse({ detail: 'SYSTEM_ADMIN_REQUIRED' }, 403);
      return jsonResponse({ installation_id: await installationId(), app_version: '1.0-android-dev', schema_version: DB_VERSION, data_dir: 'Android app-private SQLite storage' });
    }

    return jsonResponse({ detail: 'ANDROID_ENDPOINT_NOT_PORTED', path: route, method }, 501);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return jsonResponse({ detail: message }, 400);
  }
}
