"""Evaluate the person detector on the sample images against manual counts.

Usage (from project root):
    .venv\\Scripts\\python.exe scripts/evaluate.py
    .venv\\Scripts\\python.exe scripts/evaluate.py --conf 0.25 0.4 0.5 --repeat 3 --enhance

Uses the same validate -> decode -> preprocess -> detect path as the API, but
does NOT write to the detection history. Writes to backend/evaluation/:
    results.json             raw per-image results for every threshold
    results.md               README-ready summary + per-image tables
    overlays/conf_<t>/*.jpg  annotated images for visual verification

Metric notes
------------
Ground truth is a per-image COUNT (backend/samples/ground_truth.json), not boxes,
so per-image matching is count-based:
    correct  = min(detected, actual)
    extra    = max(0, detected - actual)   -> counted as false positives
    missed   = max(0, actual - detected)
This can hide a miss + false positive in the same image, so check the
overlays: any box not on a person should be recorded as a false positive.
"""

import argparse
import json
import shutil
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from backend.config import get_settings  # noqa: E402
from backend.services.detector import get_detector  # noqa: E402
from backend.utils.preprocessing import load_image, preprocess  # noqa: E402
from backend.utils.visualization import draw_detections  # noqa: E402

SAMPLES = ROOT / "backend" / "samples"
OUT = ROOT / "backend" / "evaluation"

TARGETS = {
    "accuracy": (">=", 0.85),
    "fp_rate": ("<=", 0.10),
    "avg_inference_ms": ("<=", 1500),
    "avg_confidence": (">=", 0.70),
    "reliability": (">=", 1.0),
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--conf", type=float, nargs="+", default=None,
                   help="Confidence threshold(s) to evaluate (default: DETECTO_CONF_THRESHOLD)")
    p.add_argument("--enhance", action="store_true", help="Apply CLAHE contrast enhancement")
    p.add_argument("--repeat", type=int, default=3, help="Timed runs per image (mean is reported)")
    p.add_argument("--no-overlays", action="store_true", help="Skip writing annotated images")
    return p.parse_args()


def run_images(gt_items, settings, detector, min_conf, enhance, repeat):
    """Detect once per image at the lowest threshold; higher thresholds filter these results."""
    runs = []
    for item in gt_items:
        path = SAMPLES / item["file"]
        rec = {**item, "ok": False, "error": None}
        try:
            t0 = time.perf_counter()
            img = load_image(path.read_bytes(), None, settings)
            pre = preprocess(img, settings, enhance=enhance)
            prep_ms = (time.perf_counter() - t0) * 1000

            inference, detect_total = [], []
            for _ in range(repeat):
                res = detector.detect(pre, conf=min_conf)
                inference.append(res.inference_ms)
                detect_total.append(res.total_ms)

            rec.update(
                ok=True, image=img, detections=res.detections,
                width=res.image_size[0], height=res.image_size[1],
                inference_ms=statistics.mean(inference),
                end_to_end_ms=prep_ms + statistics.mean(detect_total),
            )
        except Exception as exc:  # reliability metric: record, don't crash
            rec["error"] = f"{type(exc).__name__}: {exc}"
        runs.append(rec)
    return runs


def score(runs, conf):
    """Per-image + summary metrics for one confidence threshold."""
    rows, all_conf = [], []
    for r in runs:
        if not r["ok"]:
            rows.append({"file": r["file"], "ok": False, "error": r["error"], "actual": r["people"]})
            continue
        dets = [d for d in r["detections"] if d.confidence >= conf]
        n, actual = len(dets), r["people"]
        confs = [d.confidence for d in dets]
        all_conf += confs
        rows.append({
            "file": r["file"], "ok": True, "conditions": r["conditions"],
            "actual": actual, "detected": n,
            "correct": min(n, actual), "extra": max(0, n - actual), "missed": max(0, actual - n),
            "avg_confidence": round(statistics.mean(confs), 3) if confs else None,
            "inference_ms": round(r["inference_ms"], 1),
            "end_to_end_ms": round(r["end_to_end_ms"], 1),
            "size": f'{r["width"]}x{r["height"]}',
        })

    ok = [r for r in rows if r["ok"]]
    total_actual = sum(r["actual"] for r in ok)
    total_detected = sum(r["detected"] for r in ok)
    summary = {
        "conf_threshold": conf,
        "images": len(rows),
        "processed": len(ok),
        "total_actual": total_actual,
        "total_detected": total_detected,
        "total_correct": sum(r["correct"] for r in ok),
        "total_extra": sum(r["extra"] for r in ok),
        "total_missed": sum(r["missed"] for r in ok),
        "accuracy": round(sum(r["correct"] for r in ok) / total_actual, 4) if total_actual else None,
        "fp_rate": round(sum(r["extra"] for r in ok) / total_detected, 4) if total_detected else 0.0,
        "avg_inference_ms": round(statistics.mean(r["inference_ms"] for r in ok), 1) if ok else None,
        "avg_end_to_end_ms": round(statistics.mean(r["end_to_end_ms"] for r in ok), 1) if ok else None,
        "avg_confidence": round(statistics.mean(all_conf), 4) if all_conf else None,
        "reliability": round(len(ok) / len(rows), 4) if rows else None,
    }
    return summary, rows


