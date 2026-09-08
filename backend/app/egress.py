"""Request-local minimization and supported-pattern guard for all provider flows."""
from .redaction import RedactedContent, redact_content, unresolved_placeholders


class EgressRejected(ValueError):
    pass


SCALARS = {"text", "summary", "note", "assessment", "plan", "instruction", "follow_up"}
COLLECTIONS = {
    "segments": {"index", "speaker", "text"},
    "messages": {"id", "speaker", "text", "intent", "question_type"},
    "patient_visible_tasks": {"task_id", "title", "status"},
    "evidence": {"evidence_id", "event_time", "artifact_type", "author_role", "quote"},
}
FLOW_FIELDS = {
    "summarize": SCALARS | {"segments", "messages"},
    "copilot": {"category", "question", "evidence"},
    "checkin_turn": {"messages", "patient_visible_tasks"},
    "checkin_summary": {"messages"},
}


def prepare(redacted, method):
    if not isinstance(redacted, RedactedContent) or method not in FLOW_FIELDS:
        raise EgressRejected("egress_schema_rejected")
    aliases = {}
    reverse = {}
    content = {}
    for key in FLOW_FIELDS[method]:
        if key not in redacted.content:
            continue
        value = redacted.content[key]
        if key in COLLECTIONS:
            if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
                raise EgressRejected("egress_schema_rejected")
            projected = []
            for row in value:
                item = {k: v for k, v in row.items() if k in COLLECTIONS[key]}
                for field, field_value in item.items():
                    if field == "index":
                        valid = type(field_value) is int and field_value >= 0
                    else:
                        valid = isinstance(field_value, str) or (
                            field in {"intent", "question_type"} and field_value is None
                        )
                    if not valid:
                        raise EgressRejected("egress_schema_rejected")
                for id_key in ("id", "task_id", "evidence_id"):
                    if id_key in item:
                        original = item[id_key]
                        if not isinstance(original, str):
                            raise EgressRejected("egress_schema_rejected")
                        if original not in aliases:
                            alias = f"ref_{len(aliases) + 1}"
                            aliases[original] = alias
                            reverse[alias] = original
                        item[id_key] = aliases[original]
                projected.append(item)
            content[key] = projected
        else:
            if not isinstance(value, str):
                raise EgressRejected("egress_schema_rejected")
            content[key] = value
    # Re-running the supported detector is a guard, not another redaction pass:
    # caller must retain mappings needed for source anchoring.
    if any(redact_content(content, []).redacted.redaction_counts.values()):
        raise EgressRejected("egress_sensitive_pattern")
    def check(node):
        if isinstance(node, dict):
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)
        elif isinstance(node, str):
            tokens = {token: "" for token in redacted.placeholder_tokens}
            if unresolved_placeholders(node, tokens):
                raise EgressRejected("egress_placeholder_invalid")
    check(content)
    return RedactedContent(content, redacted.redaction_counts, redacted.placeholder_tokens), reverse


def restore_references(result, mapping):
    def walk(value):
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return mapping.get(value, value) if isinstance(value, str) else value
    return type(result).model_validate(walk(result.model_dump()))


def call_provider(client, method, redacted, *args):
    payload, reverse = prepare(redacted, method)
    return restore_references(getattr(client, method)(payload, *args), reverse)


def guarded(method):
    """Final adapter defense even when an internal caller bypasses orchestration."""
    from functools import wraps
    @wraps(method)
    def checked(self, redacted, *args, **kwargs):
        payload, reverse = prepare(redacted, method.__name__)
        return restore_references(method(self, payload, *args, **kwargs), reverse)
    return checked
