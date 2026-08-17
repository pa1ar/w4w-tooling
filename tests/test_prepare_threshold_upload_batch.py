import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts" / "OSM"))

from prepare_threshold_upload_batch import (  # noqa: E402
    refresh_unpublished_items,
    select_active_items,
    write_active_ledger,
)


class PrepareThresholdUploadBatchTests(unittest.TestCase):
    def test_selects_only_pushed_first_batch_and_next_24_pathways(self):
        items = [self.item(rank, "pushed") for rank in range(1, 101)]
        items.extend(self.item(rank) for rank in range(101, 125))
        items.append(self.item(125, highway="service"))

        published, next_items = select_active_items(items)

        self.assertEqual(len(published), 100)
        self.assertEqual([item["rank"] for item in next_items], list(range(101, 125)))
        self.assertTrue(all(item["highway"] == "path" for item in next_items))

    def test_live_refresh_refuses_a_new_smoothness_tag(self):
        item = self.item(101)
        with self.assertRaisesRegex(ValueError, "already has smoothness=good"):
            refresh_unpublished_items(
                [item],
                {item["way_id"]: self.live(item["way_id"], smoothness="good")},
            )

    def test_writes_two_batch_active_ledger(self):
        published = [self.item(rank, "pushed") for rank in range(1, 101)]
        next_items = [self.item(rank) for rank in range(101, 125)]
        manifests = {
            1: self.manifest(1, "2026-08-14", published),
            2: self.manifest(2, "2026-08-17", next_items),
        }
        geometries = {
            item["way_id"]: {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[24.7, 59.4], [24.8, 59.5]]},
                "properties": {"way_id": item["way_id"], "rank": item["rank"]},
            }
            for item in published + next_items
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "active"
            write_active_ledger(
                output,
                manifests,
                published,
                next_items,
                geometries,
                "2026-08-17T00:00:00Z",
                "2026-08-17",
            )
            summary = json.loads((output / "summary.json").read_text())
            batch_two = json.loads((output / "batch-02-2026-08-17.json").read_text())

        self.assertEqual(summary["active_candidates"], 124)
        self.assertEqual(summary["remaining_candidates"], 24)
        self.assertEqual(len(batch_two["items"]), 24)

    @staticmethod
    def item(rank, status="needs_pipeline_validation", highway="path"):
        return {
            "rank": rank,
            "way_id": 10_000 + rank,
            "highway": highway,
            "proposed_value": "bad",
            "confidence_tier": "high_confidence",
            "coverage_pct": 80,
            "rides": 2,
            "dominant_class": "bad",
            "dominant_share_pct": 80,
            "bad_run_m": 35,
            "mean_match_distance_m": 1,
            "observed_version": 1,
            "observed_smoothness": None,
            "status": status,
            "upload_allowed": False,
            "changeset_id": "123" if status == "pushed" else None,
            "changeset_url": "https://www.openstreetmap.org/changeset/123"
            if status == "pushed"
            else None,
        }

    @staticmethod
    def live(way_id, smoothness=None):
        tags = {"highway": "path"}
        if smoothness is not None:
            tags["smoothness"] = smoothness
        return {
            "id": way_id,
            "version": 2,
            "changeset": 456,
            "timestamp": "2026-08-17T00:00:00Z",
            "tags": tags,
        }

    @staticmethod
    def manifest(batch, date, items):
        return {
            "batch": batch,
            "planned_review_date": date,
            "generated_at": "2026-08-14T00:00:00Z",
            "status": "preflight_only",
            "upload_allowed": False,
            "items": items,
        }


if __name__ == "__main__":
    unittest.main()
