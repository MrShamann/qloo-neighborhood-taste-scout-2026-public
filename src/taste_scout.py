"""Independent Qloo Taste AI agentic flow with sandbox-only synthetic inputs."""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

HOST = "https://hackathon.api.qloo.com"
SEARCH_PATH = "/search"
INSIGHTS_PATH = "/v2/insights"
ALLOWED_CITIES = {"New York", "Paris", "Tokyo", "Fukuoka"}
BANNED_MARKERS = ("@", "http://", "https://", "ignore previous", "system prompt", "real gps")
ENTITY_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MAX_RESPONSE = 196608


class GuardError(ValueError):
    pass


class DenyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # A redirect can leak the event API key to an unapproved host.
        raise GuardError("Qloo API redirect refused")


def guarded_qloo_fetcher():
    # Python.org macOS builds may ship without OpenSSL root certificates.
    # Use system-provided roots only; never turn off hostname verification.
    context=ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"]==0:
        ca=Path("/etc/ssl/cert.pem")
        if sys.platform!="darwin" or not ca.is_file():
            raise GuardError("verified certificate store unavailable")
        context=ssl.create_default_context(cafile=str(ca))
    if context.verify_mode!=ssl.CERT_REQUIRED or not context.check_hostname:
        raise GuardError("TLS verification required")
    if context.cert_store_stats()["x509_ca"]==0:
        raise GuardError("empty trust roots")
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        DenyRedirect(),
        urllib.request.HTTPSHandler(context=context),
    ).open


def valid_input(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"mode", "interest_artist", "city", "limit"}:
        raise GuardError("unexpected fields")
    if payload["mode"] != "synthetic_group":
        raise GuardError("only synthetic aggregate scenario permitted")
    artist, city, limit = payload["interest_artist"], payload["city"], payload["limit"]
    if not isinstance(artist, str) or not (2 <= len(artist) <= 60):
        raise GuardError("invalid interest")
    if any(s in artist.lower() for s in BANNED_MARKERS):
        raise GuardError("untrusted or identifying content")
    if not isinstance(city, str) or city not in ALLOWED_CITIES:
        raise GuardError("unsupported broad city; no personal location allowed")
    if type(limit) is not int or not (1 <= limit <= 5):
        raise GuardError("bounded limit required")
    return payload


def search_url(payload: dict) -> str:
    p = valid_input(payload)
    # Official Qloo Entity Search parameter is *types*, not type.
    # Source: qloo/docs-public/reference/get-search.md (2026-10-24).
    params = {"query": p["interest_artist"], "types":"urn:entity:artist",
              "take":3, "sort_by":"match"}
    return HOST + SEARCH_PATH + "?" + urllib.parse.urlencode(params)


def _search_items(body: object) -> list:
    if not isinstance(body, dict):
        raise GuardError("search body invalid")
    if body.get("success") is False:
        raise GuardError("search explicitly unsuccessful")
    items = body.get("results", body.get("entities"))
    if not isinstance(items, list):
        raise GuardError("search results absent")
    return items


def resolve_artist(body: object, target: str) -> str:
    if not isinstance(target, str):
        raise GuardError("target invalid")
    matches = []
    for item in _search_items(body):
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        entity = item.get("entity_id", item.get("id"))
        if isinstance(name, str) and name.strip().casefold() == target.strip().casefold():
            listed_types = item.get("types")
            subtype = item.get("subtype")
            declared_type = item.get("type")
            # Official API entities may use generic type=urn:entity plus
            # subtype=urn:entity:artist. Reject explicitly contradictory types.
            if declared_type is not None and declared_type not in (
                    "urn:entity", "urn:entity:artist"):
                continue
            if listed_types is not None and (
                    type(listed_types) is not list or
                    "urn:entity:artist" not in listed_types):
                continue
            if subtype is not None and subtype != "urn:entity:artist":
                continue
            # A name and valid UUID cannot establish the Qloo entity class.
            # Require the source to explicitly assert artist type in at least
            # one of the documented type/subtype/types fields.
            has_artist_type = (
                declared_type == "urn:entity:artist" or
                subtype == "urn:entity:artist" or
                (type(listed_types) is list and
                 "urn:entity:artist" in listed_types))
            if not has_artist_type:
                continue
            if isinstance(entity,str) and ENTITY_ID_RE.fullmatch(entity):
                matches.append(entity)
    if len(set(matches)) != 1:
        raise GuardError("ambiguous or missing resolved artist; no inference")
    return matches[0]


def insights_url(payload: dict, entity_id: str) -> str:
    p = valid_input(payload)
    if not ENTITY_ID_RE.fullmatch(entity_id):
        raise GuardError("invalid Qloo entity ID")
    params = {
        "filter.type":"urn:entity:place",
        "signal.interests.entities":entity_id,
        "filter.location.query":p["city"],
        "filter.location.radius":0,
        "take":p["limit"],
        "feature.explainability":"true",
    }
    return HOST + INSIGHTS_PATH + "?" + urllib.parse.urlencode(params)


