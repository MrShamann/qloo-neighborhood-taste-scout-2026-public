"""Private, explicit handoff from one actual Qloo source flow to a bounded
offline judge snapshot. This is NOT proof of API access by itself.
Never call this on invented test evidence for a public/demo assertion.
Requires separately verified provider quota, publication rights and Founder gate.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from .taste_bridge import LIVE_TRUTH, _private_bridge
from .taste_scout import ENTITY_ID_RE, GuardError

CACHED_TRUTH = "QLOO_HACKATHON_VERIFIED_SOURCE_SNAPSHOT"
_SOURCE_FIELDS = {
    "mode", "provider_verified", "scene_id", "city", "artists", "places",
    "source_explainability_count", "agent_steps", "provider_api_calls",
    "automatic_actions", "human_confirmation_required", "comparison", "limits",
}


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def snapshot_from_live(bridge_id: str, result: object,
                       timestamp_utc: str) -> dict:
    """Validate + sanitize an operator-reviewed successful live_bridge result.

    The caller must actually run live_bridge first. The resulting digest is
    integrity-only, not an organizer-signed or cryptographic provenance proof.
    """
    scene = _private_bridge(bridge_id)
    if (type(result) is not dict or set(result) != _SOURCE_FIELDS
            or result.get("mode") != LIVE_TRUTH
            or result.get("provider_verified") is not True
            or result.get("provider_api_calls") != 3
            or result.get("automatic_actions") != 0
            or result.get("human_confirmation_required") is not True
            or result.get("scene_id") != bridge_id
            or result.get("city") != scene["city"]):
        raise GuardError("unverified or unexpected source result")
    if not isinstance(timestamp_utc, str) or not re.fullmatch(
            r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            timestamp_utc):
        raise GuardError("UTC source acquisition time required")
    try:
        recorded = datetime.strptime(timestamp_utc, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise GuardError("invalid source date") from exc
    if recorded.year < 2026:
        raise GuardError("source predates hackathon")
    artists = result["artists"]
    if (type(artists) is not list or len(artists) != 2
            or any(type(a) is not dict or set(a) != {"artist", "source_entity_id"}
                   for a in artists)
            or [a["artist"] for a in artists] != scene["artists"]):
        raise GuardError("artist provenance mismatch")
    ids = [a["source_entity_id"] for a in artists]
    if len(set(ids)) != 2 or not all(
            isinstance(v, str) and ENTITY_ID_RE.fullmatch(v) for v in ids):
        raise GuardError("source artist IDs invalid or duplicated")
    steps = result["agent_steps"]
    if (not isinstance(steps, list) or
        [s.get("phase") for s in steps if isinstance(s, dict)] !=
        ["RESOLVE_A", "RESOLVE_B", "GROUND_BOTH", "FACT_CHECK", "HUMAN_REVIEW"] or
        [s.get("status") for s in steps[:3]] != ["LIVE", "LIVE", "LIVE"] or
        steps[3].get("status") != "PASS" or
        steps[4].get("status") != "REQUIRED"):
        raise GuardError("source agent trace does not describe verified Qloo calls")
    places = result["places"]
    if (type(places) is not list or not 1 <= len(places) <= 3
            or result["source_explainability_count"] != sum(
                bool(p.get("source_explainability")) for p in places
                if isinstance(p, dict))):
        raise GuardError("place count/provenance summary contradictory")
    seen = set()
    for idx, p in enumerate(places, 1):
        expected = {
            "name", "entity_id", "rank", "source_explainability",
            "source_attribution_state", "source_coverage_count",
            "source_coverage_state", "source_coverage_is_user_fit",
            "agent_decision", "agent_decision_is_automatic_approval",
        }
        if (type(p) is not dict or set(p) != expected
                or not isinstance(p["name"], str)
                or len(p["name"]) not in range(1, 131)
                or p["name"].startswith("Fictional ")
                or not isinstance(p["entity_id"], str)
                or not ENTITY_ID_RE.fullmatch(p["entity_id"])
                or p["entity_id"] in seen or p["rank"] != idx
                or p["source_coverage_is_user_fit"] is not False
                or p["agent_decision_is_automatic_approval"] is not False):
            raise GuardError("place type/ID/claim invalid")
        seen.add(p["entity_id"])
        contrib = p["source_explainability"]
        if type(contrib) is not list or len(contrib) > 2:
            raise GuardError("source explainability format invalid")
        seen_contrib = set()
        for c in contrib:
            if (type(c) is not dict or set(c) != {"entity_id", "score"}
                    or c["entity_id"] not in ids
                    or c["entity_id"] in seen_contrib
                    or type(c["score"]) not in (float, int)
                    or not math.isfinite(c["score"])
                    or not 0 <= c["score"] <= 1):
                raise GuardError("invalid source explanation reference")
            seen_contrib.add(c["entity_id"])
        coverage = len(seen_contrib)
        state = ("BOTH_EXPLICIT_INPUT_IDS" if coverage == 2 else
                 "ONE_EXPLICIT_INPUT_ID" if coverage == 1 else
                 "NO_INTEREST_ATTRIBUTION_PROVIDED")
        decision = ("SOURCE_VALUES_FOR_BOTH_REVIEW_ONLY" if coverage == 2 else
                    "SECOND_INTEREST_NOT_EVIDENCED" if coverage == 1 else
                    "ABSTAIN_NO_INTEREST_ATTRIBUTION")
        attribution = ("EXPLICIT_SOURCE_VALUES_ONLY" if coverage else
                       "UNAVAILABLE_NOT_INFERRED")
        if (p["source_coverage_count"] != coverage or
                p["source_coverage_state"] != state or
                p["agent_decision"] != decision or
                p["source_attribution_state"] != attribution):
            raise GuardError("contradictory public source claims")
    # Reject extraneous model output, full API response, prompt and key fields.
    raw = _canonical(result)
    if len(raw) > 52000 or b"X-Api-Key" in raw or b"QLOO_API_KEY" in raw:
        raise GuardError("source payload too large or sensitive")
    result_copy = json.loads(raw)
    result_copy["mode"] = CACHED_TRUTH
    result_copy["provider_api_calls"] = 0
    result_copy["source_acquisition_calls"] = 3
    result_copy["source_acquired_at_utc"] = timestamp_utc
    result_copy["snapshot_is_sponsor_signed"] = False
    result_copy["source_data_is_live_per_request"] = False
    # This hash proves only that the serialized data was not modified since
    # assembly; it cannot prove Qloo itself signed or approved these values.
    return {
        "format": "QLOO_PRIVATE_SOURCE_SNAPSHOT_V1",
        "scene_id": bridge_id,
        "source_digest_sha256": hashlib.sha256(raw).hexdigest(),
        "data": result_copy,
        "distribution_license_checked": False,
        "published": False,
    }


def make_one_private_snapshot(bridge_id: str, output: Path) -> dict:
    """One 2 Search + 1 Insights flow; no network unless ALL gates allow it.

    This routine does not supply Qloo credentials or grant a public license.
    """
    import os
    from .taste_bridge import live_bridge
    if (os.getenv("QLOO_EVENT_QUOTA_APPROVED") != "YES"
            or os.getenv("QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED") != "YES"
            or os.getenv("QLOO_LOCAL_PROBE_APPROVED") != "YES"):
        raise GuardError("event, source rights, and bounded real probe gates missing")
    # Missing credentials must fail BEFORE consuming the one-shot budget.
    # Never print, serialize or copy this credential.
    if not os.getenv("QLOO_API_KEY"):
        raise GuardError("event credential unavailable, no request attempted")
    target = Path(output).resolve()
    source_root = Path(__file__).resolve().parents[1]
    if source_root == target or source_root in target.parents:
        raise GuardError("verified snapshot cannot be written into source repository")
    if target.exists() or not target.parent.is_dir():
        raise GuardError("private output must not exist")
    marker_name = os.getenv("QLOO_PRIVATE_SINGLE_SHOT_MARKER", "")
    if not marker_name:
        raise GuardError("durable one-shot call budget marker required")
    marker = Path(marker_name).absolute()
    if (marker.parent.resolve() != target.parent or marker == target
            or marker.exists() or marker.is_symlink()):
        raise GuardError("marker must be unused and beside private output")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    # Durable reservation FIRST: if the process crashes after call one,
    # this marker still blocks an accidental retry of all three GETs.
    try:
        mfd = os.open(str(marker), flags, 0o600)
    except FileExistsError as exc:
        raise GuardError("Qloo three-request allowance already reserved") from exc
    with os.fdopen(mfd, "w", encoding="utf-8") as reservation:
        reservation.write(json.dumps({
            "status": "RESERVED_BEFORE_NETWORK_NO_AUTOMATIC_RETRY",
            "scene_id": bridge_id,
            "maximum_authorized_get_requests": 3,
            "created_at_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        }, sort_keys=True) + "\n")
    body = live_bridge(bridge_id)  # EXACT 3 read-only GETs, no retries.
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = snapshot_from_live(bridge_id, body, ts)
    fd = os.open(str(target), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    return {
        "private_source_snapshot": target.name,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "qloo_read_only_calls": 3,
        "single_shot_budget_marker_reserved": True,
        "public_release": False,
    }

def main() -> None:
    """CLI: a single authorized, non-retrying Qloo private evidence pass.

    Requires out-of-band server-side key provisioning and written event quota
    + source use clearance. This command alone can NOT approve any gate.
    """
    import argparse
    import os
    from .taste_bridge import bridge_catalogue

    parser = argparse.ArgumentParser(
        description="Private one-shot Qloo source proof. NEVER publishes content.")
    parser.add_argument("--bridge", choices=[row["id"]
                        for row in bridge_catalogue()], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    args = parser.parse_args()
    original = os.environ.get("QLOO_PRIVATE_SINGLE_SHOT_MARKER")
    if original and Path(original).absolute() != args.marker.absolute():
        parser.error("existing one-shot reservation path differs")
    os.environ["QLOO_PRIVATE_SINGLE_SHOT_MARKER"] = str(args.marker.absolute())
    try:
        result = make_one_private_snapshot(args.bridge, args.output)
    except (GuardError, OSError, ValueError) as exc:
        parser.error("private Qloo evidence step refused: " + str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
