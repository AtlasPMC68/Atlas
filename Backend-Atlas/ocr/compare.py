"""
Score prototype runs against the expected texts of the extraction tests.

Ground truth comes from ``tests/utils/expected_text_results.py``; matching and
metrics are copied from ``tests/test_extraction_text.py`` so the numbers are the
ones the test thresholds (``CARD_THRESHOLDS``) were set against.

Every run given is scored on its boxes read by the recognizer (``new_text``).

Standard library only, runs on the host. From the repo root:
    python3 Backend-Atlas/ocr/compare.py [run_dir ...]
Without run dirs, the latest complete run of each kind under outputs/ is used
(one kind per recognizer model, e.g. ``ocr-latin_PP-OCRv5_mobile_rec``).
"""
import csv
import importlib.util
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUTS = os.path.join(HERE, "outputs")
EXPECTED_PATH = os.path.join(HERE, "..", "tests", "utils", "expected_text_results.py")

spec = importlib.util.spec_from_file_location("expected_text_results", EXPECTED_PATH)
expected_results = importlib.util.module_from_spec(spec)
spec.loader.exec_module(expected_results)
MAP_EXPECTED_TEXTS = expected_results.MAP_EXPECTED_TEXTS
MAP_EXPECTED_ZONE_DETECTION_COUNTS = expected_results.MAP_EXPECTED_ZONE_DETECTION_COUNTS
CARD_THRESHOLDS = expected_results.CARD_THRESHOLDS
DEFAULT_THRESHOLDS = {"min_hit_rate": 40.0, "max_dist": 15.0}


def levenshtein_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


# --- copied from tests/test_extraction_text.py -------------------------------


def normalize_array_to_ascii_format(text: list[str]) -> list[str]:
    """Normalize a list of strings into lowercase ASCII without punctuation."""
    res = []
    for word in text:
        cleaned = (
            word.replace("\n", " ")
            .replace("'", "")
            .replace("’", "")
            .replace("-", " ")
            .replace(".", "")
            .replace(",", "")
            .replace("(", " ")
            .replace(")", " ")
            .replace(":", " ")
            .replace(";", " ")
            .replace("?", " ")
            .replace("!", " ")
            .replace('"', " ")
            .replace("«", " ")
            .replace("»", " ")
            .replace("/", " ")
            .replace("\\", " ")
        )
        cleaned = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii").lower()
        cleaned = " ".join(cleaned.split())
        res.append(cleaned)
    return res


def check_for_match(actual: list[str], expected: list[str]) -> list[tuple[str, tuple[str, float]]]:
    """Match each OCR word with the closest expected word and compute Levenshtein distance."""
    actual_ascii = normalize_array_to_ascii_format(actual)
    expected_ascii = normalize_array_to_ascii_format(expected)

    actual_dict = {}
    for i, word in enumerate(actual_ascii):
        if word not in actual_dict:
            actual_dict[word] = []
        actual_dict[word].append(i)

    used_exp_indices = set()
    used_ocr_indices = set()
    result = []

    for exp_idx, exp_word in enumerate(expected_ascii):
        if exp_word in actual_dict:
            available_ocr_indices = [idx for idx in actual_dict[exp_word] if idx not in used_ocr_indices]
            if available_ocr_indices:
                ocr_idx = available_ocr_indices[0]
                used_exp_indices.add(exp_idx)
                used_ocr_indices.add(ocr_idx)
                dist = 0.0 if actual[ocr_idx] == expected[exp_idx] else 0.1
                result.append((actual[ocr_idx], (expected[exp_idx], dist)))

    all_pairs = []
    for exp_idx, exp_word in enumerate(expected_ascii):
        if exp_idx in used_exp_indices:
            continue

        for ocr_idx, ocr_word in enumerate(actual_ascii):
            if ocr_idx in used_ocr_indices:
                continue

            dist = float(levenshtein_distance(ocr_word, exp_word))

            base_expected = re.sub(r"\b(1[5-9]\d\d|20\d\d)\b", "", exp_word).strip()
            base_expected = " ".join(base_expected.split())
            if base_expected and len(base_expected) >= 4 and base_expected != exp_word:
                if len(ocr_word) >= 4 and (base_expected in ocr_word or ocr_word in base_expected):
                    dist = min(dist, 0.5)
                else:
                    base_dist = float(levenshtein_distance(ocr_word, base_expected))
                    dist = min(dist, base_dist)
            elif len(exp_word) >= 4 and len(ocr_word) >= 4:
                if exp_word in ocr_word or ocr_word in exp_word:
                    dist = min(dist, 0.5)

            all_pairs.append((dist, exp_idx, ocr_idx))

    all_pairs.sort(key=lambda x: x[0])

    MAX_ALLOWED_DIST = 6.0

    for dist, exp_idx, ocr_idx in all_pairs:
        if exp_idx not in used_exp_indices and ocr_idx not in used_ocr_indices:
            if dist <= MAX_ALLOWED_DIST:
                used_exp_indices.add(exp_idx)
                used_ocr_indices.add(ocr_idx)
                result.append((actual[ocr_idx], (expected[exp_idx], dist)))

    for exp_idx in range(len(expected)):
        if exp_idx not in used_exp_indices:
            result.append(("", (expected[exp_idx], 1000.0)))

    return result


