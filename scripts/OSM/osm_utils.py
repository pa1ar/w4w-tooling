#!/usr/bin/env python3
"""
OSM utility functions for finding ways and working with the Overpass API
Part of the Wheels4Wheels project
"""

import requests
from typing import List, Dict, Optional, Tuple
from time import sleep


OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"


def find_ways_near_point(lat: float, lon: float, radius: int = 20) -> List[Dict]:
    """
    find OSM ways near a specific coordinate using Overpass API

    args:
        lat: latitude
        lon: longitude
        radius: search radius in meters (default: 20)

    returns:
        list of way dictionaries with id, name, tags, and distance
    """
    query = f"""
    [out:json];
    (
      way(around:{radius},{lat},{lon})["highway"];
    );
    out body;
    >;
    out skel qt;
    """

    try:
        response = requests.post(
            OVERPASS_API_URL,
            data={'data': query},
            timeout=30
        )

        if response.status_code != 200:
            print(f"Error: Overpass API returned status {response.status_code}")
            return []

        data = response.json()

        ways = []
        for element in data.get('elements', []):
            if element.get('type') == 'way':
                way_info = {
                    'id': element['id'],
                    'tags': element.get('tags', {}),
                    'name': element.get('tags', {}).get('name', 'Unnamed'),
                    'highway_type': element.get('tags', {}).get('highway', 'unknown'),
                    'surface': element.get('tags', {}).get('surface', None),
                    'smoothness': element.get('tags', {}).get('smoothness', None),
                    'tracktype': element.get('tags', {}).get('tracktype', None)
                }
                ways.append(way_info)

        return ways

    except requests.exceptions.RequestException as e:
        print(f"Error querying Overpass API: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []


def find_way_by_coordinates(lat: float, lon: float, radius: int = 20,
                           interactive: bool = True, auto_confirm: bool = False) -> Optional[int]:
    """
    find and optionally select a way near coordinates

    args:
        lat: latitude
        lon: longitude
        radius: search radius in meters
        interactive: if True, prompts user to select; if False, returns first match
        auto_confirm: if True, automatically selects first/only way without prompting

    returns:
        way ID or None if not found
    """
    print(f"Searching for ways near ({lat}, {lon}) within {radius}m radius...")
    ways = find_ways_near_point(lat, lon, radius)

    if not ways:
        print("No ways found at this location.")
        print(f"Try increasing the radius (current: {radius}m)")
        return None

    print(f"\nFound {len(ways)} way(s):\n")

    for idx, way in enumerate(ways, 1):
        print(f"{idx}. Way {way['id']}: {way['name']}")
        print(f"   Type: {way['highway_type']}")
        if way['surface']:
            print(f"   Surface: {way['surface']}")
        if way['smoothness']:
            print(f"   Smoothness: {way['smoothness']}")
        if way['tracktype']:
            print(f"   Track type: {way['tracktype']}")
        print()

    # Auto-confirm if flag is set or non-interactive mode
    if auto_confirm or not interactive:
        print(f"Auto-selecting way {ways[0]['id']}")
        return ways[0]['id']

    # Interactive mode without auto-confirm
    if len(ways) == 1:
        choice = input(f"Use way {ways[0]['id']}? [Y/n]: ").strip().lower()
        if choice in ('', 'y', 'yes'):
            return ways[0]['id']
        return None

    while True:
        try:
            choice = input(f"Select way (1-{len(ways)}) or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None

            idx = int(choice) - 1
            if 0 <= idx < len(ways):
                return ways[idx]['id']
            else:
                print(f"Please enter a number between 1 and {len(ways)}")
        except ValueError:
            print("Invalid input. Please enter a number.")


def get_way_info(way_id: int) -> Optional[Dict]:
    """
    get detailed information about a specific way from Overpass API

    args:
        way_id: OSM way ID

    returns:
        dictionary with way information or None if not found
    """
    query = f"""
    [out:json];
    way({way_id});
    out body;
    >;
    out skel qt;
    """

    try:
        response = requests.post(
            OVERPASS_API_URL,
            data={'data': query},
            timeout=30
        )

        if response.status_code != 200:
            return None

        data = response.json()
        elements = data.get('elements', [])

        if not elements:
            return None

        way = elements[0]
        if way.get('type') != 'way':
            return None

        return {
            'id': way['id'],
            'tags': way.get('tags', {}),
            'nodes': way.get('nodes', []),
            'version': way.get('version'),
            'timestamp': way.get('timestamp'),
            'changeset': way.get('changeset')
        }

    except Exception as e:
        print(f"Error getting way info: {e}")
        return None


def calculate_way_bounds(way_id: int) -> Optional[Tuple[float, float, float, float]]:
    """
    calculate bounding box for a way

    args:
        way_id: OSM way ID

    returns:
        tuple of (min_lat, min_lon, max_lat, max_lon) or None
    """
    query = f"""
    [out:json];
    way({way_id});
    out body;
    >;
    out skel qt;
    """

    try:
        response = requests.post(
            OVERPASS_API_URL,
            data={'data': query},
            timeout=30
        )

        if response.status_code != 200:
            return None

        data = response.json()

        lats = []
        lons = []

        for element in data.get('elements', []):
            if element.get('type') == 'node' and 'lat' in element and 'lon' in element:
                lats.append(element['lat'])
                lons.append(element['lon'])

        if not lats or not lons:
            return None

        return (min(lats), min(lons), max(lats), max(lons))

    except Exception as e:
        print(f"Error calculating bounds: {e}")
        return None


def check_existing_smoothness(way_id: int) -> Optional[str]:
    """
    check if a way already has a smoothness tag

    args:
        way_id: OSM way ID

    returns:
        existing smoothness value or None
    """
    info = get_way_info(way_id)
    if info:
        return info['tags'].get('smoothness')
    return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python osm_utils.py <latitude> <longitude> [radius]")
        print("\nExample:")
        print("  python osm_utils.py 50.328132 8.738048 20")
        sys.exit(1)

    lat = float(sys.argv[1])
    lon = float(sys.argv[2])
    radius = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    way_id = find_way_by_coordinates(lat, lon, radius, interactive=True)

    if way_id:
        print(f"\n" + "=" * 70)
        print(f"Selected way ID: {way_id}")
        print("=" * 70)

        existing = check_existing_smoothness(way_id)
        if existing:
            print(f"Note: This way already has smoothness={existing}")
        else:
            print("This way does not have a smoothness tag yet.")

        print(f"\nView on OSM: https://www.openstreetmap.org/way/{way_id}")
        print(f"\nTo edit this way, run:")
        print(f"  python scripts/OSM/osm_edit.py set-tag --way-id {way_id} --key smoothness --value intermediate --comment 'W4W: add surface smoothness'")
