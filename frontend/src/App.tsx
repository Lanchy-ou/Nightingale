import { useCallback, useEffect, useState } from 'react';
import { api, DEMO_AUTH, ROLE_USERS, setRole, setSessionIdentity, setUnauthorizedHandler } from './api';
import type { CurrentIdentity } from './types';
import AdminWorkspacePage from './pages/AdminWorkspacePage';
import ClinicianWorkspacePage from './pages/ClinicianWorkspacePage';
import LoginPage from './pages/LoginPage';
import PatientViewPage from './pages/PatientViewPage';
import RegisterPage from './pages/RegisterPage';

const PATIENT_ID = 'pat_001'; // staff/admin pre-C2 minimal demo path

// ---------------------------------------------------------------------------
// Development demo mode. Only active when VITE_DEMO_AUTH=true (the backend
// additionally requires NANTINGALE_DEMO_AUTH=true). The role toolbar is never
// part of the product shell and is never a security boundary.
// ---------------------------------------------------------------------------
function DemoApp() {
  const [roleIndex, setRoleIndex] = useState(0);
  const selected = ROLE_USERS[roleIndex];
  const roleKey = `${selected.role}:${selected.userId}`;

  function changeRole(i: number) {
    setRole(ROLE_USERS[i].userId, ROLE_USERS[i].role);
    setRoleIndex(i);
  }

  return (
    <div className="app">
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
        <span>Legacy header simulation (VITE_DEMO_AUTH only)</span>
      </div>
      <div className="product-root" key={roleKey}>
        {selected.role === 'patient' ? (
          <PatientViewPage patientId={PATIENT_ID} roleKey={roleKey} />
        ) : selected.role === 'clinician' || selected.role === 'staff' ? (
          <ClinicianWorkspacePage roleKey={roleKey} />
        ) : (
          <AdminWorkspacePage
            identity={{ user_id: selected.userId, role: 'admin', clinic_id: 'clinic_001', patient_id: null, display_name: 'Nightingale Admin', professional_title: null, clinic_name: 'Nightingale Demo Clinic', authenticated: true }}
            onLogout={() => undefined}
          />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Product mode. Identity comes exclusively from the server-side HttpOnly
// session cookie: boot restores the session via GET /api/auth/session, any
// 401 clears state and returns to Login, and logout unmounts the whole
// product root so no patient/source/comment/draft state can survive.
// ---------------------------------------------------------------------------
export default function App() {
  if (DEMO_AUTH) return <DemoApp />;
  return <SessionApp />;
}

function SessionApp() {
  const [identity, setIdentity] = useState<CurrentIdentity | null>(null);
  const [booting, setBooting] = useState(true);
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    // 401 anywhere in product mode -> clear sensitive state and return to Login.
    setUnauthorizedHandler(() => {
      setIdentity(null);
      setSessionIdentity(null);
      if (window.location.pathname !== '/login') {
        window.history.pushState({}, '', '/login');
      }
    });

    // Refresh restores identity from the server session, never from localStorage.
    api
      .getSession()
      .then((identity) => {
        setSessionIdentity(identity);
        setIdentity(identity);
      })
      .catch(() => setIdentity(null))
      .finally(() => setBooting(false));

    const onPopState = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPopState);
    return () => {
      window.removeEventListener('popstate', onPopState);
      setUnauthorizedHandler(null);
    };
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* session already gone — still clear client state */
    }
    setIdentity(null);
    setSessionIdentity(null);
    setPath('/login');
    if (window.location.pathname !== '/login') {
      window.history.pushState({}, '', '/login');
    }
  }, []);

  function navigate(next: string) {
    window.history.pushState({}, '', next);
    setPath(next);
  }

  if (booting) {
    return <div className="auth-page"><p className="muted">Restoring session…</p></div>;
  }

  if (!identity) {
    if (path.startsWith('/register')) return <RegisterPage />;
    return <LoginPage onAuthenticated={(next) => { setSessionIdentity(next); setIdentity(next); }} />;
  }

  const role = identity.role ?? '';
  const productKey = `session:${identity.user_id}:${role}`;

  if (role === 'patient') {
    return (
      <div className="app" key={productKey}>
        <div className="product-root">
          <PatientViewPage
            patientId={identity.patient_id ?? ''}
            roleKey={productKey}
            onLogout={logout}
          />
        </div>
      </div>
    );
  }

  if (role === 'clinician') {
    return (
      <div className="app" key={productKey}>
        <div className="product-root">
          <ClinicianWorkspacePage roleKey={productKey} onLogout={logout} />
        </div>
      </div>
    );
  }

  if (role === 'staff') {
    return (
      <div className="app" key={productKey}>
        <div className="product-root">
          <ClinicianWorkspacePage roleKey={productKey} onLogout={logout} />
        </div>
      </div>
    );
  }

  if (role === 'admin') {
    const initialTab = path.startsWith('/admin/invites') ? 'invites' : path.startsWith('/admin/audit') ? 'audit' : 'overview';
    return (
      <div className="app" key={productKey}>
        <div className="product-root">
          <AdminWorkspacePage
            identity={identity}
            initialTab={initialTab}
            onLogout={logout}
            onNavigate={(tab) => navigate(tab === 'overview' ? '/admin' : `/admin/${tab}`)}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page"><div className="form-error">This account role has no workspace.</div></div>
  );
}
