#!/usr/bin/env python3
"""Os efeitos de voz do vídeo final: gás hélio, eco, robô, grave e rádio num trecho da fala.

O trecho é um item `voz` do efeitos.json (o mesmo arquivo dos filtros, no relógio do cut.mp4):

    {"id": "v1", "tipo": "voz", "inicio": 12.4, "duracao": 2.1, "efeito": "helio"}

Fora dos trechos a voz sai amostra por amostra igual à do corte. Dentro, o trecho passa pelo ffmpeg
e é alinhado ao original pela envoltória (a energia de cada sílaba): o deslocamento de tom e o
afftfilt atrasam ou adiantam o som de 10 a 60 ms, e esse número muda com o build do ffmpeg, então ele
é MEDIDO em cada trecho, nunca fixo (o hélio do Reels 1 saiu 11 ms adiantado). As emendas têm 20 ms
de transição cruzada, sem estalo. O eco deixa a cauda passar do fim do trecho, como um eco de verdade.

O mixar_final.py usa a voz pronta no lugar do áudio do cut.mp4 sempre que há item `voz`; ela fica
guardada em `<edit>/.voz/efeitos-<assinatura>.wav` e só é refeita quando o corte ou os itens mudam.

    uv run python -X utf8 helpers/voz_efeitos.py <edit>                      (prepara e diz o que fez)
    uv run python -X utf8 helpers/voz_efeitos.py <edit> --previa helio 12.4 2.1 -o previa.wav
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

import efeitos as ef  # mesma pasta deste arquivo

SR = 48000
CRUZA = 0.02  # s de transição cruzada em cada emenda
FOLGA = 0.25  # s de som original antes e depois do trecho que o filtro recebe (o tom precisa de contexto)
BUSCA = 0.12  # s: o maior deslocamento que o alinhamento procura
CAUDA_ECO = 0.7  # s de cauda do eco depois do trecho

# o nome, o nome em inglês e a cadeia do ffmpeg (ar = a taxa de amostragem). O tom vai pelo rubberband
# quando o ffmpeg tem (o atraso dele é constante; o do atempo oscila ~5 ms de sílaba para sílaba) e,
# sem ele, pelo asetrate + atempo (RESERVA), que soa igual: o tom e o timbre sobem juntos, voz de desenho.
EFEITOS = {
    "helio": ("Gás hélio", "Helium", "rubberband=pitch=1.335:formant=shifted"),
    "eco": ("Eco", "Echo", "aecho=0.8:0.85:180|360:0.4|0.25"),
    "robo": ("Robô", "Robot", "afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=512:overlap=0.75"),
    "grave": ("Grave", "Deep", "rubberband=pitch=0.78:formant=shifted"),
    "radio": ("Rádio", "Radio", "highpass=f=320,lowpass=f=3200,acompressor=threshold=0.1:ratio=6:attack=5:release=60,volume=1.6"),
}
RESERVA = {"helio": "asetrate={ar}*1.335,aresample={ar},atempo=0.749", "grave": "asetrate={ar}*0.78,aresample={ar},atempo=1.282"}
_RUBBERBAND: list[bool] = []


def tem_rubberband() -> bool:
    if not _RUBBERBAND:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, errors="replace")
        _RUBBERBAND.append(" rubberband " in r.stdout)
    return _RUBBERBAND[0]


def cadeia(efeito: str) -> str:
    """A cadeia do efeito neste ffmpeg."""
    return RESERVA[efeito] if efeito in RESERVA and not tem_rubberband() else EFEITOS[efeito][2]
PASTA = ".voz"


def _ler_audio(arquivo: Path) -> np.ndarray:
    """O som do arquivo, estéreo float32 a 48 kHz (o mesmo formato do mixar_final)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arquivo), "-vn", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def _ffmpeg(x: np.ndarray, cadeia: str) -> np.ndarray:
    """Passa o trecho (estéreo float32) pela cadeia do ffmpeg e devolve no mesmo formato."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-i", "-",
                        "-af", cadeia.format(ar=SR), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                       input=np.ascontiguousarray(x, np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(r, np.float32).reshape(-1, 2).copy()


def _envoltoria(x: np.ndarray, passo: int) -> np.ndarray:
    m = np.abs(x).mean(axis=1)
    n = len(m) // passo
    e = m[: n * passo].reshape(n, passo).mean(axis=1)
    return (e - e.mean()) / (e.std() + 1e-9)


def deslocamento(original: np.ndarray, processado: np.ndarray) -> int:
    """Quantas amostras o processado está ATRASADO em relação ao original (negativo = adiantado),
    pela correlação das envoltórias em passos de 1 ms, refinada em passos de 0,1 ms."""
    def melhor(passo: int, centro: int, raio: int) -> int:
        a, b = _envoltoria(original, passo), _envoltoria(processado, passo)
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
        c0 = centro // passo
        cands = range(c0 - raio, c0 + raio + 1)
        score = [float(np.dot(a[max(0, -k):n - max(0, k)], b[max(0, k):n - max(0, -k)])) / max(1, n - abs(k)) for k in cands]
        return cands[int(np.argmax(score))] * passo

    grosso = melhor(SR // 1000, 0, int(BUSCA * 1000))
    return melhor(SR // 10000, grosso, 12)


def processar(voz: np.ndarray, inicio: float, duracao: float, efeito: str) -> tuple[np.ndarray, int]:
    """O trecho com o efeito, alinhado: devolve (o trecho do tamanho [inicio, fim) — mais a cauda,
    no eco —, o deslocamento medido em amostras)."""
    a, b = int(round(inicio * SR)), int(round((inicio + duracao) * SR))
    f0, f1 = max(0, a - int(FOLGA * SR)), min(len(voz), b + int(FOLGA * SR))
    entrada = voz[f0:f1]
    if efeito == "eco":
        entrada = np.concatenate([entrada, np.zeros((int(CAUDA_ECO * SR), 2), np.float32)])
    saida = _ffmpeg(entrada, cadeia(efeito))
    d = 0 if efeito == "eco" else deslocamento(voz[f0:f1], saida[: f1 - f0])
    saida = saida[d:] if d >= 0 else np.concatenate([np.zeros((-d, 2), np.float32), saida])
    cauda = int(CAUDA_ECO * SR) if efeito == "eco" else 0
    trecho = saida[a - f0: b - f0 + cauda]
    falta = (b - a + cauda) - len(trecho)
    if falta > 0:
        trecho = np.concatenate([trecho, np.zeros((falta, 2), np.float32)])
    return trecho, d


def aplicar(voz: np.ndarray, itens: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """A voz inteira com os trechos trocados. Fora deles, igual amostra por amostra."""
    out = voz.copy()
    feitos = []
    cr = int(CRUZA * SR)
    for it in sorted(itens, key=lambda i: i["inicio"]):
        a = int(round(it["inicio"] * SR))
        b = min(len(voz), int(round((it["inicio"] + it["duracao"]) * SR)))
        if b - a < 2 * cr:
            continue
        trecho, d = processar(voz, it["inicio"], it["duracao"], it["efeito"])
        n = b - a
        sobe = np.ones(n, np.float32)
        sobe[:cr] = np.linspace(0, 1, cr)
        sobe[-cr:] = np.linspace(1, 0, cr)
        out[a:b] = voz[a:b] * (1 - sobe)[:, None] + trecho[:n] * sobe[:, None]
        if len(trecho) > n:  # a cauda do eco soma por cima do que vem depois
            cauda = trecho[n: n + (len(out) - b)]
            k = np.linspace(1, 0, len(cauda), dtype=np.float32)[:, None]
            out[b: b + len(cauda)] += cauda * k
        feitos.append({**it, "deslocamento_ms": round(d / SR * 1000, 1)})
    return out, feitos


def _itens(edit: Path) -> list[dict]:
    return [i for i in ef.load(Path(edit) / "efeitos.json")["itens"] if i["tipo"] == "voz"]


def _gravar_wav(p: Path, x: np.ndarray) -> None:
    import wave
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    tmp = p.with_suffix(".tmp.wav")
    with wave.open(str(tmp), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    tmp.replace(p)


def preparar(edit: Path, video: Path | None = None) -> Path | None:
    """A voz com os efeitos do efeitos.json (None sem item `voz`), guardada por assinatura."""
    edit = Path(edit)
    itens = _itens(edit)
    if not itens:
        return None
    if video is None:
        state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
        video = edit / (state.get("video") or "cut.mp4")
    st = Path(video).stat()
    assinatura = hashlib.sha1(json.dumps([str(video), st.st_size, st.st_mtime_ns, itens, EFEITOS], sort_keys=True,
                                         default=str).encode()).hexdigest()[:16]
    pasta = edit / PASTA
    alvo = pasta / f"efeitos-{assinatura}.wav"
    if alvo.is_file():
        return alvo
    pasta.mkdir(exist_ok=True)
    for velho in pasta.glob("efeitos-*.wav"):
        velho.unlink(missing_ok=True)
    voz, _ = aplicar(_ler_audio(video), itens)
    _gravar_wav(alvo, voz)
    return alvo


def previa(edit: Path, efeito: str, inicio: float, duracao: float, saida: Path, video: Path | None = None) -> Path:
    """Só o trecho, com o efeito, para ouvir no editor antes de usar (meio segundo antes e depois)."""
    edit = Path(edit)
    if video is None:
        state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
        video = edit / (state.get("video") or "cut.mp4")
    voz = _ler_audio(video)
    out, _ = aplicar(voz, [{"inicio": inicio, "duracao": duracao, "efeito": efeito}])
    a, b = max(0, int((inicio - 0.5) * SR)), min(len(out), int((inicio + duracao + 0.5) * SR))
    _gravar_wav(Path(saida), out[a:b])
    return Path(saida)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--previa", nargs=3, metavar=("EFEITO", "INICIO", "DURACAO"))
    ap.add_argument("-o", "--saida", type=Path)
    a = ap.parse_args()
    if a.previa:
        efeito, ini, dur = a.previa[0], float(a.previa[1]), float(a.previa[2])
        if efeito not in EFEITOS:
            print(f"efeito `{efeito}` não existe; os que existem: {', '.join(EFEITOS)}", file=sys.stderr)
            return 1
        print(previa(a.edit, efeito, ini, dur, a.saida or a.edit / PASTA / f"previa-{efeito}.wav"))
        return 0
    p = preparar(a.edit)
    print(p if p else "sem item `voz` no efeitos.json: a voz vai como está")
    return 0


if __name__ == "__main__":
    sys.exit(main())
