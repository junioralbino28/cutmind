"""Grade de batida de uma música: batidas, tempos fortes, BPM, energia por compasso, o drop e a força do
golpe em cada batida e em cada contratempo (`acentos`).

É a base para cortar na batida: o Modelo de montagem põe cada troca de clipe numa batida, e a linha
do tempo do editor mostra as batidas da trilha para o corte grudar nelas. Roda no CPU com o
Beat This! (CPJKU, 2024; MIT no código e nos pesos), sobre o torch que o whisperx já traz. O modelo
baixa uma vez para ~/.cutmind/batida (CUTMIND_BATIDA_DIR), conferido por tamanho e sha256.

    uv run python helpers/batida.py analisar <música> [--edit <dir>] [--modelo pequeno|completo]
    uv run python helpers/batida.py ouvir <música> [--edit <dir>] [--modelo …] [-o saida.mp3]
    uv run python helpers/batida.py baixar [--modelo pequeno|completo]

`analisar` grava a grade em JSON e imprime um resumo. O cache é pelo CONTEÚDO do áudio (sha256), não
pelo nome: renomear o arquivo não refaz a análise, trocar a música refaz. Com --edit a grade fica em
`<edit>/batidas/`, junto do projeto; sem ele, em `~/.cutmind/batida/grades/`.

`ouvir` grava a música com um clique em cada batida (mais agudo e mais forte no tempo forte), para
conferir de ouvido se a grade caiu no lugar. Quem decide se a batida está certa é o ouvido.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path

import numpy as np

VERSAO = 2  # 2: a grade ganhou `acentos` (a força do golpe na batida e no contratempo)
SR = 22050  # a taxa em que o Beat This! trabalha; o áudio já chega nela e ele não reamostra

_URL = "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/"
MODELOS = {
    "pequeno": {"nome": "small0", "arquivo": "beat_this-small0.ckpt", "tamanho": 8_451_101,
                "sha256": "6074be2c4d490c5f6101fcc374a1ec72ae93456e23bb6019783b849f5dc7d47b"},
    "completo": {"nome": "final0", "arquivo": "beat_this-final0.ckpt", "tamanho": 81_058_141,
                 "sha256": "8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331"},
}
# Qual dos dois vai como padrão sai da prova de ouvido com músicas de verdade: se o pequeno acertar
# tanto quanto o completo, fica o pequeno, pelo peso do download. Medido em 24/10/2026 numa bateria
# sintética: os dois acertam 100% num andamento fixo e em troca de andamento com 30 s em cada um;
# com só 10 s em cada andamento, o pequeno acerta 62% das batidas e o completo 88%.
MODELO_PADRAO = "completo"


class ErroBatida(Exception):
    """Falha que a pessoa entende e consegue resolver (download, arquivo, ffmpeg)."""


def pasta() -> Path:
    return Path(os.environ.get("CUTMIND_BATIDA_DIR") or Path.home() / ".cutmind" / "batida")


def sha256_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(modelo: str = MODELO_PADRAO) -> Path:
    """O arquivo do modelo, baixado uma vez e conferido por tamanho e sha256."""
    m = MODELOS[modelo]
    destino = pasta() / m["arquivo"]
    if destino.is_file() and destino.stat().st_size == m["tamanho"]:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    part = destino.with_name(destino.name + ".part")
    print(f"baixando o modelo de batida ({m['tamanho'] / 1e6:.0f} MB, uma vez)…", flush=True)
    try:
        req = urllib.request.Request(_URL + m["nome"] + ".ckpt", headers={"User-Agent": "cutmind-batida"})
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
            while bloco := r.read(1 << 20):
                f.write(bloco)
    except (urllib.error.URLError, OSError) as e:
        part.unlink(missing_ok=True)
        raise ErroBatida(f"não consegui baixar o modelo de batida ({e.__class__.__name__}); tente de novo")
    if part.stat().st_size != m["tamanho"] or sha256_arquivo(part) != m["sha256"]:
        part.unlink()
        raise ErroBatida("o modelo de batida chegou diferente do esperado e foi apagado; tente de novo")
    part.replace(destino)
    return destino


def ler_audio(arquivo: Path, sr: int = SR) -> np.ndarray:
    """O áudio do arquivo em mono, float32, na taxa `sr`. Qualquer formato que o ffmpeg abra
    serve, inclusive o som de um vídeo."""
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(arquivo), "-vn",
                            "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                           capture_output=True)
    except FileNotFoundError:
        raise ErroBatida("o ffmpeg não está no PATH")
    if r.returncode != 0:
        msg = (r.stderr or b"").decode("utf-8", "replace").strip()[-300:]
        raise ErroBatida(f"o ffmpeg não conseguiu ler {Path(arquivo).name}: {msg}")
    return np.frombuffer(r.stdout, dtype="<f4").copy()


_detectores: dict = {}


def detectar(sinal: np.ndarray, sr: int, modelo: str = MODELO_PADRAO) -> tuple[np.ndarray, np.ndarray]:
    """Batidas e tempos fortes, em segundos. O detector fica carregado entre uma música e outra."""
    if modelo not in _detectores:
        from beat_this.inference import Audio2Beats
        _detectores[modelo] = Audio2Beats(checkpoint_path=str(baixar(modelo)), device="cpu", dbn=False)
    if len(sinal) < sr:  # menos de 1 s não tem batida, e o modelo não precisa ver
        return np.zeros(0), np.zeros(0)
    batidas, fortes = _detectores[modelo](sinal, sr)
    return np.asarray(batidas, dtype=float), np.asarray(fortes, dtype=float)


def bpm(batidas) -> float | None:
    """Pelo ajuste de reta do tempo de cada batida contra o número dela. O ajuste desfaz o
    arredondamento do modelo, que marca as batidas em quadros de 20 ms (a 140 BPM, a mediana dos
    intervalos sozinha dava 142,9). As batidas são numeradas intervalo a intervalo, pela mediana:
    numerar pelo tempo total acumulava o erro do período de partida e passava a numerar errado no
    fim de uma música longa; e um intervalo de ~2 períodos conta como uma batida perdida no meio."""
    t = np.asarray(batidas, dtype=float)
    if len(t) < 2:
        return None
    d = np.diff(t)
    p0 = float(np.median(d))
    if len(t) < 3:
        return round(60.0 / p0, 1)
    k = np.concatenate([[0.0], np.cumsum(np.maximum(1.0, np.round(d / p0)))])
    return round(60.0 / float(np.polyfit(k, t, 1)[0]), 1)


def confianca(batidas) -> str:
    """Quão regular é a grade. Música sem batida clara (piano sozinho, ambiente) sai "baixa", e o
    agente avisa antes de cortar nela."""
    if len(batidas) < 8:
        return "baixa"
    d = np.diff(batidas)
    cv = float(np.std(d) / np.mean(d))
    return "alta" if cv < 0.06 else "media" if cv < 0.15 else "baixa"


def compassos(sinal: np.ndarray, sr: int, fortes, duracao: float) -> list[dict]:
    """Um item por compasso (de um tempo forte ao seguinte), com a energia RMS relativa à do
    compasso mais forte da música (0 a 1)."""
    if len(fortes) == 0:
        return []
    bordas = list(fortes) + [duracao]
    itens = []
    for a, b in zip(bordas, bordas[1:]):
        trecho = sinal[int(a * sr):int(b * sr)]
        rms = float(np.sqrt(np.mean(np.square(trecho, dtype=np.float64)))) if len(trecho) else 0.0
        itens.append({"inicio": round(float(a), 3), "fim": round(float(b), 3), "energia": rms})
    pico = max(i["energia"] for i in itens) or 1.0
    for i in itens:
        i["energia"] = round(i["energia"] / pico, 3)
    return itens


def envelope_de_ataque(sinal: np.ndarray, sr: int = SR, hop: int = 220, nfft: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    """A força de ataque a cada `hop` amostras (10 ms a 22.050 Hz), pelo fluxo espectral: quanto o espectro
    sobe de um quadro para o outro. Conta o grave (bumbo, até 150 Hz) e o médio (caixa, palma e voz, até
    4 kHz), cada um dividido pelo próprio percentil 99 e somados, para um golpe de bumbo e um de caixa pesarem
    parecido. O agudo (chimbal) fica fora: ele marca todas as colcheias por igual e não é o que se ouve como
    batida. Devolve (instantes, força)."""
    if len(sinal) < nfft:
        return np.zeros(0), np.zeros(0)
    sinal = np.ascontiguousarray(sinal, dtype=np.float32)
    n = 1 + (len(sinal) - nfft) // hop
    quadros = np.lib.stride_tricks.as_strided(sinal, shape=(n, nfft), strides=(sinal.strides[0] * hop, sinal.strides[0]))
    janela = np.hanning(nfft).astype(np.float32)
    freqs = np.fft.rfftfreq(nfft, 1 / sr)
    grave, medio = freqs < 150.0, (freqs >= 150.0) & (freqs < 4000.0)
    fg, fm = np.zeros(n), np.zeros(n)
    anterior = None
    for a in range(0, n, 2048):  # em blocos: uma música longa inteira de uma vez passaria de 1 GB
        m = np.log1p(10 * np.abs(np.fft.rfft(quadros[a:a + 2048] * janela, axis=1)))
        d = np.maximum(0.0, np.diff(np.vstack([m[:1] if anterior is None else anterior, m]), axis=0))
        fg[a:a + len(m)] = d[:, grave].sum(axis=1)
        fm[a:a + len(m)] = d[:, medio].sum(axis=1)
        anterior = m[-1:]
    t = np.arange(n) * hop / sr + nfft / 2 / sr
    return t, fg / (np.percentile(fg, 99) or 1.0) + fm / (np.percentile(fm, 99) or 1.0)


def acentos(t_env: np.ndarray, env: np.ndarray, batidas, raio: float = 0.04) -> list[list[float]]:
    """A força do golpe em cada batida e no contratempo, o meio entre uma batida e a seguinte, em ordem:
    [batida 0, meio 0, batida 1, meio 1, …, última batida], cada um [instante, força]. A força é o maior
    ataque a até 40 ms. No contratempo o instante é o do próprio pico: o golpe fora da grade não cai
    exatamente no meio (medido numa música real: de 3 a 18 ms dele)."""
    b = [float(x) for x in batidas]
    if not len(env) or not b:
        return []

    def pico(x: float, refinar: bool) -> list[float]:
        i0, i1 = np.searchsorted(t_env, [x - raio, x + raio])
        if i1 <= i0:
            return [round(x, 3), 0.0]
        j = i0 + int(np.argmax(env[i0:i1]))
        return [round(float(t_env[j]) if refinar else x, 3), round(float(env[j]), 3)]

    out = []
    for i, x in enumerate(b):
        out.append(pico(x, False))
        if i + 1 < len(b):
            out.append(pico((x + b[i + 1]) / 2, True))
    return out


def achar_drop(itens: list[dict], janela: int = 4, salto: float = 0.15) -> float | None:
    """O começo do compasso em que a música "explode": a maior subida entre a energia média dos
    `janela` compassos seguintes e a dos anteriores. Sem uma subida clara (`salto`), não há drop."""
    e = [i["energia"] for i in itens]
    melhor, onde = salto, None
    for k in range(2, len(e)):
        antes = e[max(0, k - janela):k]
        depois = e[k:k + janela]
        subida = float(np.mean(depois) - np.mean(antes))
        if subida > melhor and float(np.mean(depois)) >= 0.6:
            melhor, onde = subida, itens[k]["inicio"]
    return onde


def caminho_grade(sha: str, modelo: str, edit: Path | None) -> Path:
    base = Path(edit) / "batidas" if edit else pasta() / "grades"
    return base / f"{sha[:16]}.{modelo}.json"


def analisar(arquivo: Path, edit: Path | None = None, modelo: str = MODELO_PADRAO) -> tuple[dict, Path]:
    """A grade da música (do cache, se essa música já foi analisada com esse modelo)."""
    arquivo = Path(arquivo)
    if not arquivo.is_file():
        raise ErroBatida(f"arquivo não encontrado: {arquivo}")
    sha = sha256_arquivo(arquivo)
    destino = caminho_grade(sha, modelo, edit)
    if destino.is_file():
        try:
            grade = json.loads(destino.read_text(encoding="utf-8"))
            if grade.get("versao") == VERSAO and grade.get("sha256") == sha:
                return grade, destino
        except (OSError, ValueError):
            pass
    sinal = ler_audio(arquivo)
    duracao = len(sinal) / SR
    batidas, fortes = detectar(sinal, SR, modelo)
    itens = compassos(sinal, SR, fortes, duracao)
    t_env, env = envelope_de_ataque(sinal, SR)
    grade = {
        "versao": VERSAO,
        "arquivo": arquivo.name,
        "sha256": sha,
        "duracao": round(duracao, 3),
        "modelo": f"beat_this {MODELOS[modelo]['nome']}",
        "bpm": bpm(batidas),
        "confianca": confianca(batidas),
        "drop": achar_drop(itens),
        "batidas": [round(float(t), 3) for t in batidas],
        "fortes": [round(float(t), 3) for t in fortes],
        "compassos": itens,
        "acentos": acentos(t_env, env, batidas),
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_bytes(json.dumps(grade, ensure_ascii=False, indent=1).encode("utf-8"))
    tmp.replace(destino)
    return grade, destino


def cliques(batidas, fortes, duracao: float, sr: int = 44100) -> np.ndarray:
    """Uma faixa só de cliques: 25 ms de seno com queda rápida em cada batida, mais agudo (2,5 kHz)
    e mais forte no tempo forte que nas outras (1,5 kHz)."""
    faixa = np.zeros(int(duracao * sr) + sr, dtype=np.float32)
    n = int(0.025 * sr)
    t = np.arange(n) / sr
    envelope = np.exp(-t * 160.0)
    fortes_set = {round(float(f), 2) for f in fortes}
    for b in batidas:
        forte = round(float(b), 2) in fortes_set
        clique = (0.8 if forte else 0.5) * np.sin(2 * np.pi * (2500.0 if forte else 1500.0) * t) * envelope
        i = int(float(b) * sr)
        faixa[i:i + n] += clique[: max(0, len(faixa) - i)]
    return faixa[: int(duracao * sr)]


def _grava_wav(caminho: Path, faixa: np.ndarray, sr: int) -> None:
    pcm = (np.clip(faixa, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def ouvir(arquivo: Path, saida: Path, edit: Path | None = None, modelo: str = MODELO_PADRAO) -> Path:
    """A música com um clique em cada batida, para conferir a grade de ouvido."""
    grade, _ = analisar(arquivo, edit, modelo)
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "cliques.wav"
        _grava_wav(wav, cliques(grade["batidas"], grade["fortes"], grade["duracao"]), 44100)
        codec = {".mp3": ["-c:a", "libmp3lame", "-q:a", "3"], ".m4a": ["-c:a", "aac", "-b:a", "192k"],
                 ".wav": ["-c:a", "pcm_s16le"]}.get(saida.suffix.lower())
        if codec is None:
            raise ErroBatida("a saída precisa terminar em .mp3, .m4a ou .wav")
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(arquivo), "-i", str(wav),
                            "-filter_complex",
                            "[0:a]aresample=44100,volume=0.7[m];[m][1:a]amix=inputs=2:duration=first:normalize=0",
                            "-vn", *codec, str(saida)], capture_output=True)
        if r.returncode != 0:
            msg = (r.stderr or b"").decode("utf-8", "replace").strip()[-300:]
            raise ErroBatida(f"o ffmpeg não conseguiu juntar os cliques: {msg}")
    return saida


def _resumo(grade: dict, destino: Path) -> str:
    drop = f"{grade['drop']:.2f} s" if grade.get("drop") is not None else "sem drop claro"
    return (f"{grade['arquivo']}: {grade['bpm']} BPM, {len(grade['batidas'])} batidas, "
            f"{len(grade['fortes'])} compassos, drop {drop}, confiança {grade['confianca']} "
            f"({grade['modelo']})\n  grade: {destino}")


def main() -> None:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="batida", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("analisar", "ouvir"):
        p = sub.add_parser(nome)
        p.add_argument("musica", type=Path)
        p.add_argument("--edit", type=Path, default=None)
        p.add_argument("--modelo", choices=sorted(MODELOS), default=MODELO_PADRAO)
        if nome == "ouvir":
            p.add_argument("-o", "--saida", type=Path, default=None)
    p = sub.add_parser("baixar")
    p.add_argument("--modelo", choices=sorted(MODELOS), default=MODELO_PADRAO)
    args = ap.parse_args()
    try:
        if args.cmd == "baixar":
            print(f"ok: {baixar(args.modelo)}")
        elif args.cmd == "analisar":
            grade, destino = analisar(args.musica, args.edit, args.modelo)
            print(_resumo(grade, destino))
        else:
            saida = args.saida or ((args.edit / "verify") if args.edit else Path.cwd()) / f"batida_{args.musica.stem}.mp3"
            grade, destino = analisar(args.musica, args.edit, args.modelo)
            print(_resumo(grade, destino))
            print(f"  para ouvir: {ouvir(args.musica, saida, args.edit, args.modelo)}")
    except ErroBatida as e:
        sys.exit(f"batida: {e}")


if __name__ == "__main__":
    main()
