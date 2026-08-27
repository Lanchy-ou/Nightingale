# M2 Task Card — Timeline, Glance, and Provenance Slice

> Status: COMPLETE

## Outcome

Deliver a chronological Event Timeline and a precomputed Glance projection with exact source navigation.

## Permanent contract

- Timeline sorts by Event.started_at, never Artifact creation time.
- Event cards expand into related Artifacts.
- Glance reads precomputed Highlights and performs no LLM work.
- Every Highlight points through its AI Summary Artifact to one raw source Artifact and exact Span.
- Failed quote anchoring drops the candidate.
- Ranking is deterministic and inspectable.

## Exit evidence

The canonical patient story can be followed end to end, Glance is useful without reading the full Timeline, and provenance micro-tests resolve the exact quote.
