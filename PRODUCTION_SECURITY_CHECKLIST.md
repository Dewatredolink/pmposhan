# PM POSHAN Production Security Checklist

- Remove existing demo users from the running Keycloak realm.
- Change Keycloak bootstrap/admin credentials from development defaults.
- Change PostgreSQL password from the development default.
- Change MinIO root credentials from the development default.
- Replace localhost-only origins/redirect URIs with the production HTTPS domain.
- Use HTTPS/TLS for frontend, backend, and identity provider.
- Keep individual named accounts; do not share admin accounts.
- Review role assignments.
- Treat credentials previously committed to a public repository as exposed and rotate them.
- Make the repository private unless public source distribution is intentional.
