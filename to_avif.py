"""
Convert rendered PNG frames into an AVIF sequence for the web.

  python to_avif.py frames web/frames --crf 32 --width 1920

Uses ffmpeg with libaom-av1 instead of avifenc, so any ffmpeg build that
includes libaom works. Frames are encoded in parallel.
"""

import argparse
import concurrent.futures as cf
import os
import shutil
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument("src", help="folder with the PNG frames")
ap.add_argument("dst", help="output folder for the AVIF frames (created if missing)")
ap.add_argument("--crf", type=int, default=32, help="lower = higher quality, larger files")
ap.add_argument("--width", type=int, default=0, help="output width in px, 0 = no scaling")
ap.add_argument("--cpu-used", type=int, default=6, help="0-8, higher = faster encode, larger files")
ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4, help="parallel encodes")
a = ap.parse_args()

if not shutil.which("ffmpeg"):
    sys.exit("ffmpeg not found on PATH (install an ffmpeg build with libaom-av1)")

os.makedirs(a.dst, exist_ok=True)
frames = sorted(f for f in os.listdir(a.src) if f.lower().endswith(".png"))
if not frames:
    sys.exit(f"no PNG files in {a.src}")


def encode(name):
    src = os.path.join(a.src, name)
    out = os.path.join(a.dst, os.path.splitext(name)[0] + ".avif")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src]
    if a.width:
        cmd += ["-vf", f"scale={a.width}:-2:flags=lanczos"]
    cmd += [
        "-c:v", "libaom-av1", "-still-picture", "1",
        "-crf", str(a.crf), "-cpu-used", str(a.cpu_used),
        "-pix_fmt", "yuv420p", out,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return name, 0, r.stderr.strip()[:200]
    return name, os.path.getsize(out), None


total = 0
errors = []
print(f"{len(frames)} frames -> AVIF (crf {a.crf}, {a.jobs} parallel)")

with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
    for i, (name, size, err) in enumerate(ex.map(encode, frames), 1):
        if err:
            errors.append((name, err))
        total += size
        if i % 24 == 0 or i == len(frames):
            print(f"  {i}/{len(frames)}")

src_bytes = sum(os.path.getsize(os.path.join(a.src, f)) for f in frames)
print(f"\nPNG  : {src_bytes / 1024 / 1024:6.1f} MB")
print(f"AVIF : {total / 1024 / 1024:6.1f} MB  ({total / len(frames) / 1024:.1f} KB/frame)")
for name, err in errors:
    print("ERROR", name, err)