def read_insights(body: object, limit: int) -> list[dict]:
    if not isinstance(body,dict):
        raise GuardError("insights body invalid")
    if body.get("success") is False:
        raise GuardError("insights explicitly unsuccessful")
    items = body.get("results",{})
    if isinstance(items,dict):
        items = items.get("entities")
    if not isinstance(items,list):
        raise GuardError("insights list missing")
    result=[]
    seen=set()
    for item in items[:limit]:
        if not isinstance(item,dict):
            continue
        name = item.get("name")
        iid = item.get("entity_id", item.get("id"))
        if not isinstance(name,str) or not (1<=len(name)<=130):
            continue
        if not isinstance(iid,str) or not ENTITY_ID_RE.fullmatch(iid):
            continue
        if iid in seen:
            continue
        seen.add(iid)
        result.append({"name":name, "qloo_entity_id":iid,
                       "note":"group-level affinity signal, not an individual prediction.",
                       "rank":len(result)+1})
    return result


def offline_flow(payload: dict, replay: dict | None = None) -> dict:
    p=valid_input(payload)
    local=Path(__file__).resolve().parents[1]/"fixtures"/"mock_api.json"
    responses=json.loads(local.read_text()) if replay is None else replay
    if not isinstance(responses,dict) or set(responses)!={"search","insights"}:
        raise GuardError("invalid synthetic replay fixture")
    artist=resolve_artist(responses["search"],p["interest_artist"])
    choices=read_insights(responses["insights"],p["limit"])
    return {"mode":"SYNTHETIC_FIXTURE_NO_API_CALL","provider_verified":False,
            "selected_artist_id":artist,"city":p["city"],"places":choices,
            "human_confirmation_required":True,
            "agent_steps":[
                {"phase":"RESOLVE","tool":"Qloo /search (synthetic replay)","status":"MOCK"},
                {"phase":"GROUND","tool":"Qloo /v2/insights (synthetic replay)","status":"MOCK"},
                {"phase":"REVIEW","tool":"Entity ID + group-level safety checks","status":"PASS"}
            ],
            "limits":["All place names are fictional fixtures.",
                      "No personal preferences, GPS, or identity was submitted.",
                      "No Qloo API call was made."]}


def live_flow(payload: dict, fetcher:Callable|None=None) -> dict:
    p=valid_input(payload)
    key=os.environ.get("QLOO_API_KEY","")
    if not key or os.environ.get("QLOO_EVENT_QUOTA_APPROVED")!="YES":
        raise GuardError("hackathon Qloo key and free event quota clearance required")
    if (not isinstance(key,str) or not 12<=len(key)<=256 or not key.isascii()
        or any(ord(char)<33 or ord(char)>126 for char in key)):
        raise GuardError("invalid local event credential format")
    if fetcher is None:
        fetcher=guarded_qloo_fetcher()
    headers={"X-Api-Key":key,"Accept":"application/json"}
    url=search_url(p)
    artist=None
    places=[]
    trace=[]
    for phase in range(2):
        target=urllib.parse.urlsplit(url)
        if (target.scheme!="https" or target.netloc!="hackathon.api.qloo.com"
            or target.path not in {SEARCH_PATH,INSIGHTS_PATH}
            or target.username is not None or target.password is not None):
            raise GuardError("unapproved remote host")
        req=urllib.request.Request(url,method="GET",headers=headers)
        try:
            with fetcher(req,timeout=18) as raw:
                if getattr(raw,"status",200)!=200:
                    raise GuardError("Qloo request non-200 status")
                payload_bytes=raw.read(MAX_RESPONSE+1)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise GuardError("Qloo service unavailable; no provider result verified") from exc
        if len(payload_bytes)>MAX_RESPONSE:
            raise GuardError("Qloo response too large")
        try:
            response=json.loads(payload_bytes)
        except (ValueError,TypeError,UnicodeDecodeError) as exc:
            raise GuardError("Qloo non-JSON response") from exc
        if phase==0:
            artist=resolve_artist(response,p["interest_artist"])
            trace.append({"phase":"RESOLVE","tool":"Qloo /search","status":"LIVE"})
            url=insights_url(p,artist)
        else:
            places=read_insights(response,p["limit"])
            trace.append({"phase":"GROUND","tool":"Qloo /v2/insights","status":"LIVE"})
    if not places:
        raise GuardError("no supported Qloo insight; abstaining")
    trace.append({"phase":"REVIEW","tool":"Schema, IDs and aggregate claim gate","status":"PASS"})
    return {"mode":"QLOO_HACKATHON_API_LIVE","provider_verified":True,
            "selected_artist_id":artist,"city":p["city"],"places":places,
            "human_confirmation_required":True,
            "agent_steps":trace,
            "limits":["Qloo affinities are group-level, not individual facts.",
                      "Location is a chosen city, never live GPS.",
                      "Place opening hours and availability are not verified."]}


def fixture() -> dict:
    root=Path(__file__).resolve().parents[1]
    return json.loads((root/"fixtures"/"group_request.json").read_text())
