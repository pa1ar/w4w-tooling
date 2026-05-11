#!/usr/bin/env python3
"""
Generate OSM proposals JSON for all source files in gps_paths_colored.json.

Since we have proposals CSV for some files but not all, this script:
1. Reads gps_paths_colored.json to get all source files
2. Generates proposals JSON entries for files that have proposals CSV
3. Creates empty entries for files without proposals (to be populated later)

Usage:
    python scripts/OSM/generate_all_proposals_json.py \
        --gps-paths output/gps_paths_colored.json \
        --proposals-csv output/smoothness_proposals.csv \
        --source-file "258276934-579126.json" \
        --out output/osm_smoothness_proposals.json
"""

import json
import csv
import sys
from pathlib import Path
from typing import Dict, Any, Set
import argparse
from export_osm_proposals_json import process_proposals_csv


def get_all_source_files(gps_paths_json: Path) -> Set[str]:
    """Extract all unique source_file values from gps_paths_colored.json."""
    if not gps_paths_json.exists():
        print(f"Warning: GPS paths file not found: {gps_paths_json}")
        return set()

    with open(gps_paths_json, 'r', encoding='utf-8') as f:
        data = json.load(f)

    source_files = set()
    for feature in data.get('features', []):
        props = feature.get('properties', {})
        source_file = props.get('source_file')
        if source_file:
            source_files.add(source_file)

    return source_files


def main():
    parser = argparse.ArgumentParser(
        description='Generate OSM proposals JSON for all source files'
    )
    parser.add_argument(
        '--gps-paths',
        type=str,
        required=True,
        help='Path to gps_paths_colored.json'
    )
    parser.add_argument(
        '--proposals-csv',
        type=str,
        help='Path to smoothness_proposals.csv (optional, for files with proposals)'
    )
    parser.add_argument(
        '--source-file',
        type=str,
        help='Source file name for the proposals CSV (if provided)'
    )
    parser.add_argument(
        '--out',
        type=str,
        default='output/osm_smoothness_proposals.json',
        help='Output JSON file path'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.3,
        help='Minimum wheelchair confidence threshold (0-1, default: 0.3)'
    )

    args = parser.parse_args()

    gps_paths = Path(args.gps_paths)
    out_path = Path(args.out)

    # Get all source files from GPS paths
    all_source_files = get_all_source_files(gps_paths)
    print(f"Found {len(all_source_files)} source files in GPS paths")

    # Initialize result structure
    result_data: Dict[str, Any] = {}

    # Process proposals CSV if provided
    if args.proposals_csv and args.source_file:
        csv_path = Path(args.proposals_csv)
        if csv_path.exists():
            print(f"Processing proposals CSV for {args.source_file}...")
            proposals_data = process_proposals_csv(
                csv_path,
                args.source_file,
                min_confidence=args.min_confidence
            )
            result_data.update(proposals_data)
            source_paths = proposals_data.get(args.source_file, {})
            total_ways = sum(len(p['ways']) for p in source_paths.values() if isinstance(p, dict) and 'ways' in p)
            print(f"  Added {len(source_paths)} paths with {total_ways} ways")
        else:
            print(f"Warning: Proposals CSV not found: {csv_path}")

    # Create empty entries for other source files (so structure is consistent)
    # For now, we'll only include files that have proposals
    # Empty entries can be added later when proposals are generated

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)

    print(f"\nExported proposals JSON: {out_path}")
    print(f"  Files with proposals: {len(result_data)}")
    print(f"  Total source files in GPS paths: {len(all_source_files)}")
    if len(result_data) < len(all_source_files):
        print(f"  Note: {len(all_source_files) - len(result_data)} files don't have proposals yet")


if __name__ == '__main__':
    main()
