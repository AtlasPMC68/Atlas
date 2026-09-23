"""Per-run debug dump: everything needed to see what alignment actually did.

Throwaway diagnostics, switched on with `GEOREF_DEBUG=true`. Writes a folder per
run instead of adding to already-crowded logs.

The overlays are the point. A gate value tells you a fit passed; only seeing the
reference coastline drawn through the transform, on top of the user's map, tells
you *where it went* and whether it went there for a sensible reason.

Needs cv2, so like `evidence.py` and `runner.py` this is not re-exported from the
package.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, List, Optional, Sequence

import cv2
import numpy as np

from .models import AffineModel, ControlPoint
from .projection import lonlat_to_webmercator

logger = logging.getLogger(__name__)

DEBUG_ROOT = os.getenv("GEOREF_DEBUG_DIR", "/app/debug_runs")


def debug_enabled() -> bool:
    return os.getenv("GEOREF_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


KEEP_RUNS = int(os.getenv("GEOREF_DEBUG_KEEP", "20"))


def _prune_old_runs() -> None:
    """Keep only the newest `KEEP_RUNS` folders. Each run is roughly 9 MB."""
    try:
        entries = sorted(
            d for d in os.listdir(DEBUG_ROOT)
            if os.path.isdir(os.path.join(DEBUG_ROOT, d))
        )
        import shutil

        for stale in entries[:-KEEP_RUNS] if len(entries) > KEEP_RUNS else []:
            shutil.rmtree(os.path.join(DEBUG_ROOT, stale), ignore_errors=True)
    except Exception:
        pass


def make_run_dir(label: str) -> Optional[str]:
    """A fresh folder for this run, newest-sortable by name."""
    try:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c for c in str(label) if c.isalnum() or c in "-_")[:40]
        path = os.path.join(DEBUG_ROOT, f"{stamp}_{safe}")
        os.makedirs(path, exist_ok=True)
        _prune_old_runs()
        return path
    except Exception as e:
        logger.warning(f"Could not create georef debug dir: {e}")
        return None


def _dim(image: np.ndarray, factor: float = 0.45) -> np.ndarray:
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return (image.astype(np.float32) * factor).astype(np.uint8)


def _reference_pixels(layers: Any, model: AffineModel, stride: int = 2, config: Any = None):
    """Reference curve points pushed through *model* into image pixels.

    Draws only the layers alignment actually used. Drawing all of them would
    put rivers on the overlay that the fit never saw, which is misleading in
    exactly the picture you go to when a map placed badly.
    """
    from .config import DEFAULT_GEOREF_CONFIG

    config = config or DEFAULT_GEOREF_CONFIG
    mask = layers.curve_mask(
        use_coastline=True,
        use_lakes=config.use_lakes_for_alignment,
        use_rivers=config.use_rivers_for_alignment,
    )
    lon, lat = layers.sample_curve_points(
        spacing_px=float(stride), max_points=40000, mask=mask
    )
    if lon.size == 0:
        return np.zeros(0), np.zeros(0)
    xy = np.array([lonlat_to_webmercator(a, b) for a, b in zip(lon, lat)])
    inverse = model.inverse()
    return inverse(xy[:, 0], xy[:, 1])


def _plot(canvas: np.ndarray, x, y, color, radius: int = 1) -> int:
    h, w = canvas.shape[:2]
    x = np.asarray(x)
    y = np.asarray(y)
    keep = (x >= 0) & (x < w) & (y >= 0) & (y < h)
    xs = x[keep].astype(int)
    ys = y[keep].astype(int)
    if radius <= 1:
        canvas[ys, xs] = color
    else:
        for px, py in zip(xs, ys):
            cv2.circle(canvas, (int(px), int(py)), radius, color, -1)
    return int(keep.sum())


def dump_alignment_debug(
    out_dir: str,
    image_bgr: np.ndarray,
    layers: Any,
    evidence: Any,
    alignment: Any,
    control_points: Sequence[ControlPoint],
    baseline: AffineModel,
    extra: Optional[dict] = None,
) -> List[str]:
    """Write every diagnostic for one alignment run. Never raises."""
    written: List[str] = []

    def _write(name: str, image: np.ndarray) -> None:
        try:
            path = os.path.join(out_dir, name)
            cv2.imwrite(path, image)
            written.append(path)
        except Exception as e:
            logger.warning(f"debug write failed for {name}: {e}")

    try:
        aligned = alignment.model if alignment is not None else baseline

        # The source map, so a past run's overlays can be re-rendered after a
        # code change without re-importing (which costs an OCR pass).
        _write("00_map.png", image_bgr)

        # --- user-side evidence ---------------------------------------------
        _write("01_edges.png", evidence.edges.astype(np.uint8) * 255)
        _write("02_edge_weight.png", (evidence.edge_weight * 255).astype(np.uint8))
        if evidence.text_mask is not None and evidence.text_mask.any():
            _write("03_text_mask.png", evidence.text_mask.astype(np.uint8) * 255)
        if evidence.legend_mask.any():
            _write("03_legend_mask.png", evidence.legend_mask.astype(np.uint8) * 255)

        kept = evidence.edges & (evidence.edge_weight >= 1.0)
        suppressed = evidence.edges & (evidence.edge_weight < 1.0)
        overlay = _dim(image_bgr)
        overlay[kept] = (0, 255, 0)
        overlay[suppressed] = (0, 0, 255)
        _write("04_edges_over_map.png", overlay)

        if evidence.water.any():
            water = _dim(image_bgr)
            water[evidence.ocean] = (255, 120, 0)
            water[evidence.lakes] = (255, 220, 120)
            _write("05_water.png", water)

        # --- reference, warped onto the map ----------------------------------
        # The single most useful picture here: where the real coastline lands
        # under each transform, drawn on the map it is supposed to match.
        bx, by = _reference_pixels(layers, baseline)
        ax, ay = _reference_pixels(layers, aligned)

        before = _dim(image_bgr, 0.28)
        n_before = _plot(before, bx, by, (0, 0, 255))
        _write("06_reference_baseline.png", before)

        after = _dim(image_bgr, 0.28)
        n_after = _plot(after, ax, ay, (0, 255, 0))
        _write("07_reference_aligned.png", after)

        both = _dim(image_bgr, 0.22)
        _plot(both, bx, by, (0, 0, 255))
        _plot(both, ax, ay, (0, 255, 0))
        _write("08_reference_before_red_after_green.png", both)

        # --- control points ---------------------------------------------------
        # Yellow circle = SIFT point, magenta circle + name = city.
        gcp = _dim(image_bgr, 0.6)
        for cp in control_points:
            px, py = int(cp.pixel[0]), int(cp.pixel[1])
            if cp.city is not None:
                cv2.circle(gcp, (px, py), 12, (255, 0, 255), 2)
                cv2.putText(
                    gcp, cp.city.name, (px + 14, py - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1, cv2.LINE_AA,
                )
            else:
                cv2.circle(gcp, (px, py), 12, (0, 255, 255), 2)
            X, Y = lonlat_to_webmercator(*cp.geo)
            for model, color in ((baseline, (0, 0, 255)), (aligned, (0, 255, 0))):
                qx, qy = model.inverse()(np.array([X]), np.array([Y]))
                q = (int(qx[0]), int(qy[0]))
                cv2.drawMarker(gcp, q, color, cv2.MARKER_CROSS, 16, 2)
                cv2.line(gcp, (px, py), q, color, 1)
        _write("09_control_points.png", gcp)

        # --- ICP correspondences ---------------------------------------------
        try:
            from .align import build_curve_samples, build_user_field, find_correspondences
            from .config import DEFAULT_GEOREF_CONFIG
            from .align import _params_from_model

            samples = build_curve_samples(layers, DEFAULT_GEOREF_CONFIG)
            field = build_user_field(evidence, DEFAULT_GEOREF_CONFIG)
            index, targets, _w = find_correspondences(
                _params_from_model(aligned), samples, field, 20.0, DEFAULT_GEOREF_CONFIG
            )
            corr = _dim(image_bgr, 0.28)
            if index.size:
                from .align import _to_pixel

                sx, sy = _to_pixel(_params_from_model(aligned), samples.xy[index])
                for i in range(0, index.size, max(1, index.size // 1500)):
                    cv2.line(
                        corr,
                        (int(sx[i]), int(sy[i])),
                        (int(targets[i, 0]), int(targets[i, 1])),
                        (255, 255, 0),
                        1,
                    )
                _plot(corr, sx, sy, (0, 255, 0))
            _write("10_icp_correspondences.png", corr)
            matched = int(index.size)
            total_samples = len(samples)
        except Exception as e:
            logger.warning(f"correspondence debug failed: {e}")
            matched, total_samples = -1, -1

        # --- the numbers ------------------------------------------------------
        from .gates import gcp_rms_px, similarity_of

        base_scale, base_rot, _ = similarity_of(baseline)
        new_scale, new_rot, _ = similarity_of(aligned)

        lines: List[str] = []
        lines.append("GEOREFERENCING RUN")
        lines.append(f"  written              {datetime.now().isoformat(timespec='seconds')}")
        lines.append(f"  image                {image_bgr.shape[1]} x {image_bgr.shape[0]} px")
        lines.append("")
        lines.append("CONTROL POINTS")
        lines.append(f"  count                {len(control_points)}")
        lines.append(f"  GCP RMS baseline     {gcp_rms_px(baseline, control_points):.2f} px")
        lines.append(f"  GCP RMS aligned      {gcp_rms_px(aligned, control_points):.2f} px")
        for i, cp in enumerate(control_points):
            X, Y = lonlat_to_webmercator(*cp.geo)
            qx, qy = aligned.inverse()(np.array([X]), np.array([Y]))
            err = float(np.hypot(qx[0] - cp.pixel[0], qy[0] - cp.pixel[1]))
            lines.append(
                f"    [{i}] pixel=({cp.pixel[0]:.0f},{cp.pixel[1]:.0f}) "
                f"geo=({cp.geo[0]:.3f},{cp.geo[1]:.3f}) "
                f"source={cp.source}"
                + (f" city={cp.city.name}" if cp.city is not None else "")
                + f" residual={err:.1f}px"
            )
        lines.append("")
        lines.append("EVIDENCE (the user's map)")
        for key, value in (evidence.stats or {}).items():
            lines.append(f"  {key:<22} {value}")
        lines.append("")
        lines.append("REFERENCE (framing box)")
        for key, value in (layers.coverage() or {}).items():
            lines.append(f"  {key:<22} {value:.4%}")
        lines.append(f"  grid                 {layers.grid.width} x {layers.grid.height}")
        lines.append(f"  km per raster px     {layers.grid.km_per_pixel:.3f}")
        lines.append(
            f"  reference pts on map baseline={n_before} aligned={n_after}"
        )
        lines.append("")
        lines.append("ALIGNMENT")
        if alignment is None:
            lines.append("  DISABLED (GEOREF_ENABLE_CURVE_ALIGNMENT is off)")
        else:
            lines.append(f"  method               {alignment.method}")
            lines.append(f"  recovery rung        {alignment.rung}")
            lines.append(f"  used curve evidence  {alignment.used_curve_evidence}")
            lines.append(
                f"  probe disagreement   {alignment.probe_agreement_px:.2f} px"
                if alignment.probe_agreement_px is not None
                else "  probe disagreement   n/a"
            )
            lines.append(f"  failed checks        {alignment.failed_checks or 'none'}")
            lines.append(f"  ICP correspondences  {matched} of {total_samples} samples")
            st = alignment.stats or {}
            lines.append("")
            lines.append("  DID IT ACTUALLY ENGAGE?")
            base_c = st.get("baselineChamferPx")
            aligned_c = st.get("alignedChamferPx")
            moved = st.get("coastDisplacementPx")
            lines.append(
                f"    coastline chamfer    {base_c:.1f} px -> {aligned_c:.1f} px"
                if isinstance(base_c, float) and isinstance(aligned_c, float)
                else "    coastline chamfer    n/a"
            )
            if isinstance(base_c, float) and isinstance(aligned_c, float) and base_c > 0:
                lines.append(
                    f"    improvement          {(1 - aligned_c / base_c):+.1%}"
                )
            if isinstance(moved, float):
                lines.append(f"    coastline moved      {moved:.1f} px (median)")
            lines.append(
                f"    evidence used        coastline"
                + (" + lakes" if st.get("usesLakes") else "")
                + (" + rivers" if st.get("usesRivers") else "")
            )
            lines.append(
                f"    samples              coastline={st.get('coastlineSamples')} "
                f"fine={st.get('fineSamples')}"
            )
            lines.append("")
            lines.append("  GATES")
            for g in alignment.gates:
                state = "n/a " if not g.applicable else ("PASS" if g.passed else "FAIL")
                value = "-" if g.value is None else f"{g.value:.4f}"
                threshold = "-" if g.threshold is None else f"{g.threshold:.4f}"
                lines.append(
                    f"    {state}  {g.name:<26} value={value:<12} threshold={threshold}"
                )
                if g.detail:
                    lines.append(f"          {g.detail}")
            lines.append("")
            lines.append("  STATS")
            for key, value in (alignment.stats or {}).items():
                lines.append(f"    {key:<20} {value}")
        try:
            from .gates import water_mask_iou

            base_iou = water_mask_iou(baseline, layers, evidence)
            aligned_iou = water_mask_iou(aligned, layers, evidence)
            if base_iou is not None:
                lines.append("")
                lines.append("IS THE STARTING TRANSFORM ITSELF ANY GOOD?")
                lines.append(f"  water IoU baseline   {base_iou:.4f}")
                lines.append(f"  water IoU aligned    {aligned_iou:.4f}")
                lines.append(
                    "  (both low => the GCP-only affine is already misplaced, and"
                )
                lines.append(
                    "   alignment is not the thing to fix -- check GCPs, framing box,")
                lines.append(
                    "   or whether an affine can represent this map's projection)")
        except Exception:
            pass

        lines.append("")
        lines.append("TRANSFORM")
        lines.append(f"  scale   baseline={base_scale:.4f} aligned={new_scale:.4f}")
        lines.append(f"  rotation baseline={base_rot:.3f} deg aligned={new_rot:.3f} deg")
        lines.append(f"  baseline matrix\n{baseline.matrix}")
        lines.append(f"  aligned matrix\n{aligned.matrix}")
        if extra:
            lines.append("")
            lines.append("EXTRA")
            for key, value in extra.items():
                lines.append(f"  {key:<22} {value}")

        summary_path = os.path.join(out_dir, "summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        written.append(summary_path)

        if alignment is not None:
            payload = {
                "method": alignment.method,
                "rung": alignment.rung,
                "failedChecks": alignment.failed_checks,
                "probeAgreementPx": alignment.probe_agreement_px,
                "stats": alignment.stats,
                "phaseModels": alignment.phase_models,
                "gates": [
                    {
                        "name": g.name,
                        "value": g.value,
                        "threshold": g.threshold,
                        "applicable": g.applicable,
                        "passed": g.passed,
                        "detail": g.detail,
                    }
                    for g in alignment.gates
                ],
            }
            path = os.path.join(out_dir, "alignment.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            written.append(path)

    except Exception as e:  # diagnostics must never break a run
        logger.warning(f"georef debug dump failed: {e}", exc_info=True)

    return written
