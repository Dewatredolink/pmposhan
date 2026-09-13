import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, '..', 'src', 'mobile');

const sqliteModule = "@capacitor-community/sqlite";
const typeImport = `import type { SQLiteDBConnection } from '${sqliteModule}';`;
const sharedImport = `import { getSharedAndroidDb } from './androidSharedDb';`;

function normalizeSharedImports(text) {
  // Accept both the old direct CapacitorSQLite import and an already-patched file.
  text = text.replace(
    /import\s+\{[^\n]*CapacitorSQLite[^\n]*\}\s+from\s+['"]@capacitor-community\/sqlite['"];?\r?\n?/,
    '',
  );

  // De-duplicate prior partial patches before adding the canonical pair.
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

for (const fileName of ['androidRuntime.ts','androidMasterRuntime.ts','androidOperationsRuntime.ts']) {
  const text = fs.readFileSync(path.join(src, fileName), 'utf8');
  if (!text.includes("getSharedAndroidDb")) throw new Error(`${fileName}: shared DB import missing after patch`);
  if (text.includes('new SQLiteConnection(') || text.includes('CapacitorSQLite')) {
    throw new Error(`${fileName}: direct SQLite connection owner remains after patch`);
  }
}

console.log('ANDROID_SQLITE_SINGLE_CONNECTION_PATCH_OK');
