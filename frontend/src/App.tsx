import { useState } from 'react';
import ClinicianWorkspacePage from './pages/ClinicianWorkspacePage';
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
      {/* Demo controls are visually and structurally outside every product shell.
          They are never a security boundary; the backend resolves the DB role. */}
      <div className="demo-toolbar">
        <strong>DEMO CONTROLS</strong>
        <label htmlFor="role-select">Role</label>
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
        <span>Server-enforced demo identities</span>
      </div>
      {/* Role-level binary render is permanent: patient never mounts or calls
          the clinical shell. Staff/Admin keep the pre-C2 minimal demo path. */}
      <div className="product-root" key={roleKey}>
        {selected.role === 'patient' ? (
          <PatientViewPage patientId={PATIENT_ID} roleKey={roleKey} />
        ) : selected.role === 'clinician' ? (
          <ClinicianWorkspacePage roleKey={roleKey} />
        ) : (
          <PatientPage patientId={PATIENT_ID} roleKey={roleKey} />
        )}
      </div>
    </div>
  );
}
