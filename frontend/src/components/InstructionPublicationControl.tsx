import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import { formatDateTime } from '../clinical';
import type {
  Artifact,
  PatientInstructionPublication,
  PatientInstructionReceiptHistory,
} from '../types';

const PUBLICATION_LABELS: Record<PatientInstructionPublication['state'], string> = {
  draft: 'Draft · not visible to patient',
  published: 'Published in Patient portal',
  superseded: 'Superseded by a correction',
  withdrawn: 'Withdrawn from Patient portal',
};

const RECEIPT_LABELS: Record<PatientInstructionReceiptHistory['status'], string> = {
  not_viewed: 'Not viewed',
  viewed: 'Viewed · awaiting acknowledgement',
  acknowledged: 'Acknowledged',
};

type WithdrawReason = 'entered_in_error' | 'no_longer_applicable' | 'replaced_elsewhere';

export default function InstructionPublicationControl({
  artifact,
  role,
  onChanged,
}: {
  artifact: Artifact;
  role: string;
  onChanged: (nextArtifactId?: string) => void;
}) {
  const [history, setHistory] = useState<PatientInstructionPublication[]>([]);
  const [receipts, setReceipts] = useState<PatientInstructionReceiptHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'correct' | 'withdraw' | null>(null);
  const [instruction, setInstruction] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [correctionId, setCorrectionId] = useState('');
  const [withdrawReason, setWithdrawReason] = useState<WithdrawReason>('no_longer_applicable');

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const [nextHistory, nextReceipts] = await Promise.all([
        api.getPatientInstructionPublicationHistory(artifact.artifact_id, signal),
        api.getPatientInstructionReceipts(artifact.artifact_id, signal),
      ]);
      setHistory(nextHistory);
      setReceipts(nextReceipts);
      setError(null);
    } catch (loadError: any) {
      if (loadError?.name !== 'AbortError') setError(String(loadError?.message ?? loadError));
    } finally {
      setLoading(false);
    }
  }, [artifact.artifact_id]);

  useEffect(() => {
    const controller = new AbortController();
    setMode(null);
    setInstruction(String(artifact.content.instruction ?? ''));
    setFollowUp(String(artifact.content.follow_up ?? ''));
    setCorrectionId('');
    void load(controller.signal);
    return () => controller.abort();
  }, [artifact.artifact_id, artifact.content, load]);

  const publication = history.find((row) => row.artifact_id === artifact.artifact_id) ?? null;
  const receipt = receipts.find((row) => row.artifact_version === artifact.version) ?? null;
  const orderedHistory = useMemo(
    () => [...history].sort((a, b) => b.lineage_revision - a.lineage_revision),
    [history],
  );

  async function publish() {
    setBusy(true);
    setError(null);
    try {
      await api.publishPatientInstruction(artifact.artifact_id);
      await load();
      onChanged();
    } catch (actionError: any) {
      setError(String(actionError?.message ?? actionError));
    } finally {
      setBusy(false);
    }
  }

  function startCorrection() {
    setInstruction(String(artifact.content.instruction ?? ''));
    setFollowUp(String(artifact.content.follow_up ?? ''));
    setCorrectionId(crypto.randomUUID());
    setMode('correct');
    setError(null);
  }

  async function correct() {
    if (!instruction.trim() || !correctionId) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.correctPatientInstruction(
        artifact.artifact_id,
        correctionId,
        { instruction: instruction.trim(), follow_up: followUp.trim() || null },
      );
      setMode(null);
      onChanged(next.artifact_id);
    } catch (actionError: any) {
      setError(String(actionError?.message ?? actionError));
    } finally {
      setBusy(false);
    }
  }

  async function withdraw() {
    setBusy(true);
    setError(null);
    try {
      await api.withdrawPatientInstruction(artifact.artifact_id, withdrawReason);
      setMode(null);
      await load();
      onChanged();
    } catch (actionError: any) {
      setError(String(actionError?.message ?? actionError));
    } finally {
      setBusy(false);
    }
  }

  if (loading && history.length === 0) {
    return <div className="instruction-publication-panel">Loading publication state…</div>;
  }

  return (
    <section className="instruction-publication-panel" aria-label="Patient instruction publication">
      <div className="instruction-publication-summary">
        <div>
          <strong>Patient portal publication</strong>
          <span>{publication ? PUBLICATION_LABELS[publication.state] : 'Publication state unavailable'}</span>
        </div>
        {publication && <em>Lineage revision {publication.lineage_revision}</em>}
      </div>

      {publication?.state === 'published' && (
        <div className="instruction-receipt-clinical" aria-label="Patient receipt status">
          <strong>Patient portal receipt</strong>
          <span>{receipt ? RECEIPT_LABELS[receipt.status] : 'Not viewed'}</span>
          {receipt?.acknowledged_at && <span>{formatDateTime(receipt.acknowledged_at)}</span>}
          <small>This confirms portal reading only; it is not consent or task completion.</small>
        </div>
      )}

      {publication?.state === 'withdrawn' && (
        <p className="instruction-publication-note">Reason: {publication.withdrawal_reason_code?.replace(/_/g, ' ')}. Historical content and receipts are retained.</p>
      )}
      {publication?.state === 'superseded' && publication.superseded_by_artifact_id && (
        <p className="instruction-publication-note">Corrected by {publication.superseded_by_artifact_id}. This wording remains historical and is no longer patient-visible.</p>
      )}

      {role === 'clinician' && publication?.state === 'draft' && (
        <div className="instruction-publication-actions">
          <button className="primary-button" disabled={busy} onClick={() => void publish()}>{busy ? 'Publishing…' : 'Publish to Patient portal'}</button>
          <span>Publishing creates a new Not viewed receipt. No external message is sent.</span>
        </div>
      )}
      {role === 'clinician' && publication?.state === 'published' && !mode && (
        <div className="instruction-publication-actions">
          <button className="secondary-button" onClick={startCorrection}>Correct instruction</button>
          <button className="secondary-button danger-button" onClick={() => setMode('withdraw')}>Withdraw</button>
        </div>
      )}

      {mode === 'correct' && (
        <div className="instruction-publication-form">
          <strong>Create a corrected published revision</strong>
          <label>Patient-facing instruction<textarea rows={4} value={instruction} onChange={(event) => setInstruction(event.target.value)} /></label>
          <label>Follow-up (optional)<textarea rows={2} value={followUp} onChange={(event) => setFollowUp(event.target.value)} /></label>
          <p>The old wording becomes superseded; its receipt and audit history remain unchanged.</p>
          <div><button className="primary-button" disabled={busy || !instruction.trim()} onClick={() => void correct()}>{busy ? 'Saving…' : 'Publish correction'}</button><button className="link-btn" onClick={() => setMode(null)}>Cancel</button></div>
        </div>
      )}

      {mode === 'withdraw' && (
        <div className="instruction-publication-form">
          <strong>Withdraw from active Patient View</strong>
          <label>Reason code<select value={withdrawReason} onChange={(event) => setWithdrawReason(event.target.value as WithdrawReason)}><option value="no_longer_applicable">No longer applicable</option><option value="entered_in_error">Entered in error</option><option value="replaced_elsewhere">Replaced elsewhere</option></select></label>
          <p>Withdrawal hides active content but never deletes the Artifact, versions, receipt or audit. Put any detailed clinical rationale in a clinician note.</p>
          <div><button className="secondary-button danger-button" disabled={busy} onClick={() => void withdraw()}>{busy ? 'Withdrawing…' : 'Confirm withdrawal'}</button><button className="link-btn" onClick={() => setMode(null)}>Cancel</button></div>
        </div>
      )}

      {orderedHistory.length > 1 && (
        <details className="instruction-publication-history"><summary>Lineage history ({orderedHistory.length})</summary>{orderedHistory.map((row) => <span key={row.artifact_id}>Revision {row.lineage_revision} · {PUBLICATION_LABELS[row.state]}</span>)}</details>
      )}
      {error && <div className="form-error">Could not update publication: {error}</div>}
    </section>
  );
}
