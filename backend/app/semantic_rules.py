"""Bounded source-language rules, not a general medical language parser."""
import re

NEGATED = re.compile(r"\b(no|not|denies?|without|never)\b|没有|否认|无", re.I)
FAMILY = re.compile(r"\b(mother|father|sister|brother|daughter|son|family|wife|husband)\b|母亲|父亲|家属|妈妈|爸爸|姐姐|哥哥", re.I)
PAST = re.compile(r"\b(yesterday|previously|used to|last (?:week|month|year)|was|had)\b|昨天|以前|曾经|既往|过去", re.I)
HYPOTHETICAL = re.compile(r"\b(if|might|may|could|should|possible|watch for)\b|如果|可能|假如", re.I)


def assertion_context(text):
    return {
        "assertion": "negative" if NEGATED.search(text) else "uncertain" if HYPOTHETICAL.search(text) else "positive",
        "subject": "family" if FAMILY.search(text) else "patient",
        "temporality": "hypothetical" if HYPOTHETICAL.search(text) else "historical" if PAST.search(text) else "current",
    }


def current_positive(text):
    ctx = assertion_context(text)
    return ctx == {"assertion": "positive", "subject": "patient", "temporality": "current"}


def clauses(text):
    # Returned strings are exact substrings. Inherited family/past/conditional
    # context is checked by the caller before interpreting a later clause.
    parts = [p.strip() for p in re.split(r"[.!?;。！？；]|\bbut\b|[,，]\s*(?:但|但是)", text, flags=re.I) if p.strip()]
    return [text.strip()] if len(parts) == 1 else parts


RULE_VERSION = "source-semantics-v1"
CONCEPTS = {
    "headache": ("headache", "headaches", "head pain", "头痛"),
    "nausea": ("nausea", "nauseous", "恶心"),
    "blood pressure": ("blood pressure", "bp", "血压"),
    "blood test": ("blood test", "blood tests", "验血"),
    "follow-up": ("follow-up", "follow up", "followup", "复诊"),
    "propranolol": ("propranolol", "普萘洛尔"),
    "amitriptyline": ("amitriptyline", "阿米替林"),
    "penicillin": ("penicillin", "青霉素"),
    "light-headedness": ("light-headedness", "lightheaded", "light-headed", "头晕"),
    "home blood pressure log": ("home blood pressure log", "blood pressure diary"),
    "knee discomfort": ("knee discomfort", "knee pain"),
    "wrist discomfort": ("wrist discomfort", "wrist pain"),
    "physiotherapy follow-up": ("physiotherapy", "physical therapy"),
}


def _concepts(text):
    found = set()
    for key, aliases in CONCEPTS.items():
        for alias in aliases:
            pattern = re.escape(alias)
            if alias.isascii():
                pattern = r"\b" + pattern + r"\b"
            if re.search(pattern, text, re.I):
                found.add(key)
    if "home blood pressure log" in found:
        found.discard("blood pressure")
    if "physiotherapy follow-up" in found:
        found.discard("follow-up")
    return found


def interpret(quote, entity_type, display_text=""):
    found = _concepts(quote)
    selected = found & _concepts(display_text)
    if _concepts(display_text) and not selected:
        selected = set()
    elif len(selected) != 1:
        selected = found
    concept = next(iter(selected)) if len(selected) == 1 else None
    parts = clauses(quote)
    matching = [p for p in parts if concept and concept in _concepts(p)]
    focus = matching[-1] if matching else quote
    if concept and parts and re.search(r"\bnow\b|现在|目前", parts[-1], re.I) and not (_concepts(parts[-1]) - {concept}):
        focus = parts[-1]
    context = assertion_context(focus)
    if FAMILY.search(quote) and not re.search(r"\bI (?:have|am|feel)\b|我现在|我有", focus, re.I):
        context["subject"] = "family"
    if entity_type == "task" and re.search(r"not (?:yet )?(?:done|completed)|pending|outstanding", quote, re.I):
        context["assertion"] = "positive"
    if re.search(r"\b(friend|neighbor|neighbour|colleague|someone)\b|朋友|邻居|别人", quote, re.I):
        context["subject"] = "other"
    if context["temporality"] == "current" and not re.search(
        r"\b(have|has|is|are|now|today|still|continues?|reports?|remains?|weekly|daily|pending|order\w*|scheduled|taking|takes?|every|persists?|improv\w*|wors\w*|increas\w*|elevated)\b|头痛严重|目前|现在|今天|每天|每周|持续|出现|正在", focus, re.I):
        context["temporality"] = "unknown"
    if concept is None:
        context["subject"] = "unknown" if context["subject"] == "patient" else context["subject"]
    return {**context, "concept_key": f"{entity_type}:{concept}" if concept else None,
            "recognition_status": "recognized" if concept else "unknown", "rule_version": RULE_VERSION}


def repetition_key(context):
    if context and context.get("recognition_status") == "recognized" and all(
        context.get(k) == v for k, v in (("subject", "patient"), ("assertion", "positive"), ("temporality", "current"))):
        return context.get("concept_key") or ""
    return ""


def interpret_span(content, span, entity_type, display_text=""):
    from .highlights import extract_text
    quote = extract_text(content, span) or ""
    full = extract_text(content, {k: v for k, v in span.items() if k != "offset"}) or quote
    # A model may quote only the affirmative-looking tail of a denial or a
    # family-history sentence. Interpret its containing clause, not that tail.
    containing = [p for p in clauses(full) if quote in p]
    context_text = containing[0] if containing else full
    return interpret(context_text, entity_type, display_text)
