"""Private source-snapshot static build candidate; NEVER a live Qloo endpoint.

Publication requires independently verified source acquisition, vendor display
rights, exact Founder authorization and zero-cost host limits. Default: refuse.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
from pathlib import Path

from src.source_snapshot import _canonical, snapshot_from_live
from src.taste_bridge import LIVE_TRUTH
from src.taste_scout import GuardError
from tools.build_judge_site import ROOT, build

FLAGS = (
    "QLOO_PROVIDER_SOURCE_RELEASE_APPROVED",
    "QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED",
    "QLOO_PUBLIC_DEPLOY_APPROVED",
    "QLOO_FREE_HOSTING_BILLING_VERIFIED",
)


def validate(snapshot_path: Path) -> dict:
    if any(os.getenv(k) != "YES" for k in FLAGS):
        raise GuardError("exact rights, source, deployment and billing approvals missing")
    if snapshot_path.is_symlink() or not snapshot_path.is_file():
        raise GuardError("a private ordinary source file is required")
    path = snapshot_path.resolve()
    if path == ROOT or ROOT in path.parents:
        raise GuardError("source receipt cannot be inside public repository")
    if path.stat().st_size > 80000:
        raise GuardError("source receipt too large")
    body = path.read_bytes()
    if any(secret in body for secret in
           (b"X-Api-Key", b"QLOO_API_KEY", b"-----BEGIN PRIVATE KEY-----")):
        raise GuardError("source payload includes credential-like data")
    doc = json.loads(body)
    if (type(doc) is not dict or set(doc) != {
        "format", "scene_id", "source_digest_sha256", "data",
        "distribution_license_checked", "published"
    } or doc["format"] != "QLOO_PRIVATE_SOURCE_SNAPSHOT_V1"
        or doc["distribution_license_checked"] is not True
        or doc["published"] is not False):
        raise GuardError("source must be rights-cleared and NOT yet published")
    digest = doc["source_digest_sha256"]
    if (not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest)
        or os.getenv("QLOO_SOURCE_DIGEST_APPROVED") != digest):
        raise GuardError("approved source digest mismatch")
    data = doc["data"]
    if type(data) is not dict:
        raise GuardError("source data missing")
    if (data.get("provider_api_calls") != 0 or
        data.get("source_acquisition_calls") != 3 or
        data.get("source_data_is_live_per_request") is not False or
        data.get("snapshot_is_sponsor_signed") is not False):
        raise GuardError("source snapshot truth mismatch")
    restored = copy.deepcopy(data)
    for key in (
        "source_acquisition_calls", "source_acquired_at_utc",
        "source_data_is_live_per_request", "snapshot_is_sponsor_signed"
    ):
        restored.pop(key, None)
    restored["provider_api_calls"] = 3
    restored["mode"] = LIVE_TRUTH
    if hashlib.sha256(_canonical(restored)).hexdigest() != digest:
        raise GuardError("historical source integrity mismatch")
    reviewed = snapshot_from_live(
        doc["scene_id"], restored, data["source_acquired_at_utc"]
    )
    if reviewed["data"] != data or reviewed["source_digest_sha256"] != digest:
        raise GuardError("provider source fails independent truth review")
    return doc


def build_cleared(snapshot_path: Path, destination: Path) -> dict:
    doc = validate(snapshot_path)
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents or destination.exists():
        raise GuardError("candidate output must be new and outside repo")
    # A private candidate build cannot touch venture/private-company folders.
    import tempfile
    allowed = [Path(tempfile.gettempdir()).resolve()]
    if ROOT.parent.name == "_staging":
        allowed.append(ROOT.parent.resolve())
    else:
        allowed.append((ROOT.parent / "_staging").resolve())
    if not any(base == destination or base in destination.parents for base in allowed):
        raise GuardError("output must remain within isolated staging or temp")
    scene_id = doc["scene_id"]
    if not re.fullmatch(r"bridge-[a-z-]{4,28}", scene_id):
        raise GuardError("invalid scene ID")
    report = build(destination)
    destination.chmod(0o700)
    data_dir = destination / "data"
    catalogue = data_dir / "bridges.json"
    catalog_data = json.loads(catalogue.read_text())
    if scene_id not in [b["id"] for b in catalog_data["bridges"]]:
        raise GuardError("approved source does not map to a known brief")
    catalog_data["snapshot_ready"] = True
    catalog_data["snapshot_scene_id"] = scene_id
    catalog_data["provider_ready"] = False
    catalogue.write_text(json.dumps(catalog_data, indent=2) + "\n")
    snap_file = "snapshot." + scene_id + ".json"
    (data_dir / snap_file).write_text(
        json.dumps(doc["data"], indent=2, ensure_ascii=False) + "\n"
    )
    adapter = destination / "static-adapter.js"
    js = adapter.read_text()
    needle = "    if(url==='/api/bridge'){\n"
    if js.count(needle) != 1:
        raise GuardError("unexpected static router: abort")
    addition = (
        needle +
        "      if(exactKeys(body,['bridge_id','mode']) && body.mode==='snapshot' "
        "&& body.bridge_id===" + json.dumps(scene_id) + ")\n"
        "        return local(" + json.dumps(snap_file) + ");\n"
    )
    js = js.replace(needle, addition)
    adapter.write_text(js)
    html = destination / "index.html"
    page = html.read_text()
    old = re.search(r'<aside class="offline-banner".*?</aside>', page, re.S)
    if not old:
        raise GuardError("missing source provenance warning")
    banner = (
        '<aside class="offline-banner" role="note"><strong>HISTORICAL '
        'QLOO SOURCE SNAPSHOT — NOT LIVE.</strong> Only one approved brief '
        'uses previously acquired Qloo data; all others are fictional. '
        'There are zero Qloo API calls per visitor. This snapshot is '
        'not vendor-signed, and venue facts must be checked independently.</aside>'
    )
    html.write_text(page.replace(old.group(0), banner, 1))
    (destination / "README.txt").write_text(
        "APPROVED SOURCE SNAPSHOT CANDIDATE, NOT PROOF OF DEPLOYMENT OR ENTRY.\n"
        "One historical, independently reviewed Qloo acquisition (3 GETs); "
        "no Qloo API traffic by site visitors.\n"
        "Other scenarios are explicitly fictional. Not sponsor-signed.\n"
        "Exact approved digest: " + doc["source_digest_sha256"] + "\n"
        "Source acquired UTC: " + doc["data"]["source_acquired_at_utc"] + "\n"
    )
    for file in destination.rglob("*"):
        if file.is_file() and any(marker in file.read_bytes() for marker in
                (b"QLOO_API_KEY=", b"X-Api-Key:", b"-----BEGIN PRIVATE KEY-----")):
            raise GuardError("secret-like content in candidate output")
    return {
        "status": "PRIVATE_CLEARED_SNAPSHOT_CANDIDATE_NOT_DEPLOYED",
        "scene_id": scene_id,
        "source_digest": doc["source_digest_sha256"],
        "source_acquired_at_utc": doc["data"]["source_acquired_at_utc"],
        "provider_calls_at_site_view": 0,
        "historical_source_reads": 3,
        "synthetic_other_scenes": 2,
        "source_files_built": len(report["files"]) + 1,
        "public_release_performed": False,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Construct an approved-source PRIVATE candidate only")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--target", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(build_cleared(args.source, args.target), indent=2))


if __name__ == "__main__":
    main()
