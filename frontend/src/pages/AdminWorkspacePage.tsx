import AppIcon from '../components/AppIcon';
import AdminNotificationsPage from './AdminNotificationsPage';
import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../api';
import type { AdminAccessAudit, AdminUser, CurrentIdentity } from '../types';
import AdminInvitesPage from './AdminInvitesPage';
import AdminSettingsPage from './AdminSettingsPage';
import AdminLearningPage from './AdminLearningPage';
import AdminPatientImportsPage from './AdminPatientImportsPage';

type AdminTab = 'overview' | 'invites' | 'imports' | 'audit' | 'settings' | 'learning' | 'notifications';

function formatDate(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function roleLabel(role: AdminUser['role']): string {
  return role === 'staff' ? 'Staff' : role[0].toUpperCase() + role.slice(1);
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return error.body?.error?.message ?? 'The account or session state changed. Refresh and try again.';
    if (error.status === 403) return 'This Admin session is not allowed to perform that action.';
    return error.body?.error?.message ?? error.message;
  }
  return String((error as any)?.message ?? error);
}

export default function AdminWorkspacePage({
  identity,
  initialTab = 'overview',
  onNavigate,
  onLogout,
}: {
  identity: CurrentIdentity;
  initialTab?: AdminTab;
  onNavigate?: (tab: AdminTab) => void;
  onLogout: () => void;
}) {
  const [tab, setTab] = useState<AdminTab>(initialTab);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [audit, setAudit] = useState<AdminAccessAudit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accountSearch, setAccountSearch] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const [accountRole, setAccountRole] = useState('all');
  const [auditAction, setAuditAction] = useState('all');
  const [pendingUserId, setPendingUserId] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    const [nextUsers, nextAudit] = await Promise.all([
      api.getAdminUsers(signal),
      api.getAdminAccessAudit(signal),
    ]);
    if (signal?.aborted) return;
    setUsers(nextUsers);
    setAudit(nextAudit);
    setError(null);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    load(controller.signal)
      .catch((caught) => caught?.name !== 'AbortError' && setError(errorMessage(caught)))
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [identity.user_id, load]);

  useEffect(() => setTab(initialTab), [initialTab]);

  function selectTab(next: AdminTab) {
    setTab(next);
    setMenuOpen(false);
    setError(null);
    onNavigate?.(next);
  }

  async function changeStatus(user: AdminUser) {
    const next = user.account_status === 'active' ? 'disabled' : 'active';
    const verb = next === 'disabled' ? 'disable this account and revoke its active sessions' : 'reactivate this account';
    if (!window.confirm(`Confirm that you want to ${verb}: ${user.display_name}?`)) return;
    setPendingUserId(user.user_id);
    setError(null);
    try {
      await api.updateAdminUserStatus(user.user_id, user.account_status, next);
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
      await load().catch(() => undefined);
    } finally {
      setPendingUserId(null);
    }
  }

  async function revokeSessions(user: AdminUser) {
    if (!window.confirm(`Revoke ${user.active_session_count} active session${user.active_session_count === 1 ? '' : 's'} for ${user.display_name}?`)) return;
    setPendingUserId(user.user_id);
    setError(null);
    try {
      await api.revokeAdminUserSessions(user.user_id, user.active_session_count);
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
      await load().catch(() => undefined);
    } finally {
      setPendingUserId(null);
    }
  }

  const visibleUsers = users.filter((user) => (accountRole === 'all' || user.role === accountRole)
    && `${user.display_name} ${user.email ?? ''}`.toLowerCase().includes(accountSearch.trim().toLowerCase()));
  const visibleAudit = audit.filter((row) => auditAction === 'all' || row.action === auditAction);
  const subtitles: Record<AdminTab, string> = {
    overview: 'Manage the people and sessions in your clinic.',
    invites: 'Invite team members and patients with the right access.',
    imports: 'Preview patient records before adding them to your clinic.',
    audit: 'Review sign-ins, sign-outs and account security changes.',
    settings: 'Choose how your clinic uses AI and local voice capture.',
    notifications: 'Manage reminder policy and delivery recovery.',
    learning: 'Inspect offline ranking evidence and review its limits.',
  };
  const activeUsers = users.filter((user) => user.account_status === 'active').length;
  const activeSessions = users.reduce((total, user) => total + user.active_session_count, 0);

  return (
    <div className="admin-shell">
      <aside className={`admin-sidebar${menuOpen ? ' mobile-open' : ''}`} aria-label="Admin oversight navigation">
        <div className="sidebar-brand" aria-label="Nightingale admin workspace">
          <span className="sidebar-brand-mark" aria-hidden="true"><AppIcon name="feather" /></span>
          <span><strong>Nightingale</strong><small>Clinic oversight workspace</small></span>
        </div>
        <div className="identity-card">
          <div className="identity-copy">
            <small>Signed in as</small>
            <strong>{identity.display_name ?? 'Admin'}</strong>
            <span>Clinic Administrator</span>
          </div>
        </div>
        <button className="admin-menu-toggle" aria-expanded={menuOpen} aria-controls="admin-navigation" onClick={() => setMenuOpen((value) => !value)}>Administration menu <span aria-hidden="true">{menuOpen ? '−' : '+'}</span></button>
        <nav id="admin-navigation" className="admin-nav" aria-label="Clinic administration">
          <span className="admin-nav-section">Clinic access</span>
          <button className={tab === 'overview' ? 'active' : ''} onClick={() => selectTab('overview')}><AppIcon name="users" />Overview</button>
          <button className={tab === 'invites' ? 'active' : ''} onClick={() => selectTab('invites')}><AppIcon name="plus" />Invites</button>
          <button className={tab === 'imports' ? 'active' : ''} onClick={() => selectTab('imports')}><AppIcon name="upload" />Patient import</button>
          <button className={tab === 'audit' ? 'active' : ''} onClick={() => selectTab('audit')}><AppIcon name="shield" />Access &amp; security audit</button>
          <button className={tab === 'notifications' ? 'active' : ''} onClick={() => selectTab('notifications')}><AppIcon name="bell" />Reminders & delivery</button>
          <span className="admin-nav-section">Services &amp; research</span>
          <button className={tab === 'settings' ? 'active' : ''} onClick={() => selectTab('settings')}><AppIcon name="settings" />AI &amp; Voice settings</button>
          <button className={tab === 'learning' ? 'active' : ''} onClick={() => selectTab('learning')}><AppIcon name="flask" />Shadow Learning</button>
        </nav>
        <p className="scope-note">{identity.clinic_name}<br />Clinic-scoped oversight · server enforced</p>
        <button className="sidebar-logout" onClick={onLogout}><AppIcon name="logout" />Logout</button>
      </aside>

      <main className="admin-main">
        <header className="admin-workspace-head">
          <div>
            <p className="eyebrow">{identity.clinic_name} · Administration</p>
            <h1>{tab === 'notifications' ? 'Reminders & Delivery' : tab === 'overview' ? 'Admin Overview' : tab === 'invites' ? 'Clinic Invites' : tab === 'imports' ? 'Patient Import' : tab === 'audit' ? 'Access & Security Audit' : tab === 'learning' ? 'Shadow Learning' : 'AI & Voice Settings'}</h1>
            <p>{subtitles[tab]}</p>
          </div>
          <div className="admin-header-actions"><span className="admin-role-badge">Admin</span>{tab === 'overview' && <button className="primary-button" onClick={() => selectTab('invites')}>Invite member</button>}</div>
        </header>
        <details className="admin-boundary-note"><summary>Administrative oversight only</summary><p>Account and security controls do not grant access to clinical authoring actions.</p></details>

        {loading && <div className="loading-card">Loading clinic oversight…</div>}
        {error && <div className="form-error" role="alert">{error}</div>}

        {!loading && tab === 'overview' && (
          <>
            <section className="admin-metric-grid" aria-label="Clinic access summary">
              <article><span>Clinic users</span><strong>{users.length}</strong><small>{activeUsers} active</small></article>
              <article><span>Active sessions</span><strong>{activeSessions}</strong><small>Across this clinic only</small></article>
              <article><span>Access events</span><strong>{audit.length}</strong><small>Security metadata only</small></article>
            </section>
            <section className="admin-surface">
              <div className="admin-section-head"><div><p className="eyebrow">Users and sessions</p><h2>Clinic accounts</h2></div><button className="secondary-button" onClick={() => load().catch((caught) => setError(errorMessage(caught)))}>Refresh</button></div>
              <div className="admin-list-toolbar"><label><span className="sr-only">Search accounts</span><input type="search" placeholder="Search by name or email" value={accountSearch} onChange={(event) => setAccountSearch(event.target.value)} /></label><label><span className="sr-only">Filter account role</span><select value={accountRole} onChange={(event) => setAccountRole(event.target.value)}><option value="all">All roles</option>{['clinician', 'staff', 'patient', 'admin'].map((role) => <option key={role} value={role}>{role === 'staff' ? 'Nursing / staff' : role[0].toUpperCase() + role.slice(1)}</option>)}</select></label><span>{visibleUsers.length} account{visibleUsers.length === 1 ? '' : 's'}</span></div>
              {visibleUsers.length === 0 ? <div className="empty-state">No accounts match this view.</div> : (
                <div className="admin-table-wrap">
                  <table className="admin-table">
                    <thead><tr><th>User</th><th>Role</th><th>Account</th><th>Sessions</th><th>Last seen</th><th>Actions</th></tr></thead>
                    <tbody>{visibleUsers.map((user) => (
                      <tr key={user.user_id}>
                        <td><strong>{user.display_name}</strong><small>{user.email ?? 'No login credential'}</small></td>
                        <td><span>{user.professional_title ?? roleLabel(user.role)}</span>{user.professional_title && <small>RBAC role · {user.role}</small>}</td>
                        <td><span className={`admin-status ${user.account_status}`}>{user.account_status}</span>{user.disabled_at && <small>Since {formatDate(user.disabled_at)}</small>}</td>
                        <td><strong>{user.active_session_count}</strong></td>
                        <td>{formatDate(user.last_seen_at)}</td>
                        <td><div className="admin-row-actions">
                          <button
                            className="secondary-button"
                            onClick={() => changeStatus(user)}
                            disabled={pendingUserId !== null || user.user_id === identity.user_id}
                            title={user.user_id === identity.user_id ? 'The current Admin cannot disable their own account.' : undefined}
                          >{user.account_status === 'active' ? 'Disable' : 'Reactivate'}</button>
                          <button className="secondary-button" onClick={() => revokeSessions(user)} disabled={pendingUserId !== null || user.active_session_count === 0}>Revoke sessions</button>
                        </div></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}

        {!loading && tab === 'invites' && (
          <AdminInvitesPage clinicName={identity.clinic_name} onLogout={onLogout} embedded />
        )}
        {!loading && tab === 'imports' && <AdminPatientImportsPage />}

        {!loading && tab === 'audit' && (
          <section className="admin-surface">
            <div className="admin-section-head"><div><p className="eyebrow">Metadata only</p><h2>Recent access events</h2></div><button className="secondary-button" onClick={() => load().catch((caught) => setError(errorMessage(caught)))}>Refresh</button></div>
            <div className="admin-list-toolbar"><label>Event type <select value={auditAction} onChange={(event) => setAuditAction(event.target.value)}><option value="all">All access events</option>{[...new Set(audit.map((row) => row.action))].map((action) => <option key={action} value={action}>{action.replace(/_/g, ' ')}</option>)}</select></label><span>{visibleAudit.length} event{visibleAudit.length === 1 ? '' : 's'}</span></div>
            <p className="panel-help">Clinical note edits and revisions are available in each patient event’s History.</p>
            {visibleAudit.length === 0 ? <div className="empty-state">No access events match this view.</div> : (
              <div className="admin-audit-list">{visibleAudit.map((row) => (
                <article key={row.audit_id}>
                  <span className="audit-dot" aria-hidden="true" />
                  <div><strong>{row.action.replace(/_/g, ' ')}</strong><span>{users.find((user) => user.user_id === row.actor_id)?.display_name ?? row.actor_role ?? 'Unknown actor'} · {row.actor_role ?? 'unknown role'}</span><details className="audit-identifiers"><summary>Record identifiers</summary><small>{row.target_type} · {row.target_id} · Actor {row.actor_id ?? 'unknown'}</small></details></div><time>{formatDate(row.created_at)}</time>
                </article>
              ))}</div>
            )}
          </section>
        )}
        {!loading && tab === 'notifications' && <AdminNotificationsPage />}
        {!loading && tab === 'settings' && <AdminSettingsPage />}
        {!loading && tab === 'learning' && <AdminLearningPage />}
      </main>
    </div>
  );
}
