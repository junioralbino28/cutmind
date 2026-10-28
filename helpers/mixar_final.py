#!/usr/bin/env python3
"""O vídeo final com as camadas do editor: imagem do Remotion, som montado aqui.

É a receita da Fase 3 (references/shortform.md) com as camadas de áudio do camadas.json:

  - imagem: render.mp4 do Remotion, convertido para a faixa limitada e marcado bt709
    (o Remotion sai cheio, 0–255, e marcado como PAL);
  - voz: o áudio do cut.mp4, atrasado o mesmo tanto que a imagem do Remotion vem atrás
    do corte (`videoLag`, ver atraso_da_imagem: 0 quando o vídeo do cut.mp4 começa em
    zero). Fica FORA quando a pessoa desligou o som do vídeo no editor;
  - trilha: a do edit-data (`soundtrack`), quando ligada, com o volume e os fades da receita;
  - camadas de áudio: cada item que toca (faixa não silenciada, volume > 0), cortado em
    `corte`/`duracao`, com o volume dele, a cadeia do melhorar_audio.py quando `melhorar`,
    e no tempo `inicio` do corte + o mesmo quadro de atraso da voz;
  - efeitos sonoros (--sfx): no tempo do vídeo final, sem o atraso;
  - tudo somado (sem normalizar a soma) e o loudnorm obrigatório (-14 LUFS, pico -1).

    python mixar_final.py <edit> --render <out/render.mp4> [-o <edit>/final.mp4]
                          [--base cut|render] [--imagem remotion|corte]
                          [--sfx arquivo@segundos[:volume]] ... [--mostrar]

--imagem corte é para quando a imagem final é o próprio cut.mp4 (a montagem na batida sem
texto nem efeito, montagem.py): ela é copiada sem reconverter a cor (o cut.mp4 já é da faixa
limitada) e o som entra sem o quadro de atraso do Remotion, que ali não existe. Numa montagem
(edl.json com "montagem") a normalização é a linear, como com volume de tomada: o loudnorm
dinâmico achataria o drop da música.

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
ALVO_LUFS = -14.0
LIMITE_LINEAR = 0.891  # −1 dBFS, o mesmo teto do loudnorm
FADE_ITEM = 0.015  # entrada e saída curtinhas em cada camada: sem estalo no corte
FADE_TRILHA = (0.4, 1.5)  # trilha da biblioteca: entra e sai como música, igual à soundtrack


class CamadasNoMix(ValueError):
    pass


def _n(x: float) -> str:
    return f"{x:.3f}"


def _edl(edit: Path, state: dict) -> dict:
    try:
        return json.loads((edit / (state.get("edl") or "edl.json")).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def tem_volume_de_tomada(edit: Path, state: dict) -> bool:
    """Alguma tomada do edl.json com volume próprio (régua de Volume do editor do celular)?
    Então o loudnorm de uma passada não serve: ele é dinâmico e levanta de volta a tomada
    que a pessoa baixou (medido em 21/10: a tomada a 50% voltou a 0,0 dB no final)."""
    return any(r.get("volume") is not None and float(r["volume"]) != 1.0 for r in _edl(edit, state).get("ranges") or [])


def eh_montagem(edit: Path, state: dict) -> bool:
    """Montagem na batida (montagem.py)? O som é a música inteira, e o loudnorm dinâmico achataria o
    drop: a parte calma subiria e a explosão desceria. Vai a normalização linear também."""
    return "montagem" in _edl(edit, state)


def atraso_da_imagem(ed: dict, public: Path) -> int:
    """Quadros que a imagem do Remotion vem atrás do cut.mp4: o mesmo VIDEO_LAG do modelo
    (videoLag.ts). edit-data.json `videoLag` > segments.json `videoLag` > 1, o que o cut.mp4
    de render antigo pedia (vídeo começando em 0,033 s). A voz e as camadas seguem a imagem;
    com o valor errado a voz fica um quadro fora dela (medido em 22/10/2026: vídeo do
    cut.mp4 começando em zero = 0, e o 1 fixo deixava a voz 33 ms atrasada)."""
    if ed.get("videoLag") is not None:
        return int(ed["videoLag"])
    try:
        seg = json.loads((public / "segments.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seg = {}
    return int(seg["videoLag"]) if seg.get("videoLag") is not None else 1


def montar(edit: Path, render: Path, saida: Path, vd: float, base: str = "cut",
           sfx: list[tuple[Path, float, float]] = (), norma: str | None = None,
           medir: bool = False, imagem: str = "remotion") -> tuple[list[str], dict]:
    """O comando ffmpeg e um resumo do que entrou. vd = duração do vídeo do render.

    `norma` troca o loudnorm do fim (a normalização linear, quando há volume de tomada);
    `medir` devolve só a medição da soma (sem imagem, saída nula, loudnorm em JSON);
    `imagem="corte"`: a imagem é o próprio cut.mp4, copiada, e o som vai sem atraso."""
    edit = Path(edit)
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    fps = float(state.get("fps") or 30)
    camadas = cam.load(edit / "camadas.json")
    ed = {}
    if state.get("editData") and (edit / state["editData"]).is_file():
        ed = json.loads((edit / state["editData"]).read_text(encoding="utf-8"))
    public = (edit / state["editData"]).parent if state.get("editData") else edit
    corte = imagem == "corte"
    # em ms (1 quadro = 33 a 30 qps); sem Remotion a imagem é o próprio corte e não vem atrás
    lag = 0 if corte else round(atraso_da_imagem(ed, public) * 1000 / fps)

    entradas: list[Path] = [Path(render)]
    video = [] if corte else [f"[0:v]{COR}[vid]"]
    partes = [*video, f"anullsrc=r=48000:cl=stereo,atrim=duration={_n(vd)}[base]"]
    soma = ["[base]"]  # silêncio do tamanho do vídeo: a soma nunca fica vazia nem mais curta
    porque = ("há tomada com volume próprio" if tem_volume_de_tomada(edit, state)
              else "montagem na batida, a música fica com o drop" if eh_montagem(edit, state) else "")
    resumo = {"voz": "fora", "trilha": False, "camadas": 0, "biblioteca": 0, "efeitos": 0,
              "linear": bool(porque), "linear_porque": porque}

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
        if cam.eh_video(it["arquivo"]) and not tem_som(edit / it["arquivo"]):
            continue  # o vídeo por cima sem trilha de som: nada a misturar (o [k:a] quebraria o ffmpeg)
        k = entrada(edit / it["arquivo"])
        d = it["duracao"]
        cadeia = [f"atrim=start={_n(it['corte'])}:duration={_n(d)}", "asetpts=PTS-STARTPTS"]
        if it["melhorar"]:
            cadeia.append(MELHORAR)
        fi, fo = (min(FADE_TRILHA[0], d / 2), min(FADE_TRILHA[1], d / 2)) if it.get("trilha") else (FADE_ITEM, FADE_ITEM)
        cadeia += [f"volume={_n(it['volume'])}", f"afade=t=in:st=0:d={_n(fi)}",
                   f"afade=t=out:st={_n(max(0.0, d - fo))}:d={_n(fo)}",
                   f"adelay={round(it['inicio'] * 1000) + lag}:all=1", FMT]
        partes.append(f"[{k}:a]{','.join(cadeia)}[c{n}]")
        soma.append(f"[c{n}]")
        resumo["camadas"] += 1
        resumo["biblioteca"] += bool(it.get("trilha"))

    for n, (arq, t, vol) in enumerate(sfx):
        k = entrada(arq)
        partes.append(f"[{k}:a]volume={_n(vol)},adelay={round(t * 1000)}:all=1,{FMT}[s{n}]")
        soma.append(f"[s{n}]")
        resumo["efeitos"] += 1

    fim = f"{LOUDNORM}:print_format=json" if medir else (norma or LOUDNORM)
    partes.append(f"{''.join(soma)}amix=inputs={len(soma)}:duration=first:normalize=0,{fim}[out]")
    if medir:  # só o som: a imagem não entra na conta e não custa o tempo da conversão
        cmd = ["ffmpeg", "-hide_banner", "-nostats", "-y"]
        for e in entradas:
            cmd += ["-i", str(e)]
        return cmd + ["-filter_complex", ";".join(partes[len(video):]), "-map", "[out]", "-t", _n(vd),
                      "-f", "null", "-"], resumo
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for e in entradas:
        cmd += ["-i", str(e)]
    if corte:
        v = ["-map", "0:v", "-map", "[out]", "-c:v", "copy"]
    else:
        v = ["-map", "[vid]", "-map", "[out]",
             "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
    cmd += ["-filter_complex", ";".join(partes), *v,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", _n(vd), "-movflags", "+faststart", str(saida)]
    return cmd, resumo


def tem_som(p: Path) -> bool:
    """O arquivo tem trilha de som (um vídeo gravado sem áudio não tem)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                          str(p)], capture_output=True, text=True)
    return bool(out.stdout.strip())


