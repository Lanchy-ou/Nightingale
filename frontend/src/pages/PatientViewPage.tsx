import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { PatientTask, PatientView, TaskStatus } from '../types';

const EVENT_TYPE_LABELS: Record<string, string> = {
  patient_ai_preconsult: 'AI 预问诊',
  patient_followup: '随访对话',
};

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

export default function PatientViewPage({
  patientId,
  roleKey,
  onLogout,
}: {
  patientId: string;
  roleKey: string;
  onLogout?: () => void;
}) {
  const [view, setView] = useState<PatientView | null>(null);
  const [tab, setTab] = useState<'today' | 'care' | 'checkin' | 'summaries'>('today');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const v = await api.getPatientView(patientId);
        if (!cancelled) {
          setView(v);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  useEffect(() => {
    return load();
  }, [load, roleKey, refreshKey]);

  useEffect(() => {
    // patient/session identity is a hard remount boundary. Clear every draft,
    // error and pending response even if a host reuses this component.
    setMessage('');
    setSubmitError(null);
    setTaskError(null);
    setPendingTaskId(null);
    setTab('today');
  }, [patientId, roleKey]);

  async function send() {
    if (!message.trim()) return;
    setBusy(true);
    setSubmitError(null);
    try {
      await api.createSession(
        patientId,
        `sess-${Date.now()}`,
        'patient_followup',
        new Date().toISOString(),
        { messages: [{ id: 'm1', speaker: 'patient', text: message.trim() }] },
      );
      setMessage('');
      setRefreshKey((k) => k + 1);
    } catch (e: any) {
      setSubmitError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function transition(task: PatientTask, status: TaskStatus) {
    setPendingTaskId(task.task_id);
    setTaskError(null);
    try {
      await api.transitionTask(task.task_id, task.status, status);
      setRefreshKey((key) => key + 1);
    } catch (e: any) {
      setTaskError(e?.status === 409
        ? '这项任务已在别处更新。我们正在刷新最新状态。'
        : String(e.message ?? e));
      if (e?.status === 409) setRefreshKey((key) => key + 1);
    } finally {
      setPendingTaskId(null);
    }
  }

  if (error) return <div className="error">无法加载你的信息：{error}</div>;
  if (!view || loading) return <div className="patient-view"><div className="loading-card">正在加载你的照护计划…</div></div>;

  const taskGroups: { key: keyof PatientView['care_plan']; label: string }[] = [
    { key: 'open', label: '待开始' },
    { key: 'in_progress', label: '进行中' },
    { key: 'reported_done', label: '等待诊所确认' },
    { key: 'completed', label: '已由诊所确认' },
  ];

  return (
    <div className="patient-view">
      <header className="pv-header">
        <div className="avatar">{view.display_name.slice(0, 1).toUpperCase()}</div>
        <div>
          <h1>你好，{view.display_name}</h1>
          <div className="meta">你的个人照护说明</div>
        </div>
        {onLogout && (
          <button className="secondary-button pv-logout" onClick={onLogout}>退出登录</button>
        )}
      </header>

      <nav className="pv-tabs" aria-label="Patient experience sections">
        {([
          ['today', 'Today'],
          ['care', 'Care Plan'],
          ['checkin', 'Check-in'],
          ['summaries', 'Visit Summaries'],
        ] as const).map(([key, label]) => (
          <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </nav>

      {taskError && <div className="form-error">{taskError}</div>}

      {tab === 'today' && (
        <>
          <section className="pv-card pv-primary">
            <h2>今天需要知道的事</h2>
            {view.today.instruction ? (
              <>
                <p className="pv-lead">{view.today.instruction.instruction}</p>
                <div className="pv-date muted">更新于 {fmtDate(view.today.instruction.event_time)}</div>
              </>
            ) : <p className="muted">暂时没有新的医生说明。</p>}
            {view.today.next_follow_up && <p className="pv-followup">后续安排：{view.today.next_follow_up}</p>}
          </section>
          <section className="pv-card">
            <h2>最近需要行动</h2>
            {view.today.tasks.length === 0
              ? <p className="muted">目前没有待处理的照护任务。</p>
              : view.today.tasks.map((task) => (
                <PatientTaskCard key={task.task_id} task={task} pending={pendingTaskId === task.task_id} onTransition={transition} />
              ))}
          </section>
        </>
      )}

      {tab === 'care' && (
        <section className="pv-card">
          <h2>你的照护计划</h2>
          {taskGroups.map(({ key, label }) => (
            <div className="pv-task-group" key={key}>
              <h3>{label}</h3>
              {view.care_plan[key].length === 0
                ? <p className="muted">没有项目</p>
                : view.care_plan[key].map((task) => (
                  <PatientTaskCard key={task.task_id} task={task} pending={pendingTaskId === task.task_id} onTransition={transition} />
                ))}
            </div>
          ))}
        </section>
      )}

      {tab === 'checkin' && (
        <section className="pv-card">
          <h2>提交近况</h2>
          <p className="pv-notice">发送后会保存为新的患者对话记录，并由 AI 整理给照护团队查看；不会直接修改医生记录或任务状态。</p>
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="例如：这周头痛好多了，但早上还是有点恶心…" rows={4} />
          <div className="inline-actions">
            <button onClick={send} disabled={busy || !message.trim()}>{busy ? '正在发送…' : submitError ? '重试发送' : '发送近况'}</button>
            {busy && <span className="muted">正在安全保存你的原始输入…</span>}
          </div>
          {submitError && <div className="form-error">发送失败：{submitError}。你的文字仍保留，可重试。</div>}
          <div className="pv-sessions">
            <h3 className="pv-subhead">过往 Check-in</h3>
            {view.check_in.sessions.length === 0 ? <p className="muted">还没有提交记录。</p> : (
              <ul className="pv-list">
                {view.check_in.sessions.map((session) => (
                  <li key={session.event_id} className="pv-session"><span className="pv-date muted">{fmtDate(session.started_at)}</span><span>{EVENT_TYPE_LABELS[session.event_type] ?? session.event_type}</span></li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {tab === 'summaries' && (
        <section className="pv-card">
          <h2>就诊说明</h2>
          {view.visit_summaries.summaries.length === 0 ? <p className="muted">暂时没有患者可见的就诊说明。</p> : (
            <ul className="pv-list">
              {view.visit_summaries.summaries.map((summary) => (
                <li key={summary.artifact_id} className="pv-instruction">
                  <div className="pv-date muted">{fmtDate(summary.event_time)}</div>
                  <p>{summary.instruction}</p>
                  {summary.follow_up && <p className="pv-followup">后续安排：{summary.follow_up}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function PatientTaskCard({ task, pending, onTransition }: {
  task: PatientTask;
  pending: boolean;
  onTransition: (task: PatientTask, status: TaskStatus) => void;
}) {
  return (
    <article className={`pv-task pv-task-${task.status}`}>
      <div><strong>{task.title}</strong>{task.due_at && <small>截止 {fmtDate(task.due_at)}</small>}</div>
      {task.status === 'open' && <button disabled={pending} onClick={() => onTransition(task, 'in_progress')}>{pending ? '更新中…' : '开始'}</button>}
      {(task.status === 'open' || task.status === 'in_progress') && <button disabled={pending} onClick={() => onTransition(task, 'reported_done')}>报告已完成</button>}
      {task.status === 'reported_done' && <span className="pv-waiting">已报告完成 · 等待诊所确认</span>}
      {task.status === 'completed' && <span className="pv-complete">诊所已确认完成</span>}
    </article>
  );
}
