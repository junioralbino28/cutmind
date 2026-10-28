#!/usr/bin/env python3
"""Refaz só as janelas que mudaram no vídeo da Fase 2, sem renderizar o vídeo inteiro.

Quando um efeito (`cenas[]`), um texto ou um bloco muda num trecho, o resto do render continua
certo. Este helper renderiza no Remotion só os quadros das janelas (com 2 quadros de folga de cada
lado), emenda no `out/render.mp4` pelo número do quadro e confere a contagem. O som do render fica
como estava (copiado, sem recodificar): mudou som (trilha, efeito sonoro), renderize inteiro.

A emenda vai no render, e não no final.mp4: o próximo mix parte do render, e um final.mp4 emendado
sozinho voltaria a ser o velho no mix seguinte. Depois, monte o final como depois de um render
inteiro (`mixar_final.py <edit> --render out/render.mp4`).

    python render_janelas.py <edit> --janelas 33.0-36.4,45.1-48.0 [--render <remotion>/out/render.mp4]

As janelas são segundos do corte, os mesmos `start`/`end` do edit-data. As que se tocam viram uma
só. No teste de 22/10, quatro trechos levaram ~4 min, contra 10,4 min do vídeo inteiro.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import aquecer_navegador  # mesma pasta deste arquivo
from camadas_edit_data import edit_data_do_projeto
from mixar_final import atraso_da_imagem

FOLGA = 2  # quadros de cada lado da janela: o que entra e sai na borda dela também é refeito
KIT = Path(__file__).resolve().parents[1]
PARTES_JS = KIT / "assets" / "shortform" / "scripts" / "partes.mjs"


class JanelaErro(RuntimeError):
    pass


def ler_janelas(texto: str) -> list[tuple[float, float]]:
    """`33.0-36.4,45.1-48.0` → [(33.0, 36.4), (45.1, 48.0)]."""
    out = []
    for parte in filter(None, (p.strip() for p in texto.split(","))):
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", parte)
        if not m or float(m.group(2)) <= float(m.group(1)):
            raise JanelaErro(f"janela `{parte}`: escreva início-fim em segundos do corte, com o fim depois do início")
        out.append((float(m.group(1)), float(m.group(2))))
    if not out:
        raise JanelaErro("nenhuma janela: passe --janelas início-fim[,início-fim...]")
    return out


def em_quadros(janelas: list[tuple[float, float]], fps: float, lag: int, total: int) -> list[tuple[int, int]]:
    """As janelas em quadros do render, [a, b) com a folga, dentro do vídeo; as que se tocam viram uma."""
    faixas = sorted((max(0, round(a * fps) + lag - FOLGA), min(total, round(b * fps) + lag + FOLGA)) for a, b in janelas)
    juntas: list[list[int]] = []
    for a, b in faixas:
        if b <= a:
            continue
        if juntas and a <= juntas[-1][1]:
            juntas[-1][1] = max(juntas[-1][1], b)
        else:
            juntas.append([a, b])
    return [(a, b) for a, b in juntas]


def quadros(p: Path) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip().strip(","))
    except ValueError:
        raise JanelaErro(f"o ffprobe não leu {p.name}: {r.stderr.strip()[-200:]}") from None


def _cor(p: Path) -> list[str]:
    """O formato e as marcas de cor do render (o Remotion sai em faixa cheia), para a emenda sair igual."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=pix_fmt,color_range,color_space,color_primaries,color_transfer", "-of", "json", str(p)],
                       capture_output=True, text=True)
    s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    out = ["-pix_fmt", s.get("pix_fmt") or "yuv420p"]
    for chave, opcao in (("color_range", "-color_range"), ("color_space", "-colorspace"),
                         ("color_primaries", "-color_primaries"), ("color_transfer", "-color_trc")):
        if s.get(chave) and s[chave] != "unknown":
            out += [opcao, s[chave]]
    return out


