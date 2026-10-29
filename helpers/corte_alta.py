#!/usr/bin/env python3
"""O corte em alta resolução, para o zoom do vídeo final ficar nítido (`public/cut-alta.mp4`).

O Remotion amplia a imagem de base para o enquadre de cada tomada e para o zoom da câmera. Sobre o
cut.mp4 de 1080, um enquadre de 1,7× amolece a imagem; sobre um corte da gravação em 4K, fica nítido
(medido no Reels 1, 29/10/2026). Este helper faz esse corte quando ele serve:

- a saída é vertical (Reels, TikTok, Shorts) e TODA gravação do edl.json tem o lado menor com 2× ou
  mais da saída (2160 para 1080x1920);
- algum zoom passa de 1,25×: o enquadre de uma tomada (`largura` / 1080) ou a câmera (`zooms` +
  `pushIn`, ligada).

Como: o render.py com o MESMO edl.json e `--lado-maior 3840`, numa pasta à parte (`<edit>/.alta/`,
para não trocar o `clips_graded/` nem o `edl.json` do corte); confere que o corte alto tem os mesmos
quadros do cut.mp4 (a mesma contagem e o alto reduzido parecido com o cut: PSNR ≥ 30 dB em quadros
espalhados); o efeitos_render.py desenha nele os filtros do editor (`public/cut-alta.mp4`); e o
edit-data ganha `corteAlta: true`, com o qual o template usa esse arquivo na imagem de base. As cenas,
os recortes da pessoa e as legendas continuam no cut.mp4. Sem precisar, apaga o que sobrou e grava
`corteAlta: false`.

    uv run python -X utf8 helpers/corte_alta.py <edit> [--remotion <edit>/remotion] [--forcar]

O gerar.py chama sozinho antes de cada render com a Fase 2.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HELPERS = Path(__file__).resolve().parent
SAIDA = 1080  # o lado menor da saída vertical
LADO_ALTO = 3840
ZOOM_MINIMO = 1.25
PSNR_MINIMO = 30.0
ARQUIVO = "cut-alta.mp4"


def _ler(p: Path) -> dict:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _sondar(video: Path) -> dict:
    """Largura, altura (já girada), quadros e fps do vídeo."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=width,height,nb_read_packets,r_frame_rate:stream_side_data=rotation:stream_tags=rotate",
                        "-of", "json", str(video)], capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    rot = abs(int(float((s.get("tags") or {}).get("rotate", 0) or next(
        (d.get("rotation", 0) for d in s.get("side_data_list") or []), 0))))
    w, h = int(s["width"]), int(s["height"])
    if rot in (90, 270):
        w, h = h, w
    n, d = s.get("r_frame_rate", "30/1").split("/")
    return {"largura": w, "altura": h, "quadros": int(s.get("nb_read_packets") or 0), "fps": float(n) / float(d or 1)}


def zoom_maximo(edit: Path) -> float:
    """O maior zoom do vídeo final: o enquadre das tomadas e a câmera do edit-data."""
    edl = _ler(Path(edit) / "edl.json")
    zs = [float(r["enquadre"].get("largura") or r["enquadre"].get("w") or SAIDA) / SAIDA
          for r in edl.get("ranges") or [] if isinstance(r.get("enquadre"), dict)]
    state = _ler(Path(edit) / "state.json")
    ed = _ler(Path(edit) / (state.get("editData") or "remotion/public/edit-data.json"))
    cam = ed.get("camera") or {}
    if cam.get("enabled"):
        zs += [float(z) + float(cam.get("pushIn") or 0) for z in cam.get("zooms") or [] if isinstance(z, (int, float))]
    return max(zs, default=1.0)


def fontes_altas(edit: Path) -> bool:
    """Toda gravação do edl.json tem o lado menor com pelo menos 2× o da saída."""
    edl = _ler(Path(edit) / "edl.json")
    usadas = {r.get("source") for r in edl.get("ranges") or []}
    caminhos = [Path(p) for k, p in (edl.get("sources") or {}).items() if k in usadas]
    if not caminhos or not all(p.is_file() for p in caminhos):
        return False
    return all(min(_sondar(p)["largura"], _sondar(p)["altura"]) >= 2 * SAIDA for p in caminhos)


def precisa(edit: Path) -> bool:
    """O zoom primeiro (só lê JSON); os arquivos depois, e um que não abre conta como "não precisa"."""
    cut = Path(edit) / "cut.mp4"
    if zoom_maximo(edit) <= ZOOM_MINIMO or not cut.is_file():
        return False
    try:
        info = _sondar(cut)
        if info["altura"] <= info["largura"]:  # deitado: longform, a resolução já é a da gravação
            return False
        return fontes_altas(edit)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, IndexError):
        return False


def _quadro(video: Path, n: int, fps: float, w: int, h: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, n / fps - 1):.3f}", "-i", str(video), "-copyts",
                          "-vf", f"select='gte(t,{(n - 0.5) / fps:.4f})',scale={w}:{h}:flags=area", "-frames:v", "1",
                          "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8)[: w * h].astype(float)


