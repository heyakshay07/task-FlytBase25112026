"""Optional bridge from REAL video to the pipeline (the assignment allows text-simulated frames).

    python -m drone_analyst.vlm path/to/video.mp4 --out data/real_feed.jsonl --every 2

Samples a frame every N seconds with OpenCV, captions it with a Hugging Face BLIP model and
writes the same JSONL schema as the simulator, with synthetic telemetry. Captions are then
parsed by `TextPerceiver` like any other description.

Needs: pip install opencv-python transformers torch pillow
NOTE: written for the README's "real video" path; it downloads a model on first run and was
not exercised in the offline environment this repo was generated in.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def caption_video(path: str, every_s: float = 2.0, start: str = "2026-11-24T00:00:00",
                  location: str = "Main Gate", model: str = "Salesforce/blip-image-captioning-base"):
    import cv2
    from PIL import Image
    from transformers import BlipForConditionalGeneration, BlipProcessor

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise FileNotFoundError(f"Could not open video: {path}")
    proc = BlipProcessor.from_pretrained(model)
    net = BlipForConditionalGeneration.from_pretrained(model)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step, t0, i = max(round(fps * every_s), 1), datetime.fromisoformat(start), 0
    frame_id = 0
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            if i % step == 0:
                img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                ids = net.generate(**proc(img, return_tensors="pt"), max_new_tokens=40)
                frame_id += 1
                yield {"frame_id": frame_id,
                       "timestamp": (t0 + timedelta(seconds=round(i / fps))).isoformat(timespec="seconds"),
                       "telemetry": {"location": location, "x": 0.0, "y": 0.0, "altitude_m": 25.0,
                                     "battery_pct": 80.0, "speed_mps": 0.0, "heading_deg": 0.0},
                       "description": proc.decode(ids[0], skip_special_tokens=True)}
            i += 1
    finally:
        cap.release()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("--out", default="data/real_feed.jsonl")
    ap.add_argument("--every", type=float, default=2.0); ap.add_argument("--start", default="2026-11-24T00:00:00")
    a = ap.parse_args()
    if not Path(a.video).is_file():
        ap.error(f"video file not found: {a.video}")
    rows = iter(caption_video(a.video, a.every, a.start))
    first = next(rows, None)
    if first is None:
        ap.error(f"no readable frames in video: {a.video}")
    with open(a.out, "w") as fh:
        for row in (first,):
            fh.write(json.dumps(row) + "\n"); print(row["timestamp"], row["description"])
        for row in rows:
            fh.write(json.dumps(row) + "\n"); print(row["timestamp"], row["description"])
