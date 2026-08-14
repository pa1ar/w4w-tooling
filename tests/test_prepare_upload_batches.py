import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "OSM"))

from prepare_upload_batches import (  # noqa: E402
    load_candidates,
    select_live_gaps,
    split_schedule,
    write_outputs,
)


class PrepareUploadBatchesTests(unittest.TestCase):
    def test_filters_current_tags_and_missing_ways_then_sorts_safest_first(self):
        candidates = [
            self.candidate(1, "residential", "intermediate", 4, 95, "high_confidence"),
            self.candidate(2, "path", "bad", 3, 90, "broad"),
            self.candidate(3, "footway", "intermediate", 2, 80, "high_confidence"),
            self.candidate(4, "cycleway", "intermediate", 5, 99, "high_confidence"),
            self.candidate(5, "path", "intermediate", 5, 99, "broad"),
        ]
        live = {
            1: self.live(1),
            2: self.live(2),
            3: self.live(3, smoothness="good"),
            4: self.live(4),
        }

        eligible, tagged, missing = select_live_gaps(candidates, live)

        self.assertEqual([row["way_id"] for row in eligible], [4, 1, 2])
        self.assertEqual(tagged[0]["way_id"], 3)
        self.assertEqual(missing, [5])
        self.assertTrue(all(row["upload_allowed"] is False for row in eligible))

    def test_first_batch_is_100_and_remainder_is_balanced(self):
        candidates = [{"way_id": way_id} for way_id in range(2398)]
        dates = tuple(f"date-{index}" for index in range(8))

        batches = split_schedule(candidates, dates, 100)

        self.assertEqual(
            [len(items) for _, items in batches],
            [100, 329, 329, 328, 328, 328, 328, 328],
        )
        self.assertEqual(sum(len(items) for _, items in batches), 2398)

    def test_outputs_are_explicitly_blocked_and_include_a_changeset_column(self):
        candidate = {
            **self.candidate(8, "path", "intermediate", 3, 100, "high_confidence"),
            "dominant_class": "good",
            "bad_run_m": 0,
            "observed_version": 2,
            "observed_changeset_id": 12,
            "observed_timestamp": "2026-08-14T00:00:00Z",
            "observed_smoothness": None,
            "status": "needs_pipeline_validation",
            "upload_allowed": False,
            "operator_automation_approved": True,
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
                "potential",
                1,
                1,
                [("2026-08-14", [candidate])],
                [],
                [],
            )

            manifest = (output_dir / "batch-01-2026-08-14.json").read_text()
            ledger = (output_dir / "upload_ledger.md").read_text()
            self.assertFalse(summary["upload_allowed"])
            self.assertTrue(summary["operator_automation_approval"]["approved"])
            self.assertTrue(summary["operator_automation_approval"]["external_gates_still_required"])
            self.assertIn('"upload_allowed": false', manifest)
            self.assertIn("| Status | Changeset |", ledger)

    def test_broad_scope_keeps_potential_rows_and_marks_conservative_priority(self):
        csv_text = (
            "way_id,highway,existing_smoothness,coverage_pct,rides,dominant_class,"
            "dominant_share_pct,bad_run_m,proposed_value,potential,conservative,"
            "mean_match_distance_m\n"
            "10,path,,90,2,good,90,0,intermediate,True,True,1\n"
            "11,residential,,40,1,bad,100,35,bad,True,False,2\n"
            "12,footway,,20,1,good,100,0,intermediate,False,False,1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "candidates.csv"
            source.write_text(csv_text)
            candidates = load_candidates(source, "potential")

        self.assertEqual([row["way_id"] for row in candidates], [10, 11])
        self.assertEqual(
            [row["confidence_tier"] for row in candidates],
            ["high_confidence", "broad"],
        )

    @staticmethod
    def candidate(way_id, highway, proposal, rides, coverage, confidence_tier):
        return {
            "way_id": way_id,
            "highway": highway,
            "proposed_value": proposal,
            "confidence_tier": confidence_tier,
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
