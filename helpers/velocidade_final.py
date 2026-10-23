#!/usr/bin/env python3
"""O vídeo de entrega com a velocidade do editor: final.mp4 → final-entrega.mp4.

Roda DEPOIS do mixar_final.py (references/shortform.md, Fase 3), sempre que o final for
refeito ou o velocidade.json mudar. Cada trecho de `<edit>/velocidade.json` toca no fator
dele (imagem por setpts, som por atempo, que não muda o tom da voz); o resto, normal. Como
o trecho é do vídeo já montado, legenda, efeitos, camadas e trilha aceleram juntos e
nada sai do lugar.

    python velocidade_final.py <edit> [-o <edit>/final-entrega.mp4] [--forcar] [--mostrar]

Um filtro só, de ponta a ponta, e não extração por trecho + concat: o som do final é
contínuo, e cada emenda de AAC copiado ganharia um buraco de 20 a 60 ms (medido nos
renders por partes). A imagem sai em quadros constantes, no fps do final. O atempo adianta
o som de 10 a 62 ms conforme o fator (ADIANTA_MS, medido): cada trecho devolve esse atraso
e é aparado no tamanho exato, e o som fica a ±8 ms do lugar (o teste de flash e bipe mede).

Grava `entregaVideo` no state.json (o Baixar do editor entrega esse arquivo). Sem trechos,
tira a chave e apaga a entrega antiga: o final.mp4 volta a ser a entrega.
Se o final mudou de duração desde que os trechos foram marcados (o corte foi refeito),
para sem aplicar: os trechos podem ter saído do lugar. --forcar aplica assim mesmo.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import velocidade as vel  # mesma pasta deste arquivo
from mixar_final import verificar
from render import atempo_cadeia

COR = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
FOLGA_DURACAO = 0.1  # segundos: mais que isso entre o final e o que a pessoa marcou = corte refeito
# Quanto o atempo ADIANTA o som, em ms da saída, por fator (a cadeia do atempo_cadeia; mediana
# de 12 bipes, medido em 23/10/2026 no ffmpeg 8.1). Sem compensar, o som de um trecho a 0,5×
# saía 26 a 34 ms antes da imagem (o teste de flash e bipe reprovou), e a 0,25×, 62 ms. O atraso
# volta para o trecho e o som é aparado no tamanho exato, para a duração não escorregar.
ADIANTA_MS = {0.25: 61.7, 0.33: 54.3, 0.4: 47.2, 0.5: 26.0, 0.6: 22.6, 0.75: 22.3, 0.9: 18.9, 1.1: 19.4,
              1.25: 16.5, 1.5: 12.7, 1.75: 9.8, 2.0: 11.7, 2.5: 24.0, 3.0: 20.7, 4.0: 17.5}


def adiantamento(f: float) -> float:
    """O adiantamento do atempo no fator f (ms), entre os medidos, em escala de potências."""
    pts = sorted(ADIANTA_MS.items())
    if f <= pts[0][0]:
        return pts[0][1]
    for (f0, v0), (f1, v1) in zip(pts, pts[1:]):
        if f <= f1:
            return v0 + (math.log(f / f0) / math.log(f1 / f0)) * (v1 - v0)
    return pts[-1][1]


def _sondar(p: Path) -> tuple[float, float, int]:
    """(duração do vídeo, fps, taxa do som) do final."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration,r_frame_rate,sample_rate",
                          "-of", "json", str(p)], capture_output=True, text=True, check=True).stdout
    ss = json.loads(out)["streams"]
    v = next(s for s in ss if s["codec_type"] == "video")
    a = next((s for s in ss if s["codec_type"] == "audio"), {})
    return float(v["duration"]), float(Fraction(v["r_frame_rate"])), int(a.get("sample_rate") or 48000)


def _no_quadro(t: float, fps: float) -> float:
    return round(t * fps) / fps


