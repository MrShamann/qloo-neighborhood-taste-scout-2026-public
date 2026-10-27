"""Verify original portable capability contract without importing private platforms."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "capability" / "portable-manifest.v1.json"

class PortableCapabilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_unique_original_capability_and_no_automatic_transfer(self):
        m=self.manifest
        self.assertEqual(m["schema_version"],"lab-portable-capability-candidate/1.0")
        self.assertTrue(m["capability_id"].startswith("neighborhood-taste-scout."))
        self.assertEqual(m["lifecycle_state"],"ORIGINAL_CANDIDATE_NOT_TRANSFERRED")
        self.assertFalse(m["transfer"]["automatic_import_enabled"])
        self.assertFalse(m["transfer"]["private_system_dependency"])
        self.assertEqual(m["transfer"]["source_code_or_credentials_transfer"],"NONE")

    def test_code_rights_distinct_from_qloo_data_rights(self):
        m=self.manifest
        self.assertEqual(m["author"]["code_license"],"MIT")
        self.assertIn("not MIT-licensed",m["rights"]["external_api_data"])
        self.assertIn("NO_TRANSFER",m["transfer"]["state"])
        self.assertEqual(m["provider"]["maximum_reads_per_live_run"],3)
        self.assertEqual(m["provider"]["retries"],0)
        self.assertTrue(m["provider"]["fresh_result_per_live_run"])
        self.assertTrue(m["safety"]["human_review_required"])

    def test_contract_matches_executable_and_original_source_files(self):
        m=self.manifest
        c=m["invocation"]
        self.assertEqual(c["method"],"POST")
        self.assertEqual(c["relative_path"],"/api/bridge")
        inp=c["input_contract"]
        self.assertEqual(set(inp["required"]),{"bridge_id","mode"})
        self.assertFalse(inp["additionalProperties"])
        self.assertEqual(set(inp["properties"]["mode"]["enum"]),{"mock","live"})
        for rel in m["provenance"]["source_paths"]+m["provenance"]["test_paths"]:
            self.assertTrue((ROOT/rel).is_file(),rel)
            self.assertFalse((ROOT/rel).is_symlink(),rel)
        worker=(ROOT/"cloudflare/worker.mjs").read_text()
        for q in ("/api/bridge","/search","/v2/insights","QLOO_MAX_READS","authenticAgent"):
            self.assertIn(q,worker)

    def test_manifest_is_credential_free_and_has_no_private_reuse_claim(self):
        raw=MANIFEST.read_text()
        for forbidden in ("QLOO_API_KEY=","/Volumes/AI-Work/","/Users/","Asterion","YCE","YVIS","private_key"):
            self.assertNotIn(forbidden,raw)
        self.assertEqual(self.manifest["rights"]["first_party_code"],"MIT")
        self.assertTrue(self.manifest["safety"]["no_credential_or_vendor_result_in_export"])

if __name__=="__main__":
    unittest.main()
