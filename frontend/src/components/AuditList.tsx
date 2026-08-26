import { useEffect, useState } from 'react';
import { api } from '../api';
import type { AuditLog } from '../types';

export default function AuditList({
  eventId,
  defaultOpen = false,
}: {
  eventId: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setLogs(await api.getAudit(eventId));
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  useEffect(() => {
    if (open) load();
  }, [open, eventId]);

  if (!open) {
    return (
      <button className="link-btn" onClick={() => setOpen(true)}>
        Audit trail
      </button>
    );
  }
  return (
    <div className="audit-list">
      <button className="link-btn" onClick={() => setOpen(false)}>
        Close audit
      </button>
      {error && <div className="error-inline">{error}</div>}
      {logs.length === 0 && <div className="muted">No activity yet.</div>}
      {logs.map((l) => (
        <div key={l.audit_id} className="audit-row">
          <span className="audit-action">{l.action}</span>
          <span className="audit-meta">
            {l.actor_role} · {new Date(l.created_at).toLocaleString()}
            {l.to_version ? ` · v${l.to_version}` : ''}
          </span>
        </div>
      ))}
    </div>
  );
}