def _duracao_video(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration",
                          "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _lufs(medir: list[str]) -> float:
    """O volume integrado (LUFS) da soma, pelo JSON que o loudnorm imprime no fim."""
    err = subprocess.run(medir, capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    bloco = err[err.rfind("{"):err.rfind("}") + 1]
    try:
        i = float(json.loads(bloco)["input_i"])
    except (ValueError, KeyError):
        raise SystemExit(f"não consegui medir o volume da soma:\n{err[-800:]}") from None
    return i if i > -70 else ALVO_LUFS  # soma em silêncio: nada a normalizar


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
    ap.add_argument("--imagem", choices=("remotion", "corte"), default="remotion",
                    help="corte: a imagem é o próprio cut.mp4 (montagem sem texto nem efeito)")
    ap.add_argument("--sfx", type=_sfx, action="append", default=[], help="arquivo@segundos[:volume], repetível")
    ap.add_argument("--mostrar", action="store_true", help="só mostra o comando, não roda")
    a = ap.parse_args()
    edit = a.edit.resolve()
    saida = a.saida or edit / "final.mp4"
    try:
        cmd, resumo = montar(edit, a.render, saida, _duracao_video(a.render), a.base, a.sfx, imagem=a.imagem)
    except CamadasNoMix as e:
        print(f"não montei: {e}", file=sys.stderr)
        return 2
    entradas = cmd[cmd.index("-i") + 1:cmd.index("-filter_complex"):2]
    faltando = [c for c in entradas if not Path(c).is_file()]
    if faltando:
        print("faltam arquivos: " + ", ".join(faltando), file=sys.stderr)
        return 1
    if resumo["linear"]:
        # volume de tomada: mede a soma e aplica um ganho fixo + limitador (normalização
        # linear), para a tomada que a pessoa baixou continuar mais baixa no vídeo final
        medir, _ = montar(edit, a.render, saida, _duracao_video(a.render), a.base, a.sfx, medir=True,
                          imagem=a.imagem)
        if a.mostrar:
            print(subprocess.list2cmdline(medir))
            print("(o ganho do volume=…dB sai dessa medição)")
            return 0
        ganho = ALVO_LUFS - _lufs(medir)
        cmd, resumo = montar(edit, a.render, saida, _duracao_video(a.render), a.base, a.sfx,
                             norma=f"volume={ganho:+.2f}dB,alimiter=limit={LIMITE_LINEAR}:level=false:latency=true",
                             imagem=a.imagem)
        print(f"normalização linear ({resumo['linear_porque']}): ganho {ganho:+.2f} dB")
    if a.mostrar:
        print(subprocess.list2cmdline(cmd))
        return 0
    subprocess.run(cmd, check=True)
    bib = f" ({resumo['biblioteca']} trilha(s) da biblioteca)" if resumo["biblioteca"] else ""
    print(f"{saida.name}: voz {resumo['voz']}, trilha do edit-data {'sim' if resumo['trilha'] else 'não'}, "
          f"{resumo['camadas']} camada(s) de áudio{bib}, {resumo['efeitos']} efeito(s) · {verificar(saida)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
