"""
Shared batch runner and output for the prototype scripts.

Each script supplies a ``load`` and a ``process(image_path)``; this walks the
assets, times every image and writes the same files for every detector, so runs
can be compared side by side.
"""
import csv
import json
import logging
import os
import statistics
import sys
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BOX_COLOR = (230, 0, 60)


def find_images(root: str, filters: list[str]) -> list[str]:
    paths = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in IMAGE_EXTENSIONS:
                continue
            path = os.path.join(dirpath, name)
            if filters and not any(f in path for f in filters):
                continue
            paths.append(path)
    return sorted(paths)


def _one_line(text: str) -> str:
    return text.replace("\n", " / ")


def draw_overlay(image_path: str, labels: list[dict], out_path: str) -> None:
    """Draw the merged boxes, numbered, with the new reading, on the original image."""
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    longest = max(image.size)
    line_width = max(1, longest // 800)
    try:
        font = ImageFont.truetype(FONT_PATH, max(10, longest // 110))
    except OSError:
        # The backend image has no system fonts
        font = ImageFont.load_default(size=max(10, longest // 110))

    for i, label in enumerate(labels, 1):
        points = [(x, y) for x, y in label["quad"]]
        draw.polygon(points, outline=BOX_COLOR, width=line_width)

        caption = f"{i}: {_one_line(label['new_text'])}"
        x, y = min(p[0] for p in points), min(p[1] for p in points)
        left, top, right, bottom = draw.textbbox((0, 0), caption, font=font)
        y = y - (bottom - top) - 2 if y - (bottom - top) - 2 >= 0 else max(p[1] for p in points) + 2
        draw.rectangle((x, y, x + right - left + 4, y + bottom - top + 4), fill=(255, 255, 255))
        draw.text((x + 2 - left, y + 2 - top), caption, fill=BOX_COLOR, font=font)

    image.save(out_path)


def format_labels(labels: list[dict]) -> list[str]:
    return [f"  [{i:>3}] {_one_line(label['new_text'])!r}" for i, label in enumerate(labels, 1)]


def _stamp(moment: datetime) -> str:
    return moment.strftime("%H:%M:%S.%f")[:-3]


def run_batch(name: str, load, process, stages: list[str]) -> None:
    """
    Run ``process`` on every asset image and write the outputs.

    :param name: suffix of the run folder, e.g. ``paddle-det``.
    :param load: called once before the first image (model loading).
    :param process: ``image_path -> result``; the result has ``labels`` (each
        with ``quad`` and ``new_text``) and
        ``timings_s`` keyed by ``stages``.
    :param stages: timing keys reported per image, in order.
    """
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "warning").upper())
    assets_dir = os.environ.get("ASSETS_DIR", "/assets")
    output_root = os.environ.get("OUTPUT_DIR", "/output")

    images = find_images(assets_dir, sys.argv[1:])
    if not images:
        print(f"No images found under {assets_dir}")
        return

    run_started = datetime.now()
    run_dir = os.path.join(output_root, f"{run_started.strftime('%Y%m%d-%H%M%S')}-{name}")
    os.makedirs(run_dir, exist_ok=True)
    print(f"[{_stamp(run_started)}] {name}: {len(images)} images, output in {run_dir}")

    load()
    loaded = datetime.now()
    print(f"[{_stamp(loaded)}] Models loaded in {(loaded - run_started).total_seconds():.1f}s\n")

    columns = (
        ["index", "image", "status", "started_at", "finished_at", "since_prev_done_s", "total_s"]
        + [f"{stage}_s" for stage in stages]
        + ["output_s", "labels"]
    )
    # Written row by row so it can be followed while the run is going.
    timeline_file = open(os.path.join(run_dir, "timeline.csv"), "w", encoding="utf-8", newline="")
    timeline = csv.DictWriter(timeline_file, fieldnames=columns)
    timeline.writeheader()

    summary = []
    durations = []
    prev_done = loaded
    for n, image_path in enumerate(images, 1):
        rel = os.path.relpath(image_path, assets_dir)
        started = datetime.now()
        print(f"=== [{n}/{len(images)}] {rel}")
        print(f"[{_stamp(started)}] start")
        row = {"index": n, "image": rel, "started_at": started.isoformat(timespec="milliseconds")}
        try:
            result = process(image_path)
            labels = result["labels"]
            t = result["timings_s"]

            out_started = time.monotonic()
            out_dir = os.path.join(run_dir, os.path.splitext(rel)[0])
            os.makedirs(out_dir, exist_ok=True)
            draw_overlay(image_path, labels, os.path.join(out_dir, "overlay.png"))
            with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            lines = format_labels(labels)
            with open(os.path.join(out_dir, "comparison.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            output_s = time.monotonic() - out_started

            print("\n".join(lines))
            row.update(status="ok", output_s=round(output_s, 2), labels=len(labels))
            row.update({f"{stage}_s": t[stage] for stage in stages})
            stats = f"{len(labels)} labels"
            stage_times = ", ".join(f"{stage} {t[stage]:.1f}s" for stage in stages)
            stats += f" | {stage_times}, output {output_s:.1f}s"
        except Exception as e:
            print(f"  FAILED: {e}")
            row["status"] = "failed"
            stats = f"FAILED ({e})"

        done = datetime.now()
        total_s = (done - started).total_seconds()
        since_prev = (done - prev_done).total_seconds()
        prev_done = done
        durations.append(total_s)
        row.update(
            finished_at=done.isoformat(timespec="milliseconds"),
            since_prev_done_s=round(since_prev, 2), total_s=round(total_s, 2),
        )
        timeline.writerow(row)
        timeline_file.flush()

        print(
            f"[{_stamp(done)}] done in {total_s:.1f}s "
            f"(+{since_prev:.1f}s since previous, {(done - run_started).total_seconds():.1f}s into run) | {stats}\n"
        )
        summary.append(f"{rel}: {total_s:.1f}s | {stats}")

    timeline_file.close()
    run_done = datetime.now()
    totals = (
        f"{len(durations)} images in {(run_done - run_started).total_seconds() / 60:.1f} min "
        f"(model load {(loaded - run_started).total_seconds():.1f}s) | "
        f"avg {statistics.mean(durations):.1f}s, median {statistics.median(durations):.1f}s, "
        f"min {min(durations):.1f}s, max {max(durations):.1f}s per image"
    )
    with open(os.path.join(run_dir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n\n" + totals + "\n")
    print("=== Summary")
    print("\n".join(summary))
    print(f"\n[{_stamp(run_done)}] {totals}")
