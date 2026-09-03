import { useState } from 'react';
import { ApiError, api } from '../api';
import type { PatientImportBatch } from '../types';

function message(error: unknown): string {
  if (error instanceof ApiError) return error.body?.error?.message ?? error.message;
  return String((error as any)?.message ?? error);
}

function downloadReport(batch: PatientImportBatch) {
  const escape = (value: unknown) => {
    const text = String(value ?? '');
    const safe = /^[=+\-@]/.test(text) ? `'${text}` : text;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  const lines = [
    ['row_number', 'external_patient_id', 'name', 'status', 'error_code', 'patient_id'].join(','),
    ...batch.rows.map((row) => [row.row_number, row.external_patient_id, row.name, row.status, row.error_code, row.patient_id].map(escape).join(',')),
  ];
  const url = URL.createObjectURL(new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `patient-import-${batch.batch_id}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function AdminPatientImportsPage() {
  const [source, setSource] = useState('clinic_csv');
  const [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState<PatientImportBatch | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function preview() {
    if (!file || busy) return;
    setBusy(true); setError(null);
    try { setBatch(await api.previewPatientImport(source.trim(), file)); }
    catch (caught) { setError(message(caught)); }
    finally { setBusy(false); }
  }

  async function commit() {
    if (!batch || busy || batch.status === 'committed') return;
    setBusy(true); setError(null);
    try { setBatch(await api.commitPatientImport(batch.batch_id)); }
    catch (caught) { setError(message(caught)); }
    finally { setBusy(false); }
  }

  return <div className="admin-settings-page">
    {error && <div className="form-error" role="alert">{error}</div>}
    <section className="admin-surface admin-setting-card">
      <div className="admin-section-head"><div><p className="eyebrow">Preview before write</p><h2>Import patients</h2></div>{batch && <span className={`admin-status ${batch.status === 'committed' ? 'active' : ''}`}>{batch.status}</span>}</div>
      <p className="settings-copy">Upload a UTF-8 CSV containing exactly <strong>external_patient_id,name</strong>. Conflicts are reported and never overwrite an existing patient.</p>
      <div className="settings-key-form">
        <div className="settings-key-field"><label htmlFor="import-source">Source system</label><input id="import-source" value={source} onChange={(event) => setSource(event.target.value)} maxLength={64} /></div>
        <div className="settings-key-field"><label htmlFor="import-file">CSV file · maximum 1 MB / 1,000 rows</label><input id="import-file" type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setBatch(null); }} /></div>
        <button className="primary-button" disabled={!file || !source.trim() || busy} onClick={() => void preview()}>{busy ? 'Checking…' : 'Preview import'}</button>
      </div>
    </section>
    {batch && <section className="admin-surface">
      <div className="admin-section-head"><div><p className="eyebrow">{batch.source_system}</p><h2>Import report</h2></div><div className="admin-row-actions"><button className="secondary-button" onClick={() => downloadReport(batch)}>Download report</button>{batch.status === 'previewed' && <button className="primary-button" disabled={busy || batch.counts.ready === 0} onClick={() => void commit()}>{busy ? 'Importing…' : `Import ${batch.counts.ready} valid rows`}</button>}</div></div>
      <div className="admin-metric-grid" aria-label="Patient import summary">{(['ready', 'imported', 'unchanged', 'invalid', 'conflict'] as const).map((key) => <article key={key}><span>{key}</span><strong>{batch.counts[key]}</strong></article>)}</div>
      <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Row</th><th>External ID</th><th>Name</th><th>Status</th><th>Reason</th></tr></thead><tbody>{batch.rows.map((row) => <tr key={row.row_number}><td>{row.row_number}</td><td>{row.external_patient_id || '—'}</td><td>{row.name || '—'}</td><td><span className={`admin-status ${row.status}`}>{row.status}</span></td><td>{row.error_code?.replace(/_/g, ' ') ?? '—'}</td></tr>)}</tbody></table></div>
    </section>}
  </div>;
}