def calculate_match_metrics(matches, expected: list[str]) -> tuple[float, float]:
    """Compute hit rate coverage percentage and average distance from matched OCR results."""
    if not matches:
        return (0.0, 0.0)

    valid_distances = [distance for _, (_, distance) in matches if distance < 500.0]
    total_distance = sum(valid_distances)

    matched_expected_words = {
        expected_word
        for _, (expected_word, distance) in matches
        if expected_word and (distance <= max(3.0, len(expected_word) * 0.25))
    }
    box_find_rate = (len(matched_expected_words) / len(expected)) * 100 if expected else 0.0

    average_dist = total_distance / len(valid_distances) if valid_distances else 0.0
    return box_find_rate, average_dist


# --- end of copy --------------------------------------------------------------


def _run_kind(run_dir: str) -> str:
    """``ocr-latin_PP-OCRv5_mobile_rec``...: the run name without its timestamp."""
    name = os.path.basename(run_dir.rstrip("/"))
    return name.split("-", 2)[2] if name.count("-") >= 2 else name


def _covers_expected(run_dir: str) -> bool:
    return all(os.path.exists(os.path.join(run_dir, stem, "result.json")) for stem in MAP_EXPECTED_TEXTS)


def latest_runs() -> list[str]:
    """Latest finished run of each kind that has every map of the tests."""
    runs = {}
    for name in sorted(os.listdir(OUTPUTS)):
        run_dir = os.path.join(OUTPUTS, name)
        if os.path.isdir(run_dir) and os.path.exists(os.path.join(run_dir, "summary.txt")) and _covers_expected(run_dir):
            runs[_run_kind(run_dir)] = run_dir
    return [runs[kind] for kind in sorted(runs)]


def _result(run_dir: str, stem: str) -> dict:
    with open(os.path.join(run_dir, stem, "result.json"), encoding="utf-8") as f:
        return json.load(f)


def _image_seconds(run_dir: str) -> dict[str, float]:
    """Wall time per image from timeline.csv, keyed by image stem."""
    path = os.path.join(run_dir, "timeline.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {
            os.path.splitext(row["image"])[0]: float(row["total_s"])
            for row in csv.DictReader(f)
            if row.get("total_s")
        }


def _score(texts: list[str], expected: list[str], thresholds: dict) -> dict:
    matches = check_for_match(texts, list(expected))
    hit_rate, avg_dist = calculate_match_metrics(matches, expected)
    hit_ok = round(hit_rate, 1) >= round(thresholds["min_hit_rate"], 1)
    dist_ok = round(avg_dist, 2) <= round(thresholds["max_dist"], 2)
    status = "PASS" if hit_ok and dist_ok else ("WARN" if hit_ok or dist_ok else "FAIL")
    misses = sorted(
        [(exp, ocr, d) for ocr, (exp, d) in matches if d > 0.1],
        key=lambda m: m[2],
        reverse=True,
    )
    return {"hit_rate": hit_rate, "avg_dist": avg_dist, "status": status, "misses": misses}


