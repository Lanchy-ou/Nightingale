import AppIcon from '../components/AppIcon';
import { FormEvent, useState } from 'react';
import { api } from '../api';
import type { CurrentIdentity } from '../types';

// Demo-only account hint (synthetic data; see backend/seed/fixture.py).
const DEMO_ACCOUNTS = [
  { label: 'Clinician', email: 'doctor@demo.clinic' },
  { label: 'Staff', email: 'staff@demo.clinic' },
  { label: 'Patient', email: 'alice@demo.clinic' },
  { label: 'Admin', email: 'admin@demo.clinic' },
];
const DEMO_PASSWORD = 'nightingale-demo';

export default function LoginPage({
  onAuthenticated,
}: {
  onAuthenticated: (identity: CurrentIdentity) => void;
}) {
  const params = new URLSearchParams(window.location.search);
  const [email, setEmail] = useState(params.get('email') ?? '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDemo, setShowDemo] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !email.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      const identity = await api.login(email.trim(), password);
      onAuthenticated(identity);
    } catch (e: any) {
      setError(e?.body?.error?.message ?? 'Login failed. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true"><AppIcon name="feather" /></span>
          <div>
            <h1>Nightingale</h1>
            <p className="muted">Shared longitudinal care record</p>
          </div>
        </div>
        <div className="auth-security-note"><strong>Secure clinic access</strong><span>Your role and permitted workspace are determined by the authenticated server session.</span></div>
        <h2>Sign in</h2>
        <form onSubmit={submit} className="auth-form">
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@clinic.example"
            required
          />
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <div className="form-error">{error}</div>}
          <button className="primary-button auth-submit" type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="auth-foot muted">
          No account? Ask your clinic administrator for an invite link.
        </p>
        <button className="link-btn" onClick={() => setShowDemo((v) => !v)}>
          {showDemo ? 'Hide demo accounts' : 'Show demo accounts'}
        </button>
        {showDemo && (
          <div className="demo-accounts">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                className="demo-account-row"
                onClick={() => {
                  setEmail(account.email);
                  setPassword(DEMO_PASSWORD);
                }}
              >
                <strong>{account.label}</strong>
                <span>{account.email}</span>
              </button>
            ))}
            <p className="muted">Shared demo password: {DEMO_PASSWORD}</p>
          </div>
        )}
      </div>
    </div>
  );
}
