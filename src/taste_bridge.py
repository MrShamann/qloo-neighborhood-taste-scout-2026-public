"""Original, bounded dual-taste discovery agent for the Qloo contest.

Two independently resolved *public* artist entities -> a combined Qloo Insights
query -> cited place entities -> a human review. There are no profiles, devices,
GPS, personal names, bookings, payment calls, or third-party AI gateways.

The local replay is fictional. A real result is labeled real ONLY after three
successfully validated reads from the Hackathon-specific Qloo API.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from .taste_scout import (
    HOST, ENTITY_ID_RE, GuardError, MAX_RESPONSE, guarded_qloo_fetcher,
    resolve_artist, search_url, valid_input,
)

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_FILE = ROOT / "fixtures" / "taste_bridges.json"
BRIDGE_TRUTH = "SYNTHETIC_BRIDGE_REPLAY_NO_API"
LIVE_TRUTH = "QLOO_HACKATHON_TWO_ARTIST_API_LIVE"
MAX_REMOTE_CALLS = 3


def bridge_catalogue() -> list[dict]:
    data=json.loads(BRIDGE_FILE.read_text(encoding="utf-8"))
    if not isinstance(data,dict) or set(data)!={"revision","bridges"}:
        raise GuardError("unsupported bridge catalogue")
    records=data["bridges"]
    if not isinstance(records,list) or not 1<=len(records)<=5:
        raise GuardError("unsupported bridge count")
    ids=[]
    safe=[]
    for row in records:
        if not isinstance(row,dict) or set(row)!={
                "id","name","city","artists","objective","replay"}:
            raise GuardError("bridge fixture fields invalid")
        if (not isinstance(row["id"],str) or
            not re.fullmatch(r"[a-z0-9-]{5,44}",row["id"])):
            raise GuardError("invalid bridge handle")
        artists=row["artists"]
        if (not isinstance(artists,list) or len(artists)!=2 or
            any(not isinstance(s,str) for s in artists) or
            artists[0].casefold()==artists[1].casefold()):
            raise GuardError("two independent artists required")
        for name in artists:
            valid_input({"mode":"synthetic_group","interest_artist":name,
                         "city":row["city"],"limit":3})
        for field in ("name","objective"):
            if not isinstance(row[field],str) or not 8<=len(row[field])<=200:
                raise GuardError("invalid public bridge description")
        ids.append(row["id"])
        safe.append({key:row[key] for key in (
            "id","name","city","artists","objective")})
    if len(set(ids))!=len(ids):
        raise GuardError("duplicate bridge handles")
    return safe


def _private_bridge(bridge_id: str) -> dict:
    if not isinstance(bridge_id,str) or not re.fullmatch(r"[a-z0-9-]{5,44}",bridge_id):
        raise GuardError("unsupported bridge id")
    catalogue=bridge_catalogue()
    matches=[row for row in catalogue if row["id"]==bridge_id]
    if len(matches)!=1:
        raise GuardError("unknown curated cultural brief")
    original=json.loads(BRIDGE_FILE.read_text(encoding="utf-8"))
    return next(row for row in original["bridges"] if row["id"]==bridge_id)


def _extract_explainability(item: dict, resolved_ids: list[str]) -> list[dict]:
    """Only expose explicitly ID-bound scores, never infer reasons from names.

    The public API documents query.explainability but may change the internal
    shape. Unknown shapes return zero contributions, not invented attribution.
    """
    query=item.get("query")
    if not isinstance(query,dict):
        return []
    explain=query.get("explainability")
    if not isinstance(explain,dict):
        return []
    entries=explain.get("signal.interests.entities")
    if not isinstance(entries,list):
        return []
    accepted=[]
    for entry in entries[:8]:
        if not isinstance(entry,dict):
            continue
        entity=entry.get("entity_id")
        score=entry.get("score")
        if (entity not in resolved_ids or
            isinstance(score,bool) or not isinstance(score,(int,float)) or
            not 0<=score<=1):
            continue
        if entity in [e["entity_id"] for e in accepted]:
            continue
        accepted.append({"entity_id":entity,"score":round(float(score),3)})
    return accepted


def _normalize_places(body: object, expected_ids: list[str], limit: int,
                      must_be_fictional: bool) -> list[dict]:
    if not isinstance(body,dict) or body.get("success") is False:
        raise GuardError("invalid Qloo Insights response")
    values=body.get("results")
    if isinstance(values,dict):
        values=values.get("entities")
    if not isinstance(values,list) or len(values)>200:
        raise GuardError("Qloo Insights entity list missing or excessive")
    seen=set()
    rows=[]
    for item in values:
        if len(rows)>=limit:
            break
        if not isinstance(item,dict):
            continue
        # Official Qloo examples use type=urn:entity + subtype=urn:entity:place.
        # Some event/legacy fixtures use type=urn:entity:place directly.
        # Unclassified or self-contradictory source records are never venues.
        declared_type=item.get("type")
        subtype=item.get("subtype")
        declared_types=item.get("types")
        if declared_types is not None and (
                not isinstance(declared_types,list) or
                "urn:entity:place" not in declared_types):
            continue
        if subtype is not None and subtype!="urn:entity:place":
            continue
        if declared_type=="urn:entity:place":
            pass
        elif declared_type=="urn:entity":
            if subtype is None and declared_types is None:
                continue
        elif declared_type is None:
            if subtype is None and declared_types is None:
                continue
        else:
            continue
        name=item.get("name")
        entity=item.get("entity_id",item.get("id"))
        if (not isinstance(name,str) or not 1<=len(name)<=130 or
            not isinstance(entity,str) or not ENTITY_ID_RE.fullmatch(entity)):
            continue
        if must_be_fictional and not name.startswith("Fictional "):
            raise GuardError("synthetic fixture contains unlabeled place")
        if entity in seen:
            continue
        seen.add(entity)
        contributions=_extract_explainability(item,expected_ids)
        # Count the EXACT input entity IDs in a source-provided explanation.
        # This checks trace coverage, NOT audience fit, harmony or usefulness.
        source_ids={ref["entity_id"] for ref in contributions}
        coverage=len(source_ids)
        assert 0<=coverage<=2
        # Deliberately an evidence triage, NOT a recommendation or fit score.
        # A missing per-place explanation never becomes a dual-taste claim.
        decision=(
            "SOURCE_VALUES_FOR_BOTH_REVIEW_ONLY" if coverage==2 else
            "SECOND_INTEREST_NOT_EVIDENCED" if coverage==1 else
            "ABSTAIN_NO_INTEREST_ATTRIBUTION")
        rows.append({
            "name":name,
            "entity_id":entity,
            "rank":len(rows)+1,
            "source_explainability":contributions,
            "source_attribution_state":(
                "EXPLICIT_SOURCE_VALUES_ONLY" if contributions
                else "UNAVAILABLE_NOT_INFERRED"),
            "source_coverage_count":coverage,
            "source_coverage_state":(
                "BOTH_EXPLICIT_INPUT_IDS" if coverage==2 else
                "ONE_EXPLICIT_INPUT_ID" if coverage==1 else
                "NO_INTEREST_ATTRIBUTION_PROVIDED"),
            "source_coverage_is_user_fit":False,
            "agent_decision":decision,
            "agent_decision_is_automatic_approval":False,
        })
    if not rows:
        raise GuardError("Qloo offered no usable place evidence")
    return rows


def _compose(scene: dict, ids: list[str], body: object, live: bool) -> dict:
    if len(ids)!=2 or len(set(ids))!=2 or any(
            not isinstance(x,str) or not ENTITY_ID_RE.fullmatch(x) for x in ids):
        raise GuardError("two independently resolved entities required")
    places=_normalize_places(body,ids,3,must_be_fictional=not live)
    return {
        "mode": LIVE_TRUTH if live else BRIDGE_TRUTH,
        "provider_verified": bool(live),
        "scene_id":scene["id"],
        "city":scene["city"],
        "artists": [
            {"artist":name,"source_entity_id":iid} for name,iid
            in zip(scene["artists"],ids)
        ],
        "places":places,
        "source_explainability_count":sum(
            bool(row["source_explainability"]) for row in places),
        "agent_steps":[
            {"phase":"RESOLVE_A","tool":"Qloo /search","status":"LIVE" if live else "MOCK"},
            {"phase":"RESOLVE_B","tool":"Qloo /search","status":"LIVE" if live else "MOCK"},
            {"phase":"GROUND_BOTH","tool":"Qloo /v2/insights","status":"LIVE" if live else "MOCK"},
            {"phase":"FACT_CHECK","tool":"Entity ID, source provenance and abstention gate","status":"PASS"},
            {"phase":"HUMAN_REVIEW","tool":"Human decides; never booking","status":"REQUIRED"},
        ],
        "provider_api_calls":3 if live else 0,
        "automatic_actions":0,
        "human_confirmation_required":True,
        "comparison":{
            "ungrounded_baseline":"ABSTAIN_FROM_NAMING_UNVERIFIED_PLACES",
            "unverified_place_names_allowed":0,
            "measured_user_benefit_proven":False,
            "cross_taste_lift_proven":False,
        },
        "limits":[
            "The two input artist names are public cultural entities, not personal profiles.",
            "A group-level affinity is not an individual prediction.",
            "Qloo entity rank is not proof of place opening hours or availability.",
            "Explainability is displayed only if explicit Qloo values are returned.",
        ],
    }


def offline_bridge(bridge_id: str) -> dict:
    scene=_private_bridge(bridge_id)
    replay=scene["replay"]
    if not isinstance(replay,dict) or set(replay)!={"searches","insights"}:
        raise GuardError("missing synthetic replay records")
    searches=replay["searches"]
    if not isinstance(searches,list) or len(searches)!=2:
        raise GuardError("two synthetic search results required")
    ids=[resolve_artist(response,name)
         for response,name in zip(searches,scene["artists"])]
    return _compose(scene,ids,replay["insights"],False)


def bridge_insights_url(city: str, ids: list[str], limit: int = 3) -> str:
    if (not isinstance(ids,list) or len(ids)!=2 or len(set(ids))!=2 or
        any(not isinstance(i,str) or not ENTITY_ID_RE.fullmatch(i) for i in ids)):
        raise GuardError("invalid multi-artist signal")
    valid_input({"mode":"synthetic_group","interest_artist":"Cultural taste",
                 "city":city,"limit":limit})
    # Official Qloo 2026 API docs: GET list of entity IDs is comma separated.
    params={
        "filter.type":"urn:entity:place",
        "signal.interests.entities":",".join(ids),
        "filter.location.query":city,
        "filter.location.radius":0,
        "take":limit,
        "feature.explainability":"true",
    }
    return HOST + "/v2/insights?" + urllib.parse.urlencode(params)


def _get_hackathon_json(url: str, key: str, fetcher: Callable) -> dict:
    parsed=urllib.parse.urlsplit(url)
    if (parsed.scheme!="https" or parsed.netloc!="hackathon.api.qloo.com"
        or parsed.path not in {"/search","/v2/insights"} or parsed.fragment):
        raise GuardError("disallowed egress endpoint")
    request=urllib.request.Request(url,headers={
        "X-Api-Key":key,"Accept":"application/json"},method="GET")
    try:
        with fetcher(request,timeout=18) as response:
            if getattr(response,"status",200)!=200:
                raise GuardError("Qloo did not return success")
            raw=response.read(MAX_RESPONSE+1)
    except (urllib.error.URLError,OSError,TimeoutError) as exc:
        raise GuardError("Qloo provider failed; no fallback recommendation") from exc
    if len(raw)>MAX_RESPONSE:
        raise GuardError("oversized Qloo response")
    try:
        value=json.loads(raw)
    except (TypeError,ValueError,UnicodeDecodeError) as exc:
        raise GuardError("invalid Qloo response format") from exc
    if not isinstance(value,dict):
        raise GuardError("Qloo source document was not an object")
    return value


def live_bridge(bridge_id: str, fetcher: Callable|None=None) -> dict:
    scene=_private_bridge(bridge_id)
    key=os.environ.get("QLOO_API_KEY","")
    if os.getenv("QLOO_EVENT_QUOTA_APPROVED")!="YES" or not key:
        raise GuardError("event key or verified no-spend quota unavailable")
    if (not isinstance(key,str) or not 12<=len(key)<=256 or not key.isascii()
        or any(not 33<=ord(ch)<=126 for ch in key)):
        raise GuardError("malformed event API credential")
    if fetcher is None:
        fetcher=guarded_qloo_fetcher()
    ids=[]
    for artist in scene["artists"]:
        request=valid_input({"mode":"synthetic_group","interest_artist":artist,
                            "city":scene["city"],"limit":3})
        body=_get_hackathon_json(search_url(request),key,fetcher)
        ids.append(resolve_artist(body,artist))
    if ids[0]==ids[1]:
        raise GuardError("two artists resolved to the same entity")
    body=_get_hackathon_json(
        bridge_insights_url(scene["city"],ids),key,fetcher)
    return _compose(scene,ids,body,True)
