#!/usr/bin/env python3
"""
Export analysis data for web charts from the scooter data analysis notebook.

This script extracts the key data needed for the 4-chart dashboard:
1. Surface quality distribution (pie chart)
2. Surface quality distribution (treemap)
3. Z-std distribution (bar chart)
4. Confidence vs speed scatter plot
"""

import json
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional


def load_telemetry_data(telemetry_file: str) -> pd.DataFrame:
    """Load and process telemetry data from JSON file."""
    with open(telemetry_file, 'r') as f:
        data = json.load(f)

    ride_data = data['rideData']

    # Process each data point
    processed_data = []
    for item in ride_data:
        # Extract accelerometer data
        accel_coords = item.get('accelerationCoord', [])
        if len(accel_coords) >= 3:
            x_values = accel_coords[::3]  # Every 3rd value starting from 0
            y_values = accel_coords[1::3]  # Every 3rd value starting from 1
            z_values = accel_coords[2::3]  # Every 3rd value starting from 2

            # Calculate statistics
            x_mean = np.mean(x_values) if x_values else np.nan
            y_mean = np.mean(y_values) if y_values else np.nan
            z_mean = np.mean(z_values) if z_values else np.nan
            z_std = np.std(z_values) if z_values else np.nan

            # Extract GPS speed
            gps_info = item.get('gpsInfo', {})
            speed_kmh = gps_info.get('speed', 0) / 10.0  # raw unit: 1/10 km/h

            processed_data.append({
                'timestamp': item.get('timestamp', ''),
                'x_mean': x_mean,
                'y_mean': y_mean,
                'z_mean': z_mean,
                'z_std': z_std,
                'speed_kmh': speed_kmh,
                'gps_lat': item.get('gpsPos', {}).get('gpsLat', 0),
                'gps_lon': item.get('gpsPos', {}).get('gpsLon', 0),
            })

    return pd.DataFrame(processed_data)


def classify_smoothness(z_std: float) -> str:
    """Classify smoothness based on z_std value."""
    if z_std < 50:
        return 'excellent'
    elif z_std < 100:
        return 'good'
    elif z_std < 200:
        return 'intermediate'
    elif z_std < 400:
        return 'bad'
    else:
        return 'very_bad'


def calculate_wheelchair_confidence(z_std: float, speed_kmh: float) -> float:
    """Calculate wheelchair accessibility confidence."""
    # Base confidence from classification clarity
    thresholds = [50, 100, 200, 400]
    min_distance = min(abs(z_std - threshold) for threshold in thresholds)

    if min_distance < 10:
        base_confidence = 0.5 + (min_distance / 20)
    else:
        base_confidence = 1.0

    # Speed factor for wheelchair accessibility
    if speed_kmh == 0:
        speed_factor = 0.3  # low confidence when stopped
    elif 2 <= speed_kmh <= 6:
        speed_factor = 1.0  # optimal wheelchair speed
    elif speed_kmh > 10:
        speed_factor = 0.4  # too fast
    elif speed_kmh > 6:
        speed_factor = 0.7  # moderately fast
    else:
        speed_factor = 0.8  # slow but moving

    return min(1.0, base_confidence * speed_factor)


def export_analysis_charts_json(
    telemetry_file: str,
    out_path: Path,
    min_speed: float = 1.0
) -> Path:
    """Export analysis data for web charts."""

    # Load and process data
    df = load_telemetry_data(telemetry_file)

    # Filter for moving periods only
    moving_data = df[df['speed_kmh'] >= min_speed].copy()

    if len(moving_data) == 0:
        raise ValueError("No moving data found")

    # Add smoothness classification
    moving_data['smoothness'] = moving_data['z_std'].apply(classify_smoothness)

    # Add confidence scores
    moving_data['wheelchair_confidence'] = moving_data.apply(
        lambda row: calculate_wheelchair_confidence(row['z_std'], row['speed_kmh']),
        axis=1
    )

    # 1. Surface quality distribution data
    smoothness_counts = moving_data['smoothness'].value_counts()
    surface_quality_data = [
        {
            'name': category,
            'value': int(count),
            'percentage': round(count / len(moving_data) * 100, 1)
        }
        for category, count in smoothness_counts.items()
    ]

    # 2. Z-std distribution data (histogram)
    z_std_bins = np.arange(0, 1000, 20)  # 20mg bins up to 1000mg
    z_std_hist, bin_edges = np.histogram(moving_data['z_std'], bins=z_std_bins)
    z_std_distribution = [
        {
            'range': f"{int(bin_edges[i])}-{int(bin_edges[i+1])}",
            'count': int(hist),
            'z_std_min': float(bin_edges[i]),
            'z_std_max': float(bin_edges[i+1])
        }
        for i, hist in enumerate(z_std_hist)
        if hist > 0  # Only include bins with data
    ]

    # 3. Confidence vs speed scatter data
    scatter_data = [
        {
            'speed_kmh': float(row['speed_kmh']),
            'z_std': float(row['z_std']),
            'confidence': float(row['wheelchair_confidence']),
            'smoothness': row['smoothness']
        }
        for _, row in moving_data.iterrows()
    ]

    # 4. Confidence comparison data
    confidence_comparison = {
        'wheelchair_confidence': {
            'mean': float(moving_data['wheelchair_confidence'].mean()),
            'std': float(moving_data['wheelchair_confidence'].std()),
            'min': float(moving_data['wheelchair_confidence'].min()),
            'max': float(moving_data['wheelchair_confidence'].max())
        }
    }

    # Create the export data structure
    export_data = {
        'meta': {
            'total_samples': len(df),
            'moving_samples': len(moving_data),
            'min_speed_threshold': min_speed,
            'export_timestamp': pd.Timestamp.now().isoformat()
        },
        'surface_quality_distribution': surface_quality_data,
        'z_std_distribution': z_std_distribution,
        'confidence_scatter': scatter_data,
        'confidence_stats': confidence_comparison,
        'thresholds': {
            'excellent_max': 50,
            'good_max': 100,
            'intermediate_max': 200,
            'bad_max': 400
        }
    }

    # Write to file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported analysis charts data to: {out_path}")
    print(f"Total samples: {len(df)}, Moving samples: {len(moving_data)}")
    print(f"Surface quality distribution: {len(surface_quality_data)} categories")
    print(f"Z-std distribution: {len(z_std_distribution)} bins")
    print(f"Scatter data points: {len(scatter_data)}")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export analysis chart JSON from telemetry")
    parser.add_argument("--input", default="example_data/258276934-579126.json", help="Telemetry JSON path")
    parser.add_argument("--out", default="output/analysis_charts.json", help="Output JSON path")
    parser.add_argument("--min-speed", type=float, default=1.0, help="Minimum speed in km/h")
    args = parser.parse_args()

    export_analysis_charts_json(args.input, Path(args.out), min_speed=args.min_speed)
