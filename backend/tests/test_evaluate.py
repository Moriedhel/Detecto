"""Unit tests for the evaluation metrics in scripts/evaluate.py (no model needed)."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate.py"
_spec = importlib.util.spec_from_file_location("evaluate", _path)
evaluate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate)


def _run(file, people, confs, ms=100.0, ok=True):
    return {
        "file": file, "people": people, "conditions": [], "ok": ok, "error": None if ok else "boom",
        "detections": [SimpleNamespace(confidence=c) for c in confs],
        "width": 640, "height": 480, "inference_ms": ms, "end_to_end_ms": ms + 10,
    }


def test_count_based_metrics():
    runs = [
        _run("a.jpg", 2, [0.9, 0.8]),             # perfect
        _run("b.jpg", 4, [0.9, 0.6, 0.3]),        # misses 1 at 0.25, 2 at 0.5
        _run("c.jpg", 0, [0.55]),                 # 1 false positive
    ]
    s, rows = evaluate.score(runs, 0.25)
    assert (s["total_actual"], s["total_detected"]) == (6, 6)
    assert s["total_correct"] == 5 and s["total_missed"] == 1 and s["total_extra"] == 1
    assert s["accuracy"] == pytest.approx(5 / 6, abs=1e-4)
    assert s["fp_rate"] == pytest.approx(1 / 6, abs=1e-4)
    assert s["reliability"] == 1.0

    s, _ = evaluate.score(runs, 0.5)
    assert s["total_detected"] == 5 and s["total_correct"] == 4
    assert s["avg_confidence"] == pytest.approx((0.9 + 0.8 + 0.9 + 0.6 + 0.55) / 5, abs=1e-4)


def test_failed_image_lowers_reliability():
    runs = [_run("a.jpg", 1, [0.9]), _run("bad.jpg", 3, [], ok=False)]
    s, rows = evaluate.score(runs, 0.4)
    assert s["reliability"] == 0.5
    assert s["accuracy"] == 1.0  # computed over processed images only
    assert rows[1]["ok"] is False


def test_target_checks():
    assert evaluate.passes("accuracy", 0.85) and not evaluate.passes("accuracy", 0.84)
    assert evaluate.passes("fp_rate", 0.10) and not evaluate.passes("fp_rate", 0.11)
    assert evaluate.passes("avg_inference_ms", 300)
    assert not evaluate.passes("avg_confidence", None)
