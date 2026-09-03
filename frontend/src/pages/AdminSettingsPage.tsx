import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../api';
import type { ClinicSettings } from '../types';

function message(error: unknown): string {
  if (error instanceof ApiError) return error.body?.error?.message ?? error.message;
  return String((error as any)?.message ?? error);
}

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<ClinicSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    const next = await api.getClinicSettings(signal);
    setSettings(next);
    setError(null);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).catch((caught) => caught?.name !== 'AbortError' && setError(message(caught)));
    return () => controller.abort();
  }, [load]);

  async function update(updates: { ai_mode?: 'inherit' | 'local' | 'deepseek'; voice_mode?: 'inherit' | 'enabled' | 'disabled' }) {
    if (!settings || busy) return;
    setBusy(true);
    setError(null);
    try {
      setSettings(await api.updateClinicSettings(settings.version, updates));
    } catch (caught) {
      setError(message(caught));
      await load().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  if (!settings) return <section className="admin-surface"><div className="loading-card">Loading clinic settings…</div>{error && <div className="form-error">{error}</div>}</section>;
  const voiceReady = settings.voice.model_status === 'ready';

  return <div className="admin-settings-page">
    {error && <div className="form-error" role="alert">{error}</div>}
    <section className="admin-surface admin-setting-card">
      <div className="admin-section-head"><div><p className="eyebrow">Clinic setting</p><h2>AI mode</h2></div><span className={`admin-status ${settings.ai.effective_mode === 'deepseek' ? 'active' : ''}`}>{settings.ai.effective_mode === 'deepseek' ? 'Online AI' : 'Local Private'}</span></div>
      <p className="settings-copy">Choose this clinic's policy. The deployment owner manages the shared Provider credential; only redacted text may cross that boundary.</p>
      <fieldset className="settings-mode-controls" disabled={busy}>
        <legend>Clinic AI policy</legend>
        {(['inherit', 'local', 'deepseek'] as const).map((mode) => <label key={mode} className={settings.ai.selected_mode === mode ? 'selected' : ''}>
          <input type="radio" name="clinic-ai-mode" checked={settings.ai.selected_mode === mode} disabled={mode === 'deepseek' && !settings.ai.provider_available} onChange={() => void update({ ai_mode: mode })} />
          <span><strong>{mode === 'inherit' ? 'Use device default' : mode === 'local' ? 'Local Private' : 'Online AI'}</strong><small>{mode === 'deepseek' && !settings.ai.provider_available ? 'Device Provider is not configured' : mode === 'inherit' ? `Currently ${settings.ai.effective_mode}` : 'Applies to this clinic only'}</small></span>
        </label>)}
      </fieldset>
    </section>
    <section className="admin-surface admin-setting-card">
      <div className="admin-section-head"><div><p className="eyebrow">Clinic setting</p><h2>Voice Capture</h2></div><span className={`admin-status ${settings.voice.effective_enabled ? 'active' : ''}`}>{settings.voice.effective_enabled ? 'Enabled' : 'Disabled'}</span></div>
      <p className="settings-copy">The deployment owner prepares the shared local model. This clinic can inherit the device default or set its own enable/disable choice.</p>
      <fieldset className="settings-mode-controls" disabled={busy}>
        <legend>Clinic Voice policy</legend>
        {(['inherit', 'enabled', 'disabled'] as const).map((mode) => <label key={mode} className={settings.voice.selected_mode === mode ? 'selected' : ''}>
          <input type="radio" name="clinic-voice-mode" checked={settings.voice.selected_mode === mode} disabled={mode === 'enabled' && !voiceReady} onChange={() => void update({ voice_mode: mode })} />
          <span><strong>{mode === 'inherit' ? 'Use device default' : mode === 'enabled' ? 'Enable for this clinic' : 'Disable for this clinic'}</strong><small>{mode === 'enabled' && !voiceReady ? 'Deployment owner must prepare the model' : mode === 'inherit' ? `Currently ${settings.voice.effective_enabled ? 'enabled' : 'disabled'}` : 'Applies to this clinic only'}</small></span>
        </label>)}
      </fieldset>
      <div className="settings-status-grid"><div><span>Provider</span><strong>{settings.voice.provider}</strong></div><div><span>Model</span><strong>{settings.voice.model}</strong><small>{settings.voice.model_status}</small></div><div><span>Storage</span><strong>{settings.voice.storage_mode}</strong></div></div>
      {settings.voice.warning && <div className="settings-warning">{settings.voice.warning}</div>}
    </section>
  </div>;
}
