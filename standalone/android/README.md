# PM POSHAN Android Editions

This folder tracks the Android work for both standalone products.

## 1. PM POSHAN Android

The existing React UI is packaged with Capacitor. Android uses local SQLite through `@capacitor-community/sqlite`; there is no Docker, PostgreSQL, Keycloak, Python sidecar, Nginx, or internet requirement for normal standalone use.

The first Android runtime slice currently provides local installation ID, signed-license verification, activation, first-admin setup, local login/logout, `/me`, school access lookup, and app-private SQLite bootstrap storage. Operational modules are ported in later 5E steps.

Android app ID: `com.dewatredolink.pmposhan`

## 2. PM POSHAN License Authority Android

This is a separate trusted-device app for issuing activation packages.

Android app ID: `com.dewatredolink.pmposhan.authority`

Security rules:

- The private Ed25519 signing seed is **never bundled in the APK or Git repository**.
- The authority app accepts the private seed only on the trusted Android authority device.
- It verifies that the imported private seed derives the existing trusted public key `3vsN+dDnufUGNaUnev+i4WMYqRU5OocDl2jXIUWvoFA=`.
- The seed is encrypted with AES-256-GCM using a PBKDF2-SHA256 derived authority PIN before being stored in Android app-private preferences.
- The PIN is required again for each license-signing operation.
- Never paste or send the private key through ChatGPT, email, or source-control messages.

## Windows build prerequisites

Install Android Studio with the Android SDK, platform tools, build tools, and an emulator or USB-connected Android device. Use the JDK bundled with Android Studio or another compatible JDK and set `JAVA_HOME` if required.

Preflight from PowerShell:

```powershell
java -version
node --version
npm --version
Write-Host "JAVA_HOME=$env:JAVA_HOME"
Write-Host "ANDROID_HOME=$env:ANDROID_HOME"
```

Prepare both Android projects from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File ".\standalone\android\build_all.ps1"
```

Expected ending:

```text
ANDROID_PREPARE_OK
```

Open PM POSHAN in Android Studio:

```powershell
cd .\frontend
npx.cmd cap open android
```

Open the License Authority app in Android Studio:

```powershell
cd .\standalone\android\license_authority
npx.cmd cap open android
```

## Phase 5E roadmap

- 5E-A: Capacitor scaffolds, Android local bootstrap runtime, Android License Authority signing app.
- 5E-B: Port full PM POSHAN standalone schema and master data to Android SQLite.
- 5E-C: Port daily attendance/meal, Government recipe standards, stock, verification and reports.
- 5E-D: Port system administration, users, backup/export/import and device/license UI.
- 5E-E: Android acceptance: offline use, reboot persistence, backup/restore, APK/AAB signing and release build.
