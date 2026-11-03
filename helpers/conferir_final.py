#!/usr/bin/env python3
"""Confere o vídeo final, sem olhar imagem nenhuma: o que um Reels editado com o kit só mostrou quando alguém
assistiu (edição real de 01/11).

- **Sincronia:** o som do final contra o do corte, em 6 trechos do começo ao fim. O deslocamento tem de ser
  CONSTANTE e igual ao atraso da imagem; e o som decodificado tem de durar o mesmo que a imagem (o ffprobe
  lê o cabeçalho e não vê 0,8 s de som a mais).
- **Trocas de tomada:** a maior diferença entre quadros vizinhos em ±4 quadros de cada início do
  segments.json tem de cair no quadro exato. Comparar o final com a gravação não serve: em trecho com zoom,
  texto ou foto, o casamento de quadros satura e parece dessincronia.
- **Sons de efeito:** o PICO de cada um contra o pico da voz numa janela de 0,25 s, não a média: o clique
  de câmera tem o estalo em 0 ms e cauda até 90 ms.

    uv run python -X utf8 helpers/conferir_final.py <edit> [--video final.mp4]

Sai 0 com tudo certo e 1 com o que achar (uma linha por problema). Grava o resultado em verify/conferencia.txt.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import camadas as cam  # mesma pasta deste arquivo
from mixar_final import atraso_da_imagem
import sonda

TAXA = 16000
PASSO = 0.005  # s por ponto da curva do som
PONTOS = 6
TRECHO = 8.0  # s de cada trecho da sincronia
BUSCA = 0.5  # s procurados para cada lado
LIMITE_SYNC = 0.04  # s de diferença para o atraso esperado
LIMITE_DERIVA = 0.025  # s entre o trecho mais adiantado e o mais atrasado
SOBRA_SOM = 0.1  # s de som a mais ou a menos que a imagem
RAIO = 4  # quadros procurados em volta de cada troca
QW, QH = 96, 170
JANELA_PICO = 0.25  # s para cada lado do som
ABAIXO_DB = -9.0  # o som some debaixo da voz
ACIMA_DB = 9.0  # o som passa por cima da voz


def ler_som(p: Path) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(p), "-map", "0:a:0", "-ac", "1", "-ar", str(TAXA),
                        "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32) if r.returncode == 0 else np.zeros(0, dtype=np.float32)


def curva(x: np.ndarray) -> np.ndarray:
    n = int(TAXA * PASSO)
    m = len(x) // n
    if not m:
        return np.zeros(0)
    return np.log(np.sqrt((x[: m * n].reshape(m, n) ** 2).mean(axis=1)) + 1e-4)


def deslocamento(final: np.ndarray, corte: np.ndarray, t: float, dur: float = TRECHO) -> tuple[float, float]:
    """Quanto o som do final vem depois do corte em volta de t (s) e quanto casa (0 a 1). `final` e `corte` são curvas."""
    a, n, m = int(t / PASSO), int(dur / PASSO), int(BUSCA / PASSO)
    base = corte[a:a + n]
    if len(base) < n // 2 or base.std() < 0.2:  # sem fala não tem o que casar
        return 0.0, 0.0
    melhor = (0.0, -1.0)
    for d in range(-m, m + 1):
        ini = a + d
        if ini < 0:
            continue
        v = final[ini:ini + len(base)]
        if len(v) < len(base) or v.std() < 1e-6:
            continue
        c = float(np.corrcoef(base, v)[0, 1])
        if c > melhor[1]:
            melhor = (d * PASSO, c)
    return melhor


def conferir_sincronia(final: np.ndarray, corte: np.ndarray, lag_s: float) -> dict:
    cf, cc = curva(final), curva(corte)
    dur = len(corte) / TAXA
    medidas = []
    for k in range(PONTOS):
        t = max(0.0, (dur - TRECHO - BUSCA) * k / max(1, PONTOS - 1))  # o último deixa folga para procurar atraso
        d, c = deslocamento(cf, cc, t)
        if c >= 0.5:
            medidas.append((round(t, 1), round(d, 3)))
    probs = []
    if medidas:
        ds = [d for _, d in medidas]
        fora = [f"{t} s: {d * 1000:+.0f} ms" for t, d in medidas if abs(d - lag_s) > LIMITE_SYNC]
        if fora:
            probs.append(f"som fora da imagem (esperado {lag_s * 1000:+.0f} ms): " + "; ".join(fora))
        if max(ds) - min(ds) > LIMITE_DERIVA:
            probs.append(f"o som escorrega ao longo do vídeo: de {min(ds) * 1000:+.0f} a {max(ds) * 1000:+.0f} ms")
    return {"medidas": medidas, "problemas": probs}


def quadros(video: Path, a: int, b: int, fps: float, inicio: float = 0.0) -> np.ndarray:
    """Os quadros [a, b) em cinza pequeno, pelo número: -ss 1 s antes e seleção por tempo, porque -frames:v depois
    de -ss duplica o 1º quadro e deixa todos os outros um adiantados, sem erro nenhum."""
    a = max(0, a)
    de, ate = inicio + (a - 0.5) / fps, inicio + (b - 0.5) / fps
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{max(0.0, de - 1):.3f}", "-copyts", "-i", str(video),
                        "-vf", f"select='gte(t,{de:.4f})*lt(t,{ate:.4f})',scale={QW}:{QH},format=gray", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-"], capture_output=True)
    q = np.frombuffer(r.stdout, dtype=np.uint8)
    return q[: len(q) // (QW * QH) * (QW * QH)].reshape(-1, QH, QW).astype(np.float32)


def pico_da_troca(difs: np.ndarray) -> int | None:
    """O índice da troca nas diferenças entre quadros vizinhos; None quando nenhuma se destaca: tomada sobre a mesma
    imagem, ou uma transição, em que não há quadro exato para conferir."""
    if len(difs) < 3:
        return None
    k = int(np.argmax(difs))
    outros = np.delete(difs, k)
    if difs[k] < 4.0 or difs[k] < 2.5 * max(float(np.median(outros)), 0.5):
        return None
    return k


def conferir_trocas(video: Path, inicios: list[float], fps: float, lag: int, inicio: float = 0.0) -> dict:
    exatas, sem, fora = 0, 0, []
    for s in inicios[1:]:  # o 1º começa o vídeo: não há troca
        q = round(s * fps) + lag
        qs = quadros(video, q - RAIO - 1, q + RAIO + 1, fps, inicio)
        if len(qs) < 2 * RAIO + 2:
            sem += 1
            continue
        difs = np.abs(qs[1:] - qs[:-1]).mean(axis=(1, 2))
        k = pico_da_troca(difs)
        if k is None:
            sem += 1
        elif k == RAIO:
            exatas += 1
        else:
            fora.append((round(s, 2), k - RAIO))
    probs = [f"a troca de tomada em {s} s saiu {d:+d} quadro(s) fora do lugar" for s, d in fora]
    return {"exatas": exatas, "sem_corte": sem, "fora": fora, "problemas": probs}


def _db(x: float) -> float:
    return 20 * float(np.log10(max(x, 1e-9)))


def conferir_sons(edit: Path, voz: np.ndarray) -> dict:
    """Cada som curto das camadas (não a trilha) contra a voz em volta dele, os dois no volume que entram."""
    camadas = cam.load(edit / "camadas.json")
    linhas, probs = [], []
    for it in cam.tocam(camadas):
        if it.get("trilha") or cam.eh_video(it["arquivo"]) or float(it["duracao"]) > 4:
            continue
        t = float(it["inicio"])
        som = ler_som(edit / it["arquivo"])
        if not som.size:
            continue
        pico_som = _db(float(np.abs(som).max()) * float(it["volume"]))
        trecho = voz[max(0, int((t - JANELA_PICO) * TAXA)):int((t + JANELA_PICO) * TAXA)]
        pico_voz = _db(float(np.abs(trecho).max())) if trecho.size else -120.0
        if pico_voz < -45:  # sem fala por perto não tem contra o que medir
            continue
        d = pico_som - pico_voz
        linhas.append((round(t, 2), round(d, 1)))
        nome = Path(it["arquivo"]).name
        if d < ABAIXO_DB:
            probs.append(f"o som {nome} em {t:.2f} s fica {-d:.1f} dB abaixo da voz: não vai aparecer")
        elif d > ACIMA_DB:
            probs.append(f"o som {nome} em {t:.2f} s fica {d:.1f} dB acima da voz: vai por cima da fala")
    return {"sons": linhas, "problemas": probs}


def conferir(edit: Path, video: Path | None = None) -> dict:
    edit = Path(edit)
    st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    video = Path(video) if video else edit / (st.get("finalVideo") or "final.mp4")
    corte_p = edit / (st.get("video") or "cut.mp4")
    public = (edit / st["editData"]).parent if st.get("editData") else edit / "remotion" / "public"
    ed = json.loads((public / "edit-data.json").read_text(encoding="utf-8")) if (public / "edit-data.json").is_file() else {}
    fps = float(ed.get("fps") or st.get("fps") or 30)
    lag = atraso_da_imagem(ed, public) if ed else 0
    final, corte = ler_som(video), ler_som(corte_p)
    r: dict = {"problemas": []}
    n = sonda.valor(video, "stream=nb_frames")
    dur_img = int(n) / fps if n.isdigit() else float(sonda.valor(video, "format=duration", None) or 0)
    r["som_s"], r["imagem_s"] = round(len(final) / TAXA, 3), round(dur_img, 3)
    if abs(r["som_s"] - dur_img) > SOBRA_SOM:
        r["problemas"].append(f"o som dura {r['som_s']} s e a imagem {r['imagem_s']} s")
    if cam.load(edit / "camadas.json")["video"]["mudo"]:
        r["sincronia"] = {"medidas": [], "problemas": []}  # sem a voz do corte, não tem com o que casar
    else:
        r["sincronia"] = conferir_sincronia(final, corte, lag / fps)
    try:
        inicios = [float(s["start"]) for s in json.loads((public / "segments.json").read_text(encoding="utf-8"))["segments"]]
    except (OSError, ValueError, KeyError, TypeError):
        inicios = []
    inicio = float(sonda.valor(video, "stream=start_time") or 0)
    r["trocas"] = conferir_trocas(video, inicios, fps, lag, inicio)
    r["sons"] = conferir_sons(edit, corte)
    for k in ("sincronia", "trocas", "sons"):
        r["problemas"] += r[k]["problemas"]
    r["ok"] = not r["problemas"]
    return r


def resumo(r: dict) -> list[str]:
    tr, sy, so = r["trocas"], r["sincronia"], r["sons"]
    ds = [d for _, d in sy["medidas"]]
    linhas = [f"som {r['som_s']} s, imagem {r['imagem_s']} s",
              "sincronia: " + (f"{len(ds)} trecho(s), de {min(ds) * 1000:+.0f} a {max(ds) * 1000:+.0f} ms" if ds else "sem fala para medir"),
              f"trocas: {tr['exatas']} no quadro exato, {len(tr['fora'])} fora, {tr['sem_corte']} sem corte visível",
              f"sons: {len(so['sons'])} medido(s) contra a voz"]
    return linhas + [f"PROBLEMA {p}" for p in r["problemas"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--video", type=Path)
    a = ap.parse_args()
    r = conferir(a.edit.resolve(), a.video)
    linhas = resumo(r)
    print("\n".join(linhas))
    pasta = a.edit.resolve() / "verify"
    pasta.mkdir(exist_ok=True)
    (pasta / "conferencia.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
