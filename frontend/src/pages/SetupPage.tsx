import AppIcon from '../components/AppIcon';
import { FormEvent, useEffect, useState } from 'react';
import { api } from '../api';
import type { OnboardingComplete, OnboardingPreview } from '../types';

type SetupState =
  | { kind: 'loading' }
  | { kind: 'invalid' }
  | { kind: 'used' }
  | { kind: 'expired' }
  | { kind: 'valid'; preview: OnboardingPreview };

export default function SetupPage() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '';
  const [state, setState] = useState<SetupState>({ kind: 'loading' });
  const [clinicName, setClinicName] = useState('');
  const [adminName, setAdminName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<OnboardingComplete | null>(null);

  useEffect(() => {
    if (!token) {
      setState({ kind: 'invalid' });
      return;
    }
    let cancelled = false;
    api.getOnboardingPreview(token).then((preview) => {
      if (cancelled) return;
      setState(preview.status === 'valid' ? { kind: 'valid', preview } : { kind: preview.status });
    }).catch(() => !cancelled && setState({ kind: 'invalid' }));
    return () => { cancelled = true; };
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
      setDone(await api.completeOnboarding({
        token,
        clinic_name: clinicName.trim(),
        admin_name: adminName.trim(),
        email: email.trim(),
        password,
      }));
      window.history.replaceState({}, '', '/setup');
    } catch (caught: any) {
      setError(caught?.body?.error?.message ?? 'Clinic setup failed. Ask the deployment owner for a new link.');
    } finally {
      setBusy(false);
    }
  }

  function signIn() {
    window.location.href = done ? `/login?email=${encodeURIComponent(done.email)}` : '/login';
  }

  return <div className="auth-page"><div className="auth-card">
    <div className="auth-brand"><span className="auth-brand-mark" aria-hidden="true"><AppIcon name="feather" /></span><div><h1>Nightingale</h1><p className="muted">Set up your clinic</p></div></div>
    <div className="auth-security-note"><strong>Deployment-authorised setup</strong><span>This single-use link creates one clinic and its first administrator.</span></div>
    {state.kind === 'loading' && <p className="muted">Checking setup link…</p>}
    {['invalid', 'used', 'expired'].includes(state.kind) && <div className="invite-terminal"><h2>Setup link {state.kind}</h2><p>This link cannot create a clinic. Ask the deployment owner for a new one.</p><button className="secondary-button" onClick={signIn}>Back to sign in</button></div>}
    {state.kind === 'valid' && !done && <><h2>Create clinic</h2><form className="auth-form" onSubmit={submit}>
      <label htmlFor="setup-clinic">Clinic name</label><input id="setup-clinic" value={clinicName} onChange={(e) => setClinicName(e.target.value)} required maxLength={255} />
      <label htmlFor="setup-admin">Administrator name</label><input id="setup-admin" value={adminName} onChange={(e) => setAdminName(e.target.value)} required maxLength={255} />
      <label htmlFor="setup-email">Administrator email</label><input id="setup-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      <label htmlFor="setup-password">Password (min 8 characters)</label><input id="setup-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} maxLength={128} />
      <label htmlFor="setup-confirm">Confirm password</label><input id="setup-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={8} />
      {error && <div className="form-error">{error}</div>}
      <button className="primary-button auth-submit" type="submit" disabled={busy}>{busy ? 'Creating clinic…' : 'Create clinic and administrator'}</button>
    </form><p className="auth-foot muted">This form cannot choose an existing clinic or create a clinical role.</p></>}
    {done && <div className="invite-terminal"><h2>Clinic created</h2><p>Your administrator account is ready. Sign in with <strong>{done.email}</strong>.</p><button className="primary-button" onClick={signIn}>Sign in</button></div>}
  </div></div>;
}
