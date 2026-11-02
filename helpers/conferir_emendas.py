"""Ouve cada emenda do cut.mp4: transcreve uma janela em volta de cada junção e mostra as palavras dos dois
lados, para achar palavra comida ou sobra de fala que não devia estar ali.

Edição real de 01/11: as medidas (verify_cut.py, o nível, as regiões de fala) davam tudo certo e a pessoa
ouvia palavra cortada. Só transcrever a emenda pronta pegou o que nenhuma medida pegava, inclusive uma
palavra que a conferência de antes tinha dado como limpa.

    uv run python -X utf8 helpers/conferir_emendas.py <edit> [--language pt]

As junções vêm dos quadros de cada trecho do último render (clips_graded/), não da soma dos segundos do
edl.json. As janelas vão juntas num áudio só, separadas por silêncio, e uma transcrição ouve todas.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ANTES, DEPOIS, VAO = 2.0, 1.6, 1.5  # s ouvidos antes e depois de cada junção, e o silêncio entre as janelas


def juncoes(edit: Path) -> list[float]:
    """Onde cada tomada encontra a seguinte no cut.mp4 (s)."""
    import gerar as gr  # mesma pasta deste arquivo
    import tempo  # mesma pasta deste arquivo
    try:
        fps = gr._sondar(edit / "cut.mp4")[0] or 30.0
        segs, _ = gr.segmentos_do_corte(edit, fps)
        return [s["start"] for s in segs[1:]]
    except gr.ErroGerar:  # sem os trechos do último render: pela linha do tempo do edl.json
        edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
        return [s["out"] for s in tempo.tomadas_no_corte(edl)[1:]]


def audio_das_emendas(cut: Path, jan: list[float], saida: Path) -> None:
    ins = []
    for o in jan:
        ins += ["-ss", f"{max(0.0, o - ANTES):.3f}", "-t", f"{ANTES + DEPOIS:.3f}", "-i", str(cut)]
    partes = "".join(f"[{k}:a]aformat=sample_rates=16000:channel_layouts=mono,apad=pad_dur={VAO}[a{k}];"
                     for k in range(len(jan)))
    juntar = "".join(f"[a{k}]" for k in range(len(jan))) + f"concat=n={len(jan)}:v=0:a=1[o]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", partes + juntar, "-map", "[o]", str(saida)],
                   check=True)


def lados(palavras: list[dict], jan: list[float]) -> list[dict]:
    """As palavras antes e depois de cada junção, pela posição de cada uma no áudio juntado."""
    passo = ANTES + DEPOIS + VAO
    out = []
    for k, o in enumerate(jan):
        a = k * passo
        j = a + min(ANTES, o)  # a junção dentro da janela (a 1ª pode começar antes de ANTES s)
        antes = " ".join(w["text"] for w in palavras if a <= w["start"] < j)
        depois = " ".join(w["text"] for w in palavras if j <= w["start"] < a + ANTES + DEPOIS)
        out.append({"em": round(o, 2), "antes": antes, "depois": depois})
    return out


def conferir(edit: Path, language: str | None = None) -> list[dict]:
    import transcribe  # mesma pasta deste arquivo
    edit = Path(edit)
    jan = juncoes(edit)
    if not jan:
        return []
    trab = edit / "verify" / "emendas"
    trab.mkdir(parents=True, exist_ok=True)
    wav = trab / "emendas.wav"
    audio_das_emendas(edit / "cut.mp4", jan, wav)
    if language is None:
        try:
            language = json.loads((edit / "transcripts" / "cut.json").read_text(encoding="utf-8")).get("language")
        except (OSError, ValueError):
            language = None
    arq = transcribe.transcribe_one(wav, trab, language=language, verbose=False)  # o wav é novo: transcreve
    palavras = [w for w in json.loads(Path(arq).read_text(encoding="utf-8"))["words"] if w.get("type", "word") == "word"]
    return lados(palavras, jan)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--language", default=None)
    a = ap.parse_args()
    for e in conferir(a.edit, a.language):
        print(f"{e['em']:7.2f}s  …{e['antes'][-40:]:>40} | {e['depois'][:40]}")
    print("Ouça cada linha: palavra cortada no fim da esquerda ou no começo da direita, ou fala que não devia "
          "estar ali. Uma emenda suspeita se confere sozinha (timeline_view.py ou ouvindo o trecho).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