def conferir(cut: Path, alta: Path, amostras: int = 6) -> dict:
    """O corte alto tem os quadros do cut.mp4: a mesma contagem e cada quadro amostrado parecido."""
    a, b = _sondar(cut), _sondar(alta)
    if a["quadros"] != b["quadros"]:
        raise RuntimeError(f"o corte alto tem {b['quadros']} quadros e o cut.mp4 {a['quadros']}: não é o mesmo corte")
    w, h = a["largura"] // 4, a["altura"] // 4
    psnrs = []
    for n in np.linspace(2, a["quadros"] - 3, amostras).astype(int):
        x, y = _quadro(cut, int(n), a["fps"], w, h), _quadro(alta, int(n), b["fps"], w, h)
        mse = float(np.mean((x - y) ** 2)) if len(x) == len(y) == w * h else 1e9
        psnrs.append(99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse))
    if min(psnrs) < PSNR_MINIMO:
        raise RuntimeError(f"o corte alto não bate com o cut.mp4 (PSNR mínimo {min(psnrs):.1f} dB)")
    return {"quadros": a["quadros"], "psnr_min": round(min(psnrs), 1), "largura": b["largura"], "altura": b["altura"]}


def _edit_data(edit: Path) -> Path:
    state = _ler(Path(edit) / "state.json")
    return Path(edit) / (state.get("editData") or "remotion/public/edit-data.json")


def _marcar(edit: Path, ligado: bool, edit_data: Path | None = None) -> None:
    p = Path(edit_data) if edit_data else _edit_data(edit)
    if not p.is_file():
        return
    ed = _ler(p)
    if bool(ed.get("corteAlta")) == ligado:
        return
    ed["corteAlta"] = ligado
    p.write_bytes((json.dumps(ed, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def renderizar(edit: Path) -> Path:
    """O corte alto pelo render.py, numa pasta à parte, com as opções do corte de agora."""
    edit = Path(edit)
    pasta = edit / ".alta"
    pasta.mkdir(exist_ok=True)
    shutil.copyfile(edit / "edl.json", pasta / "edl.json")
    saida = edit / ARQUIVO
    tmp = edit / f".{ARQUIVO}.tmp.mp4"
    try:
        subprocess.run([sys.executable, "-X", "utf8", str(HELPERS / "render.py"), str(pasta / "edl.json"), "-o", str(tmp),
                        "--como-antes", "--no-subtitles", "--no-loudnorm", "--lado-maior", str(LADO_ALTO)], check=True)
        tmp.replace(saida)
    finally:
        tmp.unlink(missing_ok=True)
        shutil.rmtree(pasta, ignore_errors=True)
    return saida


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def aplicar(edit: Path, remotion: Path | None = None, forcar: bool = False, edit_data: Path | None = None) -> dict:
    """Faz (ou desfaz) o corte alto do projeto e marca o edit-data (`edit_data`: o do Remotion que vai
    renderizar, quando não é o do state.json). Devolve o que fez."""
    import efeitos_render  # mesma pasta deste arquivo; só aqui, ele puxa o Remotion

    edit = Path(edit)
    rem = Path(remotion) if remotion else edit / "remotion"
    pub = rem / "public" / ARQUIVO
    if not (forcar or precisa(edit)):
        pub.unlink(missing_ok=True)
        (edit / ARQUIVO).unlink(missing_ok=True)
        _marcar(edit, False, edit_data)
        return {"feito": False, "zoom": round(zoom_maximo(edit), 2)}
    alta, cut = edit / ARQUIVO, edit / "cut.mp4"
    if _mtime(alta) < max(_mtime(cut), _mtime(edit / "edl.json")):
        renderizar(edit)
    r = conferir(cut, alta)
    # os filtros do editor desenhados no corte alto: só quando ele ou o efeitos.json mudaram (leva minutos)
    if _mtime(pub) < max(_mtime(alta), _mtime(edit / "efeitos.json")):
        efeitos_render.aplicar(edit, rem, corte=alta, saida=pub)
    _marcar(edit, True, edit_data)
    return {"feito": True, "zoom": round(zoom_maximo(edit), 2), **r}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--remotion", type=Path)
    ap.add_argument("--forcar", action="store_true", help="faz o corte alto mesmo sem zoom acima de 1,25×")
    a = ap.parse_args()
    r = aplicar(a.edit, a.remotion, a.forcar)
    if r["feito"]:
        print(f"corte alto pronto: {r['largura']}x{r['altura']}, {r['quadros']} quadros, PSNR mínimo "
              f"{r['psnr_min']} dB contra o cut.mp4 (zoom máximo {r['zoom']}×)")
    else:
        print(f"sem corte alto: zoom máximo {r['zoom']}× ou gravação abaixo de 2× a saída")
    return 0


if __name__ == "__main__":
    sys.exit(main())
