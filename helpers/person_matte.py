"""Person matting → a transparent-background foreground video, for the
"element behind the subject" effect (text/image sits between the person and the
background).

Uses Robust Video Matting (RVM) — a recurrent video matting model with clean,
temporally-stable hair edges. Reads a video, estimates the person + alpha per
frame (carrying recurrent state for stability), and writes an **alpha .mov**
(ProRes 4444 `yuva444p10le`) of the person over transparency; `.webm` (VP9
alpha) only when you name the output that way. In Remotion, layer:

    <DynamicVideo src="cut.mp4">     {/* base: background + person */}
      {behindElement}                {/* the thing that goes behind */}
    </DynamicVideo>
    <DynamicVideo src="fg.mov" />    {/* person on top → element sits behind */}

Runs on ONNX Runtime by default (a base dependency of the kit): the RVM weights download once
(~15 MB, checked by sha256) to ~/.cutmind/recorte. Measured against torch.hub on 107 real frames:
the same alpha (largest difference 1/255) and 1.4x faster end to end. `--motor torch` (and
`--model resnet50`, which only torch runs) needs the `matting` extra: `uv sync --extra matting`.

Usage:
    python helpers/person_matte.py cut.mp4 -o remotion/public/fg.mov
    python helpers/person_matte.py cut.mp4 -o fg.mov --model resnet50   # higher quality, slower
    python helpers/person_matte.py cut.mp4 -o fg.mov --start 8 --duration 6
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # some RVM ops lack MPS kernels

import cv2
import numpy as np


def pick_device(requested: str) -> str:
    import torch
    if requested != "auto":
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def auto_downsample_ratio(h: int, w: int) -> float:
    # RVM guidance: keep the long side around 512px for HD content.
    return min(512 / max(h, w), 1.0)


def ler_janela(cap, start_f: int, n: int):
    """Frames start_f .. start_f+n-1 of an open cv2.VideoCapture, as RGB, one at a
    time. Frame 0 of the matte must be frame start_f of the cut: the effects lay the
    matte over the base picture frame by frame (tests/test_cenas.py checks the seek)."""
    if start_f:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    for _ in range(n):
        ok, bgr = cap.read()
        if not ok:
            return
        yield cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


# ---- engines: the same RVM through ONNX Runtime (a base dependency, the weights are data checked
# by sha256) or through torch.hub (the `matting` extra; downloads and runs the repo's code) ----
RVM_ONNX = {"arquivo": "rvm_mobilenetv3_fp32.onnx", "tamanho": 14_975_696,
            "url": "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx",
            "sha256": "88d4531297118f595bf2fd60f6f566aec2e559393802d1f436c380f0cbbd2828"}


def pasta_recorte() -> Path:
    return Path(os.environ.get("CUTMIND_RECORTE_DIR") or Path.home() / ".cutmind" / "recorte")


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def modelo_onnx() -> Path:
    """The RVM weights for ONNX Runtime, downloaded once (~15 MB) and checked by size and sha256."""
    m = RVM_ONNX
    destino = pasta_recorte() / m["arquivo"]
    if destino.is_file() and destino.stat().st_size == m["tamanho"]:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    part = destino.with_name(destino.name + ".part")
    print(f"downloading the matting model ({m['tamanho'] // 1_000_000} MB, once)…", flush=True)
    try:
        req = urllib.request.Request(m["url"], headers={"User-Agent": "cutmind-recorte"})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            while bloco := r.read(1 << 20):
                f.write(bloco)
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"could not download {m['arquivo']} ({e.__class__.__name__}); try again")
    if part.stat().st_size != m["tamanho"] or _sha256(part) != m["sha256"]:
        part.unlink()
        sys.exit(f"{m['arquivo']} arrived different from the expected one and was deleted; try again")
    part.replace(destino)
    return destino


class MotorOnnx:
    """RVM MobileNetV3 on ONNX Runtime (CPU). One call per frame, in order: the recurrent state
    of each frame feeds the next. Returns (alpha HxW 0..1, foreground colour HxWx3 0..1)."""

    def __init__(self, ratio: float):
        import onnxruntime as ort
        self.sess = ort.InferenceSession(str(modelo_onnx()), providers=["CPUExecutionProvider"])
        self.rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
        self.ratio = np.array([ratio], np.float32)

    def __call__(self, rgb: np.ndarray):
        src = (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
        fgr, pha, *self.rec = self.sess.run(None, {"src": src, "r1i": self.rec[0], "r2i": self.rec[1],
                                                    "r3i": self.rec[2], "r4i": self.rec[3], "downsample_ratio": self.ratio})
        return np.clip(pha[0, 0], 0, 1), np.clip(fgr[0].transpose(1, 2, 0), 0, 1)


class MotorTorch:
    """RVM through torch.hub (the `matting` extra). Same contract as MotorOnnx."""

    def __init__(self, model: str, device: str, ratio: float):
        import torch
        self.torch, self.device, self.ratio = torch, pick_device(device), ratio
        print(f"device: {self.device} | model: {model}")
        print("loading RVM model (torch.hub)…")
        self.model = torch.hub.load("PeterL1n/RobustVideoMatting", model, trust_repo=True).eval().to(self.device)
        self.rec = [None] * 4

    def __call__(self, rgb: np.ndarray):
        with self.torch.no_grad():
            src = self.torch.from_numpy(rgb).float().div(255.0).permute(2, 0, 1).unsqueeze(0).to(self.device)
            fgr, pha, *self.rec = self.model(src, *self.rec, downsample_ratio=self.ratio)
            return (pha.clamp(0, 1)[0, 0].cpu().numpy(),
                    fgr.clamp(0, 1)[0].permute(1, 2, 0).cpu().numpy())


def compor(rgb: np.ndarray, a: np.ndarray, fgr: np.ndarray, cor: str = "original") -> np.ndarray:
    """The RGBA frame of the matte.

    `original`: the source colour with the alpha. Right when the person goes back over the SAME
    background (text behind the person): the edge blends into the base with no seam; RVM's
    foreground colour alone would rim the person with a glow.
    `misturada`: on a NEW background the source colour of the soft edge still carries the old
    background (a green fringe from a green wall). The edge takes RVM's foreground colour instead,
    as much as the pixel is background: colour = source·α + foreground·(1−α), as CapCut does."""
    if cor == "misturada":
        k = a[..., None]
        cores = rgb.astype(np.float32) * k + fgr * 255.0 * (1 - k)
        rgb = np.clip(cores + 0.5, 0, 255).astype(np.uint8)
    return np.dstack([rgb, (a * 255.0).astype(np.uint8)[..., None]])


def main() -> None:
    ap = argparse.ArgumentParser(description="Matte the person out of a video → alpha .mov (RVM)")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True,
                    help="Output .mov (ProRes 4444 alpha, the default); .webm = VP9 alpha, less reliable")
    ap.add_argument("--model", choices=["mobilenetv3", "resnet50"], default="mobilenetv3",
                    help="mobilenetv3 = fast/good (default); resnet50 = best edges, slower")
    ap.add_argument("--device", default="auto", help="auto | mps | cuda | cpu")
    ap.add_argument("--downsample", type=float, default=None,
                    help="RVM downsample_ratio (default: auto from resolution)")
    ap.add_argument("--start", type=float, default=0.0, help="Start time (s)")
    ap.add_argument("--duration", type=float, default=None, help="Duration (s); default = to end")
    ap.add_argument("--crf", type=int, default=20, help="VP9 quality (lower = better)")
    ap.add_argument("--motor", choices=["auto", "torch", "onnx"], default="auto",
                    help="auto = onnx for mobilenetv3 (no extra install), torch for resnet50; "
                         "torch = torch.hub (the matting extra)")
    ap.add_argument("--cor", choices=["original", "misturada"], default="original",
                    help="edge colour: original (same background behind) or misturada (new background)")
    args = ap.parse_args()
    if args.motor == "auto":
        args.motor = "onnx" if args.model == "mobilenetv3" else "torch"
    if args.motor == "onnx" and args.model != "mobilenetv3":
        sys.exit("--motor onnx runs mobilenetv3 only; use --motor torch for resnet50")

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        sys.exit(f"cannot open {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    start_f = int(round(args.start * fps))
    end_f = total if args.duration is None else min(total, start_f + int(round(args.duration * fps)))
    n_frames = max(0, end_f - start_f)
    ratio = args.downsample if args.downsample is not None else auto_downsample_ratio(H, W)
    print(f"input: {W}x{H} @ {fps:.3f}fps | frames {start_f}..{end_f} ({n_frames}) | downsample_ratio={ratio:.3f}")

    motor = MotorOnnx(ratio) if args.motor == "onnx" else MotorTorch(args.model, args.device, ratio)
    print(f"engine: {args.motor} | edge colour: {args.cor}")

    # ffmpeg sink: raw RGBA frames → alpha video. ProRes 4444 (.mov) is the
    # reliable alpha format across ffmpeg builds AND is decoded with alpha by
    # Remotion's renderer. VP9/VP8 WebM alpha is lighter but silently drops the
    # alpha channel on some libvpx builds (e.g. Homebrew ffmpeg 8.x) — so .mov
    # is the default. `.webm` is honored if you explicitly ask for it.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() == ".webm":
        codec = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
                 "-b:v", "0", "-crf", str(args.crf)]
        print("warning: encoding VP9 alpha WebM — verify alpha survived (some ffmpeg builds drop it); .mov/ProRes is safer")
    else:
        # ProRes 4444 carries a real alpha plane; qscale ~6 keeps files sane.
        codec = ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
                 "-qscale:v", "6"]
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", f"{fps}",
         "-i", "-"] + codec + [str(args.output)],
        stdin=subprocess.PIPE,
    )

    done, t0 = 0, time.perf_counter()
    for rgb in ler_janela(cap, start_f, n_frames):
        a, fgr = motor(rgb)
        ff.stdin.write(compor(rgb, a, fgr, args.cor).tobytes())
        done += 1
        if done % 60 == 0 or done == n_frames:
            print(f"  matted {done}/{n_frames}", flush=True)

    cap.release()
    ff.stdin.close()
    ff.wait()
    print(f"done: {args.output}  ({done} frames, {done / max(1e-6, time.perf_counter() - t0):.2f} frames/s)")


if __name__ == "__main__":
    main()
