#!/usr/bin/env python3
"""
Export filter comparison data for web charts.

This script exports data comparing different filtering methods:
- Original z_mean
- Moving average filtered
- Exponential smoothing filtered
"""

import json
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List


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


def simple_moving_average_filter(z_values: List[float], window_size: int = 5) -> List[float]:
    """Simple moving average filter."""
    if len(z_values) < window_size:
        return z_values

    filtered = []
    for i in range(len(z_values)):
        start_idx = max(0, i - window_size // 2)
        end_idx = min(len(z_values), i + window_size // 2 + 1)
        window_data = z_values[start_idx:end_idx]
        filtered.append(np.mean(window_data))

    return filtered


def exponential_smoothing_filter(z_values: List[float], alpha: float = 0.3) -> List[float]:
    """Exponential smoothing filter."""
    if not z_values:
        return z_values

    filtered = [z_values[0]]
    for i in range(1, len(z_values)):
        smoothed = alpha * z_values[i] + (1 - alpha) * filtered[i-1]
        filtered.append(smoothed)

    return filtered


def export_filter_comparison_json(
    telemetry_file: str,
    out_path: Path,
    zoom_start: str = "2025-05-26 13:08:00",
    zoom_end: str = "2025-05-26 13:25:00",
    moving_avg_window: int = 5,
    exp_smooth_alpha: float = 0.3
) -> Path:
    """Export filter comparison data for web charts."""

    df = load_telemetry_data(telemetry_file)

    if 'datetime' not in df.columns:
        raise ValueError("GPS datetime not available in telemetry data")

    zoom_start_dt = pd.to_datetime(zoom_start)
    zoom_end_dt = pd.to_datetime(zoom_end)

    zoom_data = df[(df['datetime'] >= zoom_start_dt) & (df['datetime'] <= zoom_end_dt)].copy()
    used_start = zoom_start_dt
    used_end = zoom_end_dt

    if len(zoom_data) == 0:
        zoom_data = df.copy()
        used_start = df['datetime'].min()
        used_end = df['datetime'].max()
        print(
            f"[export_filter_comparison_json] Requested window {zoom_start} – {zoom_end} "
            "has no samples, exporting entire dataset instead."
        )

    raw_z_means = zoom_data['z_mean'].fillna(0).tolist()

    moving_avg_filtered = simple_moving_average_filter(raw_z_means, window_size=moving_avg_window)
    exp_smoothed = exponential_smoothing_filter(raw_z_means, alpha=exp_smooth_alpha)

    zoom_data['z_mean_moving_avg'] = moving_avg_filtered
    zoom_data['z_mean_exp_smooth'] = exp_smoothed

    zoom_data['moving_avg_diff'] = zoom_data['z_mean'] - zoom_data['z_mean_moving_avg']
    zoom_data['exp_smooth_diff'] = zoom_data['z_mean'] - zoom_data['z_mean_exp_smooth']

    samples = []
    for idx, row in zoom_data.iterrows():
        samples.append({
            'idx': int(idx),
            'ts': int(row['timestamp']) if pd.notna(row['timestamp']) else None,
            'datetime': row['datetime'].isoformat() if pd.notna(row['datetime']) else None,
            'z_mean': float(row['z_mean']) if pd.notna(row['z_mean']) else None,
            'z_mean_moving_avg': float(row['z_mean_moving_avg']) if pd.notna(row['z_mean_moving_avg']) else None,
            'z_mean_exp_smooth': float(row['z_mean_exp_smooth']) if pd.notna(row['z_mean_exp_smooth']) else None,
            'moving_avg_diff': float(row['moving_avg_diff']) if pd.notna(row['moving_avg_diff']) else None,
            'exp_smooth_diff': float(row['exp_smooth_diff']) if pd.notna(row['exp_smooth_diff']) else None,
            'z_std': float(row['z_std']) if pd.notna(row['z_std']) else None,
            'speed_kmh': float(row['speed_kmh']) if pd.notna(row['speed_kmh']) else None,
        })

    export_data = {
        'meta': {
            'zoom_start': used_start.isoformat() if used_start is not None else zoom_start,
            'zoom_end': used_end.isoformat() if used_end is not None else zoom_end,
            'moving_avg_window': moving_avg_window,
            'exp_smooth_alpha': exp_smooth_alpha,
            'total_samples': len(samples),
            'export_timestamp': pd.Timestamp.now().isoformat()
        },
        'samples': samples
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported filter comparison data to: {out_path}")
    print(f"Total samples: {len(samples)}")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export filter comparison JSON from telemetry")
    parser.add_argument("--input", default="example_data/258276934-579126.json", help="Telemetry JSON path")
    parser.add_argument("--out", default="output/mean_filters.json", help="Output JSON path")
    parser.add_argument("--zoom-start", default="2025-05-26 13:08:00", help="Window start datetime")
    parser.add_argument("--zoom-end", default="2025-05-26 13:25:00", help="Window end datetime")
    parser.add_argument("--moving-avg-window", type=int, default=5, help="Moving average window")
    parser.add_argument("--exp-smooth-alpha", type=float, default=0.3, help="Exponential smoothing alpha")
    args = parser.parse_args()

    export_filter_comparison_json(
        args.input,
        Path(args.out),
        zoom_start=args.zoom_start,
        zoom_end=args.zoom_end,
        moving_avg_window=args.moving_avg_window,
        exp_smooth_alpha=args.exp_smooth_alpha,
    )
