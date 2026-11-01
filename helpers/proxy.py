#!/usr/bin/env python3
"""A cópia leve (proxy) de cada gravação inteira, para o editor mostrar e tocar o que o cut.mp4 não tem.

O cut.mp4 só tem o que ficou no corte. Puxar a ponta de uma tomada para recuperar uma fala cortada
(pela pessoa ou pelo agente) mostrava o último quadro parado e tocava a tomada seguinte, e o quadro
da alça vinha da gravação em 4K: HEVC 10 bits com HDR leva de 9 a 13 s por quadro numa máquina
ocupada. Como no CapCut, cada tomada aponta para a gravação inteira: esta cópia (lado menor 540,
H.264, um quadro-chave a cada 15 quadros, cor já em Rec.709, som no nível do corte) é feita uma vez
por gravação, em segundo plano e com prioridade baixa, e dela saem o quadro da alça (~50 ms) e o
trecho recuperado tocando.

    uv run python -X utf8 helpers/proxy.py gerar <edit> [--primeiro NOME]
    uv run python -X utf8 helpers/proxy.py estado <edit>

Os tempos da cópia são os da gravação (o mesmo `-ss` vale nos dois). Fica em
<edit>/.preview_cache/proxy/<nome>-<chave>.mp4; a chave muda se a gravação mudar. `prioridade.txt`
na mesma pasta diz qual gravação vem antes (o servidor escreve a da tomada que a pessoa mexeu).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render  # noqa: E402  (a mesma conversão de cor do corte)

PASTA = Path(".preview_cache") / "proxy"
LADO = 540            # o lado menor da cópia
GOP = 15              # um quadro-chave a cada meio segundo: a busca é imediata
ALVO_LUFS = -14.0     # o nível do cut.mp4 (o loudnorm do render)
TRAVA_VELHA_S = 1800  # trava de quem morreu sem apagar


def _pasta(edit: Path) -> Path:
    return Path(edit) / PASTA


def chave(fonte: Path) -> str:
    st = Path(fonte).stat()
    base = f"{Path(fonte).resolve()}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]


def caminho(edit: Path, fonte: Path) -> Path:
    return _pasta(edit) / f"{Path(fonte).stem}-{chave(fonte)}.mp4"


def pronto(edit: Path, fonte: Path) -> Path | None:
    """A cópia desta gravação, se já existe inteira."""
    try:
        p = caminho(edit, fonte)
    except OSError:
        return None
    return p if p.is_file() else None


def fontes(edit: Path) -> dict[str, Path]:
    """As gravações do edl.json do projeto, na ordem dele (só as que existem)."""
    edit = Path(edit)
    try:
        estado = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        estado = {}
    try:
        edl = json.loads((edit / str(estado.get("edl") or "edl.json")).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    saida: dict[str, Path] = {}
    for nome, rel in (edl.get("sources") or {}).items():
        p = Path(rel)
        p = p if p.is_absolute() else edit / p
        if p.is_file() and p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"):
            saida[nome] = p.resolve()
    return saida


def _duracao(fonte: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(fonte)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def ganho_db(fonte: Path) -> float | None:
    """O ganho que leva o som da gravação ao nível do corte (None: sem som)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(fonte), "-vn",
                        "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r'"input_i"\s*:\s*"(-?[\d.]+|-inf)"', r.stderr)
    if not m or m.group(1) == "-inf":
        return None
    return max(-10.0, min(20.0, ALVO_LUFS - float(m.group(1))))


def filtro_video(fonte: Path) -> str:
    escala = (f"scale='if(gt(iw,ih),-2,{LADO})':'if(gt(iw,ih),{LADO},-2)':flags=bilinear")
    if render.is_hdr_source(fonte):
        return f"{escala},{render.TONEMAP_CHAIN}"
    cor = render.wide_gamut_chain(fonte)
    return f"{escala},{cor},format=yuv420p" if cor else f"{escala},format=yuv420p"


def comando(fonte: Path, destino: Path, ganho: float | None, placa: bool) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-nostats", "-y", "-progress", "pipe:1"]
    if placa:
        cmd += ["-hwaccel", "d3d11va"]  # decodificar na placa alivia o processador (Windows)
    cmd += ["-i", str(fonte), "-map", "0:v:0", "-map", "0:a:0?", "-vf", filtro_video(fonte),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-g", str(GOP), "-keyint_min", str(GOP),
            "-sc_threshold", "0", "-pix_fmt", "yuv420p"]
    if ganho is not None:
        cmd += ["-af", f"volume={ganho:.2f}dB,alimiter=limit=0.89:level=0"]
    cmd += ["-c:a", "aac", "-b:a", "96k", "-ac", "2", "-ar", "48000", "-movflags", "+faststart",
            "-f", "mp4", str(destino)]
    return cmd


