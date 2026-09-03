import { useState } from 'react';
import { api } from '../api';
import type { Artifact } from '../types';

export default function PatientInstructionComposer({
  eventId,
  onSaved,
}: {
  eventId: string;
  onSaved: (artifact: Artifact) => void;
}) {
  const [instruction, setInstruction] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const nextInstruction = instruction.trim();
    if (!nextInstruction) return;
    setBusy(true);
    setError(null);
    try {
      const artifact = await api.createNote(eventId, 'patient_instruction', {
        instruction: nextInstruction,
        ...(followUp.trim() ? { follow_up: followUp.trim() } : {}),
      });
      onSaved(artifact);
    } catch (saveError: any) {
      setError(String(saveError.message ?? saveError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="patient-instruction-composer" aria-label="New patient instruction">
      <header><div><strong>New patient instruction</strong><span>Write the patient-facing wording here. It will be saved as a clinic draft and must be published separately.</span></div></header>
      <label>Instruction<textarea rows={4} value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="What should the patient know or do next?" /></label>
      <label>Follow-up (optional)<textarea rows={2} value={followUp} onChange={(event) => setFollowUp(event.target.value)} placeholder="When or how will the clinic follow up?" /></label>
      <div className="inline-actions"><button className="primary-button" disabled={busy || !instruction.trim()} onClick={() => void save()}>{busy ? 'Saving…' : 'Save clinic draft'}</button><span>Nothing is patient-visible until a clinician publishes it.</span></div>
      {error && <div className="form-error">Could not save instruction: {error}</div>}
    </section>
  );
}
