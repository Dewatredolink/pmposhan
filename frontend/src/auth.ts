import Keycloak from 'keycloak-js';

export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:8080',
  realm: import.meta.env.VITE_KEYCLOAK_REALM || 'pmposhan',
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'pmposhan-web',
});

export async function initAuth() {
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
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  await keycloak.updateToken(30);
  const headers = new Headers(init.headers || {});
  headers.set('Authorization', `Bearer ${keycloak.token}`);
  headers.set('Content-Type', 'application/json');
  return fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}${path}`, {
    ...init,
    headers,
  });
}

export function realmRoles(): string[] {
  return keycloak.realmAccess?.roles || [];
}