def passes(metric, value):
    if value is None:
        return False
    op, target = TARGETS[metric]
    return value >= target if op == ">=" else value <= target


def to_markdown(results, meta):
    pct = lambda v: "n/a" if v is None else f"{v * 100:.1f} %"  # noqa: E731
    tick = lambda m, v: "✅" if passes(m, v) else "❌"  # noqa: E731
    lines = [
        "# Detecto evaluation results",
        "",
        f"- Model: `{meta['model']}` on `{meta['device']}`, input size {meta['img_size']}, "
        f"CLAHE: {'on' if meta['enhance'] else 'off'}",
        f"- Images: {meta['images']} (ground truth: `backend/samples/ground_truth.json`)",
        f"- Timing: mean of {meta['repeat']} runs per image after warm-up",
        "- Matching is count-based per image (see `scripts/evaluate.py`); overlays in "
        "`backend/evaluation/overlays/` were checked by eye to confirm the extra boxes are real false positives",
        f"- Run at: {meta['run_at']}",
        "",
    ]
    for res in results:
        s = res["summary"]
        lines += [
            f"## Confidence threshold {s['conf_threshold']}",
            "",
            "| Metric | Description | Target | Result | |",
            "|---|---|---|---|---|",
            f"| Detection Accuracy | Correct detections ÷ total visible persons "
            f"({s['total_correct']}/{s['total_actual']}) | ≥ 85 % | {pct(s['accuracy'])} | {tick('accuracy', s['accuracy'])} |",
            f"| False Positives | Extra boxes ÷ all boxes ({s['total_extra']}/{s['total_detected']}) "
            f"| ≤ 10 % | {pct(s['fp_rate'])} | {tick('fp_rate', s['fp_rate'])} |",
            f"| Average Inference Time | Model time per image (end-to-end {s['avg_end_to_end_ms']} ms) "
            f"| ≤ 1.5 s | {s['avg_inference_ms']} ms | {tick('avg_inference_ms', s['avg_inference_ms'])} |",
            f"| Average Confidence | Mean confidence of detections | ≥ 0.7 | {s['avg_confidence']} "
            f"| {tick('avg_confidence', s['avg_confidence'])} |",
            f"| System Reliability | Images processed without errors ({s['processed']}/{s['images']}) "
            f"| 100 % | {pct(s['reliability'])} | {tick('reliability', s['reliability'])} |",
            "",
            "| Image | Conditions | Actual | Detected | Missed | Extra | Avg conf | Inference (ms) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in res["images"]:
            if not r["ok"]:
                lines.append(f"| {r['file']} | ERROR: {r['error']} | {r['actual']} | – | – | – | – | – |")
                continue
            lines.append(
                f"| {r['file']} | {', '.join(r['conditions'])} | {r['actual']} | {r['detected']} "
                f"| {r['missed']} | {r['extra']} | {r['avg_confidence'] or '–'} | {r['inference_ms']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    settings = get_settings()
    thresholds = args.conf or [settings.conf_threshold]  # first one is the headline result
    gt = json.loads((SAMPLES / "ground_truth.json").read_text(encoding="utf-8"))["images"]

    detector = get_detector()
    runs = run_images(gt, settings, detector, min(thresholds), args.enhance, args.repeat)

    if not args.no_overlays:
        shutil.rmtree(OUT / "overlays", ignore_errors=True)  # drop overlays from earlier runs

    results = []
    for conf in thresholds:
        summary, rows = score(runs, conf)
        results.append({"summary": summary, "images": rows})

        if not args.no_overlays:
            odir = OUT / "overlays" / f"conf_{conf:.2f}"
            odir.mkdir(parents=True, exist_ok=True)
            for r in runs:
                if r["ok"]:
                    dets = [d for d in r["detections"] if d.confidence >= conf]
                    cv2.imwrite(str(odir / r["file"]), draw_detections(r["image"], dets))

    meta = {
        "model": settings.model_name, "device": detector.device, "img_size": settings.img_size,
        "enhance": args.enhance, "repeat": args.repeat, "images": len(gt),
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2), encoding="utf-8")
    (OUT / "results.md").write_text(to_markdown(results, meta), encoding="utf-8")

    # Console summary
    print(f"\nEvaluated {len(gt)} images  (model={meta['model']}, device={meta['device']}, "
          f"CLAHE={'on' if args.enhance else 'off'})\n")
    print(f"{'conf':>5} {'accuracy':>9} {'fp_rate':>8} {'avg_ms':>7} {'avg_conf':>9} {'reliab.':>8}")
    for res in results:
        s = res["summary"]
        print(f"{s['conf_threshold']:>5} {s['accuracy']:>9.1%} {s['fp_rate']:>8.1%} "
              f"{s['avg_inference_ms']:>7} {s['avg_confidence']:>9} {s['reliability']:>8.0%}")
    print(f"\nWrote {OUT / 'results.md'}")


if __name__ == "__main__":
    main()
