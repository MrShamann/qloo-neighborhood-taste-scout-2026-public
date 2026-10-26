"""Offline-only clearance builder tests; artificial sources are NOT sponsor proof."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.source_snapshot import snapshot_from_live, CACHED_TRUTH
from src.taste_bridge import offline_bridge, LIVE_TRUTH
from src.taste_scout import GuardError
from tools.build_cleared_source_site import build_cleared, validate, FLAGS

SCENE = "bridge-new-york"
TIME = "2026-10-26T06:00:00Z"


def synthetic_renamed_test_doc():
    # Deliberately forged live-shaped object for validator/unit tests ONLY.
    fake = copy.deepcopy(offline_bridge(SCENE))
    fake["mode"] = LIVE_TRUTH
    fake["provider_verified"] = True
    fake["provider_api_calls"] = 3
    for step in fake["agent_steps"][:3]:
        step["status"] = "LIVE"
    for place in fake["places"]:
        place["name"] = place["name"].removeprefix("Fictional ")
    doc = snapshot_from_live(SCENE, fake, TIME)
    doc["distribution_license_checked"] = True  # TEST ONLY, never actual permission
    assert doc["published"] is False  # keep actual unpublished state
    return doc


def write_test_doc(where, doc):
    where.write_text(json.dumps(doc))
    where.chmod(0o600)


class StrictSnapshotBuildTests(unittest.TestCase):
    def test_without_explicit_gates_neither_source_nor_output_accessed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/"missing.json"
            target=root/"never-created"
            with patch.dict(os.environ,{},clear=True), self.assertRaises(GuardError):
                build_cleared(source,target)
            self.assertFalse(target.exists())

    def test_missing_each_gate_denied_before_filesystem_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/"candidate.json"
            doc=synthetic_renamed_test_doc()
            write_test_doc(source,doc)
            all_flags={key:"YES" for key in FLAGS}
            all_flags["QLOO_SOURCE_DIGEST_APPROVED"]=doc["source_digest_sha256"]
            for key in FLAGS:
                setting=dict(all_flags)
                setting[key]="NO"
                dest=root/("blocked-"+key)
                with self.subTest(key=key),patch.dict(os.environ,setting,clear=True):
                    with self.assertRaises(GuardError):
                        build_cleared(source,dest)
                    self.assertFalse(dest.exists())

    def test_source_mutation_and_rights_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/"candidate.json"
            doc=synthetic_renamed_test_doc()
            flags={key:"YES" for key in FLAGS}
            flags["QLOO_SOURCE_DIGEST_APPROVED"]=doc["source_digest_sha256"]
            for mutation in ("digest","missing_license","fake_published","fake_name","per_view_live"):
                candidate=copy.deepcopy(doc)
                if mutation=="digest":
                    candidate["source_digest_sha256"]="0"*64
                elif mutation=="missing_license":
                    candidate["distribution_license_checked"]=False
                elif mutation=="fake_published":
                    candidate["published"]=True
                elif mutation=="fake_name":
                    candidate["data"]["places"][0]["name"]="Tampered Venue"
                else:
                    candidate["data"]["source_data_is_live_per_request"]=True
                write_test_doc(source,candidate)
                dest=root/("blocked-"+mutation)
                with self.subTest(mutation=mutation),patch.dict(os.environ,flags,clear=True):
                    with self.assertRaises(GuardError):
                        build_cleared(source,dest)
                    self.assertFalse(dest.exists())

    def test_positive_approved_shape_stays_private_and_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/"artificial-test-only.json"
            doc=synthetic_renamed_test_doc()
            write_test_doc(source,doc)
            dest=root/"private-test-site"
            flags={key:"YES" for key in FLAGS}
            flags["QLOO_SOURCE_DIGEST_APPROVED"]=doc["source_digest_sha256"]
            with patch.dict(os.environ,flags,clear=True):
                result=build_cleared(source,dest)
            self.assertEqual(result["provider_calls_at_site_view"],0)
            self.assertEqual(result["historical_source_reads"],3)
            self.assertFalse(result["public_release_performed"])
            self.assertEqual(dest.stat().st_mode&0o777,0o700)
            catalog=json.loads((dest/"data/bridges.json").read_text())
            self.assertEqual(catalog["snapshot_scene_id"],SCENE)
            self.assertTrue(catalog["snapshot_ready"])
            self.assertFalse(catalog["provider_ready"])
            raw=(dest/"data/snapshot.bridge-new-york.json").read_text()
            self.assertEqual(json.loads(raw)["mode"],CACHED_TRUTH)
            self.assertNotIn("QLOO_API_KEY=",raw)
            self.assertIn("body.mode==='snapshot'",(dest/"static-adapter.js").read_text())
            self.assertIn("NOT LIVE",(dest/"index.html").read_text())
            self.assertIn("not vendor-signed",(dest/"index.html").read_text())
            self.assertTrue((dest/"data/bridge.bridge-new-york.json").is_file())

    def test_source_path_inside_repo_never_cleared(self):
        from tools.build_judge_site import ROOT
        with tempfile.TemporaryDirectory() as folder:
            env={key:"YES" for key in FLAGS}
            env["QLOO_SOURCE_DIGEST_APPROVED"]="0"*64
            with patch.dict(os.environ,env,clear=True),self.assertRaises(GuardError):
                validate(ROOT/"README.md")


if __name__=="__main__":
    unittest.main()
