import { useEffect, useMemo, useState } from 'react';
import { getFrameworks } from './lib/api';
import { getAuthConfigSummary, getAccessToken, isSignedIn, login, logout } from './lib/auth';
import './styles.css';

const authConfigSummary = getAuthConfigSummary();

export default function App() {
  const [authState, setAuthState] = useState('checking');
  const [tokenPreview, setTokenPreview] = useState('');
  const [apiResult, setApiResult] = useState(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    void refreshSessionState();
  }, []);

  const statusLabel = useMemo(() => {
    if (authState === 'checking') {
      return 'Checking session…';
    }

    return authState === 'authenticated' ? 'Signed in' : 'Signed out';
  }, [authState]);

  async function refreshSessionState() {
    setIsBusy(true);

    try {
      const signedIn = await isSignedIn();
      setAuthState(signedIn ? 'authenticated' : 'signed_out');

      if (!signedIn) {
        setTokenPreview('');
        return;
      }

      const accessToken = await getAccessToken();
      setTokenPreview(accessToken ? `${accessToken.slice(0, 24)}...` : 'No access token available');
    } finally {
      setIsBusy(false);
    }
  }

  async function handleLogin() {
    await login();
  }

  async function handleLogout() {
    setIsBusy(true);

    try {
      await logout();
      setApiResult(null);
      setTokenPreview('');
      setAuthState('signed_out');
    } finally {
      setIsBusy(false);
    }
  }

  async function handleTestApi() {
    setIsBusy(true);
    setApiResult(null);

    try {
      const result = await getFrameworks();
      setApiResult(result);
    } catch (error) {
      setApiResult({
        ok: false,
        status: 500,
        error: error instanceof Error ? error.message : 'Unknown API error.',
      });
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="shell">
      <section className="panel hero-panel">
        <p className="eyebrow">Minimal hosted auth verification</p>
        <h1>DataProtection</h1>
        <p className="lead">
          Confirm Cognito Hosted UI login, session restoration, access-token retrieval, and the
          protected <code>GET /frameworks</code> API call.
        </p>
      </section>

      <section className="panel status-panel">
        <div>
          <p className="label">Auth status</p>
          <strong className={`status-badge ${authState}`}>{statusLabel}</strong>
        </div>
        <div>
          <p className="label">Configured user pool</p>
          <span>{authConfigSummary.userPoolId}</span>
        </div>
        <div>
          <p className="label">Configured region</p>
          <span>{authConfigSummary.region}</span>
        </div>
      </section>

      <section className="panel actions-panel">
        <button disabled={isBusy || authState === 'authenticated'} onClick={() => void handleLogin()} type="button">
          Sign in
        </button>
        <button disabled={isBusy || authState !== 'authenticated'} onClick={() => void handleLogout()} type="button">
          Sign out
        </button>
        <button disabled={isBusy || authState !== 'authenticated'} onClick={() => void handleTestApi()} type="button">
          Test API
        </button>
      </section>

      <section className="panel">
        <p className="label">Access token preview</p>
        <pre>{tokenPreview || 'No active session.'}</pre>
      </section>

      <section className="panel">
        <p className="label">/frameworks response</p>
        <pre>{apiResult ? JSON.stringify(apiResult, null, 2) : 'Run the protected API test after signing in.'}</pre>
      </section>
    </main>
  );
}
