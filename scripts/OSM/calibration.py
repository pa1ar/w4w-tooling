import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import math


@dataclass
class Thresholds:
    excellent_max: float
    good_max: float
    intermediate_max: float
    bad_max: float = 250.0


LABELS = ["excellent", "good", "intermediate", "bad", "very_bad"]


def normalize_osm_label(tag: Optional[str]) -> Optional[str]:
    if not tag:
        return None
    t = str(tag).strip().lower()
    if t in {"very-bad", "very bad"}:
        return "very_bad"
    if t in {"excellent", "good", "intermediate", "bad", "very_bad"}:
        return t
    # unknown → None (ignore)
    return None


def predict_label_from_z(z_value: float, thr: Thresholds) -> str:
    if z_value < thr.excellent_max:
        return "excellent"
    if z_value < thr.good_max:
        return "good"
    if z_value < thr.intermediate_max:
        return "intermediate"
    if z_value < thr.bad_max:
        return "bad"
    return "very_bad"


def collect_labeled_samples(
    df_assigned,
    way_id_to_osm_label: Dict[int, str],
    z_column: str,
    min_mg: float = 5.0,
    max_mg: float = 800.0,
) -> Tuple[List[float], List[str]]:
    xs: List[float] = []
    ys: List[str] = []
    if z_column not in df_assigned.columns:
        return xs, ys
    for _, row in df_assigned.iterrows():
        wid = row.get("way_id")
        if wid is None or math.isnan(float(wid)):
            continue
        label = normalize_osm_label(way_id_to_osm_label.get(int(wid)))
        if label is None:
            continue
        z = row.get(z_column)
        if z is None:
            continue
        try:
            zf = float(z)
        except Exception:
            continue
        if not math.isfinite(zf):
            continue
        # Filter out stationary and clip outliers
        if zf <= min_mg:
            continue
        if zf > max_mg:
            zf = max_mg
        xs.append(zf)
        ys.append(label)
    return xs, ys


def _macro_f1(y_true: List[str], y_pred: List[str]) -> float:
    # Compute macro-F1 without external deps
    from collections import Counter, defaultdict

    labels = LABELS
    tp = Counter()
    fp = Counter()
    fn = Counter()

    for yt, yp in zip(y_true, y_pred):
        for lb in labels:
            if yp == lb and yt == lb:
                tp[lb] += 1
            elif yp == lb and yt != lb:
                fp[lb] += 1
            elif yt == lb and yp != lb:
                fn[lb] += 1

    f1s: List[float] = []
    for lb in labels:
        p = tp[lb] / (tp[lb] + fp[lb]) if (tp[lb] + fp[lb]) > 0 else 0.0
        r = tp[lb] / (tp[lb] + fn[lb]) if (tp[lb] + fn[lb]) > 0 else 0.0
        if p + r == 0:
            f1 = 0.0
        else:
            f1 = 2 * p * r / (p + r)
        f1s.append(f1)
    if not f1s:
        return 0.0
    return sum(f1s) / len(f1s)


def search_thresholds_grid(
    z_values: List[float],
    labels: List[str],
    t1_range: Tuple[int, int, int] = (50, 120, 10),
    t2_range: Tuple[int, int, int] = (90, 240, 10),
    t3_range: Tuple[int, int, int] = (160, 600, 20),
    t4_range: Tuple[int, int, int] = (200, 400, 20),
) -> Thresholds:
    best_score = -1.0
    best_thr = Thresholds(60.0, 110.0, 180.0, 250.0)
    if not z_values or not labels:
        return best_thr
    for t1 in range(*t1_range):
        for t2 in range(*t2_range):
            if t2 <= t1:
                continue
            for t3 in range(*t3_range):
                if t3 <= t2:
                    continue
                for t4 in range(*t4_range):
                    if t4 <= t3:
                        continue
                    thr = Thresholds(float(t1), float(t2), float(t3), float(t4))
                    preds = [predict_label_from_z(x, thr) for x in z_values]
                    score = _macro_f1(labels, preds)
                    if score > best_score:
                        best_score = score
                        best_thr = thr
    return best_thr


def save_thresholds_json(thr: Thresholds, path) -> None:
    payload = {
        "excellent_max": thr.excellent_max,
        "good_max": thr.good_max,
        "intermediate_max": thr.intermediate_max,
        "bad_max": thr.bad_max,
        "note": "Calibrated thresholds (mg) using OSM tags as ground truth.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_thresholds_json(path) -> Optional[Thresholds]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Thresholds(
            excellent_max=float(data["excellent_max"]),
            good_max=float(data["good_max"]),
            intermediate_max=float(data["intermediate_max"]),
            bad_max=float(data.get("bad_max", 250.0)),
        )
    except Exception:
        return None
