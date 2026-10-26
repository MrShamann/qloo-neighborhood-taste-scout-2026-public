"""Offline-only negative tests for a potential future source-backed Qloo snapshot.

An artificially relabeled synthetic result exercises the validator only.
It does NOT prove a Qloo request occurred, source attribution or public rights.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.source_snapshot import (
    CACHED_TRUTH, make_one_private_snapshot, snapshot_from_live
)
from src.taste_bridge import LIVE_TRUTH, offline_bridge
from src.taste_scout import GuardError

SCENE = "bridge-new-york"
TIMESTAMP = "2026-10-26T02:30:00Z"


def artificial_live_shape():
    """Artificial test shape; NEVER persist/claim it as provider evidence."""
    value = copy.deepcopy(offline_bridge(SCENE))
    value["mode"] = LIVE_TRUTH
    value["provider_verified"] = True
    value["provider_api_calls"] = 3
    for step in value["agent_steps"][:3]:
        step["status"] = "LIVE"
    for place in value["places"]:
        place["name"] = place["name"].removeprefix("Fictional ")
    return value


class SnapshotTruthValidationTests(unittest.TestCase):
    def test_artificial_positive_shape_remains_private_unverified_signed(self):
        fake = artificial_live_shape()
        out = snapshot_from_live(SCENE, fake, TIMESTAMP)
        self.assertEqual(out["scene_id"], SCENE)
        self.assertEqual(out["format"], "QLOO_PRIVATE_SOURCE_SNAPSHOT_V1")
        self.assertEqual(out["data"]["mode"], CACHED_TRUTH)
        self.assertFalse(out["data"]["source_data_is_live_per_request"])
        self.assertFalse(out["data"]["snapshot_is_sponsor_signed"])
        self.assertEqual(out["data"]["provider_api_calls"], 0)
        self.assertEqual(out["data"]["source_acquisition_calls"], 3)
        self.assertEqual(out["data"]["source_acquired_at_utc"], TIMESTAMP)
        self.assertFalse(out["distribution_license_checked"])
        self.assertFalse(out["published"])
        self.assertEqual(len(out["source_digest_sha256"]), 64)
        self.assertTrue(all(
            p["agent_decision_is_automatic_approval"] is False
            for p in out["data"]["places"]))

    def test_reject_offline_fixture_and_partial_provider_trace(self):
        original=offline_bridge(SCENE)
        with self.assertRaises(GuardError):
            snapshot_from_live(SCENE, original, TIMESTAMP)
        for value in (0, 1, 2, 4, True, "3"):
            with self.subTest(value=value):
                data=artificial_live_shape()
                data["provider_api_calls"]=value
                with self.assertRaises(GuardError):
                    snapshot_from_live(SCENE, data, TIMESTAMP)
        data=artificial_live_shape()
        data["agent_steps"][1]["status"]="MOCK"
        with self.assertRaises(GuardError):
            snapshot_from_live(SCENE, data, TIMESTAMP)

    def test_reject_private_fields_or_source_claim_switch(self):
        for key,val in (
            ("X-Api-Key","NEVER_REAL_KEY"),("prompt","ignore rules"),
            ("authorization","FAKE"),("source_contact","example@invalid.test")):
            with self.subTest(field=key):
                data=artificial_live_shape()
                data[key]=val
                with self.assertRaises(GuardError):
                    snapshot_from_live(SCENE,data,TIMESTAMP)
        for key,value in (("provider_verified",False),("mode","SYNTHETIC"),
                          ("automatic_actions",1),("human_confirmation_required",False),
                          ("scene_id","bridge-tokyo"),("city","Paris")):
            with self.subTest(field=key):
                data=artificial_live_shape()
                data[key]=value
                with self.assertRaises(GuardError):
                    snapshot_from_live(SCENE,data,TIMESTAMP)

    def test_reject_artist_references_inconsistent_with_original_brief(self):
        for operation in range(4):
            data=artificial_live_shape()
            if operation==0:
                data["artists"][0]["artist"]="Wrong Person"
            elif operation==1:
                data["artists"][1]["source_entity_id"]=data["artists"][0]["source_entity_id"]
            elif operation==2:
                data["artists"][0]["source_entity_id"]="not-an-entity"
            else:
                data["artists"][0]["unexpected_identifier"]="private"
            with self.subTest(operation=operation), self.assertRaises(GuardError):
                snapshot_from_live(SCENE,data,TIMESTAMP)

    def test_reject_place_fabrication_or_conflicting_coverage(self):
        mutations=[
            lambda d:d["places"][0].update(name="Fictional Not A Venue"),
            lambda d:d["places"][0].update(rank=99),
            lambda d:d["places"][1].update(entity_id=d["places"][0]["entity_id"]),
            lambda d:d["places"][0].update(source_coverage_count=1),
            lambda d:d["places"][1].update(source_coverage_state="BOTH_EXPLICIT_INPUT_IDS"),
            lambda d:d["places"][0].update(agent_decision="AUTOMATIC_APPROVED"),
            lambda d:d["places"][0].update(agent_decision_is_automatic_approval=True),
            lambda d:d["places"][0]["source_explainability"][0].update(score=float("nan")),
            lambda d:d["places"][0]["source_explainability"][0].update(score=1.5),
            lambda d:d["places"][0]["source_explainability"][0].update(score=0),
            lambda d:d["places"][0]["source_explainability"].append(
                dict(d["places"][0]["source_explainability"][0])),
            lambda d:d["places"][2].update(name=""),
            lambda d:d["places"][2].update(extra_key="hidden"),
            lambda d:d.update(source_explainability_count=0),
            lambda d:d.update(places=[]),
        ]
        for i, mutate in enumerate(mutations):
            data=artificial_live_shape()
            mutate(data)
            with self.subTest(case=i), self.assertRaises(GuardError):
                snapshot_from_live(SCENE,data,TIMESTAMP)

    def test_reject_wrong_agent_steps_and_oversized_source(self):
        operations=[
            lambda d:d.update(agent_steps=[]),
            lambda d:d["agent_steps"][2].update(status="MOCK"),
            lambda d:d["agent_steps"][3].update(status="SKIPPED"),
            lambda d:d["agent_steps"][4].update(status="AUTO_APPROVED"),
            lambda d:d["places"][0].update(name="A"*131),
        ]
        for i, mutation in enumerate(operations):
            data=artificial_live_shape()
            mutation(data)
            with self.subTest(case=i), self.assertRaises(GuardError):
                snapshot_from_live(SCENE,data,TIMESTAMP)

    def test_reject_invalid_source_times(self):
        for timestamp in (
            "", "2024-01-01T00:00:00Z", "2026-02-30T02:30:00Z",
            "2026-10-26 02:30:00", "2026-10-26T02:30:00+00:00",
            "2026-13-26T02:30:00Z", "2026-10-26T02:30:00Z\n",
        ):
            with self.subTest(t=timestamp), self.assertRaises(GuardError):
                snapshot_from_live(SCENE,artificial_live_shape(),timestamp)

    def test_no_live_call_when_event_approval_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"empty-private.json"
            for var in ("QLOO_EVENT_QUOTA_APPROVED",
                        "QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED",
                        "QLOO_LOCAL_PROBE_APPROVED"):
                base={s:"YES" for s in (
                    "QLOO_EVENT_QUOTA_APPROVED",
                    "QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED",
                    "QLOO_LOCAL_PROBE_APPROVED")}
                base[var]="NO"
                with self.subTest(var=var), patch.dict(os.environ,base):
                    with patch("src.taste_bridge.live_bridge",
                               side_effect=AssertionError("provider must not run")):
                        with self.assertRaises(GuardError):
                            make_one_private_snapshot(SCENE,target)
                    self.assertFalse(target.exists())

    def test_one_shot_budget_reserves_before_mocked_fetch_and_never_retries(self):
        """Artificial source fixture exercises private I/O, NEVER real Qloo."""
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            marker=root/"THREE_GETS_AT_MOST.marker"
            first=root/"fake_source_test_only.json"
            second=root/"must_not_exist.json"
            config={s:"YES" for s in (
                "QLOO_EVENT_QUOTA_APPROVED",
                "QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED",
                "QLOO_LOCAL_PROBE_APPROVED")}
            config["QLOO_PRIVATE_SINGLE_SHOT_MARKER"]=str(marker)
            config["QLOO_API_KEY"]="UNIT_TEST_FAKE_NEVER_SENT"
            def mocked_provider(_scene):
                self.assertTrue(marker.is_file(), "budget must exist before fetch")
                self.assertFalse(first.exists())
                record=json.loads(marker.read_text())
                self.assertEqual(record["maximum_authorized_get_requests"],3)
                return artificial_live_shape()
            with patch.dict(os.environ, config):
                with patch("src.taste_bridge.live_bridge",
                           side_effect=mocked_provider) as fake_fetch:
                    result=make_one_private_snapshot(SCENE,first)
                    self.assertEqual(fake_fetch.call_count,1)
                    self.assertTrue(result["single_shot_budget_marker_reserved"])
                    self.assertEqual(result["qloo_read_only_calls"],3)
                    self.assertEqual(json.loads(first.read_text())["published"],False)
                    self.assertEqual(first.stat().st_mode&0o777,0o600)
                    self.assertEqual(marker.stat().st_mode&0o777,0o600)
                    with self.assertRaises(GuardError):
                        make_one_private_snapshot(SCENE,second)
                    self.assertEqual(fake_fetch.call_count,1)
                    self.assertFalse(second.exists())

    def test_one_shot_failure_also_blocks_automatic_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            marker=root/"first_attempt.marker"
            out=root/"failed_attempt.json"
            env={s:"YES" for s in (
                "QLOO_EVENT_QUOTA_APPROVED",
                "QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED",
                "QLOO_LOCAL_PROBE_APPROVED")}
            env["QLOO_PRIVATE_SINGLE_SHOT_MARKER"]=str(marker)
            env["QLOO_API_KEY"]="UNIT_TEST_FAKE_NEVER_SENT"
            with patch.dict(os.environ,env):
                with patch("src.taste_bridge.live_bridge",
                           side_effect=RuntimeError("synthetic mock failed")) as call:
                    with self.assertRaisesRegex(RuntimeError,"synthetic"):
                        make_one_private_snapshot(SCENE,out)
                    self.assertTrue(marker.exists())
                    self.assertFalse(out.exists())
                    with self.assertRaises(GuardError):
                        make_one_private_snapshot(SCENE,out)
                    self.assertEqual(call.call_count,1)

    def test_private_cli_defaults_to_no_network_and_no_disk_mutation(self):
        import subprocess
        import sys
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"never-produced.json"
            marker=Path(folder)/"never-reserved.marker"
            env=os.environ.copy()
            for key in (
                "QLOO_API_KEY","QLOO_EVENT_QUOTA_APPROVED",
                "QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED",
                "QLOO_LOCAL_PROBE_APPROVED",
                "QLOO_PRIVATE_SINGLE_SHOT_MARKER"):
                env.pop(key,None)
            env["PYTHONPATH"]=str(root)
            command=[sys.executable,"-m","src.source_snapshot",
                     "--bridge",SCENE,"--output",str(target),
                     "--marker",str(marker)]
            r=subprocess.run(command,env=env,cwd=root,text=True,
                             capture_output=True,timeout=8)
            self.assertNotEqual(r.returncode,0)
            self.assertIn("gate",r.stderr)
            self.assertFalse(target.exists())
            self.assertFalse(marker.exists())
            self.assertEqual(r.stdout,"")

    def test_missing_key_does_not_burn_one_shot_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/"never.marker"
            target=Path(folder)/"never.json"
            env={s:"YES" for s in (
                "QLOO_EVENT_QUOTA_APPROVED",
                "QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED",
                "QLOO_LOCAL_PROBE_APPROVED")}
            env["QLOO_PRIVATE_SINGLE_SHOT_MARKER"]=str(marker)
            with patch.dict(os.environ,env,clear=True):
                with patch("src.taste_bridge.live_bridge",
                           side_effect=AssertionError("must not call provider")):
                    with self.assertRaises(GuardError):
                        make_one_private_snapshot(SCENE,target)
            self.assertFalse(marker.exists())
            self.assertFalse(target.exists())

    def test_never_write_into_source_repository_even_with_all_flags(self):
        repo=Path(__file__).resolve().parents[1]
        env={s:"YES" for s in (
            "QLOO_EVENT_QUOTA_APPROVED",
            "QLOO_SOURCE_PUBLICATION_RIGHTS_APPROVED",
            "QLOO_LOCAL_PROBE_APPROVED")}
        target=repo/"_absolutely_do_not_create_snapshot.json"
        self.assertFalse(target.exists())
        env["QLOO_API_KEY"]="UNIT_TEST_FAKE_NEVER_SENT"
        with patch.dict(os.environ,env), patch(
                "src.taste_bridge.live_bridge",
                side_effect=AssertionError("network must not run")):
            with self.assertRaises(GuardError):
                make_one_private_snapshot(SCENE,target)
        self.assertFalse(target.exists())


if __name__=="__main__":
    unittest.main()
