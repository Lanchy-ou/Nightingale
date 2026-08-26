import { FormEvent, useEffect, useState } from 'react';
import { api } from '../api';
import type { InviteCreated, InviteInfo, Patient } from '../types';

const ROLES = ['clinician', 'staff', 'patient', 'admin'] as const;
const ROLE_LABELS: Record<string, string> = {
  patient: 'Patient',
  staff: 'Staff',
  clinician: 'Clinician',
  admin: 'Admin',
};

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export default function AdminInvitesPage({
  clinicName,
  onLogout,
  onBack,
}: {
  clinicName: string | null;
  onLogout: () => void;
  onBack: () => void;
}) {
  const [invites, setInvites] = useState<InviteInfo[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<string>('clinician');
  const [patientId, setPatientId] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [copied, setCopied] = useState(false);

  async function load() {
    try {
      const [inviteList, patientList] = await Promise.all([
        api.listInvites(),
        api.getClinicPatients(),
      ]);
      setInvites(inviteList);
      setPatients(patientList);
    } catch (e: any) {
      setError(String(e?.body?.error?.message ?? e?.message ?? e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !email.trim()) return;
    if (role === 'patient' && !patientId) {
      setError('A patient invite must be linked to an existing patient record.');
      return;
    }
    setBusy(true);
    setError(null);
    setCreated(null);
    setCopied(false);
    try {
      const result = await api.createInvite({
        email: email.trim(),
        role,
        patient_id: role === 'patient' ? patientId : null,
      });
      setCreated(result);
      setEmail('');
      setRole('clinician');
      setPatientId('');
      await load();
    } catch (e: any) {
      setError(e?.body?.error?.message ?? 'Failed to create invite.');
    } finally {
      setBusy(false);
    }
  }

  function copyLink() {
    if (!created) return;
    const url = `${window.location.origin}${created.invite_link}`;
    navigator.clipboard?.writeText(url).then(
      () => setCopied(true),
      () => setError('Clipboard unavailable — copy the link manually.'),
    );
  }

  return (
    <div className="admin-invites">
      <header className="admin-invites-head">
        <div>
          <p className="eyebrow">{clinicName ?? 'Clinic'}</p>
          <h1>Invite management</h1>
          <p className="muted">
            The demo sends no real email — copy the one-time link and share it with the person.
          </p>
        </div>
        <div className="admin-invites-actions">
          <button className="secondary-button" onClick={onBack}>Back to patient record</button>
          <button className="secondary-button" onClick={onLogout}>Logout</button>
        </div>
      </header>

      <section className="auth-card admin-invite-card">
        <h2>New invite</h2>
        <form onSubmit={submit} className="auth-form">
          <label htmlFor="inv-email">Email</label>
          <input
            id="inv-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="newcolleague@clinic.example"
            required
          />
          <label htmlFor="inv-role">Role</label>
          <select id="inv-role" value={role} onChange={(e) => { setRole(e.target.value); setPatientId(''); }}>
            {ROLES.map((r) => (
              <option key={r} value={r}>{ROLE_LABELS[r]}</option>
            ))}
          </select>
          {role === 'patient' && (
            <>
              <label htmlFor="inv-patient">Link to existing patient record (required)</label>
              <select id="inv-patient" value={patientId} onChange={(e) => setPatientId(e.target.value)} required>
                <option value="">Select patient…</option>
                {patients.map((p) => (
                  <option key={p.patient_id} value={p.patient_id}>
                    {p.name} · {p.patient_id}
                  </option>
                ))}
              </select>
              <p className="muted auth-foot">
                Patient registration links a new login to this existing record — it never creates a second patient record.
              </p>
            </>
          )}
          {error && <div className="form-error">{error}</div>}
          <button className="primary-button auth-submit" type="submit" disabled={busy}>
            {busy ? 'Creating…' : 'Create invite'}
          </button>
        </form>
        {created && (
          <div className="invite-created">
            <strong>Invite created — copy the link now (shown once):</strong>
            <code>{window.location.origin}{created.invite_link}</code>
            <button className="secondary-button" onClick={copyLink}>
              {copied ? 'Copied ✓' : 'Copy link'}
            </button>
            <p className="muted">
              {created.email} · {ROLE_LABELS[created.role] ?? created.role}
              {created.patient_id ? ` · ${created.patient_id}` : ''} · expires {fmtDate(created.expires_at)}
            </p>
          </div>
        )}
      </section>

      <section className="auth-card admin-invite-card">
        <h2>Invites ({invites.length})</h2>
        {invites.length === 0 ? (
          <p className="muted">No invites yet.</p>
        ) : (
          <table className="invite-table">
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Patient</th>
                <th>Status</th>
                <th>Created</th>
                <th>Expires</th>
                <th>Used</th>
              </tr>
            </thead>
            <tbody>
              {invites.map((invite) => (
                <tr key={invite.invite_id}>
                  <td>{invite.email}</td>
                  <td>{ROLE_LABELS[invite.role] ?? invite.role}</td>
                  <td>{invite.patient_id ?? '—'}</td>
                  <td>
                    <span className={`invite-status invite-status-${invite.status}`}>{invite.status}</span>
                  </td>
                  <td>{fmtDate(invite.created_at)}</td>
                  <td>{fmtDate(invite.expires_at)}</td>
                  <td>{invite.used_at ? fmtDate(invite.used_at) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
