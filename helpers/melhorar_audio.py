#!/usr/bin/env python3
"""Melhora uma gravação de voz: tira o ruído de fundo e passa a cadeia de voz do kit.

É o "Melhorar" do editor: o item de camada com `"melhorar": true` passa por esta cadeia
dentro do `mixar_final.py`. Rodado sozinho, devolve um arquivo novo (o original fica).

    python melhorar_audio.py <entrada> [-o <saída.wav>]

A cadeia é a `VOICE_MASTER_CHAIN` do render.py com redução de ruído logo depois do
passa-alta: primeiro sai o grave (ronco, vento, batida no microfone), depois o chiado
constante (ventilador, ar-condicionado), e só então EQ, compressão e de-esser.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from render import VOICE_MASTER_CHAIN  # mesma pasta deste arquivo

# afftdn: nr = quanto reduz (dB), nf = piso de ruído estimado (dB), tn = segue o ruído
# quando ele muda ao longo da gravação
DENOISE = "afftdn=nr=12:nf=-35:tn=1"
_HP = "highpass=f=80,"
assert VOICE_MASTER_CHAIN.startswith(_HP), "a cadeia de voz do render.py mudou de começo"
MELHORAR = _HP + DENOISE + "," + VOICE_MASTER_CHAIN[len(_HP):]


def melhorar(entrada: Path, saida: Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(entrada), "-vn",
                    "-af", MELHORAR, "-ar", "48000", str(saida)], check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("-o", "--saida", type=Path, help="padrão: <nome>-melhorado.wav ao lado da entrada")
    a = ap.parse_args()
    if not a.entrada.is_file():
        print(f"não achei {a.entrada}", file=sys.stderr)
        return 1
    saida = a.saida or a.entrada.with_name(f"{a.entrada.stem}-melhorado.wav")
    melhorar(a.entrada, saida)
    print(f"melhorado: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
