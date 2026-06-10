"""Tier 7 cascade funnel metrics."""

from __future__ import annotations

from ebay_workflows.operations.metrics import merge_tier7_into_metrics, tier7_metrics_payload


def test_tier7_metrics_payload() -> None:
    payload = tier7_metrics_payload(proposals_raw=10, post_veto=7, verified=2)
    assert payload == {
        "tier7_proposals_raw": 10,
        "tier7_post_veto": 7,
        "tier7_verified": 2,
    }


def test_merge_tier7_into_metrics() -> None:
    merged = merge_tier7_into_metrics({"detections_created": 3}, proposals_raw=5, post_veto=4, verified=1)
    assert merged["detections_created"] == 3
    assert merged["tier7_verified"] == 1
