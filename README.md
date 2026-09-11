# PM POSHAN Management System — Phase 1 Foundation

Custom, bilingual Marathi + English foundation using React, FastAPI, PostgreSQL, Keycloak, Redis and MinIO.

## Included
- Docker Compose development stack
- PostgreSQL relational model foundation
- District → Block → Cluster → School hierarchy
- Academic Year master
- Translation master
- Menu master seeded with Week 1/3 and Week 2/4 menus
- Ingredient master seeded with the requested commodities
- Recipe model ready for government-approved per-student rates
- FastAPI endpoints: health, districts, schools, translations, menus, ingredients
- React/TypeScript responsive bilingual dashboard shell
- Keycloak realm with the requested six roles
- Redis and MinIO services ready for jobs/documents

## Important
Recipe quantities are deliberately NOT seeded. Government-approved PM POSHAN entitlement/nutrition quantities must be validated before production data is loaded.

## Start on Windows PowerShell
From the project directory:

```powershell
docker compose up -d --build
```

Seed master data:

```powershell
docker compose exec backend python -m app.seed
```

Check backend:

```powershell
curl.exe http://localhost:8000/api/v1/health
```

Open:
- Web app: http://localhost:5173
- API docs: http://localhost:8000/docs
- Keycloak: http://localhost:8080
- MinIO console: http://localhost:9001

Development Keycloak admin: `admin / admin`. Change all development credentials before any non-local deployment.

Demo Keycloak user: `admin.demo / ChangeMe123!` (temporary password).

## Current auth mode
`AUTH_REQUIRED=false` is intentionally set for the first local boot so the database/UI foundation is easy to validate. Phase 1B should turn authentication enforcement on and add JWT validation + school-scope authorization to backend APIs.

## Next implementation slice
1. Keycloak JWT enforcement and user-school access
2. DailyMealEntry
3. Menu auto-selection
4. Recipe consumption calculator
5. StockReceipt + immutable StockMovement ledger
6. Audit event tables

## Phase 1B - Keycloak authentication

The application now requires Keycloak login. The bundled development realm contains these local test users:

- Teacher: `teacher.demo` / `Teacher@123`
- Headmaster: `headmaster.demo` / `Headmaster@123`
- System Administrator: `admin.demo` / `Admin@123`
- Keycloak master admin console: `admin` / `admin`

The teacher and headmaster are mapped to the seeded `SAMPLE001` school. These are development-only credentials and must be replaced before any pilot or production deployment.

Because realm import is applied when Keycloak starts with a fresh internal database, recreate the Keycloak container after updating from an older Phase 1 package:

```powershell
docker compose stop keycloak
docker compose rm -f keycloak
docker compose up -d --build keycloak backend frontend
docker compose exec backend python -m app.seed
```

Open `http://localhost:5173`. The app should redirect to Keycloak for login and return to the dashboard after authentication.

Useful authenticated API check: open the app first; `/api/v1/health` remains public while application data endpoints require a bearer token.
