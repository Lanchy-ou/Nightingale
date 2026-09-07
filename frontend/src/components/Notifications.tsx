import AppIcon from './AppIcon';
import { useEffect, useState } from 'react';
import { resultRequest } from '../api';
import type { NotificationList } from '../resultTypes';

export default function Notifications() {
  const [data, setData] = useState<NotificationList | null>(null);
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  async function refresh() {
    try { setData(await resultRequest<NotificationList>(`/notifications?offset=${offset}`)); setError(''); }
    catch { setError('Notifications could not be refreshed.'); }
  }
  useEffect(() => {
    let active = true;
    const load = () => { if (active && !document.hidden) void refresh(); };
    load(); const timer = window.setInterval(load, 30000);
    window.addEventListener('focus', load); document.addEventListener('visibilitychange', load);
    return () => { active = false; clearInterval(timer); window.removeEventListener('focus', load); document.removeEventListener('visibilitychange', load); };
  }, [offset]);
  if (!data?.enabled && !data?.items.length) return null;
  return <div className="notification-entry"><button className="secondary-button" onClick={() => setOpen(!open)} aria-expanded={open}><AppIcon name="bell" />Notifications {data ? `(${data.unread_count})` : ''}</button>
    {open && <section className="notification-popover" aria-label="Your notifications"><h2>Notifications</h2><p>Reading a notification does not complete its task.</p>{error && <p role="alert">{error}</p>}
      {data?.items.length === 0 && <p>No notifications yet.</p>}
      {data?.items.map(item => <article key={item.notification_id}><strong>{item.title}</strong><small>{item.resolved ? 'Resolved or replaced' : item.stage}</small>
        {!item.read_at && <button onClick={() => void resultRequest(`/notifications/${item.notification_id}/read`, {}).then(refresh).catch(() => setError('Could not mark as read.'))}>Mark read</button>}
        {item.target && <a href={item.target}>Open →</a>}</article>)}
      <nav aria-label="Notification pages"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>Previous</button><button disabled={(data?.items.length || 0) < 30} onClick={() => setOffset(offset + 30)}>Next</button></nav>
    </section>}
  </div>;
}
