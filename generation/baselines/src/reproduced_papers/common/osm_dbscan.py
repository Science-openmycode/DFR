# Grounding: transcribed from experiments/paper_comparison/final/osm_dbscan/four_papers_all_metrics.py (osm_centers_from_ways function)
"""
OSM-DBSCAN: Zero-budget road-density-based center extraction.

Core algorithm: grid city bbox, accumulate OSM road segment density,
select top-K densest cells as discretization centers.
"""

import numpy as np
import pickle
import os


def _normalize_bbox(bbox):
    if isinstance(bbox, dict):
        return (
            float(bbox["lat_min"]),
            float(bbox["lat_max"]),
            float(bbox["lon_min"]),
            float(bbox["lon_max"]),
        )
    return tuple(float(v) for v in bbox)


def osm_centers_from_ways(ways, bbox, K, gs=50):
    """
    Extract K discretization centers from OSM road density.

    Args:
        ways: list of OSM way dicts, each with 'geometry' list of {'lat':, 'lon':}
        bbox: tuple (lat_min, lat_max, lon_min, lon_max)
        K: number of centers to extract
        gs: grid size (default 50, producing gs^2 cells)

    Returns:
        numpy array of shape (K, 2) with [lat, lon] center coordinates

    Source: four_papers_all_metrics.py:69-77
    """
    lat_min, lat_max, lon_min, lon_max = _normalize_bbox(bbox)
    ls = lat_max - lat_min
    ll = lon_max - lon_min

    # Grid density accumulation
    rd = np.zeros((gs, gs), dtype=np.float64)

    for w in ways:
        g = w.get('geometry', [])
        for i in range(len(g) - 1):
            p1 = g[i]
            p2 = g[i + 1]
            # Sample 3 points per segment: endpoints + midpoint
            for pt in [(p1['lat'], p1['lon']),
                       (p2['lat'], p2['lon']),
                       ((p1['lat'] + p2['lat']) / 2,
                        (p1['lon'] + p2['lon']) / 2)]:
                if lat_min <= pt[0] <= lat_max and lon_min <= pt[1] <= lon_max:
                    r = int((pt[0] - lat_min) / ls * gs)
                    c = int((pt[1] - lon_min) / ll * gs)
                    r = min(max(r, 0), gs - 1)
                    c = min(max(c, 0), gs - 1)
                    rd[r, c] += 1.0

    # Select top-K densest cells
    idx = np.argsort(rd.flatten())[-K:]

    # Convert grid indices to geographic coordinates
    centers = np.array([
        [lat_min + (i // gs + 0.5) * ls / gs,
         lon_min + (i % gs + 0.5) * ll / gs]
        for i in idx
    ], dtype=np.float64)

    return centers


def load_osm_ways(city_name, base_dir):
    """
    Load cached OSM way data.

    Uses pre-cached pickle files because direct tile.openstreetmap.org
    access was blocked by DNS resolution failure during experiments.
    Cache files must be pre-populated via offline OSM data extraction.

    Source: four_papers_all_metrics.py (inline in run_city)
    """
    osmf = os.path.join(base_dir, 'osm_cache_{}.pkl'.format(city_name))
    if not os.path.exists(osmf):
        raise FileNotFoundError(
            "OSM cache not found: {}. Run OSM data collection first.".format(osmf))
    with open(osmf, 'rb') as f:
        return pickle.load(f)


def format_centers_for_privtrace(centers):
    """
    Convert numpy centers to PrivTrace-compatible format.

    Source: four_papers_all_metrics.py:128-129
    """
    return [{'lat': float(c[0]), 'lon': float(c[1]), 'type': 'rndv'}
            for c in centers]


def format_centers_for_dpstd(centers):
    """
    Convert numpy centers to DPStd-compatible format.

    Source: four_papers_all_metrics.py:188-189
    """
    return [{'lat': float(c[0]), 'lon': float(c[1])}
            for c in centers]
