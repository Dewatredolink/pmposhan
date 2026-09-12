# Phase 4A-S4B5 Backup / Restore Rehearsal

Completed successfully on 2026-09-12.

Verified:
- PM POSHAN PostgreSQL custom-format backup created and readable.
- Keycloak PostgreSQL custom-format backup created and readable.
- PM POSHAN restored successfully into isolated test database.
- School UDISE restored as 27360803502.
- Installation/license state restored with installation ID:
  b63ed575-e52f-4437-a329-f6cb1100928b
- Keycloak restored successfully into isolated test database.
- Realms restored: master, pmposhan.
- Production user system.admin restored and enabled.
- Temporary restore databases removed after verification.

Backup location:
backups\s4b5_20260912_135528

Important:
- Backup dump files are sensitive and must not be committed to Git.
- Store an additional encrypted/off-machine copy before production deployment.
