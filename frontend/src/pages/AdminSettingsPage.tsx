import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../api';
import type { AdminSystemSettings } from '../types';

function message(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return error.body?.error?.message ?? 'Settings changed. Refresh and try again.';
    return error.body?.error?.message ?? error.message;
  }
  return String((error as any)?.message ?? error);
}

function formatDate(value: string | null): string {
  if (!value) return 'Not verified';
  return new Date(value).toLocaleString();
}

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<AdminSystemSettings | null>(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    const next = await api.getAdminSystemSettings(signal);
    setSettings(next);
    setError(null);
    return next;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).catch((caught) => caught?.name !== 'AbortError' && setError(message(caught)));
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    if (settings?.voice.model_status !== 'downloading') return;
    const timer = window.setInterval(() => void load().catch(() => undefined), 2500);
    return () => window.clearInterval(timer);
  }, [settings?.voice.model_status, load]);

  async function update(updates: { ai_mode?: 'local' | 'deepseek'; voice_enabled?: boolean }) {
    if (!settings || busy) return;
    setBusy('settings');
    setError(null);
    try {
      setSettings(await api.updateAdminSystemSettings(settings.version, updates));
    } catch (caught) {
      setError(message(caught));
      await load().catch(() => undefined);
    } finally {
      setBusy(null);
    }
  }

  async function saveKey() {
    if (!settings || busy || !key.trim()) return;
    setBusy('key');
    setError(null);
    try {
      const stored = await api.storeDeepSeekKey(settings.version, key.trim());
      const enabled = stored.ai.mode === 'deepseek'
        ? stored
        : await api.updateAdminSystemSettings(stored.version, { ai_mode: 'deepseek' });
      setSettings(enabled);
      setKey('');
    } catch (caught) {
      setError(message(caught));
      await load().catch(() => undefined);
    } finally {
      setBusy(null);
    }
  }

  async function removeKey() {
    if (!settings || busy || !window.confirm('Remove the stored AI API key and return to Local Private mode?')) return;
    setBusy('key');
    setError(null);
    try {
      setSettings(await api.removeDeepSeekKey(settings.version));
      setKey('');
    } catch (caught) {
      setError(message(caught));
      await load().catch(() => undefined);
    } finally {
      setBusy(null);
    }
  }

  async function prepareModel() {
    if (!settings || busy) return;
    setBusy('model');
    setError(null);
    try {
      await api.prepareVoiceModel();
      await load();
    } catch (caught) {
      setError(message(caught));
    } finally {
      setBusy(null);
    }
  }

  if (!settings) return <section className="admin-surface"><div className="loading-card">Loading device settings…</div>{error && <div className="form-error">{error}</div>}</section>;

  const voiceReady = settings.voice.model_status === 'ready';
  return (
    <div className="admin-settings-page">
      {error && <div className="form-error" role="alert">{error}</div>}
      <section className="admin-surface admin-setting-card">
        <div className="admin-section-head"><div><p className="eyebrow">AI &amp; privacy</p><h2>AI mode</h2></div><span className={`admin-status ${settings.ai.mode === 'deepseek' ? 'active' : ''}`}>{settings.ai.mode === 'deepseek' ? 'AI API' : 'Local Private'}</span></div>
        <p className="settings-copy">Choose whether Nightingale uses private on-device responses or the configured online AI API. Only redacted text may cross the Provider boundary.</p>
        <div className="settings-active-mode" aria-label="Current AI mode">
          <span className="settings-active-mark" aria-hidden="true">✓</span>
          <div><small>Currently active</small><strong>{settings.ai.mode === 'deepseek' ? 'AI API' : 'Local Private'}</strong><span>{settings.ai.mode === 'deepseek' ? 'Uses the verified API key after redaction' : 'On-device deterministic responses · no API key'}</span></div>
        </div>
        {settings.ai.key_configured ? (
          <fieldset className="settings-mode-controls" disabled={busy !== null}>
            <legend>Switch AI mode</legend>
            <label className={settings.ai.mode === 'local' ? 'selected' : ''}><input type="radio" name="ai-mode" checked={settings.ai.mode === 'local'} onChange={() => void update({ ai_mode: 'local' })} /><span><strong>Local Private</strong><small>Keep text on this device</small></span></label>
            <label className={settings.ai.mode === 'deepseek' ? 'selected' : ''}><input type="radio" name="ai-mode" checked={settings.ai.mode === 'deepseek'} onChange={() => void update({ ai_mode: 'deepseek' })} /><span><strong>AI API</strong><small>Use the verified key</small></span></label>
          </fieldset>
        ) : (
          <div className="settings-setup-intro"><strong>Set up AI API</strong><span>Enter and verify a key below. Nightingale will enable AI API automatically after the test succeeds.</span></div>
        )}
        <div className="settings-key-panel">
          <div><strong>AI API key</strong><span>{settings.ai.key_configured ? `Configured · ••••${settings.ai.key_suffix}` : 'Not configured'}</span><small>{settings.ai.key_source ? `${settings.ai.key_source.replace('_', ' ')} · ${formatDate(settings.ai.verified_at)}` : 'Stored only in Windows Credential Manager after verification.'}</small></div>
          <label>New or replacement key<input type="password" value={key} autoComplete="off" onChange={(event) => setKey(event.target.value)} placeholder="Enter your own AI API key" /></label>
          <div className="settings-actions"><button disabled={busy !== null || !key.trim()} onClick={() => void saveKey()}>{busy === 'key' ? 'Verifying…' : 'Test, save and enable'}</button>{settings.ai.key_configured && <button className="secondary-button" disabled={busy !== null} onClick={() => void removeKey()}>Remove key</button>}</div>
        </div>
      </section>

      <section className="admin-surface admin-setting-card">
        <div className="admin-section-head"><div><p className="eyebrow">Local capture</p><h2>Voice Capture</h2></div><label className="settings-switch"><input type="checkbox" checked={settings.voice.enabled} disabled={busy !== null || !voiceReady} onChange={(event) => void update({ voice_enabled: event.target.checked })} /><span>{settings.voice.enabled ? 'On' : 'Off'}</span></label></div>
        <div className="settings-status-grid"><div><span>ASR provider</span><strong>faster-whisper · Local CPU</strong></div><div><span>Model</span><strong>{settings.voice.model}</strong><small>{settings.voice.model_status}</small></div><div><span>Storage</span><strong>{settings.voice.storage_mode}</strong></div></div>
        {settings.voice.warning && <div className="settings-warning">{settings.voice.warning}</div>}
        {settings.voice.model_status !== 'ready' && <div className="settings-model-row"><div><strong>Local model required</strong><span>Fixed revision · approximately 148 MB · no audio leaves this device.</span>{settings.voice.error_code && <small>Last attempt: {settings.voice.error_code.replace(/_/g, ' ')}</small>}</div><button disabled={busy !== null || settings.voice.model_status === 'downloading'} onClick={() => void prepareModel()}>{settings.voice.model_status === 'downloading' ? 'Downloading…' : 'Download local model'}</button></div>}
        {voiceReady && <p className="settings-ready">Model ready. Admin can enable Doctor, Nurse and Patient Check-in recording for this device.</p>}
      </section>
    </div>
  );
}
