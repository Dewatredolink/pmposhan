# PM POSHAN Standalone Edition

Phase 5 converts the existing PM POSHAN server application into a local-first standalone edition for Windows and Android while preserving the current server edition.

## Goals

- Install and run without Docker, PostgreSQL, Keycloak, Nginx, a public domain, or an Internet connection.
- Store operational data locally in SQLite.
- Preserve the existing React bilingual UI and business workflows.
- Support signed UDISE-bound licensing using the existing Ed25519 public verification key model.
- Provide local users and role-based access for SYSTEM_ADMIN, HEADMASTER and TEACHER.
- Provide backup and restore of the complete local data set.
- Build Windows installer first, then Android APK from the same UI/business contracts.

## Storage layout

Windows default application data root:

```text
C:\ProgramData\PMPoshan\
  data\pmposhan.db
  documents\
  photos\
  reports\
  backups\
  config\
```

Android uses the app's private storage and a SQLite database managed by the packaged application.

## Architecture

```text
React UI
  -> standalone data-service abstraction
  -> local API/runtime adapter
  -> SQLite
```

The existing server edition remains:

```text
React -> FastAPI -> PostgreSQL -> Keycloak
```

The standalone edition must not change or weaken the existing server edition.

## Phase 5A scope

1. Define the SQLite foundation schema.
2. Define local authentication and roles.
3. Define application metadata, installation identity and licensing storage.
4. Define backup metadata.
5. Add a storage boundary that can later be implemented by Windows/Tauri and Android/Capacitor adapters.

## Planned packaging

- Windows: Tauri-based installer (`PMPoshan-Setup-v1.0.exe` or MSI depending on release target).
- Android: Capacitor-based APK with a native SQLite plugin.

## Important

Phase 5A is a foundation only. The existing web/server production branch remains the source of truth until standalone functional parity and offline tests are completed.
