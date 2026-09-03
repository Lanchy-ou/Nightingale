import { useMemo, useState } from 'react';
import type { CurrentIdentity, Patient } from '../types';

export default function ClinicianSidebar({
  identity,
  patients,
  selectedPatientId,
  collapsed,
  mobileOpen,
  onToggleCollapsed,
  onCloseMobile,
  onDashboard,
  onSelectPatient,
  onLogout,
}: {
  identity: CurrentIdentity;
  patients: Patient[];
  selectedPatientId: string | null;
  collapsed: boolean;
  mobileOpen: boolean;
  onToggleCollapsed: () => void;
  onCloseMobile: () => void;
  onDashboard: () => void;
  onSelectPatient: (patientId: string) => void;
  onLogout?: () => void;
}) {
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => {
    const token = query.trim().toLowerCase();
    if (!token) return patients;
    return patients.filter((patient) =>
      `${patient.name} ${patient.patient_id}`.toLowerCase().includes(token),
    );
  }, [patients, query]);
  return (
    <aside
      id="clinical-patient-navigation"
      className={`clinician-sidebar${collapsed ? ' is-collapsed' : ''}${mobileOpen ? ' is-mobile-open' : ''}`}
      aria-label={identity.role === 'staff' ? 'Nurse workspace navigation' : 'Clinician navigation'}
    >
      <div className="sidebar-brand-row">
        <div className="sidebar-brand" aria-label={identity.role === 'staff' ? 'Nightingale nurse workspace' : 'Nightingale clinician workspace'} title={collapsed ? 'Nightingale' : undefined}>
          <span className="sidebar-brand-mark" aria-hidden="true">N</span>
          <span className="sidebar-label">
            <strong>Nightingale</strong>
            <small>{identity.role === 'staff' ? 'Clinical support workspace' : 'Clinical workspace'}</small>
          </span>
        </div>
        <button
          className="sidebar-toggle sidebar-toggle-desktop"
          type="button"
          aria-controls="clinical-patient-navigation"
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expand patient navigation' : 'Collapse patient navigation'}
          title={collapsed ? 'Expand patient navigation' : 'Collapse patient navigation'}
          onClick={onToggleCollapsed}
        >
          <span aria-hidden="true">{collapsed ? '›' : '‹'}</span>
        </button>
        <button
          className="sidebar-toggle sidebar-close-mobile"
          type="button"
          aria-controls="clinical-patient-navigation"
          aria-expanded={mobileOpen}
          aria-label="Close patient navigation"
          onClick={onCloseMobile}
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <div className="identity-card">
        <span className="identity-avatar" aria-hidden="true" title={collapsed ? identity.display_name ?? 'Clinician' : undefined}>{(identity.display_name ?? 'Clinician').slice(0, 1).toUpperCase()}</span>
        <div className="identity-copy sidebar-label">
          <small>Signed in as</small>
          <strong>{identity.display_name ?? 'Clinician'}</strong>
          <span>{identity.professional_title ?? (identity.role === 'staff' ? 'Clinical support' : identity.role)}</span>
        </div>
      </div>

      <button
        className={`sidebar-dashboard ${selectedPatientId === null ? 'active' : ''}`}
        aria-current={selectedPatientId === null ? 'page' : undefined}
        aria-label="Clinic dashboard"
        title={collapsed ? 'Clinic dashboard' : undefined}
        onClick={onDashboard}
      >
        <span className="sidebar-nav-icon" aria-hidden="true">⌂</span><span className="sidebar-label">Clinic dashboard</span>
      </button>

      <div className="sidebar-section-head sidebar-label">
        <h2>Clinic Patients</h2>
        <span>{patients.length}</span>
      </div>
      <label className="patient-search sidebar-label">
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
            aria-current={patient.patient_id === selectedPatientId ? 'page' : undefined}
            aria-label={`Open ${patient.name} record`}
            title={collapsed ? patient.name : undefined}
            onClick={() => onSelectPatient(patient.patient_id)}
          >
            <span className="patient-list-avatar">{patient.name.slice(0, 1).toUpperCase()}</span>
            <span className="sidebar-label">
              <strong>{patient.name}</strong>
              <small>{patient.patient_id} · Clinic patient</small>
            </span>
          </button>
        ))}
      </nav>
      <p className="scope-note sidebar-label">{identity.clinic_name}<br />Clinic-scoped access · server enforced</p>
      {onLogout && (
        <button className="sidebar-logout" aria-label="Logout" title={collapsed ? 'Logout' : undefined} onClick={onLogout}>
          <span className="sidebar-nav-icon" aria-hidden="true">↪</span><span className="sidebar-label">Logout</span>
        </button>
      )}
    </aside>
  );
}
