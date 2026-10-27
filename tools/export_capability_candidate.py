"""Export a rights-blocked portable capability candidate: hashes ONLY, no vendor output or private repo."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"capability"/"portable-manifest.v1.json"

def git(*args: str)->str:
    result=subprocess.run(["git","-C",str(ROOT),*args],capture_output=True,text=True,check=True)
    return result.stdout.strip()

def export(output: Path)->dict:
    output=output.expanduser().resolve()
    source=ROOT.resolve()
    if source==output or source in output.parents or output.exists():
        raise ValueError("Candidate output must be new and outside the source repository")
    if not (source.parent==output.parent or source.parent in output.parents):
        raise ValueError("Candidate output must be isolated beside the source worktree")
    if git("rev-parse","--show-toplevel")!=str(source):
        raise ValueError("Unexpected source git root")
    if git("status","--porcelain"):
        raise ValueError("Source has pending changes; commit and rerun checks first")
    origin=git("remote","get-url","origin")
    if not (origin.endswith("/MrShamann/qloo-neighborhood-taste-scout-2026-public.git") or
            origin.endswith(":MrShamann/qloo-neighborhood-taste-scout-2026-public.git")):
        raise ValueError("Unexpected source repository")
    m=json.loads(MANIFEST.read_text(encoding="utf-8"))
    if m["schema_version"]!="lab-portable-capability-candidate/1.0" or (
        m["transfer"]["automatic_import_enabled"] is not False or
        m["transfer"]["source_code_or_credentials_transfer"]!="NONE"):
        raise ValueError("Portability manifest fails transfer boundary")
    if not (ROOT/"LICENSE").read_text().startswith("MIT License"):
        raise ValueError("Original-source license unavailable")
    tracked=set(git("ls-files").splitlines())
    files=m["provenance"]["source_paths"]+m["provenance"]["test_paths"]+[
        "capability/portable-manifest.v1.json","LICENSE"]
    receipts=[]
    for relative in files:
        if relative not in tracked or ".." in Path(relative).parts:
            raise ValueError("Requested original file is not tracked")
        f=(ROOT/relative)
        if not f.is_file() or f.is_symlink():
            raise ValueError("Untrusted source artifact path")
        receipts.append({"path":relative,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()})
    item={
        "packet_type":"RIGHTS_BLOCKED_CAPABILITY_HARVEST_CANDIDATE",
        "schema_version":"1.0",
        "created_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "capability_id":m["capability_id"],
        "source_repository":m["provenance"]["public_repository"],
        "source_commit":git("rev-parse","HEAD"),
        "source_tree":git("rev-parse","HEAD^{tree}"),
        "source_file_sha256":receipts,
        "code_license":"MIT",
        "third_party_outputs":"NO_QLOO_API_RESPONSE_CONTENT_INCLUDED",
        "api_credentials":"NONE",
        "confidential_venture_data":"NONE",
        "transfer_status":"NO_TRANSFER_UNTIL_SEPARATE_RIGHTS_AND_INTERFACE_APPROVAL",
        "target_system_compatibility_verified":False,
        "source_digest_is_signature":False,
        "validation_required":["Rights holder's exact approval","Target contract audit",
          "Provider data/API license audit","Independent integration tests"]
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    data=(json.dumps(item,indent=2,sort_keys=True)+"\n").encode()
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(str(output),flags,0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    return {"capability_id":m["capability_id"],"source_commit":item["source_commit"],
       "source_tree":item["source_tree"],"files":len(receipts),
       "packet_sha256":hashlib.sha256(data).hexdigest(),
       "transfer_status":item["transfer_status"]}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="Create a private rights-blocked capability export receipt")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(export(args.output),sort_keys=True))
