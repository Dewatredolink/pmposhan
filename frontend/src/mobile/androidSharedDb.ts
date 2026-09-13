import { CapacitorSQLite, SQLiteConnection, type SQLiteDBConnection } from '@capacitor-community/sqlite';

const DB_NAME = 'pmposhan';
const DB_VERSION = 1;
const sqlite = new SQLiteConnection(CapacitorSQLite);
let sharedDbPromise: Promise<SQLiteDBConnection> | null = null;

/**
 * All Android local runtimes must use one SQLiteConnection owner for pmposhan.
 * Separate SQLiteConnection wrappers for the same native database can race and
 * produce "No available connection for database pmposhan" on Android.
 */
export async function getSharedAndroidDb(): Promise<SQLiteDBConnection> {
  if (!sharedDbPromise) {
    sharedDbPromise = (async () => {
      let db: SQLiteDBConnection;
      try {
        const consistent = (await sqlite.checkConnectionsConsistency()).result;
        const exists = (await sqlite.isConnection(DB_NAME, false)).result;
        if (consistent && exists) {
          db = await sqlite.retrieveConnection(DB_NAME, false);
        } else {
          if (!consistent) {
            try { await sqlite.closeAllConnections(); } catch { /* stale native handles */ }
          }
          db = await sqlite.createConnection(DB_NAME, false, 'no-encryption', DB_VERSION, false);
        }
      } catch {
        // Recover from a stale native connection left by a WebView/app reload.
        try { await sqlite.closeAllConnections(); } catch { /* ignore */ }
        db = await sqlite.createConnection(DB_NAME, false, 'no-encryption', DB_VERSION, false);
      }

      try { await db.open(); } catch { /* already open */ }
      return db;
    })().catch(error => {
      sharedDbPromise = null;
      throw error;
    });
  }
  return sharedDbPromise;
}
