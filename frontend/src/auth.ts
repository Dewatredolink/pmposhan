import Keycloak from 'keycloak-js';

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
const standaloneMode = String(import.meta.env.VITE_STANDALONE_MODE || '').toLowerCase() === 'true';
const standaloneTokenKey = 'pmposhan.standalone.token';
const standaloneUserKey = 'pmposhan.standalone.user';

export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:8080',
  realm: import.meta.env.VITE_KEYCLOAK_REALM || 'pmposhan',
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'pmposhan-web',
});

export function isStandaloneMode(): boolean {
  return standaloneMode;
}

export function hasStandaloneSession(): boolean {
  return !!sessionStorage.getItem(standaloneTokenKey);
}

export async function standaloneLogin(username: string, password: string) {
  const r = await fetch(`${apiBase}/auth/login`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({username, password}),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `Login HTTP ${r.status}`);
  sessionStorage.setItem(standaloneTokenKey, body.access_token);
  sessionStorage.setItem(standaloneUserKey, JSON.stringify(body.user || {}));
  return body.user;
}

export async function standaloneLogout() {
  const token = sessionStorage.getItem(standaloneTokenKey);
  if (token) {
    await fetch(`${apiBase}/auth/logout`, {
      method: 'POST',
      headers: {'Authorization': `Bearer ${token}`},
    }).catch(() => undefined);
  }
  sessionStorage.removeItem(standaloneTokenKey);
  sessionStorage.removeItem(standaloneUserKey);
}

export async function initAuth() {
  if (standaloneMode) return true;
  const authenticated = await keycloak.init({
    onLoad: 'login-required',
    pkceMethod: 'S256',
    checkLoginIframe: false,
  });
  if (!authenticated) {
    await keycloak.login();
  }
  window.setInterval(() => {
    keycloak.updateToken(60).catch(() => keycloak.login());
  }, 30000);
  return authenticated;
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers || {});
  if (standaloneMode) {
    const token = sessionStorage.getItem(standaloneTokenKey);
    if (token) headers.set('Authorization', `Bearer ${token}`);
  } else {
    await keycloak.updateToken(30);
    headers.set('Authorization', `Bearer ${keycloak.token}`);
  }
  if (!headers.has('Content-Type') && init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  return fetch(`${apiBase}${path}`, {...init, headers});
}

export function realmRoles(): string[] {
  if (standaloneMode) {
    try {
      const user = JSON.parse(sessionStorage.getItem(standaloneUserKey) || '{}');
      return user.role ? [user.role] : [];
    } catch {
      return [];
    }
  }
  return keycloak.realmAccess?.roles || [];
}
