#!/usr/bin/env python3
"""
Export rolling std comparison data for web charts.

This script exports data comparing original z_std vs rolling window z_std,
showing the noise reduction effect of rolling window smoothing.
"""

import json
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def load_telemetry_data(telemetry_file: str) -> pd.DataFrame:
    """Load and process telemetry data from JSON file."""
    with open(telemetry_file, 'r') as f:
        data = json.load(f)

    ride_data = data['rideData']

    processed_data = []
    for item in ride_data:
        accel_coords = item.get('accelerationCoord', [])
        if len(accel_coords) >= 3:
            z_values = accel_coords[2::3]  # Every 3rd value starting from 2

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


def calculate_rolling_std(z_values: List[float], window_size: int = 30) -> List[float]:
    """Calculate rolling standard deviation with centered window."""
    rolling_std = []
    for i in range(len(z_values)):
        start_idx = max(0, i - window_size // 2)
        end_idx = min(len(z_values), i + window_size // 2 + 1)
        window_data = z_values[start_idx:end_idx]

        if len(window_data) > 1:
            std_dev = np.std(window_data)
            rolling_std.append(std_dev)
        else:
            rolling_std.append(0.0)

    return rolling_std


def export_rolling_std_json(
    telemetry_file: str,
    out_path: Path,
    zoom_start: str = "2025-05-26 13:08:00",
    zoom_end: str = "2025-05-26 13:25:00",
    window_size: int = 30
) -> Path:
    """Export rolling std comparison data for web charts."""

    df = load_telemetry_data(telemetry_file)

    if 'datetime' not in df.columns:
        raise ValueError("GPS datetime not available in telemetry data")

    zoom_start_dt = pd.to_datetime(zoom_start)
    zoom_end_dt = pd.to_datetime(zoom_end)

    zoom_data = df[(df['datetime'] >= zoom_start_dt) & (df['datetime'] <= zoom_end_dt)].copy()
    used_start = zoom_start_dt
    used_end = zoom_end_dt

    if len(zoom_data) == 0:
        # Fall back to full dataset if the requested window does not exist in the sample file
        zoom_data = df.copy()
        used_start = df['datetime'].min()
        used_end = df['datetime'].max()
        print(
            f"[export_rolling_std_json] Requested window {zoom_start} – {zoom_end} "
            "has no samples, exporting entire dataset instead."
        )

    z_std_values = zoom_data['z_std'].fillna(0).tolist()
    z_rolling_std = calculate_rolling_std(z_std_values, window_size=window_size)

    zoom_data['z_rolling_std'] = z_rolling_std
    zoom_data['std_difference'] = zoom_data['z_std'] - zoom_data['z_rolling_std']

    samples = []
    for idx, row in zoom_data.iterrows():
        samples.append({
            'idx': int(idx),
            'ts': int(row['timestamp']) if pd.notna(row['timestamp']) else None,
            'datetime': row['datetime'].isoformat() if pd.notna(row['datetime']) else None,
            'z_std': float(row['z_std']) if pd.notna(row['z_std']) else None,
            'z_rolling_std': float(row['z_rolling_std']) if pd.notna(row['z_rolling_std']) else None,
            'std_difference': float(row['std_difference']) if pd.notna(row['std_difference']) else None,
            'speed_kmh': float(row['speed_kmh']) if pd.notna(row['speed_kmh']) else None,
        })

    export_data = {
        'meta': {
            'window_size': window_size,
            'zoom_start': used_start.isoformat() if used_start is not None else zoom_start,
            'zoom_end': used_end.isoformat() if used_end is not None else zoom_end,
            'total_samples': len(samples),
            'export_timestamp': pd.Timestamp.now().isoformat()
        },
        'samples': samples
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported rolling std comparison data to: {out_path}")
    print(f"Total samples: {len(samples)}")
    print(f"Window size: {window_size}")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export rolling std comparison JSON from telemetry")
    parser.add_argument("--input", default="example_data/258276934-579126.json", help="Telemetry JSON path")
    parser.add_argument("--out", default="output/smoothness_rolling.json", help="Output JSON path")
    parser.add_argument("--zoom-start", default="2025-05-26 13:08:00", help="Window start datetime")
    parser.add_argument("--zoom-end", default="2025-05-26 13:25:00", help="Window end datetime")
    parser.add_argument("--window-size", type=int, default=30, help="Rolling window size")
    args = parser.parse_args()

    export_rolling_std_json(
        args.input,
        Path(args.out),
        zoom_start=args.zoom_start,
        zoom_end=args.zoom_end,
        window_size=args.window_size,
    )
