"""Compile an ORIGINAL, offline-only Qloo judge preview from source.

Synthetic cultural cases only. No public release, Qloo API key, sponsor request,
cloud deployment or payment. A genuine provider response is never generated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.webapp import catalogue, scene_request, select_scene
from src.taste_scout import offline_flow
from src.taste_bridge import bridge_catalogue, offline_bridge

STATIC_JS = r"""/* Strict static review adapter: only local generated SYNTHETIC JSON.
No backend, Qloo key, real API call, booking or external network. */
'use strict';
(()=>{
  const realFetch=window.fetch.bind(window);
  const allowedScenes=new Set(['jazz-new-york','jazz-tokyo','jazz-paris']);
  const allowedBridges=new Set(['bridge-new-york','bridge-tokyo','bridge-paris']);
  const rejected=(code,error)=>new Response(JSON.stringify({error}),
    {status:code,headers:{'Content-Type':'application/json'}});
  const exactKeys=(val,keys)=>val && typeof val==='object' &&
    !Array.isArray(val) &&
    Object.keys(val).sort().join('|')===keys.slice().sort().join('|');
  const local=(name)=>realFetch('./data/'+name,{cache:'no-store'});
  window.QLOO_STATIC_OFFLINE_ONLY=true;
  window.fetch=(url,options={})=>{
    if(typeof url!=='string' || !url.startsWith('/api/'))
      return Promise.resolve(rejected(403,'STATIC_EXTERNAL_FETCH_BLOCKED'));
    const method=(options.method||'GET').toUpperCase();
    if(method==='GET'){
      if(url==='/api/scenes')return local('scenes.json');
      if(url==='/api/bridges')return local('bridges.json');
      return Promise.resolve(rejected(404,'NOT_FOUND'));
    }
    if(method!=='POST')return Promise.resolve(rejected(405,'METHOD_NOT_ALLOWED'));
    let body;
    try{body=JSON.parse(options.body)}catch(_){
      return Promise.resolve(rejected(400,'INVALID_JSON'));
    }
    if(url==='/api/bridge'){
      if(!exactKeys(body,['bridge_id','mode']) ||
          body.mode!=='mock' || !allowedBridges.has(body.bridge_id))
        return Promise.resolve(rejected(422,'SYNTHETIC_ONLY'));
      return local('bridge.'+body.bridge_id+'.json');
    }
    if(url==='/api/execute'){
      if(!exactKeys(body,['scene_id','mode']) ||
          body.mode!=='mock' || !allowedScenes.has(body.scene_id))
        return Promise.resolve(rejected(422,'SYNTHETIC_ONLY'));
      return local('scene.'+body.scene_id+'.json');
    }
    return Promise.resolve(rejected(403,'UNSUPPORTED'));
  };
})();"""


def build(target: Path) -> dict:
    target = target.resolve()
    if target == ROOT or ROOT in target.parents:
        raise ValueError("static preview must not overwrite source repository")
    target.mkdir(parents=True, exist_ok=True)
    data = target / "data"
    data.mkdir(exist_ok=True)

    for filename in ("styles.css", "app.js"):
        shutil.copyfile(ROOT / "web" / filename, target / filename)
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    exact = {
        'href="/styles.css"': 'href="./styles.css"',
        'src="/app.js"': 'src="./app.js"',
    }
    for original, new in exact.items():
        if html.count(original) != 1:
            raise ValueError("unexpected website reference")
        html = html.replace(original, new)

    old = '<script defer src="./app.js"></script>'
    if html.count(old) != 1:
        raise ValueError("unexpected script entrypoint")
    html = html.replace(
        old,
        '<script defer src="./static-adapter.js"></script>\n  ' + old,
    )
    html = html.replace(
        "<main>",
        '<aside class="offline-banner" role="note"><strong>FICTIONAL JUDGE REPLAY ONLY.</strong> '
        'No live Qloo API, personal data, venue booking or measured shared-taste fit. '
        'The authentic sponsor integration remains gated pending verified event '
        'quota, expiration and no-billing terms.</aside>\n    <main>',
        1,
    )
    (target / "index.html").write_text(html, encoding="utf-8")
    (target / "static-adapter.js").write_text(STATIC_JS, encoding="utf-8")
    with (target / "styles.css").open("a", encoding="utf-8") as f:
        f.write(
            "\n.offline-banner{background:#173932;color:#d8f5e8;"
            "border-bottom:1px solid #587d68;padding:13px 28px;"
            "font-size:12px;line-height:1.6}\n"
        )

    def put(name: str, item: dict):
        if not re.fullmatch(r"[a-z0-9.-]{5,100}", name):
            raise ValueError("invalid static data filename")
        (data / name).write_text(
            json.dumps(item, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    scenes = catalogue()
    bridges = bridge_catalogue()
    if len(scenes) != 3 or len(bridges) != 3:
        raise ValueError("original scenario catalogue changed")
    put("scenes.json", {
        "scenes":scenes, "provider_ready":False, "live_call_count":0,
        "source":"ORIGINAL SYNTHETIC OFFLINE DEMO",
    })
    put("bridges.json", {
        "bridges":bridges, "provider_ready":False, "live_call_count":0,
        "event_key_exposed":False, "source":"ORIGINAL SYNTHETIC OFFLINE DEMO",
    })
    for scene in scenes:
        s = select_scene(scene["id"])
        response = offline_flow(scene_request(s), s["replay"])
        response["scene_id"] = s["id"]
        response["brief"] = {
            "city":s["city"], "interest_artist":s["artist"],
            "mission":s["mission"],
        }
        if response["provider_verified"] or response["mode"] != "SYNTHETIC_FIXTURE_NO_API_CALL":
            raise ValueError("single artist static response is not synthetic")
        put("scene."+s["id"]+".json",response)
    for bridge in bridges:
        answer = offline_bridge(bridge["id"])
        if (answer["provider_verified"] or answer["provider_api_calls"]
                or answer["mode"] != "SYNTHETIC_BRIDGE_REPLAY_NO_API"):
            raise ValueError("cross-taste static response pretends live Qloo")
        if [p["source_coverage_count"] for p in answer["places"]] != [2,1,0]:
            raise ValueError("source coverage regression in offline response")
        put("bridge."+bridge["id"]+".json", answer)

    (target / "README.txt").write_text(
        "PRIVATE QLOO OFFLINE JUDGE PREVIEW. DO NOT PUBLISH OR SUBMIT AS LIVE INTEGRATION.\n"
        "Three fictional city / two-artist briefs, source coverage and human review.\n"
        "Original Python application includes a real-provider adapter that is NOT RUN HERE.\n"
        "Key issue, event quota, rate, expiry, free billing and actual provider result "
        "must be independently verified before any source-backed claims or contest submission.\n",
        encoding="utf-8",
    )
    files = [p for p in sorted(target.rglob("*")) if p.is_file()]
    for f in files:
        if any(bad in f.read_bytes() for bad in (
            b"QLOO_API_KEY=", b"Bearer sk-", b"-----BEGIN PRIVATE KEY-----",
            b"/Users/", b"/Volumes/",
        )):
            raise ValueError("possible secret or private path in preview")
    return {
        "status":"PRIVATE_SYNTHETIC_ONLY_NOT_PUBLISHED",
        "provider_api_calls":0,
        "key_in_bundle":False,
        "person_profile_in_bundle":False,
        "scenes":len(scenes),
        "bridges":len(bridges),
        "files":[{
            "path":str(p.relative_to(target)),
            "bytes":p.stat().st_size,
            "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
        } for p in files],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    print(json.dumps(build(Path(args.target)),indent=2))