def _abaixo_do_normal() -> int:
    return getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _escrever(p: Path, dado: dict) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False), encoding="utf-8")
    for i in range(20):  # o servidor lê este arquivo o tempo todo: no Windows a troca espera
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)


def _rodar(cmd: list[str], total: float, avisa) -> int:
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", creationflags=_abaixo_do_normal())
    for linha in proc.stdout:
        if linha.startswith("out_time_us=") and total > 0:
            try:
                avisa(min(0.99, int(linha.split("=", 1)[1]) / 1e6 / total))
            except ValueError:
                pass
    proc.wait()
    return proc.returncode


def gerar(fonte: Path, destino: Path, avisa=lambda f: None) -> Path:
    """Faz a cópia de uma gravação. Grava num arquivo à parte e só troca no fim: quem lê nunca vê
    uma cópia pela metade."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.stem + ".parte.mp4")
    total, ganho = _duracao(fonte), ganho_db(fonte)
    rc = 1
    if os.name == "nt":
        rc = _rodar(comando(fonte, tmp, ganho, placa=True), total, avisa)
    if rc != 0:  # sem placa (ou ela recusou este arquivo): o processador faz
        rc = _rodar(comando(fonte, tmp, ganho, placa=False), total, avisa)
    if rc != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"a cópia leve de {fonte.name} falhou (ffmpeg {rc})")
    for i in range(20):
        try:
            os.replace(tmp, destino)
            break
        except PermissionError:
            time.sleep(0.25)
    else:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"não deu para gravar {destino.name}")
    return destino


def _travar(destino: Path) -> Path | None:
    trava = destino.with_suffix(".trava")
    try:
        if trava.exists() and time.time() - trava.stat().st_mtime > TRAVA_VELHA_S:
            trava.unlink(missing_ok=True)
        fd = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return trava
    except FileExistsError:
        return None


def _proxima(edit: Path, ja: set[str]) -> tuple[str, Path] | None:
    todas = fontes(edit)
    try:
        primeiro = (_pasta(edit) / "prioridade.txt").read_text(encoding="utf-8").strip()
    except OSError:
        primeiro = ""
    ordem = ([primeiro] if primeiro in todas else []) + [n for n in todas if n != primeiro]
    for nome in ordem:
        if nome not in ja and not pronto(edit, todas[nome]):
            return nome, todas[nome]
    return None


def gerar_todas(edit: Path) -> int:
    """Uma gravação por vez, a de prioridade primeiro (ela é relida antes de cada uma)."""
    edit = Path(edit).resolve()
    pasta = _pasta(edit)
    pasta.mkdir(parents=True, exist_ok=True)
    andamento = pasta / "andamento.json"
    feitas: set[str] = set()
    erros: dict[str, str] = {}
    while True:
        prox = _proxima(edit, feitas)
        if not prox:
            break
        nome, fonte = prox
        feitas.add(nome)
        destino = caminho(edit, fonte)
        trava = _travar(destino)
        if not trava:  # outro processo já está fazendo esta
            continue
        try:
            def avisa(f, nome=nome):
                _escrever(andamento, {"fonte": nome, "fracao": round(f, 3), "pid": os.getpid(), "quando": time.time()})
            avisa(0.0)
            gerar(fonte, destino, avisa)
        except (OSError, RuntimeError) as e:
            erros[nome] = str(e)
        finally:
            trava.unlink(missing_ok=True)
    _escrever(andamento, {"fonte": None, "fracao": 1.0, "pid": os.getpid(), "quando": time.time(), "erros": erros})
    return 1 if erros else 0


def estado(edit: Path) -> dict:
    """O que o editor lê: cada gravação pronta ou não, e a que está sendo feita agora."""
    edit = Path(edit)
    todas = fontes(edit)
    try:
        a = json.loads((_pasta(edit) / "andamento.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        a = {}
    return {"fontes": {n: bool(pronto(edit, p)) for n, p in todas.items()},
            "fazendo": a.get("fonte"), "fracao": a.get("fracao"), "erros": a.get("erros") or {}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("acao", choices=("gerar", "estado"))
    ap.add_argument("edit", type=Path)
    ap.add_argument("--primeiro", help="o nome (do edl.json) da gravação que vem antes")
    a = ap.parse_args()
    if a.acao == "estado":
        print(json.dumps(estado(a.edit), ensure_ascii=False))
        return 0
    if a.primeiro:
        _pasta(a.edit).mkdir(parents=True, exist_ok=True)
        (_pasta(a.edit) / "prioridade.txt").write_text(a.primeiro, encoding="utf-8")
    return gerar_todas(a.edit)


if __name__ == "__main__":
    sys.exit(main())
