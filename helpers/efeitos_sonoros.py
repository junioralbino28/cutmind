#!/usr/bin/env python3
"""A biblioteca de efeitos sonoros do kit: sons sintetizados aqui, sem gravação nem licença de ninguém.

Os papéis são os dos sons que mais aparecem em Reels (impacto, notificação, dinheiro, brilho, ding,
whoosh, clique, pop, risco de disco, digitação). Os virais de marca e de série não vão num kit público:
o references/efeitos-sonoros.md diz onde a pessoa acha esses para os próprios vídeos.

Cada som começa no golpe (o ataque está no primeiro quadro: posto num segundo, ele cai NAQUELE
segundo). O whoosh é a exceção, porque cresce até o meio: o catálogo dá o `golpe` dele (o instante
do pico), e quem posiciona desconta.

    uv run python -X utf8 helpers/efeitos_sonoros.py listar
    uv run python -X utf8 helpers/efeitos_sonoros.py usar <edit> <id>      (copia para <edit>/midia/)
    uv run python -X utf8 helpers/efeitos_sonoros.py gerar [--pasta assets/sfx]   (só quem mantém o kit)

No vídeo: uma camada de áudio na agulha (o editor, Áudio → Efeitos sonoros), ou na mixagem final,
`mixar_final.py --sfx <arquivo>@<segundo>:<volume>`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
PICO = 10 ** (-3 / 20)  # todo som sai com o pico em -3 dBFS
PASTA = Path(__file__).resolve().parents[1] / "assets" / "sfx"
CATALOGO = "catalogo.json"


def _t(seg: float) -> np.ndarray:
    return np.arange(int(seg * SR)) / SR


def _rng(nome: str) -> np.random.Generator:
    return np.random.default_rng(sum(ord(c) * 31 ** i for i, c in enumerate(nome)) % 2**32)


def _seno(f, t: np.ndarray) -> np.ndarray:
    """Seno de frequência fixa ou variando (f em Hz por amostra)."""
    if np.isscalar(f):
        return np.sin(2 * np.pi * f * t)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _passa_baixa(x: np.ndarray, a) -> np.ndarray:
    """Passa-baixa de um polo; `a` (0..1) fixo ou por amostra."""
    a = np.broadcast_to(np.asarray(a, dtype=float), x.shape)
    y = np.empty_like(x)
    p = 0.0
    for i in range(len(x)):
        p += a[i] * (x[i] - p)
        y[i] = p
    return y


def _passa_faixa(x: np.ndarray, fc, q: float = 6.0) -> np.ndarray:
    """Passa-faixa ressonante de dois polos, com o centro fixo ou por amostra (Hz)."""
    fc = np.broadcast_to(np.asarray(fc, dtype=float), x.shape)
    y = np.zeros_like(x)
    y1 = y2 = 0.0
    for i in range(len(x)):
        w = 2 * np.pi * fc[i] / SR
        r = 1 - w / (2 * q)
        y0 = (1 - r) * x[i] + 2 * r * np.cos(w) * y1 - r * r * y2
        y[i] = y0
        y2, y1 = y1, y0
    return y


def _sino(f: float, t: np.ndarray, decai: float, parciais=((1, 1), (2.76, 0.4), (5.4, 0.2), (8.93, 0.1))) -> np.ndarray:
    """Um sino: parciais inarmônicas, as agudas morrendo mais depressa."""
    return sum(amp * _seno(f * k, t) * np.exp(-t * decai * (1 + 0.6 * (k - 1))) for k, amp in parciais)


def _em(y: np.ndarray, x: np.ndarray, seg: float, ganho: float = 1.0) -> None:
    i = int(seg * SR)
    n = min(len(x), len(y) - i)
    if n > 0:
        y[i:i + n] += ganho * x[:n]


# ---------------------------------------------------------------- os sons

def impacto() -> np.ndarray:
    t = _t(1.4)
    sub = _seno(70 * np.exp(-t * 2.2) + 36, t) * np.exp(-t * 3.0)
    corpo = _sino(110, t, 4.0, ((1, 1), (1.51, 0.5), (2.26, 0.3)))
    batida = _passa_baixa(_rng("impacto").standard_normal(len(t)), 0.08) * np.exp(-t * 38) * 6
    return sub * 1.4 + corpo * 0.5 + batida


def notificacao() -> np.ndarray:
    t = _t(0.7)
    y = np.zeros_like(t)
    for seg, f in ((0.0, 1318.5), (0.11, 1760.0)):
        tt = _t(0.7 - seg)
        nota = (_seno(f, tt) + 0.3 * _seno(2 * f, tt)) * np.exp(-tt * 9) * np.minimum(1, tt / 0.002)
        _em(y, nota, seg)
    return y


def dinheiro() -> np.ndarray:
    t = _t(1.0)
    y = np.zeros_like(t)
    cha = _passa_faixa(_rng("dinheiro").standard_normal(int(0.07 * SR)), 5200, 3) * np.exp(-_t(0.07) * 45)
    _em(y, cha / (np.max(np.abs(cha)) + 1e-9), 0.0, 0.9)
    tt = _t(0.93)
    ching = sum(_sino(f, tt, 4.5) for f in (2637.0, 3136.0, 3951.1)) / 3
    _em(y, ching, 0.07, 1.0)
    return y


def brilho() -> np.ndarray:
    t = _t(1.1)
    y = np.zeros_like(t)
    rng = _rng("brilho")
    tempos = np.sort(np.concatenate(([0.0], rng.uniform(0.02, 0.8, 26) ** 1.3)))
    for i, seg in enumerate(tempos):
        tt = _t(0.25)
        f = rng.uniform(2500, 7000)
        _em(y, _seno(f, tt) * np.exp(-tt * 28), seg, 1.0 if i == 0 else rng.uniform(0.25, 0.7))
    subida = _seno(np.linspace(1200, 2600, len(t)), t) * np.sin(np.pi * np.minimum(1, t / 1.1)) * 0.15
    return y + subida


def ding() -> np.ndarray:
    t = _t(1.6)
    ataque = _rng("ding").standard_normal(len(t)) * np.exp(-t * 900) * 0.4
    return _sino(1568.0, t, 2.6) + ataque


def whoosh() -> np.ndarray:
    t = _t(0.5)
    u = t / 0.5
    ruido = _passa_baixa(_rng("whoosh").standard_normal(len(t)), 0.02 + 0.38 * np.sin(np.pi * u) ** 1.2)
    return ruido * np.sin(np.pi * u) ** 1.4


def clique() -> np.ndarray:
    t = _t(0.12)
    y = np.zeros_like(t)
    rng = _rng("clique")
    for seg, g in ((0.0, 1.0), (0.07, 0.55)):
        tt = _t(0.012)
        tique = _passa_faixa(rng.standard_normal(len(tt)), 3200, 2) * np.exp(-tt * 700) + 0.5 * _seno(1800, tt) * np.exp(-tt * 500)
        _em(y, tique, seg, g)
    return y


def pop() -> np.ndarray:
    t = _t(0.16)
    tom = _seno(680 * np.exp(-t * 7), t)
    ataque = _rng("pop").standard_normal(len(t)) * np.exp(-t * 120) * 0.4
    return (tom + ataque) * np.exp(-t * 26)


def risco() -> np.ndarray:
    t = _t(0.45)
    curva = np.interp(t, [0, 0.13, 0.27, 0.36, 0.45], [500, 2600, 350, 1800, 600])
    ruido = _rng("risco").standard_normal(len(t))
    y = _passa_faixa(ruido, curva, 9) + 0.35 * _seno(curva * 0.5, t)
    return y * np.minimum(1, (0.45 - t) / 0.04 + 0.02) * np.minimum(1, 0.3 + t / 0.01)


def digitacao() -> np.ndarray:
    t = _t(1.9)
    y = np.zeros_like(t)
    rng = _rng("digitacao")
    seg = 0.0
    while seg < 1.75:
        tt = _t(0.03)
        tecla = _passa_faixa(rng.standard_normal(len(tt)), rng.uniform(2500, 4200), 2) * np.exp(-tt * 600)
        tum = _seno(rng.uniform(150, 210), tt) * np.exp(-tt * 260) * 0.5
        _em(y, tecla + tum, seg, 1.0 if seg == 0 else rng.uniform(0.55, 0.95))
        seg += rng.uniform(0.07, 0.16)
    return y


# id, nome (pt), nome (en), uso, o som, o golpe (s)
SONS = (
    ("impacto", "Impacto", "Impact", "a palavra grande ou o número que cai", impacto, 0.0),
    ("notificacao", "Notificação", "Notification", "comentário, mensagem, direct aparecendo", notificacao, 0.0),
    ("dinheiro", "Dinheiro", "Cash", "preço, faturamento, economia", dinheiro, 0.0),
    ("brilho", "Brilho mágico", "Magic sparkle", "IA, a transformação, o antes e depois", brilho, 0.0),
    ("ding", "Ding", "Ding", "acerto, o item que entra na lista", ding, 0.0),
    ("whoosh", "Whoosh", "Whoosh", "o cartão ou o texto que passa", whoosh, 0.25),
    ("clique", "Clique", "Click", "o botão clicado, o cursor", clique, 0.0),
    ("pop", "Pop", "Pop", "cada palavra que surge", pop, 0.0),
    ("risco", "Risco de disco", "Record scratch", "a objeção, o \"pera aí\", o riscado", risco, 0.0),
    ("digitacao", "Digitação", "Typing", "o comentário sendo escrito", digitacao, 0.0),
)


def _pronto(y: np.ndarray) -> np.ndarray:
    """Pico em -3 dBFS e 3 ms de saída suave (nada de estalo no fim)."""
    y = y / (np.max(np.abs(y)) + 1e-12) * PICO
    n = int(0.003 * SR)
    y[-n:] *= np.linspace(1, 0, n)
    return y


ALVO_RMS = -26.0  # dBFS nos 300 ms do golpe: ~12 dB abaixo da voz normalizada, presente sem cobrir a fala


def volume_sugerido(y: np.ndarray, golpe: float) -> float:
    """O volume da camada que deixa os 300 ms a partir do golpe em ALVO_RMS. Pico igual não é volume
    percebido igual: um ding de 1,6 s soa mais alto que um clique de 0,12 s com o mesmo pico."""
    i = int(golpe * SR)
    trecho = y[i:i + int(0.3 * SR)]
    rms = 20 * np.log10(np.sqrt(np.mean(trecho ** 2)) + 1e-12)
    return round(float(np.clip(10 ** ((ALVO_RMS - rms) / 20), 0.1, 1.0)), 2)


def gerar(pasta: Path = PASTA) -> list[dict]:
    """Sintetiza tudo e grava `<id>.mp3` + o catálogo. Sem metadado e bit a bit igual a cada vez."""
    pasta.mkdir(parents=True, exist_ok=True)
    cat = []
    with tempfile.TemporaryDirectory() as tmp:
        for sid, nome, nome_en, uso, fn, golpe in SONS:
            y = _pronto(fn())
            wav = Path(tmp) / f"{sid}.wav"
            with wave.open(str(wav), "w") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((y * 32767).astype("<i2").tobytes())
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(wav), "-map_metadata", "-1",
                            "-fflags", "+bitexact", "-flags:a", "+bitexact", "-c:a", "libmp3lame", "-b:a", "128k",
                            str(pasta / f"{sid}.mp3")], check=True)
            cat.append({"id": sid, "nome": nome, "nome_en": nome_en, "uso": uso, "arquivo": f"{sid}.mp3",
                        "duracao": round(len(y) / SR, 3), "golpe": golpe, "volume": volume_sugerido(y, golpe)})
    (pasta / CATALOGO).write_text(json.dumps(cat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return cat


def catalogo(pasta: Path = PASTA) -> list[dict]:
    return json.loads((pasta / CATALOGO).read_text(encoding="utf-8"))


def usar(edit: Path, sid: str, pasta: Path = PASTA) -> Path:
    """Copia o som para `<edit>/midia/sfx-<id>.mp3` (a mesma pasta das camadas) e devolve o caminho."""
    item = next((x for x in catalogo(pasta) if x["id"] == sid), None)
    if item is None:
        raise KeyError(f"efeito sonoro `{sid}` não existe; os que existem: {', '.join(x['id'] for x in catalogo(pasta))}")
    destino = Path(edit) / "midia" / f"sfx-{sid}.mp3"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.is_file() or destino.read_bytes() != (pasta / item["arquivo"]).read_bytes():
        shutil.copyfile(pasta / item["arquivo"], destino)
    return destino


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar")
    u = sub.add_parser("usar")
    u.add_argument("edit", type=Path)
    u.add_argument("id")
    g = sub.add_parser("gerar")
    g.add_argument("--pasta", type=Path, default=PASTA)
    a = ap.parse_args()
    if a.cmd == "gerar":
        for x in gerar(a.pasta):
            print(f"{x['id']:<12} {x['duracao']:.2f} s")
        return 0
    if a.cmd == "usar":
        try:
            print(usar(a.edit, a.id))
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 1
        return 0
    for x in catalogo():
        golpe = f", golpe em {x['golpe']} s" if x["golpe"] else ""
        print(f"{x['id']:<12} {x['duracao']:.2f} s{golpe} — {x['uso']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
