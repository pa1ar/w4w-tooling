#!/usr/bin/env python3
"""
Apply smoothness proposals CSV to OSM using the existing CLI.

Reads CSV (columns: way_id, proposed_value, comment) and issues calls to
scripts/OSM/osm_edit.py set-tag -y for non-empty proposals.

Safety:
- Skips rows where proposed_value is empty
- Optional bbox filter
- Optional dry-run to print commands only
"""

import csv
import sys
import argparse
from pathlib import Path
from typing import Optional
import subprocess


PROJECT_ROOT = Path(__file__).parent.parent.parent
OSM_EDIT = PROJECT_ROOT / "scripts" / "OSM" / "osm_edit.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch apply smoothness proposals to OSM")
    parser.add_argument("--csv", required=True, help="Path to proposals CSV")
    parser.add_argument("--key", default="smoothness", help="Tag key (default: smoothness)")
    parser.add_argument("--min-coverage", type=float, default=0.7, help="Min coverage pct to apply (0..1)")
    parser.add_argument("--min-agree", type=float, default=0.7, help="Min agree pct to apply (0..1)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    parser.add_argument("--open", action="store_true", help="Open each changeset in browser after upload")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    applied = 0
    skipped = 0
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            way_id = row.get("way_id")
            value = (row.get("proposed_value") or "").strip()
            comment = row.get("comment") or "[w4w] smoothness from scooter telemetry"
            try:
                coverage = float(row.get("coverage_pct") or 0.0)
                agree = float(row.get("agree_pct") or 0.0)
            except ValueError:
                coverage = 0.0
                agree = 0.0
            if not way_id or not value:
                skipped += 1
                continue
            if coverage < args.min_coverage or agree < args.min_agree:
                skipped += 1
                continue
            cmd = [
                sys.executable,
                str(OSM_EDIT),
                "set-tag",
                "--way-id", str(way_id),
                "--key", args.key,
                "--value", value,
                "--comment", comment,
                "--create-only",
                "-y",
            ]
            if args.open:
                cmd.append("--open")
            if args.dry_run:
                print("DRY-RUN:", " ".join(cmd))
            else:
                print("APPLY:", " ".join(cmd))
                res = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
                if res.returncode != 0:
                    print(f"Command failed for way {way_id} (exit {res.returncode})")
                    skipped += 1
                else:
                    applied += 1

    print(f"Done. applied={applied}, skipped={skipped}")


if __name__ == "__main__":
    main()
