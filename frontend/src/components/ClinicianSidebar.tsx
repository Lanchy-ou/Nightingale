import { useMemo, useState } from 'react';
import type { CurrentIdentity, Patient } from '../types';

export default function ClinicianSidebar({
  identity,
  patients,
  selectedPatientId,
  onDashboard,
  onSelectPatient,
}: {
  identity: CurrentIdentity;
  patients: Patient[];
  selectedPatientId: string | null;
  onDashboard: () => void;
  onSelectPatient: (patientId: string) => void;
}) {
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => {
    const token = query.trim().toLowerCase();
    if (!token) return patients;
    return patients.filter((patient) =>
      `${patient.name} ${patient.patient_id}`.toLowerCase().includes(token),
    );
  }, [patients, query]);
  const initials = (identity.display_name ?? 'Clinician')
    .split(/\s+/)
    .map((word) => word[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <aside className="clinician-sidebar" aria-label="Clinician navigation">
      <div className="sidebar-brand" aria-label="Nightingale clinician workspace">
        <span className="sidebar-brand-mark" aria-hidden="true">N</span>
        <span>
          <strong>Nightingale</strong>
          <small>Clinical workspace</small>
        </span>
      </div>
      <div className="identity-card">
        <div className="avatar avatar-small">{initials}</div>
        <div className="identity-copy">
          <small>Signed in as</small>
          <strong>{identity.display_name ?? 'Clinician'}</strong>
          <span>{identity.role} · {identity.clinic_name}</span>
        </div>
      </div>

      <button
        className={`sidebar-dashboard ${selectedPatientId === null ? 'active' : ''}`}
        onClick={onDashboard}
      >
        <span aria-hidden="true">⌂</span> Clinic dashboard
      </button>

      <div className="sidebar-section-head">
        <h2>Clinic Patients</h2>
        <span>{patients.length}</span>
      </div>
      <label className="patient-search">
        <span className="sr-only">Search clinic patients</span>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search patients"
        />
      </label>
      <nav className="clinic-patient-list" aria-label="Clinic Patients">
        {filtered.length === 0 && <p className="empty-compact">No matching patients.</p>}
        {filtered.map((patient) => (
          <button
            key={patient.patient_id}
            className={patient.patient_id === selectedPatientId ? 'active' : ''}
            onClick={() => onSelectPatient(patient.patient_id)}
          >
            <span className="patient-list-avatar">{patient.name.slice(0, 1).toUpperCase()}</span>
            <span>
              <strong>{patient.name}</strong>
              <small>{patient.patient_id} · Clinic patient</small>
            </span>
          </button>
        ))}
      </nav>
      <p className="scope-note">Clinic-scoped access · server enforced</p>
    </aside>
  );
}
