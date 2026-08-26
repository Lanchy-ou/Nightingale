import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { PatientView } from '../types';

const EVENT_TYPE_LABELS: Record<string, string> = {
  patient_ai_preconsult: 'AI 预问诊',
  patient_followup: '随访对话',
};

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

export default function PatientViewPage({
  patientId,
  roleKey,
  onLogout,
}: {
  patientId: string;
  roleKey: string;
  onLogout?: () => void;
}) {
  const [view, setView] = useState<PatientView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(() => {
    let cancelled = false;
    (async () => {
      try {
        const v = await api.getPatientView(patientId);
        if (!cancelled) {
          setView(v);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  useEffect(() => {
    return load();
  }, [load, roleKey, refreshKey]);

  async function send() {
    if (!message.trim()) return;
    setBusy(true);
    setSubmitError(null);
    try {
      await api.createSession(
        patientId,
        `sess-${Date.now()}`,
        'patient_followup',
        new Date().toISOString(),
        { messages: [{ id: 'm1', speaker: 'patient', text: message.trim() }] },
      );
      setMessage('');
      setRefreshKey((k) => k + 1);
    } catch (e: any) {
      setSubmitError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="error">无法加载你的信息：{error}</div>;
  if (!view) return <div className="muted">加载中…</div>;

  const summary = view.current_summary;

  return (
    <div className="patient-view">
      <header className="pv-header">
        <div className="avatar">{view.display_name.slice(0, 1).toUpperCase()}</div>
        <div>
          <h1>你好，{view.display_name}</h1>
          <div className="meta">你的个人照护说明</div>
        </div>
        {onLogout && (
          <button className="secondary-button pv-logout" onClick={onLogout}>退出登录</button>
        )}
      </header>

      <section className="pv-card pv-primary">
        <h2>你现在需要知道的事</h2>
        {summary ? (
          <>
            <p className="pv-lead">{summary.instruction}</p>
            {summary.follow_up && (
              <p className="pv-followup">📅 {summary.follow_up}</p>
            )}
            <div className="pv-date muted">更新于 {fmtDate(summary.event_time)}</div>
          </>
        ) : (
          <p className="muted">暂时没有新的说明。如有疑问请联系你的诊所。</p>
        )}
      </section>

      <section className="pv-card">
        <h2>你的下一步</h2>
        {view.upcoming.length === 0 ? (
          <p className="muted">暂时没有待办安排。</p>
        ) : (
          <ul className="pv-list">
            {view.upcoming.map((u) => (
              <li key={`${u.source_artifact_id}:${u.event_time}`}>
                <span className="pv-check">✔</span>
                <span>{u.text}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="pv-card">
        <h2>医生给你的说明</h2>
        {view.instructions.length === 0 ? (
          <p className="muted">暂时没有医生说明。</p>
        ) : (
          <ul className="pv-list">
            {view.instructions.map((i) => (
              <li key={i.artifact_id} className="pv-instruction">
                <div className="pv-date muted">{fmtDate(i.event_time)}</div>
                <p>{i.instruction}</p>
                {i.follow_up && <p className="pv-followup">📅 {i.follow_up}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="pv-card">
        <h2>和 AI 助手说说你的情况</h2>
        <p className="muted">用一两句话描述你最近的情况，AI 助手会整理成你的就诊记录。</p>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="例如：这周头痛好多了，但早上还是有点恶心…"
          rows={3}
        />
        <div className="inline-actions">
          <button onClick={send} disabled={busy || !message.trim()}>
            {busy ? '发送中…' : '发送'}
          </button>
          {submitError && <span className="error-inline">{submitError}</span>}
        </div>

        {view.sessions.length > 0 && (
          <div className="pv-sessions">
            <h3 className="pv-subhead">过往对话</h3>
            <ul className="pv-list">
              {view.sessions.map((s) => (
                <li key={s.event_id} className="pv-session">
                  <span className="pv-date muted">{fmtDate(s.started_at)}</span>
                  <span>{EVENT_TYPE_LABELS[s.event_type] ?? s.event_type}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
