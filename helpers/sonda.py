"""Um valor do ffprobe sem surpresa.

O ffprobe 8.1 (o do gyan.dev, no Windows) põe uma vírgula no fim da linha de `stream=` quando o fluxo
traz dados extras (a gravação HLG do iPhone traz "Ambient viewing environment"): com `-of csv=p=0` sai
`5568,` e `0.021029,`, o int()/float() cai no except e o leitor devolvia 0 sem aviso nenhum. Edição real
de 01/11: a contagem de quadros e o atraso da imagem do corte zerados.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def valor(arquivo: Path | str, entrada: str, fluxo: str | None = "v:0") -> str:
    """O 1º valor de `entrada` (ex.: "stream=nb_frames"), sem vírgula nem espaço; "" quando não há."""
    cmd = ["ffprobe", "-v", "error"]
    if fluxo:
        cmd += ["-select_streams", fluxo]
    cmd += ["-show_entries", entrada, "-of", "default=nw=1:nk=1", str(arquivo)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    for linha in r.stdout.splitlines():
        v = linha.strip().strip(",").strip()
        if v:
            return v
    return ""
