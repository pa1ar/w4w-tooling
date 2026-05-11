#!/usr/bin/env python3
"""
Export OSM smoothness proposals to JSON format for web app consumption.

Reads smoothness_proposals.csv and groups proposals by source_file and path_id,
creating a structured JSON file that the Next.js map popups can use.

This script assumes proposals CSV was generated from a single telemetry file.
To match proposals to specific paths, either:
1. Enhance OSM_smoothness_workflow.py to track path_id in proposals
2. Use spatial intersection between way geometries and path geometries
3. Process one path at a time and generate separate CSVs per path

For now, this script groups all proposals from a CSV under a single source_file.
"""

import json
import csv
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse





def parse_counts(counts_str: str) -> Dict[str, int]:
    """Parse counts JSON string into dict."""
    if not counts_str or counts_str.strip() == '':
        return {}
    try:
        return json.loads(counts_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def qualify_way(proposal: Dict[str, Any], min_confidence: float = 0.3) -> bool:
    """
    Determine if a way qualifies for tagging based on policy.

    Qualifies if:
    - coverage_pct >= 0.3 (30% coverage threshold)
    - confidence_wheelchair >= min_confidence (default 0.3 = 30% wheelchair confidence)
    - Either no existing smoothness tag OR proposed differs from existing

    Note: Using 0.3 as default confidence threshold since actual dataset values
    range 0.15-0.55, and we want to include meaningful proposals.
    """
    coverage = float(proposal.get('coverage_pct', 0) or 0)
    confidence = float(proposal.get('confidence_wheelchair', 0) or 0)
    existing = (proposal.get('existing_smoothness') or '').strip()
    proposed = (proposal.get('proposed_value') or '').strip()

    # Must meet coverage and confidence thresholds
    if coverage < 0.3 or confidence < min_confidence:
        return False

    # Must have a proposed value
    if not proposed:
        return False

    # If already tagged, only qualify if proposed differs
    if existing:
        return proposed.lower() != existing.lower()

    # No existing tag - qualifies
    return True


def load_path_ids(progress_path: Path) -> Dict[str, list[int]]:
    """Load mapping from source_file -> list[path_id] from gps_paths_progress.json."""
    if not progress_path.exists():
        return {}
    with open(progress_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    mapping: Dict[str, list[int]] = {}
    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            source = entry.get('source_file')
            path_id = entry.get('path_id')
            if source is None or path_id is None:
                continue
            mapping.setdefault(source, []).append(int(path_id))
    elif isinstance(data, dict):
        for source, info in data.items():
            if isinstance(info, dict) and 'path_id' in info:
                mapping.setdefault(source, []).append(int(info['path_id']))
    return mapping


def process_proposals_csv(
    csv_path: Path,
    source_file: str,
    min_confidence: float = 0.3,
    path_ids: list[int] | None = None,
) -> Dict[str, Any]:
    """
    Process proposals CSV and group by path_id.

    Returns dict structured as:
    {
        "source_file": {
            "path_id": {
                "summary": {...},
                "ways": [...]
            }
        }
    }

    Note: Currently assumes all proposals belong to path_id=0 or uses
    a single path. This should be enhanced to track actual path_id from
    the workflow.
    """
    result: Dict[str, Any] = {}

    if not csv_path.exists():
        print(f"Warning: CSV not found: {csv_path}")
        return result

    # Determine path IDs for this source (fall back to [0])
    path_id_list = path_ids or [0]
    path_proposals: Dict[int, List[Dict[str, Any]]] = {pid: [] for pid in path_id_list}
    if path_id_list and path_id_list[0] not in path_proposals:
        path_proposals[path_id_list[0]] = []

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Default to first path_id for this source (current dataset = 1 path per ride)
            path_id = path_id_list[0] if path_id_list else 0
            if path_id not in path_proposals:
                path_proposals[path_id] = []

            # Convert CSV row to structured proposal
            # Note: coverage_pct in CSV is already a decimal (0-1), confidence_wheelchair is also decimal (0-1)
            coverage_decimal = float(row.get('coverage_pct', 0) or 0)
            confidence_decimal = float(row.get('confidence_wheelchair', 0) or 0)

            proposal = {
                'wayId': int(row.get('way_id', 0)),
                'name': None,  # TODO: Fetch from OSM if needed
                'proposedSmoothness': (row.get('proposed_value') or '').strip(),
                'existingSmoothness': (row.get('existing_smoothness') or '').strip() or None,
                'coveragePct': round(coverage_decimal * 100, 1),  # Convert to percentage for display
                'confidencePct': round(confidence_decimal * 100, 1),  # Convert to percentage for display
                'counts': parse_counts(row.get('counts', '{}')),
                'osmMatch': None,
                'osmMatchPct': None,
            }

            # Parse osm_match and osm_match_pct if available
            osm_match_str = (row.get('osm_match') or '').strip().lower()
            if osm_match_str in ('true', '1', 'yes'):
                proposal['osmMatch'] = True
            elif osm_match_str in ('false', '0', 'no'):
                proposal['osmMatch'] = False

            osm_match_pct_str = row.get('osm_match_pct', '').strip()
            if osm_match_pct_str:
                try:
                    proposal['osmMatchPct'] = round(float(osm_match_pct_str) * 100, 1)
                except (ValueError, TypeError):
                    pass

            path_proposals[path_id].append(proposal)

    # Build result structure
    if source_file not in result:
        result[source_file] = {}

    for path_id, proposals in path_proposals.items():
        # Filter to qualifying ways only
        # Note: qualify_way expects coverage_pct and confidence_wheelchair as decimals (0-1)
        # but we stored them as percentages in the proposal dict, so convert back
        qualifying_ways = [p for p in proposals if qualify_way({
            'coverage_pct': p['coveragePct'] / 100.0,  # Convert percentage back to decimal
            'confidence_wheelchair': p['confidencePct'] / 100.0,  # Convert percentage back to decimal
            'existing_smoothness': p['existingSmoothness'] or '',
            'proposed_value': p['proposedSmoothness'],
        }, min_confidence=min_confidence)]

        if not qualifying_ways:
            continue

        # Calculate summary
        ways_count = len(qualifying_ways)
        avg_confidence = sum(w['confidencePct'] for w in qualifying_ways) / ways_count if ways_count > 0 else None

        result[source_file][str(path_id)] = {
            'summary': {
                'waysCount': ways_count,
                'avgConfidencePct': round(avg_confidence, 1) if avg_confidence is not None else None,
            },
            'ways': qualifying_ways,
        }

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Export OSM smoothness proposals to JSON for web app'
    )
    parser.add_argument(
        '--csv',
        type=str,
        required=True,
        help='Path to smoothness_proposals.csv'
    )
    parser.add_argument(
        '--source-file',
        type=str,
        required=True,
        help='Source telemetry file name (e.g., "258565038-580232.json")'
    )
    parser.add_argument(
        '--out',
        type=str,
        default='output/osm_smoothness_proposals.json',
        help='Output JSON file path'
    )
    parser.add_argument(
        '--merge',
        action='store_true',
        help='Merge with existing JSON file instead of overwriting'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.3,
        help='Minimum wheelchair confidence threshold (0-1, default: 0.3)'
    )
    parser.add_argument(
        '--gps-progress',
        type=str,
        default='output/gps_paths_progress.json',
        help='Path to gps_paths_progress.json for source->path_id lookup'
    )

    args = parser.parse_args()

    csv_path = Path(args.csv)
    source_file = args.source_file

    out_path = Path(args.out)

    # Load optional path_id mapping
    path_ids_map: Dict[str, list[int]] = {}
    if args.gps_progress:
        path_ids_map = load_path_ids(Path(args.gps_progress))
    selected_path_ids = path_ids_map.get(source_file)

    # Process CSV
    new_data = process_proposals_csv(
        csv_path,
        source_file,
        min_confidence=args.min_confidence,
        path_ids=selected_path_ids,
    )

    # Merge or overwrite
    if args.merge and out_path.exists():
        try:
            with open(out_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            # Remove schema/example keys if present
            existing_data = {k: v for k, v in existing_data.items() if not k.startswith('_')}
            # Merge new data
            for sf, paths in new_data.items():
                if sf in existing_data:
                    existing_data[sf].update(paths)
                else:
                    existing_data[sf] = paths
            result_data = existing_data
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not merge with existing file: {e}")
            result_data = new_data
    else:
        result_data = new_data

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)

    print(f"Exported proposals JSON: {out_path}")
    print(f"  Source file: {source_file}")
    source_paths = result_data.get(source_file, {})
    print(f"  Paths: {len(source_paths)}")
    total_ways = sum(len(p['ways']) for p in source_paths.values() if isinstance(p, dict) and 'ways' in p)
    print(f"  Total ways: {total_ways}")


if __name__ == '__main__':
    main()
