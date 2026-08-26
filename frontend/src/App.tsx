import { useState } from 'react';
import PatientPage from './pages/PatientPage';
import PatientViewPage from './pages/PatientViewPage';
import { ROLE_USERS, setRole } from './api';

const PATIENT_ID = 'pat_001';

export default function App() {
  const [roleIndex, setRoleIndex] = useState(0);
  const selected = ROLE_USERS[roleIndex];
  const roleKey = `${selected.role}:${selected.userId}`;

  function changeRole(i: number) {
    // setRole is synchronous so PatientPage sees the new role on the same render.
    setRole(ROLE_USERS[i].userId, ROLE_USERS[i].role);
    setRoleIndex(i);
  }

  return (
    <div className="app">
      {/* NOTE: role switcher is demo-only; not a security boundary — RBAC is enforced server-side */}
      <div className="role-bar">
        <label htmlFor="role-select">Viewing as:</label>
        <select
          id="role-select"
          value={roleIndex}
          onChange={(e) => changeRole(Number(e.target.value))}
        >
          {ROLE_USERS.map((u, i) => (
            <option key={u.role} value={i}>
              {u.label}
            </option>
          ))}
        </select>
        <span className="role-note">demo-only · server enforces real RBAC</span>
      </div>
      {/* Role-level binary render: the patient gets the dedicated Patient View
          page, never a trimmed clinical workspace. Remount on every role
          change so no role-sensitive state can survive. */}
      {selected.role === 'patient' ? (
        <PatientViewPage key={roleKey} patientId={PATIENT_ID} roleKey={roleKey} />
      ) : (
        <PatientPage key={roleKey} patientId={PATIENT_ID} roleKey={roleKey} />
      )}
    </div>
  );
}