def main() -> None:
    run_dirs = sys.argv[1:] or latest_runs()
    if not run_dirs:
        sys.exit("No finished run under outputs/ covers the test maps")

    # One scored reading per run
    readings = [(_run_kind(run_dir), run_dir, "new_text") for run_dir in run_dirs]
    width = max(len(name) for name, _, _ in readings)

    lines = [f"Run: {os.path.relpath(d, HERE)}" for d in run_dirs]
    lines += [
        "Ground truth: tests/utils/expected_text_results.py",
        "",
    ]

    totals = {name: {"pass": 0, "hit": 0.0, "dist": 0.0} for name, _, _ in readings}
    box_rows = []
    detail = []
    seconds = {run_dir: _image_seconds(run_dir) for run_dir in run_dirs}

    for stem, expected in MAP_EXPECTED_TEXTS.items():
        thresholds = CARD_THRESHOLDS.get(stem, DEFAULT_THRESHOLDS)
        items = {run_dir: _result(run_dir, stem)["labels"] for run_dir in run_dirs}
        box_rows.append((stem, MAP_EXPECTED_ZONE_DETECTION_COUNTS.get(stem), [len(items[d]) for d in run_dirs]))

        detail.append(
            f"=== {stem}  ({len(expected)} expected words, "
            f"min hit {thresholds['min_hit_rate']}%, max dist {thresholds['max_dist']})"
        )
        for name, run_dir, text_key in readings:
            s = _score([item[text_key] for item in items[run_dir]], expected, thresholds)
            totals[name]["pass"] += s["status"] == "PASS"
            totals[name]["hit"] += s["hit_rate"]
            totals[name]["dist"] += s["avg_dist"]
            detail.append(f"  {name:<{width}} {s['status']:<4}  hit {s['hit_rate']:5.1f}%  dist {s['avg_dist']:.2f}")
            for exp, ocr, d in s["misses"]:
                found = "NOT FOUND" if d > 500 else f"{ocr!r} (dist {d:.1f})"
                detail.append(f"      expected {exp!r}: {found}")
        detail.append("")

    kinds = [_run_kind(d) for d in run_dirs]
    col = max(8, *(len(k) for k in kinds))
    lines.append("Text boxes: expected vs found")
    lines.append(f"  {'map':<34} {'expected':>8} " + " ".join(f"{k:>{col}}" for k in kinds))
    for stem, exp_boxes, counts in box_rows:
        exp_str = "-" if exp_boxes is None else str(exp_boxes)
        lines.append(f"  {stem:<34} {exp_str:>8} " + " ".join(f"{c:>{col}}" for c in counts))
    lines.append("  (expected counts were recorded from an earlier OCR run, not hand-counted)")
    lines.append("")

    n = len(MAP_EXPECTED_TEXTS)
    lines.append(f"Text accuracy over {n} maps (test thresholds)")
    for name, run_dir, _ in readings:
        t = totals[name]
        times = [seconds[run_dir][stem] for stem in MAP_EXPECTED_TEXTS if stem in seconds[run_dir]]
        time_str = f"   avg {sum(times) / len(times):5.1f}s/map" if times else ""
        lines.append(
            f"  {name:<{width}} {t['pass']}/{n} pass   avg hit {t['hit'] / n:5.1f}%   avg dist {t['dist'] / n:.2f}{time_str}"
        )
    lines.append("")
    lines.extend(detail)

    report = "\n".join(lines)
    print(report)
    out_path = os.path.join(OUTPUTS, f"compare-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(f"Saved to {os.path.relpath(out_path, HERE)}")


if __name__ == "__main__":
    main()
