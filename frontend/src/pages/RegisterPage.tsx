import { FormEvent, useEffect, useState } from 'react';
import { api } from '../api';
import type { InvitePreview, RegisterResult } from '../types';

const ROLE_LABELS: Record<string, string> = {
  patient: 'Patient',
  staff: 'Staff',
  clinician: 'Clinician',
  admin: 'Admin',
};

type PreviewState =
  | { kind: 'loading' }
  | { kind: 'invalid' }
  | { kind: 'used' }
  | { kind: 'expired' }
  | { kind: 'valid'; preview: InvitePreview };

export default function RegisterPage() {
  const token = new URLSearchParams(window.location.search).get('token') ?? '';
  const [state, setState] = useState<PreviewState>({ kind: 'loading' });
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<RegisterResult | null>(null);

  useEffect(() => {
    if (!token) {
      setState({ kind: 'invalid' });
      return;
    }
    let cancelled = false;
    api
      .getInvitePreview(token)
      .then((preview) => {
        if (cancelled) return;
        if (preview.status === 'valid') setState({ kind: 'valid', preview });
        else if (preview.status === 'used') setState({ kind: 'used' });
        else setState({ kind: 'expired' });
      })
      .catch((e: any) => {
        if (cancelled) return;
        if (e?.status === 404) setState({ kind: 'invalid' });
        else setState({ kind: 'invalid' });
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || state.kind !== 'valid') return;
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.register({
        token,
        password,
        name: state.preview.role === 'patient' ? undefined : name.trim(),
      });
      setDone(result);
    } catch (e: any) {
      setError(e?.body?.error?.message ?? 'Registration failed. Please contact your clinic.');
    } finally {
      setBusy(false);
    }
  }

  function toLogin(email?: string) {
    window.location.href = email ? `/login?email=${encodeURIComponent(email)}` : '/login';
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true">N</span>
          <div>
            <h1>Nightingale</h1>
            <p className="muted">Accept your clinic invite</p>
          </div>
        </div>

        {state.kind === 'loading' && <p className="muted">Checking invite…</p>}

        {state.kind === 'invalid' && (
          <div className="invite-terminal">
            <h2>Invite invalid</h2>
            <p>This invite link is not recognized. Ask your clinic administrator for a new one.</p>
            <button className="secondary-button" onClick={() => toLogin()}>Back to sign in</button>
          </div>
        )}

        {state.kind === 'used' && (
          <div className="invite-terminal">
            <h2>Invite already used</h2>
            <p>This invite link was already used to register an account. Sign in with your email instead.</p>
            <button className="primary-button" onClick={() => toLogin()}>Go to sign in</button>
          </div>
        )}

        {state.kind === 'expired' && (
          <div className="invite-terminal">
            <h2>Invite expired</h2>
            <p>This invite link has expired. Ask your clinic administrator to issue a new one.</p>
            <button className="secondary-button" onClick={() => toLogin()}>Back to sign in</button>
          </div>
        )}

        {state.kind === 'valid' && !done && (
          <>
            <h2>Create your account</h2>
            <div className="invite-summary">
              <p>
                <span className="eyebrow">Invited as</span>
                <strong>{ROLE_LABELS[state.preview.role] ?? state.preview.role}</strong>
              </p>
              <p>
                <span className="eyebrow">Clinic</span>
                <strong>{state.preview.clinic_name}</strong>
              </p>
              <p>
                <span className="eyebrow">Email</span>
                <strong>{state.preview.email_masked}</strong>
              </p>
              {state.preview.patient_name && (
                <p>
                  <span className="eyebrow">Links to existing record</span>
                  <strong>{state.preview.patient_name}</strong>
                </p>
              )}
            </div>
            <form onSubmit={submit} className="auth-form">
              {state.preview.role !== 'patient' && (
                <>
                  <label htmlFor="reg-name">Your name</label>
                  <input
                    id="reg-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Dr. Full Name"
                    required
                    minLength={1}
                    maxLength={255}
                  />
                </>
              )}
              <label htmlFor="reg-password">Password (min 8 characters)</label>
              <input
                id="reg-password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                maxLength={128}
              />
              <label htmlFor="reg-confirm">Confirm password</label>
              <input
                id="reg-confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                minLength={8}
              />
              {error && <div className="form-error">{error}</div>}
              <button className="primary-button auth-submit" type="submit" disabled={busy}>
                {busy ? 'Registering…' : 'Register'}
              </button>
            </form>
            <p className="auth-foot muted">
              Your role, clinic{state.preview.role === 'patient' ? ' and patient record' : ''} are fixed by this invite.
            </p>
          </>
        )}

        {done && (
          <div className="invite-terminal">
            <h2>Account created</h2>
            <p>
              Registered <strong>{done.email}</strong> as {ROLE_LABELS[done.role] ?? done.role}.
              Sign in to continue.
            </p>
            <button className="primary-button" onClick={() => toLogin(done.email)}>Sign in</button>
          </div>
        )}
      </div>
    </div>
  );
}
