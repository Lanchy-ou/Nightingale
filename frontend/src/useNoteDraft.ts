import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';
import type { PrivateNoteDraft } from './types';

const dirtyEditors = new Set<() => boolean>();
const confirmedClicks = new WeakSet<MouseEvent>();
export function confirmLeaveDrafts(): boolean {
  return ![...dirtyEditors].some((isDirty) => isDirty()) || window.confirm('Some changes have not been saved as a private draft. Leave and discard those changes?');
}

// Private working copies are explicitly saved. No note content goes into browser storage.
export function useNoteDraft(eventId: string, slot: string, fields: Record<string, string>, baseVersion: number,
  enabled: boolean, restore: (draft: PrivateNoteDraft) => void) {
  const live = useRef({ fields, baseVersion, restore });
  live.current = { fields, baseVersion, restore };
  const revision = useRef(0);
  const baseline = useRef('');
  const active = useRef(false);
  const [ready, setReady] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [hasSaved, setHasSaved] = useState(false);
  const fingerprint = () => JSON.stringify([live.current.fields, live.current.baseVersion]);
  const dirty = () => active.current && baseline.current !== fingerprint();

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let mounted = true;
    setReady(false); setPending(false); setMessage('Loading private draft…'); setError('');
    api.getNoteDraft(eventId, slot, controller.signal).then((draft) => {
      if (!mounted) return;
      revision.current = draft.revision;
      setHasSaved(draft.fields !== null);
      if (draft.fields !== null) {
        live.current.restore(draft);
        baseline.current = JSON.stringify([draft.fields, draft.base_version]);
        setMessage('Private draft restored. It is not part of the clinical record.');
      } else {
        baseline.current = fingerprint();
        setMessage('Save a private draft before leaving to keep your changes.');
      }
      active.current = true; setReady(true);
    }).catch((caught) => {
      if (mounted && caught?.name !== 'AbortError') setError('Could not load your draft. Reopen the editor to try again.');
    });
    return () => { mounted = false; active.current = false; controller.abort(); };
  }, [eventId, slot, enabled]);

  useEffect(() => {
    if (!enabled) return;
    dirtyEditors.add(dirty);
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (dirty()) { event.preventDefault(); event.returnValue = ''; }
    };
    const leaveClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest('a, button, summary') : null;
      if (confirmedClicks.has(event) || !target || (!target.closest('[data-leave-editor]') && !target.matches('a[href]'))) return;
      if (dirty()) {
        if (!confirmLeaveDrafts()) { event.preventDefault(); event.stopImmediatePropagation(); }
        else confirmedClicks.add(event);
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('click', leaveClick, true);
    return () => { dirtyEditors.delete(dirty); window.removeEventListener('beforeunload', beforeUnload); document.removeEventListener('click', leaveClick, true); };
  }, [enabled]);

  async function savePrivate() {
    if (!ready || pending) return;
    setPending(true); setError('');
    const data = live.current;
    try {
      const draft = await api.saveNoteDraft(eventId, slot, revision.current, data.baseVersion, data.fields);
      if (!active.current) return;
      revision.current = draft.revision;
      setHasSaved(draft.fields !== null);
      baseline.current = JSON.stringify([data.fields, data.baseVersion]);
      setMessage('Private draft saved. Only you can restore it.');
    } catch (caught) {
      if (active.current) setError(caught instanceof ApiError && caught.status === 409
        ? 'Another tab changed this private draft. Your text is still here; reopen after keeping a copy, or save the clinical note with its version check.'
        : 'Draft was not saved. Keep this editor open and try again.');
    } finally { if (active.current) setPending(false); }
  }

  async function discardPrivate(fields: Record<string, string>, version: number) {
    if (!window.confirm('Discard this private draft and return to the saved clinical note?')) return false;
    setPending(true); setError('');
    try {
      const result = await api.saveNoteDraft(eventId, slot, revision.current, 0, null);
      if (!active.current) return false;
      revision.current = result.revision;
      baseline.current = JSON.stringify([fields, version]);
      setHasSaved(false); setMessage('Private draft discarded.');
      return true;
    } catch {
      if (active.current) setError('The draft could not be discarded. It may have changed in another tab; your text is still here.');
      return false;
    } finally { if (active.current) setPending(false); }
  }

  async function clearAfterPublish() {
    // Clearing uses the last known revision; never erase another tab's newer draft.
    if (revision.current > 0) {
      try {
        const result = await api.saveNoteDraft(eventId, slot, revision.current, 0, null);
        revision.current = result.revision;
        if (active.current) setHasSaved(false);
      } catch { /* A newer private draft remains retrievable. */ }
    }
    baseline.current = slot === 'new' ? JSON.stringify([{ body: '' }, 0]) : fingerprint();
  }
  const status = ready && dirty() ? 'Unsaved changes. Save a private draft to keep them before leaving.' : message;
  return { ready, pending, hasSaved, message: status, error, savePrivate, discardPrivate, clearAfterPublish };
}
