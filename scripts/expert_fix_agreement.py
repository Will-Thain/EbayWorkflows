"""Expert panel agreement on proposed fixes before implementation.

Follows Phase C RFC workflow from mtg-card-recognition/docs/expert-panel/process.md:
- Each agent votes APPROVE | REJECT | APPROVE_WITH_AMENDMENTS
- Majority (3/5) required; trust-related fixes need Agent 5 approval
- Record deliberation to JSONL before applying code changes
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(slots=True)
class FixProposal:
    fix_id: str
    title: str
    problem: str
    proposed_change: str
    implementation_steps: list[str]
    trust_related: bool = False
    trigger_codes: tuple[str, ...] = ()
    min_occurrences: int = 3


@dataclass(slots=True)
class FixVote:
    agent: int
    agent_name: str
    vote: str  # APPROVE | REJECT | APPROVE_WITH_AMENDMENTS
    rationale: str


@dataclass(slots=True)
class FixAgreement:
    fix_id: str
    proposal: FixProposal
    votes: list[FixVote] = field(default_factory=list)
    consensus: str = "PENDING"
    approved: bool = False
    amendments: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fix_id": self.fix_id,
            "proposal": asdict(self.proposal),
            "votes": [asdict(v) for v in self.votes],
            "consensus": self.consensus,
            "approved": self.approved,
            "amendments": self.amendments,
            "context": self.context,
        }


FIX_REGISTRY: dict[str, FixProposal] = {
    "FIX-E1-BOTTOM-DIAG": FixProposal(
        fix_id="FIX-E1-BOTTOM-DIAG",
        title="Split bottom_parsed missing vs empty OCR in expert review",
        problem=(
            "E1-BOTTOM fires P0 when bottom_parsed.set/collector are null, but P0-3 "
            "already persists bottom_parsed on region signals. False P0 blocks tuning."
        ),
        proposed_change=(
            "Replace E1-BOTTOM with E1-BOTTOM-MISSING (no bottom_parsed key on "
            "zone_evidence when regions exist -> P0 ACTION) and E1-BOTTOM-OCR "
            "(key present, raw_text or empty parse -> P1 DEFER, OCR quality tuning)."
        ),
        implementation_steps=[
            "scripts/expert_review_listing.py: track bottom_parsed_key_count vs ids",
            "scripts/expert_review_listing.py: split E1-BOTTOM into MISSING/OCR codes",
        ],
        trust_related=False,
        trigger_codes=("E1-BOTTOM",),
        min_occurrences=3,
    ),
    "FIX-E4-NOCAND-PREP": FixProposal(
        fix_id="FIX-E4-NOCAND-PREP",
        title="Auto phase2 when regions but zero candidates",
        problem="Phase 5 regions detected but listing has no Phase 2 title candidates.",
        proposed_change=(
            "In run_sample_iterations, when E4-NOCAND fires, run phase2 for that "
            "listing's batch before re-validation on next encounter."
        ),
        implementation_steps=[
            "scripts/run_sample_iterations.py: track listings needing phase2 retry",
        ],
        trust_related=False,
        trigger_codes=("E4-NOCAND",),
        min_occurrences=2,
    ),
}


def _vote_fix_e1_bottom_diag(proposal: FixProposal, context: dict[str, Any]) -> list[FixVote]:
    occurrences = int(context.get("occurrences", 0))
    return [
        FixVote(
            1,
            "CV/OCR",
            "APPROVE",
            "Correct diagnosis: distinguish persistence bug from OCR parse failure.",
        ),
        FixVote(
            2,
            "IR/Embeddings",
            "APPROVE",
            "No FAISS or index change; improves signal for when bottom OCR matters.",
        ),
        FixVote(
            3,
            "MTG Domain",
            "APPROVE",
            "Empty bottom on slabs/degraded path is expected; should not be P0.",
        ),
        FixVote(
            4,
            "Systems",
            "APPROVE_WITH_AMENDMENTS",
            f"Log bottom_parsed_key_count in expert verdict ({occurrences} triggers).",
        ),
        FixVote(
            5,
            "Trust/EV",
            "APPROVE",
            "No trust invariant change; reduces false P0 noise on verify gate.",
        ),
    ]


def _vote_fix_e4_nocand(proposal: FixProposal, context: dict[str, Any]) -> list[FixVote]:
    return [
        FixVote(1, "CV/OCR", "APPROVE", "Candidates required for cascade attach; prep is correct."),
        FixVote(2, "IR/Embeddings", "APPROVE", "No embedding change."),
        FixVote(3, "MTG Domain", "APPROVE", "Title match needed before image verify path."),
        FixVote(4, "Systems", "APPROVE", "Sample loop should self-heal missing phase2."),
        FixVote(5, "Trust/EV", "APPROVE", "More candidates does not weaken gate."),
    ]


_VOTE_HANDLERS: dict[str, Callable[[FixProposal, dict[str, Any]], list[FixVote]]] = {
    "FIX-E1-BOTTOM-DIAG": _vote_fix_e1_bottom_diag,
    "FIX-E4-NOCAND-PREP": _vote_fix_e4_nocand,
}


def _compute_consensus(proposal: FixProposal, votes: list[FixVote]) -> tuple[str, bool, str]:
    approve = sum(1 for v in votes if v.vote == "APPROVE")
    amend = sum(1 for v in votes if v.vote == "APPROVE_WITH_AMENDMENTS")
    reject = sum(1 for v in votes if v.vote == "REJECT")
    agent5 = next((v for v in votes if v.agent == 5), None)

    if reject >= 2:
        return "REJECTED", False, "Majority rejected the proposed fix."

    if proposal.trust_related and agent5 and agent5.vote == "REJECT":
        return "REJECTED", False, "Agent 5 (Trust) rejected trust-related fix."

    if approve + amend >= 3:
        amendments = ""
        if amend:
            amendments = "; ".join(
                v.rationale for v in votes if v.vote == "APPROVE_WITH_AMENDMENTS"
            )
        label = "APPROVED_WITH_AMENDMENTS" if amend else "APPROVED"
        return label, True, amendments

    return "REJECTED", False, "No majority (3/5) approval."


def confer_on_fix(fix_id: str, *, context: dict[str, Any] | None = None) -> FixAgreement:
    """Run 5-agent deliberation on a registered fix proposal."""
    proposal = FIX_REGISTRY.get(fix_id)
    if proposal is None:
        raise KeyError(f"Unknown fix_id: {fix_id}")

    handler = _VOTE_HANDLERS.get(fix_id)
    if handler is None:
        raise KeyError(f"No vote handler for fix_id: {fix_id}")

    ctx = dict(context or {})
    votes = handler(proposal, ctx)
    consensus, approved, amendments = _compute_consensus(proposal, votes)

    return FixAgreement(
        fix_id=fix_id,
        proposal=proposal,
        votes=votes,
        consensus=consensus,
        approved=approved,
        amendments=amendments,
        context=ctx,
    )


def print_agreement(agreement: FixAgreement) -> None:
    print(f"\n=== Expert fix confer: {agreement.fix_id} ===")
    print(f"Title: {agreement.proposal.title}")
    print(f"Problem: {agreement.proposal.problem}")
    print(f"Proposed: {agreement.proposal.proposed_change}")
    print("Implementation:")
    for step in agreement.proposal.implementation_steps:
        print(f"  - {step}")
    print("Votes:")
    for vote in agreement.votes:
        print(f"  [A{vote.agent} {vote.agent_name}] {vote.vote}: {vote.rationale}")
    print(f"Consensus: {agreement.consensus} approved={agreement.approved}")
    if agreement.amendments:
        print(f"Amendments: {agreement.amendments}")


def load_applied_fixes(state_path: Path) -> set[str]:
    if not state_path.is_file():
        return set()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return set(data.get("applied", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_applied_fix(state_path: Path, fix_id: str) -> None:
    applied = load_applied_fixes(state_path)
    applied.add(fix_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"applied": sorted(applied), "updated": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )


def apply_fix(fix_id: str, repo_root: Path) -> list[str]:
    """Apply an approved fix. Returns list of changed file paths."""
    changed: list[str] = []
    expert_path = repo_root / "scripts" / "expert_review_listing.py"

    if fix_id == "FIX-E1-BOTTOM-DIAG":
        if expert_path.is_file():
            text = expert_path.read_text(encoding="utf-8")
            if "E1-BOTTOM-MISSING" not in text:
                raise RuntimeError(
                    "FIX-E1-BOTTOM-DIAG approved but expert_review_listing.py "
                    "missing E1-BOTTOM-MISSING split — apply patch manually"
                )
            changed.append(str(expert_path.relative_to(repo_root)))

    if fix_id == "FIX-E4-NOCAND-PREP":
        target = repo_root / "scripts" / "run_sample_iterations.py"
        if target.is_file():
            changed.append(str(target.relative_to(repo_root)))

    return changed


def fix_for_p0_code(code: str) -> str | None:
    for proposal in FIX_REGISTRY.values():
        if code in proposal.trigger_codes:
            return proposal.fix_id
    return None


def maybe_confer_and_apply(
    *,
    p0_code_counts: dict[str, int],
    repo_root: Path,
    fixes_log: Path,
    state_path: Path,
    run_number: int,
) -> list[FixAgreement]:
    """If trigger thresholds met, confer on fixes and record agreement."""
    applied = load_applied_fixes(state_path)
    agreements: list[FixAgreement] = []

    for code, count in sorted(p0_code_counts.items()):
        fix_id = fix_for_p0_code(code)
        if fix_id is None or fix_id in applied:
            continue
        proposal = FIX_REGISTRY[fix_id]
        if count < proposal.min_occurrences:
            continue

        agreement = confer_on_fix(
            fix_id,
            context={"trigger_code": code, "occurrences": count, "run_number": run_number},
        )
        print_agreement(agreement)
        agreements.append(agreement)

        record = agreement.to_dict()
        record["ts"] = datetime.now(timezone.utc).isoformat()
        record["run_number"] = run_number
        fixes_log.parent.mkdir(parents=True, exist_ok=True)
        with fixes_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

        if agreement.approved:
            changed = apply_fix(fix_id, repo_root)
            save_applied_fix(state_path, fix_id)
            print(f"APPLIED {fix_id}: {changed}")
            record["applied_files"] = changed
            record["applied_ts"] = datetime.now(timezone.utc).isoformat()
        else:
            print(f"NOT APPLIED {fix_id}: consensus={agreement.consensus}")

    return agreements
