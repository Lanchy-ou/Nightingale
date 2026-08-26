import type { Patient } from '../types';

export default function PatientHeader({ patient }: { patient: Patient }) {
  const initials = patient.name
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
  return (
    <div className="patient-header">
      <div className="avatar">{initials}</div>
      <div>
        <h1>{patient.name}</h1>
        <div className="meta">
          {patient.clinic_name} · Current episode · Aug 2026
        </div>
      </div>
    </div>
  );
}
