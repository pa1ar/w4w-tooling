"""
shared geographic and quality constants for w4w pipeline.
bbox format: (south, west, north, east) - wgs84 decimal degrees.
"""

# tallinn old town core - raekoja plats +/-0.015deg (~1.5km)
TALLINN_CENTER_BBOX = (59.422, 24.730, 59.452, 24.760)

# full tallinn city extent
TALLINN_BBOX = (59.35, 24.55, 59.50, 24.95)

# quality thresholds for accepting a way-level smoothness proposal
MIN_COVERAGE_PCT = 0.70
MIN_AGREE_PCT = 0.70


def bbox_contains(bbox, lat, lon):
    """true iff point (lat, lon) is inside bbox (south, west, north, east)."""
    south, west, north, east = bbox
    return south <= lat <= north and west <= lon <= east
