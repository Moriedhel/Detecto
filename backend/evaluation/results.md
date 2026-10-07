# Detecto evaluation results

- Model: `yolov8n.pt` on `cpu`, input size 1280, CLAHE: off
- Images: 12 (ground truth: `backend/samples/ground_truth.json`)
- Timing: mean of 3 runs per image after warm-up
- Matching is count-based per image (see `scripts/evaluate.py`); overlays in `backend/evaluation/overlays/` were checked by eye to confirm the extra boxes are real false positives
- Run at: 2026-10-07 19:24:39

## Confidence threshold 0.4

| Metric | Description | Target | Result | |
|---|---|---|---|---|
| Detection Accuracy | Correct detections ÷ total visible persons (24/25) | ≥ 85 % | 96.0 % | ✅ |
| False Positives | Extra boxes ÷ all boxes (1/25) | ≤ 10 % | 4.0 % | ✅ |
| Average Inference Time | Model time per image (end-to-end 238.6 ms) | ≤ 1.5 s | 209.3 ms | ✅ |
| Average Confidence | Mean confidence of detections | ≥ 0.7 | 0.6844 | ❌ |
| System Reliability | Images processed without errors (12/12) | 100 % | 100.0 % | ✅ |

| Image | Conditions | Actual | Detected | Missed | Extra | Avg conf | Inference (ms) |
|---|---|---|---|---|---|---|---|
| 01_bedroom_empty.jpg | indoor, no people | 0 | 0 | 0 | 0 | – | 193.7 |
| 02_garage_cat_empty.jpg | indoor, dim, no people | 0 | 0 | 0 | 0 | – | 195.5 |
| 03_living_room_gaming.jpg | indoor, warm light, motion blur | 3 | 3 | 0 | 0 | 0.721 | 220.7 |
| 04_baseball_catcher.jpg | single person, crouching | 1 | 1 | 0 | 0 | 0.671 | 190.2 |
| 05_prom_couple.jpg | indoor, close-up | 2 | 2 | 0 | 0 | 0.695 | 315.5 |
| 06_bikes_path.jpg | outdoor, cut off at edge | 2 | 1 | 1 | 0 | 0.665 | 210.0 |
| 07_street_crossing.jpg | street, occlusion, small/distant | 4 | 4 | 0 | 0 | 0.69 | 175.0 |
| 08_street_statues.jpg | street, dim background, statues | 4 | 5 | 0 | 1 | 0.737 | 216.4 |
| 09_pizza_dinner.jpg | indoor, dim, background person | 1 | 1 | 0 | 0 | 0.481 | 216.8 |
| 10_stable_father_baby.jpg | close-up, overlapping, child | 2 | 2 | 0 | 0 | 0.56 | 206.0 |
| 11_wheel_repair.jpg | single person, crouching | 1 | 1 | 0 | 0 | 0.693 | 171.7 |
| 12_frisbee_team.jpg | outdoor, dusk, group, small/distant | 5 | 5 | 0 | 0 | 0.697 | 200.0 |
