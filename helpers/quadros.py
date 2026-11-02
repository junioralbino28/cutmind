#!/usr/bin/env python3
"""Quadros soltos do vídeo para conferir a Fase 2, sem encher o disco.

Edição real de 01/11: 16 `npx remotion still` deixaram 3,38 GB no temporário do sistema (~210 MB cada, com recortes da
pessoa em public/), e o disco caiu de 9,3 para 5,9 GB em dois minutos. Cada um também refazia o bundle.

Aqui: um bundle só para todos os quadros, prioridade baixa, e uma pasta temporária apagada no fim (vez.py). Sem a fila
de render: um quadro é rápido, e quem confere não pode esperar um render de meia hora acabar.

    uv run python -X utf8 helpers/quadros.py <edit> --quadros 150 330 555 [-o <pasta>] [--colunas 5]

Grava `quadro-<n>.png` em <edit>/verify (ou -o) e, com mais de um, a folha `quadros.png`, para olhar uma imagem só.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import aquecer_navegador  # mesma pasta deste arquivo
import atualizar_template  # mesma pasta deste arquivo
import vez  # mesma pasta deste arquivo

TIMEOUT_MS = 180000  # como no gerar.py: o vídeo do modelo estoura os 28 s padrão com a máquina ocupada
ALTURA_FOLHA = 640


class ErroQuadros(RuntimeError):
    pass


def _roda(cmd: list[str], rem: Path, v: vez.Vez, o_que: str) -> None:
    r = subprocess.run(cmd, cwd=rem, env=v.env(), capture_output=True, text=True, encoding="utf-8", errors="replace", **v.criar)
    if r.returncode != 0:
        fim = [x for x in (r.stderr or r.stdout or "").splitlines() if x.strip()][-6:]
        raise ErroQuadros(f"{o_que} falhou:\n" + "\n".join(fim))


def folha(arquivos: list[tuple[int, Path]], destino: Path, colunas: int = 5) -> Path:
    """Os quadros numa imagem só, com o número de cada um."""
    fotos = []
    for n, p in arquivos:
        with Image.open(p) as im:
            larg = round(im.width * ALTURA_FOLHA / im.height)
            fotos.append((n, im.convert("RGB").resize((larg, ALTURA_FOLHA))))
    larg = fotos[0][1].width
    linhas = (len(fotos) + colunas - 1) // colunas
    out = Image.new("RGB", (larg * min(colunas, len(fotos)), ALTURA_FOLHA * linhas), "#0b0b0d")
    risco = ImageDraw.Draw(out)
    for i, (n, im) in enumerate(fotos):
        x, y = (i % colunas) * larg, (i // colunas) * ALTURA_FOLHA
        out.paste(im, (x, y))
        risco.rectangle((x, y, x + 74, y + 18), fill="#000000")
        risco.text((x + 4, y + 3), f"q {n}", fill="#ffffff")
    out.save(destino)
    return destino


def tirar(edit: Path, quadros: list[int], destino: Path | None = None, colunas: int = 5) -> list[Path]:
    edit = Path(edit).resolve()
    rem = edit / "remotion"
    cli = rem / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not cli.is_file():
        raise ErroQuadros(f"o projeto do Remotion não está instalado em {rem}: rode preparar_remotion.py")
    destino = Path(destino).resolve() if destino else edit / "verify"
    destino.mkdir(parents=True, exist_ok=True)
    comp = "Reels" if atualizar_template.trilha(rem) == "shortform" else "Longform"
    feitos: list[tuple[int, Path]] = []
    with vez.vez(edit, "quadros de conferência", fila=False) as v:
        pacote = v.tmp / "pacote"
        _roda(["node", str(cli), "bundle", f"--out-dir={pacote}"], rem, v, "o bundle")
        for n in quadros:
            arq = destino / f"quadro-{n}.png"
            _roda(["node", str(cli), "still", str(pacote), comp, str(arq), f"--frame={n}", f"--timeout={TIMEOUT_MS}",
                   *aquecer_navegador.flags(rem)], rem, v, f"o quadro {n}")
            feitos.append((n, arq))
    saida = [p for _, p in feitos]
    if len(feitos) > 1:
        saida.append(folha(feitos, destino / "quadros.png", colunas))
    return saida


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--quadros", type=int, nargs="+", required=True)
    ap.add_argument("-o", type=Path, help="pasta de saída (padrão: <edit>/verify)")
    ap.add_argument("--colunas", type=int, default=5)
    a = ap.parse_args()
    if not shutil.which("node"):
        print("ERRO o Node não está no PATH", file=sys.stderr)
        return 1
    try:
        for p in tirar(a.edit, a.quadros, a.o, a.colunas):
            print(p)
    except ErroQuadros as e:
        print(f"ERRO {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
