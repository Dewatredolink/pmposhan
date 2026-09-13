import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, '..', 'src', 'mobile');

function patchFile(fileName, replacements) {
  const filePath = path.join(src, fileName);
  let text = fs.readFileSync(filePath, 'utf8');
  let changed = false;

  for (const [from, to] of replacements) {
    if (text.includes(to)) continue;
    if (!text.includes(from)) {
      throw new Error(`${fileName}: expected source block not found. Refusing partial patch.`);
    }
    text = text.replace(from, to);
    changed = true;
  }

  if (changed) {
    fs.writeFileSync(filePath, text, 'utf8');
    console.log(`PATCHED ${fileName}`);
  } else {
    console.log(`OK      ${fileName}`);
  }
}

const baseImport = "import { CapacitorSQLite, SQLiteConnection, type SQLiteDBConnection } from '@capacitor-community/sqlite';";
const sharedImport = "import type { SQLiteDBConnection } from '@capacitor-community/sqlite';\nimport { getSharedAndroidDb } from './androidSharedDb';";
const connectionState = "const sqlite = new SQLiteConnection(CapacitorSQLite);\nlet dbPromise: Promise<SQLiteDBConnection> | null = null;";
const sharedState = "let dbPromise: Promise<SQLiteDBConnection> | null = null;";

const runtimeOpenOld = `async function openDb(): Promise<SQLiteDBConnection> {
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
}`;

const runtimeOpenNew = `async function openDb(): Promise<SQLiteDBConnection> {
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

const masterOpenOld = `async function getDb(): Promise<SQLiteDBConnection> {
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
}`;

const masterOpenNew = `async function getDb(): Promise<SQLiteDBConnection> {
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

const operationsOpenOld = `async function getDb(): Promise<SQLiteDBConnection> {
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
}`;

const operationsOpenNew = `async function getDb(): Promise<SQLiteDBConnection> {
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

patchFile('androidRuntime.ts', [
  [baseImport, sharedImport],
  [connectionState, sharedState],
  [runtimeOpenOld, runtimeOpenNew],
]);

patchFile('androidMasterRuntime.ts', [
  [baseImport, sharedImport],
  [connectionState, sharedState],
  ["const DB_NAME = 'pmposhan';\nconst DB_VERSION = 1;\n", ''],
  [masterOpenOld, masterOpenNew],
]);

patchFile('androidOperationsRuntime.ts', [
  [baseImport, sharedImport],
  [connectionState, sharedState],
  ["const DB_NAME = 'pmposhan';\nconst DB_VERSION = 1;\n", ''],
  [operationsOpenOld, operationsOpenNew],
]);

console.log('ANDROID_SQLITE_SINGLE_CONNECTION_PATCH_OK');
