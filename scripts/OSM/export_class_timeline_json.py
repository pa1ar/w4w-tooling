#!/usr/bin/env python3
"""
Export surface class timeline data for web charts.

This script exports data showing surface smoothness classification over time,
including confidence scores and speed context.
"""

import json
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional


def load_telemetry_data(telemetry_file: str) -> pd.DataFrame:
    """Load and process telemetry data from JSON file."""
    with open(telemetry_file, 'r') as f:
        data = json.load(f)

    ride_data = data['rideData']

    processed_data = []
    for item in ride_data:
        accel_coords = item.get('accelerationCoord', [])
        if len(accel_coords) >= 3:
            z_values = accel_coords[2::3]

            z_mean = np.mean(z_values) if z_values else np.nan
            z_std = np.std(z_values) if z_values else np.nan

            gps_info = item.get('gpsInfo', {})
            speed_kmh = gps_info.get('speed', 0) / 10.0  # raw unit: 1/10 km/h

            gps_pos = item.get('gpsPos', {})
            utc_date = gps_info.get('utcDate', '')
            utc_time = gps_info.get('utcTime', '')

            gps_datetime = None
            if utc_date and utc_time and len(utc_date) == 6 and len(utc_time) == 6:
                try:
                    day = utc_date[:2]
                    month = utc_date[2:4]
                    year = '20' + utc_date[4:6]
                    hour = utc_time[:2]
                    minute = utc_time[2:4]
                    second = utc_time[4:6]
                    gps_datetime = f"{year}-{month}-{day} {hour}:{minute}:{second}"
                except:
                    pass

            processed_data.append({
                'timestamp': int(item.get('timestamp', 0)),
                'gps_datetime': gps_datetime,
                'z_mean': z_mean,
                'z_std': z_std,
                'speed_kmh': speed_kmh,
                'gps_lat': gps_pos.get('gpsLat'),
                'gps_lon': gps_pos.get('gpsLon'),
            })

    df = pd.DataFrame(processed_data)
    if 'gps_datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['gps_datetime'])
    return df


def classify_smoothness(z_std: float) -> str:
    """Classify smoothness based on z_std value."""
    if pd.isna(z_std):
        return 'unknown'
    if z_std < 60:
        return 'excellent'
    elif z_std < 110:
        return 'good'
    elif z_std < 180:
        return 'intermediate'
    elif z_std < 250:
        return 'bad'
    else:
        return 'very_bad'


def calculate_wheelchair_confidence(z_std: float, speed_kmh: float) -> float:
    """Calculate wheelchair accessibility confidence."""
    thresholds = [60, 110, 180, 250]
    min_distance = min(abs(z_std - threshold) for threshold in thresholds)

    if min_distance < 10:
        base_confidence = 0.5 + (min_distance / 20)
    else:
        base_confidence = 1.0

    if speed_kmh == 0:
        speed_factor = 0.3
    elif 2 <= speed_kmh <= 6:
        speed_factor = 1.0
    elif speed_kmh > 10:
        speed_factor = 0.4
    elif speed_kmh > 6:
        speed_factor = 0.7
    else:
        speed_factor = 0.8

    return min(1.0, base_confidence * speed_factor)


def export_class_timeline_json(
    telemetry_file: str,
    out_path: Path,
    zoom_start: Optional[str] = "2025-05-26 13:08:00",
    zoom_end: Optional[str] = "2025-05-26 13:25:00"
) -> Path:
    """Export class timeline data for web charts."""

    df = load_telemetry_data(telemetry_file)

    if 'datetime' not in df.columns:
        raise ValueError("GPS datetime not available in telemetry data")

    # Default to entire dataset
    data = df.copy()
    used_start = df['datetime'].min()
    used_end = df['datetime'].max()

    if zoom_start and zoom_end:
        zoom_start_dt = pd.to_datetime(zoom_start)
        zoom_end_dt = pd.to_datetime(zoom_end)
        zoom_data = df[(df['datetime'] >= zoom_start_dt) & (df['datetime'] <= zoom_end_dt)].copy()
        if len(zoom_data) > 0:
            data = zoom_data
            used_start = zoom_start_dt
            used_end = zoom_end_dt
        else:
            print(
                "[export_class_timeline_json] Requested window has no samples, "
                "exporting entire dataset instead."
            )

    if len(data) == 0:
        raise ValueError("No samples available for export")

    data['cls_calc'] = data['z_std'].apply(classify_smoothness)
    data['wheelchair_confidence'] = data.apply(
        lambda row: calculate_wheelchair_confidence(row['z_std'], row['speed_kmh']),
        axis=1
    )

    samples = []
    for idx, row in data.iterrows():
        samples.append({
            'idx': int(idx),
            'ts': int(row['timestamp']) if pd.notna(row['timestamp']) else None,
            'datetime': row['datetime'].isoformat() if pd.notna(row['datetime']) else None,
            'z_std': float(row['z_std']) if pd.notna(row['z_std']) else None,
            'cls_calc': row['cls_calc'],
            'wheelchair_confidence': float(row['wheelchair_confidence']) if pd.notna(row['wheelchair_confidence']) else None,
            'speed_kmh': float(row['speed_kmh']) if pd.notna(row['speed_kmh']) else None,
            'lat': float(row['gps_lat']) if pd.notna(row['gps_lat']) else None,
            'lon': float(row['gps_lon']) if pd.notna(row['gps_lon']) else None,
        })

    export_data = {
        'meta': {
            'zoom_start': used_start.isoformat() if used_start is not None else zoom_start,
            'zoom_end': used_end.isoformat() if used_end is not None else zoom_end,
            'total_samples': len(samples),
            'export_timestamp': pd.Timestamp.now().isoformat()
        },
        'thresholds': {
            'excellent_max': 60,
            'good_max': 110,
            'intermediate_max': 180,
            'bad_max': 250
        },
        'samples': samples
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported class timeline data to: {out_path}")
    print(f"Total samples: {len(samples)}")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export class timeline JSON from telemetry")
    parser.add_argument("--input", default="example_data/258276934-579126.json", help="Telemetry JSON path")
    parser.add_argument("--out", default="output/class_timeline.json", help="Output JSON path")
    parser.add_argument("--zoom-start", default="2025-05-26 13:08:00", help="Window start datetime")
    parser.add_argument("--zoom-end", default="2025-05-26 13:25:00", help="Window end datetime")
    args = parser.parse_args()

    export_class_timeline_json(
        args.input,
        Path(args.out),
        zoom_start=args.zoom_start,
        zoom_end=args.zoom_end,
    )
