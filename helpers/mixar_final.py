#!/usr/bin/env python3
"""O vídeo final com as camadas do editor: imagem do Remotion, som montado aqui.

É a receita da Fase 3 (references/shortform.md) com as camadas de áudio do camadas.json:

  - imagem: render.mp4 do Remotion, convertido para a faixa limitada e marcado bt709
    (o Remotion sai cheio, 0–255, e marcado como PAL);
  - voz: o áudio do cut.mp4, atrasado 1 quadro (a imagem do Remotion vem 1 quadro
    atrás do corte). Fica FORA quando a pessoa desligou o som do vídeo no editor;
  - trilha: a do edit-data (`soundtrack`), quando ligada, com o volume e os fades da receita;
  - camadas de áudio: cada item que toca (faixa não silenciada, volume > 0), cortado em
    `corte`/`duracao`, com o volume dele, a cadeia do melhorar_audio.py quando `melhorar`,
    e no tempo `inicio` do corte + o mesmo quadro de atraso da voz;
  - efeitos sonoros (--sfx): no tempo do vídeo final, sem o atraso;
  - tudo somado (sem normalizar a soma) e o loudnorm obrigatório (-14 LUFS, pico -1).

    python mixar_final.py <edit> --render <out/render.mp4> [-o <edit>/final.mp4]
                          [--base cut|render] [--sfx arquivo@segundos[:volume]] ... [--mostrar]

--base render usa o áudio do próprio Remotion no lugar da voz do corte (quando os
efeitos da legenda estão embutidos nele: references/shortform.md). Ele já traz a trilha
e os efeitos, então só as camadas são somadas; e como voz e efeitos vêm juntos, o
"som do vídeo desligado" não tem como ser atendido nessa base.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import camadas as cam  # mesma pasta deste arquivo
from melhorar_audio import MELHORAR

FMT = "aformat=sample_rates=48000:channel_layouts=stereo"
COR = ("scale=in_range=full:out_range=limited,format=yuv420p,"
       "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")
LOUDNORM = "loudnorm=I=-14:TP=-1:LRA=11"
FADE_ITEM = 0.015  # entrada e saída curtinhas em cada camada: sem estalo no corte


class CamadasNoMix(ValueError):
    pass


def _n(x: float) -> str:
    return f"{x:.3f}"


def montar(edit: Path, render: Path, saida: Path, vd: float, base: str = "cut",
           sfx: list[tuple[Path, float, float]] = ()) -> tuple[list[str], dict]:
    """O comando ffmpeg e um resumo do que entrou. vd = duração do vídeo do render."""
    edit = Path(edit)
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    fps = float(state.get("fps") or 30)
    lag = round(1000 / fps)  # 1 quadro, em ms (33 a 30 qps)
    camadas = cam.load(edit / "camadas.json")
    ed = {}
    if state.get("editData") and (edit / state["editData"]).is_file():
        ed = json.loads((edit / state["editData"]).read_text(encoding="utf-8"))
    public = (edit / state["editData"]).parent if state.get("editData") else edit

    entradas: list[Path] = [Path(render)]
    partes = [f"[0:v]{COR}[vid]", f"anullsrc=r=48000:cl=stereo,atrim=duration={_n(vd)}[base]"]
    soma = ["[base]"]  # silêncio do tamanho do vídeo: a soma nunca fica vazia nem mais curta
    resumo = {"voz": "fora", "trilha": False, "camadas": 0, "efeitos": 0}

    def entrada(p: Path) -> int:
        entradas.append(Path(p))
        return len(entradas) - 1

    if base == "render":
        if camadas["video"]["mudo"]:
            raise CamadasNoMix("o som do vídeo está desligado no editor, e o áudio do Remotion traz a voz "
                               "misturada com os efeitos: use --base cut")
        partes.append(f"[0:a]{FMT}[voz]")
        soma.append("[voz]")
        resumo["voz"] = "render"
    else:
        if not camadas["video"]["mudo"]:
            k = entrada(edit / (state.get("video") or "cut.mp4"))
            partes.append(f"[{k}:a]adelay={lag}:all=1,{FMT}[voz]")
            soma.append("[voz]")
            resumo["voz"] = "corte"
        st = ed.get("soundtrack") or {}
        if st.get("enabled"):
            k = entrada(public / st["file"])
            partes.append(f"[{k}:a]volume={st.get('volume', 0.0445)},afade=t=in:st=0:d=0.4,"
                          f"afade=t=out:st={_n(max(0.0, vd - 1.5))}:d=1.5,{FMT}[trilha]")
            soma.append("[trilha]")
            resumo["trilha"] = True

    for n, it in enumerate(cam.tocam(camadas)):
        k = entrada(edit / it["arquivo"])
        d = it["duracao"]
        cadeia = [f"atrim=start={_n(it['corte'])}:duration={_n(d)}", "asetpts=PTS-STARTPTS"]
        if it["melhorar"]:
            cadeia.append(MELHORAR)
        cadeia += [f"volume={_n(it['volume'])}", f"afade=t=in:st=0:d={FADE_ITEM}",
                   f"afade=t=out:st={_n(max(0.0, d - FADE_ITEM))}:d={FADE_ITEM}",
                   f"adelay={round(it['inicio'] * 1000) + lag}:all=1", FMT]
        partes.append(f"[{k}:a]{','.join(cadeia)}[c{n}]")
        soma.append(f"[c{n}]")
        resumo["camadas"] += 1

    for n, (arq, t, vol) in enumerate(sfx):
        k = entrada(arq)
        partes.append(f"[{k}:a]volume={_n(vol)},adelay={round(t * 1000)}:all=1,{FMT}[s{n}]")
        soma.append(f"[s{n}]")
        resumo["efeitos"] += 1

    partes.append(f"{''.join(soma)}amix=inputs={len(soma)}:duration=first:normalize=0,{LOUDNORM}[out]")
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for e in entradas:
        cmd += ["-i", str(e)]
    cmd += ["-filter_complex", ";".join(partes), "-map", "[vid]", "-map", "[out]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", _n(vd), "-movflags", "+faststart", str(saida)]
    return cmd, resumo


def _duracao_video(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                          "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _sfx(texto: str) -> tuple[Path, float, float]:
    """arquivo@segundos[:volume] — o volume padrão é o do whoosh dos cartões (0,09)."""
    arq, _, resto = texto.rpartition("@")
    t, _, vol = resto.partition(":")
    if not arq:
        raise argparse.ArgumentTypeError(f"--sfx {texto}: use arquivo@segundos[:volume]")
    return Path(arq), float(t), float(vol or 0.09)


def verificar(saida: Path) -> str:
    cores = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=color_space,color_primaries,color_transfer,color_range",
                            "-of", "default=nw=1:nk=1", str(saida)], capture_output=True, text=True).stdout.split()
    vd = subprocess.run(["ffmpeg", "-i", str(saida), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    pico = next((ln.split("max_volume:")[1].strip() for ln in vd.splitlines() if "max_volume:" in ln), "?")
    return f"cores {'/'.join(cores)} · pico {pico}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--render", type=Path, required=True, help="o render.mp4 do Remotion")
    ap.add_argument("-o", "--saida", type=Path, help="padrão: <edit>/final.mp4")
    ap.add_argument("--base", choices=("cut", "render"), default="cut")
    ap.add_argument("--sfx", type=_sfx, action="append", default=[], help="arquivo@segundos[:volume], repetível")
    ap.add_argument("--mostrar", action="store_true", help="só mostra o comando, não roda")
    a = ap.parse_args()
    edit = a.edit.resolve()
    saida = a.saida or edit / "final.mp4"
    try:
        cmd, resumo = montar(edit, a.render, saida, _duracao_video(a.render), a.base, a.sfx)
    except CamadasNoMix as e:
        print(f"não montei: {e}", file=sys.stderr)
        return 2
    entradas = cmd[cmd.index("-i") + 1:cmd.index("-filter_complex"):2]
    faltando = [c for c in entradas if not Path(c).is_file()]
    if faltando:
        print("faltam arquivos: " + ", ".join(faltando), file=sys.stderr)
        return 1
    if a.mostrar:
        print(subprocess.list2cmdline(cmd))
        return 0
    subprocess.run(cmd, check=True)
    print(f"{saida.name}: voz {resumo['voz']}, trilha {'sim' if resumo['trilha'] else 'não'}, "
          f"{resumo['camadas']} camada(s) de áudio, {resumo['efeitos']} efeito(s) · {verificar(saida)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
