"""
Run this in the same pixi env to overlay ROI on recorded mp4 videos:
    pixi run python scripts/roi_overlay.py D:\Data\2026-07-03_FC

Reads *.locked.arena.json for ROI per box, draws rectangle on every frame,
outputs *_roi.mp4 alongside originals.
"""

import json
import sys
from pathlib import Path

import cv2


def find_locked_session(save_dir: Path):
    for path in save_dir.glob("*.locked.arena.json"):
        data = json.loads(path.read_text("utf-8"))
        return data.get("session", data)
    return None


def roi_normalized(box):
    roi = box.get("roi")
    if not isinstance(roi, dict):
        return None
    sw = float(roi.get("imageWidth", 1920))
    sh = float(roi.get("imageHeight", 1080))
    x = float(roi.get("x", 0)) / sw
    y = float(roi.get("y", 0)) / sh
    w = float(roi.get("width", 0)) / sw
    h = float(roi.get("height", 0)) / sh
    if w <= 0 or h <= 0:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def main():
    if len(sys.argv) < 2:
        print("Usage: pixi run python scripts/roi_overlay.py <save_directory>")
        sys.exit(1)

    save_dir = Path(sys.argv[1]).resolve()
    session = find_locked_session(save_dir)
    if session is None:
        print(f"No locked *.arena.json found in {save_dir}")
        sys.exit(1)

    box_rois = {}
    for box in session.get("boxes", []):
        b_id = box.get("id") or box.get("boxId") or ""
        roi = roi_normalized(box)
        if b_id and roi:
            box_rois[b_id] = roi

    if not box_rois:
        print("No ROI data in session")
        sys.exit(1)

    print(f"Boxes with ROI: {list(box_rois)}\n")

    for mp4 in sorted(save_dir.glob("*.mp4")):
        if mp4.stem.endswith("_roi"):
            continue
        box_id = next((b for b in box_rois if b in mp4.stem), None)
        if box_id is None:
            print(f"  SKIP {mp4.name} — no matching box")
            continue

        roi = box_rois[box_id]
        out = mp4.with_stem(mp4.stem + "_roi")
        if out.exists():
            print(f"  SKIP {mp4.name} — already exists")
            continue

        cap = cv2.VideoCapture(str(mp4))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        rx = int(roi["x"] * w)
        ry = int(roi["y"] * h)
        rw = int(roi["w"] * w)
        rh = int(roi["h"] * h)

        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        print(f"  {mp4.name} → {out.name}  ({w}x{h}  ROI:{rx},{ry} {rw}x{rh})")

        for i in range(total):
            ok, frame = cap.read()
            if not ok:
                break
            cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 2)
            writer.write(frame)
            if (i + 1) % 500 == 0:
                print(f"    {i + 1}/{total}")

        cap.release()
        writer.release()
        print(f"    done\n")

    print("All done.")


if __name__ == "__main__":
    main()
