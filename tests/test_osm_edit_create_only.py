import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "OSM"))

from osm_edit import ensure_create_only_allowed  # noqa: E402


class OsmEditCreateOnlyTests(unittest.TestCase):
    def test_allows_absent_tag(self):
        ensure_create_only_allowed(
            {"tag_present": False, "tag_value": None}, "smoothness"
        )

    def test_refuses_existing_tag_even_if_a_batch_would_auto_confirm(self):
        with self.assertRaisesRegex(ValueError, "create-only refused"):
            ensure_create_only_allowed(
                {"tag_present": True, "tag_value": "good"}, "smoothness"
            )


if __name__ == "__main__":
    unittest.main()
