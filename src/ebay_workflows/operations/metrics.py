"""Workflow metrics helpers (Tier 7 cascade funnel)."""

from __future__ import annotations

from typing import Any


def tier7_metrics_payload(
    *,
    proposals_raw: int,
    post_veto: int,
    verified: int,
) -> dict[str, Any]:
    """Build Tier 7 funnel counters for workflow step metrics_json."""
    return {
        "tier7_proposals_raw": proposals_raw,
        "tier7_post_veto": post_veto,
        "tier7_verified": verified,
    }


def merge_tier7_into_metrics(
    metrics: dict[str, Any],
    *,
    proposals_raw: int,
    post_veto: int,
    verified: int,
) -> dict[str, Any]:
    """Return a copy of metrics with Tier 7 keys added."""
    merged = dict(metrics)
    merged.update(
        tier7_metrics_payload(
            proposals_raw=proposals_raw,
            post_veto=post_veto,
            verified=verified,
        )
    )
    return merged
