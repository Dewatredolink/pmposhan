import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { initAuth } from './auth';

async function bootstrap() {
  const root = ReactDOM.createRoot(document.getElementById('root')!);
  try {
    await initAuth();
    root.render(
      <React.StrictMode>
        <App />
      </React.StrictMode>
    );
  } catch (error) {
    console.error(error);
    root.render(
      <div style={{padding: 24, fontFamily: 'system-ui'}}>
        <h2>PM POSHAN authentication failed</h2>
        <p>Please confirm Keycloak is running at http://localhost:8080 and reload the page.</p>
      </div>
    );
  }
}

bootstrap();
