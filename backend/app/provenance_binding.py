"""Immutable Highlight-to-source version and quote binding."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Artifact, ArtifactVersion, Highlight


def quote_sha256(quote: str) -> str:
    return hashlib.sha256(quote.encode("utf-8")).hexdigest()


def _exact_quote(content: object, span: object) -> str | None:
    # Local import avoids a module cycle: Task Highlight creation also calls
    # create_source_binding after app.tasks has finished importing.
    from .tasks import resolve_exact_span

    return resolve_exact_span(content, span)


def create_source_binding(
    source: Artifact | None, span: dict | None
) -> tuple[int | None, str | None]:
    if source is None or span is None:
        return None, None
    quote = _exact_quote(source.content, span)
    if not quote:
        return None, None
    return source.version, quote_sha256(quote)


def current_source_matches_binding(highlight: Highlight, source: Artifact) -> bool:
    if (
        highlight.source_artifact_version != source.version
        or not highlight.source_quote_sha256
        or highlight.source_span is None
    ):
        return False
    quote = _exact_quote(source.content, highlight.source_span)
    return bool(quote and quote_sha256(quote) == highlight.source_quote_sha256)


@dataclass(frozen=True)
class BoundSourceResolution:
    source: Artifact | None
    content: dict | None
    quote: str | None
    bound_version: int | None
    current_version: int | None
    source_changed: bool
    status: str


def resolve_highlight_source(
    db: Session, highlight: Highlight
) -> BoundSourceResolution:
    source = (
        db.get(Artifact, highlight.source_artifact_id)
        if highlight.source_artifact_id
        else None
    )
    bound_version = highlight.source_artifact_version
    current_version = source.version if source is not None else None
    changed = bool(
        source is not None
        and bound_version is not None
        and source.version != bound_version
    )
    if source is None:
        return BoundSourceResolution(
            None, None, None, bound_version, None, False, "source_missing"
        )
    if (
        bound_version is None
        or not highlight.source_quote_sha256
        or highlight.source_span is None
    ):
        return BoundSourceResolution(
            source,
            None,
            None,
            bound_version,
            current_version,
            changed,
            "binding_missing",
        )

    if source.version == bound_version:
        content = source.content
        status = "current"
    else:
        snapshot = db.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == source.artifact_id,
                ArtifactVersion.version == bound_version,
            )
        )
        if snapshot is None:
            return BoundSourceResolution(
                source,
                None,
                None,
                bound_version,
                current_version,
                True,
                "version_missing",
            )
        content = snapshot.content
        status = "historical"

    quote = _exact_quote(content, highlight.source_span)
    if not quote:
        return BoundSourceResolution(
            source,
            content,
            None,
            bound_version,
            current_version,
            changed,
            "span_invalid",
        )
    if quote_sha256(quote) != highlight.source_quote_sha256:
        return BoundSourceResolution(
            source,
            content,
            None,
            bound_version,
            current_version,
            changed,
            "hash_mismatch",
        )
    return BoundSourceResolution(
        source,
        content,
        quote,
        bound_version,
        current_version,
        changed,
        status,
    )
