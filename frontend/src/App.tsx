import { confirmLeaveDrafts } from './useNoteDraft';
import { useCallback, useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { api, DEMO_AUTH, ROLE_USERS, setRole, setSessionIdentity, setUnauthorizedHandler } from './api';
import type { CurrentIdentity } from './types';
import AdminWorkspacePage from './pages/AdminWorkspacePage';
import ClinicianWorkspacePage from './pages/ClinicianWorkspacePage';
import LoginPage from './pages/LoginPage';
import PatientViewPage from './pages/PatientViewPage';
import RegisterPage from './pages/RegisterPage';
import SetupPage from './pages/SetupPage';

const PATIENT_ID = 'pat_001'; // staff/admin pre-C2 minimal demo path

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      retry: 1,
    },
  },
});

function adminTabFromPath(path: string): 'overview' | 'invites' | 'imports' | 'audit' | 'settings' | 'learning' | 'notifications' {
  if (path.startsWith('/admin/notifications')) return 'notifications';
  if (path.startsWith('/admin/invites')) return 'invites';
  if (path.startsWith('/admin/audit')) return 'audit';
  if (path.startsWith('/admin/imports')) return 'imports';
  if (path.startsWith('/admin/settings')) return 'settings';
  if (path.startsWith('/admin/learning')) return 'learning';
  return 'overview';
}

function roleHomePath(role: string | null | undefined): string {
  if (role === 'clinician' || role === 'staff') return '/clinical';
  if (role === 'admin') return '/admin';
  if (role === 'patient') return '/patient/today';
  return '/login';
}

function pathBelongsToRole(path: string, role: string | null | undefined): boolean {
  if (role === 'clinician' || role === 'staff') return path.startsWith('/clinical');
  if (role === 'admin') return path.startsWith('/admin');
  if (role === 'patient') return path.startsWith('/patient');
  return false;
}

// ---------------------------------------------------------------------------
// Development demo mode. Only active when VITE_DEMO_AUTH=true (the backend
// additionally requires NANTINGALE_DEMO_AUTH=true). The role toolbar is never
// part of the product shell and is never a security boundary.
// ---------------------------------------------------------------------------
function DemoApp() {
  const queryCache = useQueryClient();
  const [roleIndex, setRoleIndex] = useState(0);
  const selected = ROLE_USERS[roleIndex];
  const roleKey = `${selected.role}:${selected.userId}`;

  function changeRole(i: number) {
    if (!confirmLeaveDrafts()) return;
    const next = ROLE_USERS[i];
    queryCache.clear();
    setRole(next.userId, next.role);
    const nextPath = next.role === 'clinician' || next.role === 'staff'
      ? '/clinical'
      : next.role === 'admin' ? '/admin' : '/patient';
    window.history.replaceState({}, '', nextPath);
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
            initialTab={adminTabFromPath(window.location.pathname)}
            onNavigate={(tab) => window.history.pushState({}, '', tab === 'overview' ? '/admin' : `/admin/${tab}`)}
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
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}

function AppContent() {
  if (DEMO_AUTH) return <DemoApp />;
  return <SessionApp />;
}

function SessionApp() {
  const queryCache = useQueryClient();
  const [identity, setIdentity] = useState<CurrentIdentity | null>(null);
  const [booting, setBooting] = useState(true);
  const [path, setPath] = useState(() => window.location.pathname);

  function activateIdentity(next: CurrentIdentity, forceHome = false) {
    const nextPath = forceHome || !pathBelongsToRole(window.location.pathname, next.role)
      ? roleHomePath(next.role)
      : window.location.pathname;
    if (window.location.pathname !== nextPath) {
      window.history.replaceState({}, '', nextPath);
    }
    setPath(nextPath);
    setSessionIdentity(next);
    setIdentity(next);
  }

  useEffect(() => {
    // 401 anywhere in product mode -> clear sensitive state and return to Login.
    setUnauthorizedHandler(() => {
      queryCache.clear();
      setIdentity(null);
      setSessionIdentity(null);
      if (window.location.pathname !== '/login') {
        window.history.replaceState({}, '', '/login');
      }
      setPath('/login');
    });

    // Refresh restores identity from the server session, never from localStorage.
    api
      .getSession()
      .then((identity) => activateIdentity(identity))
      .catch(() => {
        setIdentity(null);
        setSessionIdentity(null);
        const currentPath = window.location.pathname;
        const nextPath = currentPath.startsWith('/register') || currentPath.startsWith('/setup') ? currentPath : '/login';
        if (currentPath !== nextPath) {
          window.history.replaceState({}, '', nextPath);
        }
        setPath(nextPath);
      })
      .finally(() => setBooting(false));

    const onPopState = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPopState);
    return () => {
      window.removeEventListener('popstate', onPopState);
      setUnauthorizedHandler(null);
    };
  }, [queryCache]);

  useEffect(() => {
    if (!identity || pathBelongsToRole(path, identity.role)) return;
    const nextPath = roleHomePath(identity.role);
    window.history.replaceState({}, '', nextPath);
    setPath(nextPath);
  }, [identity, path]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* session already gone — still clear client state */
    }
    setIdentity(null);
    setSessionIdentity(null);
    queryCache.clear();
    setPath('/login');
    if (window.location.pathname !== '/login') {
      window.history.replaceState({}, '', '/login');
    }
  }, [queryCache]);

  function navigate(next: string) {
    window.history.pushState({}, '', next);
    setPath(next);
  }

  if (booting) {
    return <div className="auth-page"><p className="muted">Restoring session…</p></div>;
  }

  if (!identity) {
    if (path.startsWith('/register')) return <RegisterPage />;
    if (path.startsWith('/setup')) return <SetupPage />;
    return <LoginPage onAuthenticated={(next) => activateIdentity(next, true)} />;
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
    const initialTab = adminTabFromPath(path);
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
