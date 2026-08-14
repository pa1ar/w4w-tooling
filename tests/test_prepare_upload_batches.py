import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "OSM"))

from prepare_upload_batches import (  # noqa: E402
    select_live_gaps,
    split_schedule,
    write_outputs,
)


class PrepareUploadBatchesTests(unittest.TestCase):
    def test_filters_current_tags_and_missing_ways_then_sorts_safest_first(self):
        candidates = [
            self.candidate(1, "residential", "intermediate", 4, 95),
            self.candidate(2, "path", "bad", 3, 90),
            self.candidate(3, "footway", "intermediate", 2, 80),
            self.candidate(4, "cycleway", "intermediate", 5, 99),
            self.candidate(5, "path", "intermediate", 5, 99),
        ]
        live = {
            1: self.live(1),
            2: self.live(2),
            3: self.live(3, smoothness="good"),
            4: self.live(4),
        }

        eligible, tagged, missing = select_live_gaps(candidates, live)

        self.assertEqual([row["way_id"] for row in eligible], [4, 2, 1])
        self.assertEqual(tagged[0]["way_id"], 3)
        self.assertEqual(missing, [5])
        self.assertTrue(all(row["upload_allowed"] is False for row in eligible))

    def test_first_batch_is_100_and_remainder_is_balanced(self):
        candidates = [{"way_id": way_id} for way_id in range(311)]
        dates = tuple(f"date-{index}" for index in range(8))

        batches = split_schedule(candidates, dates, 100)

        self.assertEqual([len(items) for _, items in batches], [100, 31, 30, 30, 30, 30, 30, 30])
        self.assertEqual(sum(len(items) for _, items in batches), 311)

    def test_outputs_are_explicitly_blocked_and_include_a_changeset_column(self):
        candidate = {
            **self.candidate(8, "path", "intermediate", 3, 100),
            "dominant_class": "good",
            "bad_run_m": 0,
            "observed_version": 2,
            "observed_changeset_id": 12,
            "observed_timestamp": "2026-08-14T00:00:00Z",
            "observed_smoothness": None,
            "status": "needs_pipeline_validation",
            "upload_allowed": False,
            "uploaded_at": None,
            "changeset_id": None,
            "changeset_url": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            summary = write_outputs(
                output_dir,
                Path("source.csv"),
                "2026-08-14T00:00:00Z",
                1,
                [("2026-08-14", [candidate])],
                [],
                [],
            )

            manifest = (output_dir / "batch-01-2026-08-14.json").read_text()
            ledger = (output_dir / "upload_ledger.md").read_text()
            self.assertFalse(summary["upload_allowed"])
            self.assertIn('"upload_allowed": false', manifest)
            self.assertIn("| Status | Changeset |", ledger)

    @staticmethod
    def candidate(way_id, highway, proposal, rides, coverage):
        return {
            "way_id": way_id,
            "highway": highway,
            "proposed_value": proposal,
            "coverage_pct": coverage,
            "rides": rides,
            "dominant_share_pct": 100,
            "mean_match_distance_m": 0,
        }

    @staticmethod
    def live(way_id, smoothness=None):
        tags = {} if smoothness is None else {"smoothness": smoothness}
        return {
            "id": way_id,
            "version": 7,
            "changeset": 123,
            "timestamp": "2026-08-14T00:00:00Z",
            "tags": tags,
        }


if __name__ == "__main__":
    unittest.main()
