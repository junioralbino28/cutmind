#!/usr/bin/env python3
"""Separar o áudio de uma tomada: o som da gravação vira um arquivo em `midia/`, no nível do corte.

O editor põe esse arquivo numa faixa de áudio própria, no lugar da fala, e deixa a tomada em 0%: a fala
passa a ser uma camada que a pessoa move para debaixo de outra tomada e apara (edição real de 29/10, a
primeira frase de uma gravação tinha de tocar sobre a entrada muda de outra). O arquivo tem a gravação
INTEIRA, e `corte` diz de onde ele toca, como no CapCut: puxar a ponta da camada recupera o que tinha
ficado fora do corte. É um arquivo por gravação (e por velocidade); separar de novo reaproveita.

    uv run python -X utf8 helpers/separar_audio.py <edit> <gravação> [--velocidade 1.5]

Devolve `arquivo`, `duracao` e `adianta`. Com velocidade, o som sai pelo atempo, que adianta alguns
milissegundos (velocidade_final.adiantamento): quem põe a camada desconta `adianta` do `corte`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import camadas as cam  # noqa: E402
import proxy  # noqa: E402  (o mesmo nível de som da cópia leve, e por ela a mesma chave por gravação)
import render  # noqa: E402  (a mesma cadeia de voz e o mesmo atempo do corte)
import velocidade_final  # noqa: E402

VEL_MIN, VEL_MAX = 0.1, 10.0


class SepararErro(Exception):
    pass


def _ganho(fonte: Path, antes: list[str]) -> float | None:
    """O ganho até o nível do corte, medido depois da cadeia de voz, se o corte passa por ela."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-i", str(fonte), "-vn",
                        "-af", ",".join([*antes, "loudnorm=print_format=json"]), "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r'"input_i"\s*:\s*"(-?[\d.]+|-inf)"', r.stderr)
    if not m or m.group(1) == "-inf":
        return None
    return max(-10.0, min(20.0, proxy.ALVO_LUFS - float(m.group(1))))


def _voz_no_corte(edit: Path) -> bool:
    try:
        estado = json.loads((edit / "state.json").read_text(encoding="utf-8"))
        return bool(json.loads((edit / str(estado.get("edl") or "edl.json")).read_text(encoding="utf-8")).get("voice_master"))
    except (OSError, ValueError):
        return False


def separar(edit: Path, source: object, velocidade: object = 1.0) -> dict:
    edit = Path(edit)
    fonte = proxy.fontes(edit).get(source) if isinstance(source, str) else None
    if fonte is None:
        raise SepararErro("não achei a gravação desta tomada")
    try:
        v = float(velocidade)
    except (TypeError, ValueError):
        raise SepararErro("velocidade inválida") from None
    if not VEL_MIN <= v <= VEL_MAX:
        raise SepararErro("velocidade inválida")
    pasta = edit / cam.MIDIA_DIR
    pasta.mkdir(parents=True, exist_ok=True)
    nome = re.sub(r"[^\w-]+", "-", fonte.stem).strip("-")[:40] or "gravacao"
    marca = "" if abs(v - 1) < 1e-3 else f"-{v:g}x".replace(".", "_")
    destino = pasta / f"audio-{nome}{marca}-{proxy.chave(fonte)[:8]}.m4a"
    if not destino.is_file():
        antes = [render.VOICE_MASTER_CHAIN] if _voz_no_corte(edit) else []
        ganho = _ganho(fonte, antes)
        if ganho is None:
            raise SepararErro("esta gravação não tem som")
        filtros = [*antes, f"volume={ganho:.2f}dB", "alimiter=limit=0.89:level=0", *([] if not marca else [f"atempo={f}" for f in render.atempo_cadeia(v)])]
        tmp = destino.with_name(f".{destino.stem}.{os.getpid()}.tmp.m4a")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(fonte), "-vn", "-af", ",".join(filtros),
                            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(tmp)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode or not tmp.is_file():
            tmp.unlink(missing_ok=True)
            raise SepararErro("o ffmpeg não conseguiu tirar o som desta gravação")
        for n in range(40):  # o Windows recusa a troca enquanto alguém lê o destino
            try:
                os.replace(tmp, destino)
                break
            except PermissionError:
                if n == 39:
                    tmp.unlink(missing_ok=True)
                    raise
                time.sleep(0.05)
    duracao = proxy._duracao(destino)
    if not duracao:
        raise SepararErro("o ffmpeg não conseguiu tirar o som desta gravação")
    adianta = 0.0 if not marca else velocidade_final.adiantamento(v) / 1000
    return {"ok": True, "arquivo": f"{cam.MIDIA_DIR}/{destino.name}", "duracao": round(duracao, 3), "adianta": round(adianta, 4)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("gravacao")
    ap.add_argument("--velocidade", type=float, default=1.0)
    args = ap.parse_args()
    try:
        print(json.dumps(separar(args.edit, args.gravacao, args.velocidade), ensure_ascii=False))
    except SepararErro as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
