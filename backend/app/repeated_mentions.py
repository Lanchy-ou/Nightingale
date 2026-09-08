"""Patient-scoped repetition. Callers own transactions and projection rebuilds."""
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from .models import Event, Highlight
from .semantic_rules import repetition_key

RULE_VERSION = "repetition-semantic-v2"


def group_repeated_patient_entity_keys(anchored):
    events = defaultdict(set)
    for patient_id, key, event_id in anchored:
        if key:
            events[(patient_id, key)].add(event_id)
    return {key for key, values in events.items() if len(values) >= 2}


def scoped_highlights(db, patient_id, clinic_id):
    return list(db.scalars(select(Highlight).join(Event, Event.event_id == Highlight.event_id)
        .where(Highlight.patient_id == patient_id, Event.patient_id == patient_id,
               Event.clinic_id == clinic_id)).all())


def repetition_changes(db, patient_id, clinic_id, *, legacy=False):
    rows = scoped_highlights(db, patient_id, clinic_id)
    keys = {h.highlight_id: (h.entity_key if legacy else repetition_key(h.semantic_context)) for h in rows}
    repeated = group_repeated_patient_entity_keys(
        (h.patient_id, keys[h.highlight_id], h.event_id) for h in rows)
    return [(h, bool(keys[h.highlight_id] and (patient_id, keys[h.highlight_id]) in repeated))
            for h in rows
            if bool(h.feature_flags.get("repeated_mentions")) !=
               bool(keys[h.highlight_id] and (patient_id, keys[h.highlight_id]) in repeated)]


def recompute_repeated(db, patient_id, clinic_id, *, as_of=None, legacy=False):
    db.flush()  # SQLite serializes writers before the evidence query.
    changes = repetition_changes(db, patient_id, clinic_id, legacy=legacy)
    for highlight, repeated in changes:
        highlight.feature_flags = {**highlight.feature_flags, "repeated_mentions": repeated}
        highlight.updated_at = as_of or datetime.now()
    db.flush()
    return len(changes)
