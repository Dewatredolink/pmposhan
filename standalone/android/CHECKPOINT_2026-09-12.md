# PM POSHAN Standalone Android checkpoint — 2026-09-12

Branch: `phase5-standalone`

## Completed today

- Windows standalone remains working and activated.
- Android development environment configured with JDK 21 and Android SDK.
- PM POSHAN Android APK builds and installs.
- PM POSHAN License Authority Android APK builds and runs.
- Android License Authority private-key import hardened for Base64 formatting and local file selection; private key remains external and must never be committed.
- Android login/session reload bug fixed.
- Android mobile drawer/viewport overflow and blank-page protection fixed.
- Android Master Data runtime implemented using local SQLite.
- Android local Government master seed implemented:
  - 24 active ingredients.
  - 12 active menus.
  - Maharashtra PM POSHAN Government recipe standards, effective 2024-06-11.
- Android Master Data UI confirmed working on the physical phone.
- Android Menu Planner + Daily Meal operational runtime added:
  - menus / recipe preview
  - date-wise menu plan GET/PUT
  - daily attendance
  - daily meal entry
  - Draft → Submitted workflow
  - tasting/hygiene validation
  - Headmaster/System Admin verification path
  - stock-consumption integration prepared

## Current physical-phone status

- Activation and local login work.
- Master Data works.
- User reports Menu Planner is currently showing only **2 menus**, although 12 menus exist in Master Data.

## First task next session

Investigate/fix Menu Planner menu visibility. Current frontend filters menus by selected date weekday (`day_of_week`) and, because the standard seed has two menu cycles (W13 and W24), this can result in exactly two visible menus for a weekday. Decide desired behavior and implement one of:

1. Show all 12 menus in the selector, optionally marking suggested menus for the selected weekday; or
2. Add a Week Pattern selector (W13/W24) and show the correct menu for the chosen week/date.

Do not delete or recreate Android app data while testing; use `adb install -r` so installation ID, activation, users, and SQLite data are preserved.

## Next planned work after menu visibility

- Complete Android stock lifecycle: opening balance, receipts, balances, ledger, adjustments, stock controls.
- Verify Government recipe-based automatic stock deduction on meal verification.
- Port School Calendar and compliance.
- Port monthly verification/returns and remaining reports/admin functions.
- Perform offline persistence/reboot/reinstall acceptance.
- Produce final release-signed APK/AAB after functional acceptance.

## Security notes

- Never commit or share `C:\PMPoshan-License-Authority\PRIVATE_KEY_B64.txt`.
- Trusted public key only: `3vsN+dDnufUGNaUnev+i4WMYqRU5OocDl2jXIUWvoFA=`.
- Continue development on `phase5-standalone`; do not merge into `master` until Android acceptance is complete.