def emendar(render: Path, saida: Path, partes: list[tuple[int, int, Path]], fps: float, total: int | None = None) -> int:
    """Troca no render os quadros [a, b) de cada parte (parte_<a>_<b>.mp4), pelo número do quadro, e
    recodifica a imagem uma vez; o som do render é copiado como está. Recusa parte com quadros a
    menos ou a mais, e confere a contagem do resultado."""
    total = total if total is not None else quadros(render)
    for a, b, p in partes:
        n = quadros(p)
        if n != b - a:
            raise JanelaErro(f"{p.name}: {n} quadros, esperado {b - a}; o render ficou como estava")
    entradas, filtros, rotulos, cur = [str(render)], [], [], 0
    for a, b, p in sorted(partes):
        if a > cur:
            filtros.append(f"[0:v]trim=start_frame={cur}:end_frame={a},setpts=PTS-STARTPTS[v{len(rotulos)}]")
            rotulos.append(f"[v{len(rotulos)}]")
        entradas.append(str(p))
        filtros.append(f"[{len(entradas) - 1}:v]setpts=PTS-STARTPTS[v{len(rotulos)}]")
        rotulos.append(f"[v{len(rotulos)}]")
        cur = b
    if cur < total:
        filtros.append(f"[0:v]trim=start_frame={cur},setpts=PTS-STARTPTS[v{len(rotulos)}]")
        rotulos.append(f"[v{len(rotulos)}]")
    filtros.append(f"{''.join(rotulos)}concat=n={len(rotulos)}:v=1:a=0[v]")
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y"]
    for e in entradas:
        cmd += ["-i", e]
    cmd += ["-filter_complex", ";".join(filtros), "-map", "[v]", "-map", "0:a?", "-r", f"{fps:g}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "15", *_cor(render), "-c:a", "copy",
            "-movflags", "+faststart", str(saida)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise JanelaErro(f"o ffmpeg não emendou: {r.stderr.strip()[-300:]}")
    n = quadros(saida)
    if n != total:
        saida.unlink(missing_ok=True)
        raise JanelaErro(f"a emenda saiu com {n} quadros, o render tinha {total}; o render ficou como estava")
    return total


def _rodar_partes(remotion: Path, pasta: Path, faixas: list[tuple[int, int]]) -> None:
    """Renderiza as faixas no Remotion do projeto (scripts/partes.mjs, copiado do kit a cada vez)."""
    destino = remotion / "scripts" / "partes.mjs"
    destino.parent.mkdir(exist_ok=True)
    shutil.copy2(PARTES_JS, destino)
    cmd = ["node", str(destino), str(pasta), *(f"{a}-{b}" for a, b in faixas)]
    if subprocess.run(cmd, cwd=remotion, env={**os.environ, **aquecer_navegador.ambiente(remotion)}).returncode:
        raise JanelaErro("o Remotion falhou renderizando as janelas (a saída dele está acima); o render ficou como estava")


def aplicar(edit: Path, janelas: list[tuple[float, float]], render: Path | None = None) -> dict:
    edit = Path(edit)
    ed_p = edit_data_do_projeto(edit)
    remotion = ed_p.parent.parent
    d = json.loads(ed_p.read_text(encoding="utf-8"))
    fps = float(d.get("fps") or 30)
    render = Path(render) if render else remotion / "out" / "render.mp4"
    if not render.is_file():
        raise JanelaErro(f"não há render para emendar em {render}: renderize o vídeo inteiro uma vez")
    total = quadros(render)
    faixas = em_quadros(janelas, fps, atraso_da_imagem(d, ed_p.parent), total)
    if not faixas:
        raise JanelaErro("as janelas ficam fora do vídeo")
    pasta = render.parent / f"partes-{int(time.time())}"
    pasta.mkdir()
    t0 = time.time()
    try:
        _rodar_partes(remotion, pasta, faixas)
        partes = [(a, b, pasta / f"parte_{a}_{b}.mp4") for a, b in faixas]
        faltam = [p.name for _, _, p in partes if not p.is_file()]
        if faltam:
            raise JanelaErro(f"o Remotion não gerou {', '.join(faltam)}; o render ficou como estava")
        tmp = render.with_name(render.stem + ".janelas.mp4")
        emendar(render, tmp, partes, fps, total)
        tmp.replace(render)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return {"faixas": faixas, "quadros": sum(b - a for a, b in faixas), "total": total,
            "segundos": round(time.time() - t0, 1), "render": render}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--janelas", required=True, help="início-fim em segundos do corte, separadas por vírgula")
    ap.add_argument("--render", type=Path, help="o render a emendar (padrão: <remotion>/out/render.mp4)")
    a = ap.parse_args()
    try:
        r = aplicar(a.edit.resolve(), ler_janelas(a.janelas), a.render)
    except JanelaErro as e:
        print(f"ERRO {e}", file=sys.stderr)
        return 1
    trechos = ", ".join(f"{x}-{y}" for x, y in r["faixas"])
    print(f"{r['render'].name}: {len(r['faixas'])} trecho(s) refeito(s) (quadros {trechos}; {r['quadros']} de "
          f"{r['total']}) em {r['segundos']} s")
    print(f"Agora monte o vídeo final: mixar_final.py {a.edit} --render {r['render']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