def montar(final: Path, saida: Path, pedacos: list[tuple[float, float, float]], fps: float, taxa: int = 48000) -> list[str]:
    """O comando ffmpeg: cada pedaço cortado do final, no seu fator, e tudo emendado."""
    n = len(pedacos)
    partes = [f"[0:v]split={n}" + "".join(f"[v{i}]" for i in range(n)),
              f"[0:a]asplit={n}" + "".join(f"[a{i}]" for i in range(n))]
    for i, (a, b, f) in enumerate(pedacos):
        pts = "PTS-STARTPTS" if f == 1 else f"(PTS-STARTPTS)/{f:g}"
        partes.append(f"[v{i}]trim=start={a:.6f}:end={b:.6f},setpts={pts}[vs{i}]")
        som = [f"atrim=start={a:.6f}:end={b:.6f}", "asetpts=PTS-STARTPTS"]
        if f != 1:
            amostras = round((b - a) / f * taxa)  # o tamanho exato do pedaço na entrega
            som += [f"atempo={x:g}" for x in atempo_cadeia(f)]
            som += [f"adelay={round(adiantamento(f) * taxa / 1000)}S:all=1",
                    f"apad=whole_len={amostras}", f"atrim=end_sample={amostras}"]
        partes.append(f"[a{i}]{','.join(som)}[as{i}]")
    # o concat emenda cada pedaço pelo fim do mais longo dos dois (imagem ou som): a
    # diferença de um quadro não se acumula de um pedaço para o outro
    partes.append("".join(f"[vs{i}][as{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][out]")
    partes.append(f"[vc]fps={fps:g},{COR}[vid]")
    return ["ffmpeg", "-v", "error", "-y", "-i", str(final), "-filter_complex", ";".join(partes),
            "-map", "[vid]", "-map", "[out]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(saida)]


def _gravar_state(edit: Path, entrega: str | None) -> None:
    p = edit / "state.json"
    state = json.loads(p.read_text(encoding="utf-8"))
    if entrega:
        state["entregaVideo"] = entrega
    elif "entregaVideo" not in state:
        return
    else:
        state.pop("entregaVideo")
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"))
    tmp.replace(p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("-o", "--saida", type=Path, help="padrão: <edit>/final-entrega.mp4")
    ap.add_argument("--forcar", action="store_true", help="aplica mesmo com o final de outra duração")
    ap.add_argument("--mostrar", action="store_true", help="só mostra o comando, não roda")
    a = ap.parse_args()
    edit = a.edit.resolve()
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    final = edit / (state.get("finalVideo") or "final.mp4")
    saida = (a.saida or edit / "final-entrega.mp4").resolve()
    try:
        v = vel.load(edit / "velocidade.json")
    except vel.VelocidadeInvalida as e:
        print(f"velocidade.json inválido: {e}", file=sys.stderr)
        return 1
    if not v["trechos"]:
        if not a.mostrar:
            _gravar_state(edit, None)
            if saida.exists():
                saida.unlink()
        print("sem trechos de velocidade: a entrega é o próprio " + final.name)
        return 0
    if not final.is_file():
        print(f"falta o vídeo final: {final}", file=sys.stderr)
        return 1
    total, fps, taxa = _sondar(final)
    marcado = v.get("duracao")
    if marcado is not None and abs(total - marcado) > FOLGA_DURACAO and not a.forcar:
        print(f"não apliquei: o {final.name} tem {total:.2f} s e os trechos foram marcados num vídeo de "
              f"{marcado:.2f} s. O corte mudou depois e os trechos podem ter saído do lugar: leve-os para "
              "o corte novo (ou peça para marcar de novo) e grave a duração nova; --forcar aplica assim mesmo.",
              file=sys.stderr)
        return 2
    # as bordas no quadro do final: o trecho começa e termina num quadro inteiro
    no_quadro = {**v, "trechos": [{**t, "inicio": _no_quadro(t["inicio"], fps), "fim": _no_quadro(t["fim"], fps)}
                                  for t in v["trechos"]]}
    pedacos = vel.pedacos(no_quadro, _no_quadro(total, fps))
    cmd = montar(final, saida, pedacos, fps, taxa)
    if a.mostrar:
        print(subprocess.list2cmdline(cmd))
        return 0
    subprocess.run(cmd, check=True)
    esperado = sum((b - a_) / f for a_, b, f in pedacos)
    saiu, _, _ = _sondar(saida)
    rel = saida.relative_to(edit).as_posix() if saida.is_relative_to(edit) else None
    if rel:
        _gravar_state(edit, rel)
    n = sum(1 for p in pedacos if p[2] != 1)
    print(f"{saida.name}: {n} trecho(s) · {total:.2f} s → {saiu:.2f} s (esperado {esperado:.2f}) · {verificar(saida)}")
    if abs(saiu - esperado) > (len(pedacos) + 1) / fps:
        print(f"ATENÇÃO: a duração saiu {saiu - esperado:+.3f} s fora do esperado", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
