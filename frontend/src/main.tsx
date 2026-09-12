import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import {
  apiFetch,
  hasStandaloneSession,
  initAuth,
  isAndroidMode,
  isStandaloneMode,
  standaloneLogout,
} from './auth';
import ActivationScreen, { fetchLicenseStatus } from './pages/ActivationScreen';
import StandaloneLogin from './standalone/StandaloneLogin';
import StandaloneSetup, { fetchStandaloneSetupStatus } from './standalone/StandaloneSetup';

const root = ReactDOM.createRoot(document.getElementById('root')!);

async function renderApp() {
  await initAuth();
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}

function renderStandaloneLogin() {
  root.render(
    <React.StrictMode>
      <StandaloneLogin
        onLoggedIn={() => {
          // Android keeps its local bearer session in the in-process runtime.
          // A full WebView reload here would recreate that runtime and discard
          // the freshly issued token before /me and /schools are requested.
          void renderApp();
        }}
      />
    </React.StrictMode>
  );
}

async function bootstrap() {
  try {
    const license = await fetchLicenseStatus();
    if (!license.active) {
      root.render(
        <React.StrictMode>
          <ActivationScreen status={license} onActivated={() => window.location.reload()} />
        </React.StrictMode>
      );
      return;
    }

    if (isStandaloneMode()) {
      const setup = await fetchStandaloneSetupStatus();
      if (setup.needs_admin || setup.admin_created === false) {
        root.render(
          <React.StrictMode>
            <StandaloneSetup onCreated={() => window.location.reload()} />
          </React.StrictMode>
        );
        return;
      }

      // An Android WebView/page reload can leave a token in sessionStorage while
      // the in-memory local runtime session has been recreated. Validate any
      // existing token before showing the application. If it is stale, clear it
      // and ask the user to log in again instead of displaying AUTH_REQUIRED.
      if (hasStandaloneSession() && isAndroidMode()) {
        const probe = await apiFetch('/me');
        if (!probe.ok) {
          await standaloneLogout();
          renderStandaloneLogin();
          return;
        }
      }

      if (!hasStandaloneSession()) {
        renderStandaloneLogin();
        return;
      }
    }

    await renderApp();
  } catch (error) {
    console.error(error);
    root.render(
      <div style={{padding: 24, fontFamily: 'system-ui'}}>
        <h2>PM POSHAN startup failed</h2>
        <p>{isAndroidMode()
          ? 'The Android local database/runtime could not start. Close and reopen the app; if the problem continues, check the Android build log.'
          : isStandaloneMode()
            ? 'Please confirm the PM POSHAN local service is running on this computer and reload the app.'
            : 'Please confirm Keycloak and the PM POSHAN server are running and reload the page.'}</p>
      </div>
    );
  }
}

bootstrap();

if (!isAndroidMode() && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(error => {
      console.warn('PM POSHAN service worker registration failed', error);
    });
  });
}
