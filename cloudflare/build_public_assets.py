"""Reproducible judge UI assets for Cloudflare Worker (never bundle credentials)."""
from __future__ import annotations
import sys
import shutil
from tempfile import TemporaryDirectory
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.build_judge_site import build
def main():
    target=ROOT/"cloudflare"/"public"
    if target.exists():
        raise RuntimeError("do not overwrite any prior candidate")
    with TemporaryDirectory(prefix="qloo-cf-private-assets-",dir=ROOT.parent) as stage:
        private_stage=Path(stage)/"preview"
        build(private_stage)
        shutil.copytree(private_stage,target)
    # The Worker handles /api; the static replay adapter must never intercept
    # live requests, even in local development.
    (target/"static-adapter.js").unlink()
    html=(ROOT/"web"/"index.html").read_text()
    html=html.replace("<main>",'<aside role="note" class="offline-banner">SECTION 01 — TWO-ARTIST BRIDGE is the live Qloo agent: select a brief, leave LIVE selected, then click Run LIVE Qloo evidence. SECTION 02 is a fictional single-artist comparison only. No personal histories, venue booking or payments.</aside><main>',1)
    (target/"index.html").write_text(html)
    assert "static-adapter.js" not in html
    print("PRIVATE_WORKER_ASSETS_READY",target)
if __name__=="__main__": main()
