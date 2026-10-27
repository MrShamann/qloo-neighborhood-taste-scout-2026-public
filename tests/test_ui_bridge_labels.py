"""Regression: the public interface must identify its real Qloo workflow consistently."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/"web/index.html").read_text()
JS=(ROOT/"web/app.js").read_text()
BUILDER=(ROOT/"cloudflare/build_public_assets.py").read_text()

class TwoArtistUiLabelTests(unittest.TestCase):
    def test_section_one_is_discoverable_by_name(self):
        self.assertIn("01 / TWO-ARTIST BRIDGE", HTML)
        self.assertIn('id="bridge-run"',HTML)
        self.assertIn("Run two-artist evidence audit",HTML)
        self.assertIn("Run LIVE Qloo evidence",JS)
        self.assertIn('byId("bridge-live").checked=doc.provider_ready===true',JS)

    def test_single_artist_is_explicitly_fictional(self):
        self.assertIn("02 / FICTIONAL SINGLE-TASTE COMPARISON",HTML)
        self.assertIn("Explore fictional taste signals",HTML)
        self.assertIn('id="live" disabled',HTML)
        self.assertIn('byId("live").disabled=true',JS)
        self.assertIn('byId("live").checked=false',JS)

    def test_absent_old_prekey_claims_and_matching_banner(self):
        self.assertNotIn("Official Qloo key delivered but not validated",HTML)
        self.assertNotIn("This preview uses fictional data, not live Qloo results.",HTML)
        self.assertIn("SECTION 01",BUILDER)
        self.assertIn("SECTION 02",BUILDER)
        self.assertIn("Section 02 is a fictional comparison",JS)

if __name__=="__main__":
    unittest.main()
