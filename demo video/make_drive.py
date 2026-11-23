"""Build the simulated dashcam feed for the demo's camera ride: demo video/build/drive.y4m (~1.2 GB, not committed).

    python "demo video/make_drive.py"

Real Indian road photos from RDD2022 India (CC BY-SA 4.0, ml/raw/parquet/RDD2022_India.zip, fetched by
ml/fetch_rdd_india.py): six frames with annotated potholes and two with water-filled potholes. Each photo becomes
6 s of slow push-in (long holds keep the ~1 fps overlays on the frame they describe), like riding towards it. Chrome plays the file as the camera
(--use-file-for-fake-video-capture), so the app's real on-device models run on it.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kit  # noqa: E402

ZIP = HERE.parent / "ml" / "raw" / "parquet" / "RDD2022_India.zip"
# potholes first, then the two flooded frames (the feed restarts when the ride opens the camera), then more potholes
FRAMES = ["003366", "006127", "007198", "001809", "003624", "001673", "006756", "001561"]


def main() -> None:
    out = HERE / "build" / "drive.y4m"
    out.parent.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="kestrel-drive-"))
    z = zipfile.ZipFile(ZIP)
    clips = []
    for i, k in enumerate(FRAMES):
        img = tmp / f"{k}.jpg"
        img.write_bytes(z.read(f"India/train/images/India_{k}.jpg"))
        clip = tmp / f"clip{i}.mp4"
        # 720x720 source: keep the road band, then push in slowly towards the lower middle
        vf = ("crop=720:405:0:250,scale=2560:1440,zoompan=z='1+0.0009*on':x='iw/2-(iw/zoom/2)':y='ih*0.62-(ih/zoom*0.62)'"
              ":d=180:s=1280x720:fps=30,format=yuv420p")
        kit.ff("-loop", "1", "-i", str(img), "-vf", vf, "-t", "6", "-r", "30", str(clip))
        clips.append(clip)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips))
    kit.ff("-f", "concat", "-safe", "0", "-i", str(lst), "-pix_fmt", "yuv420p", "-f", "yuv4mpegpipe", str(out))
    subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(tmp)], check=False)
    print("wrote", out)


if __name__ == "__main__":
    main()
