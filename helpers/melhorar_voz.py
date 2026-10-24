#!/usr/bin/env python3
"""Melhorar voz: a voz do próprio vídeo com dois reguladores, Voz (limpa → estúdio) e Fundo.

O desenho foi aprovado no ouvido (23/10): a voz limpa vem do DeepFilterNet (máscara: a mesma
voz, sem o ruído, no mesmo tempo do original), o timbre de estúdio vem do Sidon (generativo,
48 kHz) e o fundo é o original menos a voz limpa. A Voz mistura só a MAGNITUDE do espectro,
interpolada em log, sobre a fase da voz limpa (onde a limpa não tem som, a do Sidon). Misturar
as ondas soa dobrado: a voz reconstruída não bate fase com fase com a limpa. Fundo 100% com
Voz 0% é o original.

    python melhorar_voz.py preparar <edit> [--de-novo]     # uma vez por corte (~1 min por min)
    python melhorar_voz.py aplicar <edit> --voz 50 --fundo 20
    python melhorar_voz.py aplicar <edit>                  # a última escolha (ou 50 e 20)
    python melhorar_voz.py restaurar <edit>                # o cut.mp4 volta ao som original
    python melhorar_voz.py estado <edit>                   # JSON: o que o editor e o agente leem
    python melhorar_voz.py baixar                          # só os modelos (~1 GB, uma vez)

`preparar` grava em <edit>/.melhorar/ as faixas de trabalho (voz limpa, estúdio alinhado e
fundo), o som original do corte (para restaurar) e a prévia do editor: os degraus de Voz
(voz-000 a voz-100), o fundo e o original, todos no mesmo volume e com a mesma fase, para o
editor misturar dois degraus vizinhos sem dobrar. `aplicar` faz a mistura no número exato (não
a dos degraus), troca o som do cut.mp4 (a imagem não muda), passa o loudnorm do kit e acerta
também o remotion/public/cut.mp4 quando ele é do mesmo corte. Se o preparo não vale para o
cut.mp4 de agora (corte novo), `aplicar` prepara antes.

Modelos, baixados só quando usados, em ~/.cutmind/voz (CUTMIND_VOZ_DIR): o DeepFilterNet
0.5.6 (o executável oficial, 27 a 39 MB conforme o sistema) e o Sidon fp32 (preditor 775 MB e
vocoder 210 MB, MIT; o preditor int8 soa metálico). Conferidos por tamanho e sha256; se a
conexão cai, o pedaço baixado fica e a próxima vez continua de onde parou.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np

import render  # mesma pasta deste arquivo: o loudnorm do kit

SR = 48000
SR_SIDON = 16000
N, H = 2048, 512  # STFT: janela de Hann de 42,7 ms, passo de 10,7 ms
DEGRAUS = (0, 25, 50, 75, 100)  # Voz, em %: a prévia do editor mistura dois vizinhos
PADRAO = {"voz": 50, "fundo": 20}  # como o painel abre na primeira vez
PISO_DB = -45.0  # abaixo disto (em relação ao pico do quadro) a limpa "não tem som": vale a fase do Sidon
ALVO = -16.0  # LUFS de cada degrau da prévia: arrastar a Voz não muda o volume
TETO = 0.89  # pico máximo de qualquer faixa da prévia (−1 dBFS)
# O Sidon olha o trecho inteiro de uma vez: memória e tempo crescem com o quadrado do tamanho
# (82 s de uma vez: 11 GB e 7 min). Então roda em pedaços cortados no ponto mais quieto, cada um
# com um contexto de cada lado. Medido em 23/10 (pico de memória num vídeo de 82 s; fidelidade
# da Voz 100% contra a rodada única de 43 s aprovada na escuta): 30 s + 3 s, 3,8 GB e 0,993;
# 15 s + 2 s, 2,0 GB e 0,985 (0,996 na Voz 50%, o padrão).
PEDACO = {"grande": (30.0, 3.0), "pequeno": (15.0, 2.0)}  # (bloco, contexto), em s
MEMORIA_GRANDE = 12  # GB de memória do computador para o pedaço grande
EMENDA = 0.01  # s de transição entre dois pedaços do Sidon
FOLGA_DF = 0.25  # s de silêncio no fim da entrada do DeepFilterNet: ele devolve ~30 ms a menos
MAX_DURACAO = 10 * 60  # o Sidon leva ~1 s por s; no editor, acima de ~3 min fica para depois
VIVO = 60.0  # s sem notícia do preparo: ele morreu
PASTA = ".melhorar"
VERSAO = 1

_HF = "https://huggingface.co/soniqo/Sidon-ONNX/resolve/a6dce244cbcd0361ef79c030e246e6f9671770c1/fp32/"
_DF = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/"
SIDON = {
    "preditor": {"arquivo": "sidon-predictor-fp32.onnx", "url": _HF + "sidon-predictor.onnx",
                 "tamanho": 774666339,
                 "sha256": "4311e64704b6c7d07616f5655640ac39442e1dfb6756d7ff1dcaf87f6d2429e7"},
    "vocoder": {"arquivo": "sidon-vocoder-fp32.onnx", "url": _HF + "sidon-vocoder.onnx",
                "tamanho": 209947463,
                "sha256": "9d672758a4b920b18bc56f17763d21cac4a6d2e04354642b45ec51a1d7a5a178"},
}
_DF_BIN = {  # (sistema, máquina) → executável da Release oficial
    ("Windows", "x86_64"): ("deep-filter-0.5.6-x86_64-pc-windows-msvc.exe", 26912256,
                            "75e11fa16445f560cb6b021521ddb89e89270d13b83089705d98776f58fd7915"),
    ("Darwin", "arm64"): ("deep-filter-0.5.6-aarch64-apple-darwin", 27877081,
                          "4601e7f4e4c03e59a4c5b5000216ef3add3e808799cfccd95e14e83ea4611081"),
    ("Darwin", "x86_64"): ("deep-filter-0.5.6-x86_64-apple-darwin", 29933512,
                           "d3be84003acb7c23e738ad7f70a158ec779a8d233a82e7fa3e717d112eb5b50f"),
    ("Linux", "x86_64"): ("deep-filter-0.5.6-x86_64-unknown-linux-musl", 36417296,
                          "70775e251eee44c0f2451a1e833326cf8bcbbe304d3e7cd12851e6fce72ef7da"),
    ("Linux", "arm64"): ("deep-filter-0.5.6-aarch64-unknown-linux-gnu", 39238496,
                         "14e02a1c0028f3ca0bdf83b62b3336e56ba0556894ef295a95e8573f06557166"),
}
_DF_BIN[("Windows", "arm64")] = _DF_BIN[("Windows", "x86_64")]  # o Windows ARM roda o x64

ETAPAS = {"baixar": "Baixando os modelos de voz (só na 1ª vez)", "limpar": "Limpando a voz",
          "estudio": "Criando a voz de estúdio", "degraus": "Montando os reguladores"}


class VozErro(Exception):
    pass


# ---- modelos ----
def pasta_modelos() -> Path:
    return Path(os.environ.get("CUTMIND_VOZ_DIR") or Path.home() / ".cutmind" / "voz")


def _maquina() -> tuple[str, str]:
    m = platform.machine().lower()
    return platform.system(), {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(m, m)


def modelos() -> list[dict]:
    """O que o preparo usa neste computador: o executável do DeepFilterNet e o Sidon."""
    so = _maquina()
    if so not in _DF_BIN:
        raise VozErro(f"o DeepFilterNet não tem executável para {so[0]} {so[1]}")
    arq, tam, sha = _DF_BIN[so]
    return [{"arquivo": arq, "url": _DF + arq, "tamanho": tam, "sha256": sha, "executavel": True},
            *SIDON.values()]


def _faltam(pasta: Path) -> list[dict]:
    return [m for m in modelos() if not ((pasta / m["arquivo"]).is_file()
                                          and (pasta / m["arquivo"]).stat().st_size == m["tamanho"])]


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _baixar(m: dict, destino: Path, ao_andar: Callable[[int], None]) -> None:
    """Baixa `m` para `destino` continuando o pedaço que já existe (cabeçalho Range).
    Nunca grava mais que o tamanho esperado; só guarda depois de conferir o sha256."""
    part = destino.with_name(destino.name + ".part")
    feito = part.stat().st_size if part.is_file() else 0
    if feito > m["tamanho"]:
        part.unlink()
        feito = 0
    if feito < m["tamanho"]:
        cab = {"User-Agent": "cutmind-voz"}
        if feito:
            cab["Range"] = f"bytes={feito}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(m["url"], headers=cab), timeout=60) as r:
                if feito and r.status != 206:  # o servidor ignorou o Range: recomeça
                    ao_andar(-feito)
                    feito = 0
                with open(part, "ab" if feito else "wb") as f:
                    while feito < m["tamanho"]:
                        bloco = r.read(min(1 << 20, m["tamanho"] - feito))
                        if not bloco:
                            break
                        f.write(bloco)
                        feito += len(bloco)
                        ao_andar(len(bloco))
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            raise VozErro(f"a conexão caiu baixando {m['arquivo']} ({e.__class__.__name__}): o que já veio "
                          "ficou guardado e a próxima tentativa continua de onde parou") from None
    if part.stat().st_size < m["tamanho"]:
        raise VozErro(f"{m['arquivo']} veio pela metade: o que já veio ficou guardado e a próxima tentativa "
                      "continua de onde parou")
    if _sha256(part) != m["sha256"]:
        part.unlink()
        raise VozErro(f"{m['arquivo']} chegou diferente do esperado e foi apagado; tente de novo")
    if m.get("executavel"):
        part.chmod(part.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    part.replace(destino)


def baixar_modelos(ao_andar: Callable[[int, int], None] | None = None) -> Path:
    """Garante os modelos no cache. `ao_andar(baixado, total)` em bytes, só do que falta."""
    pasta = pasta_modelos()
    faltam = _faltam(pasta)
    if not faltam:
        return pasta
    pasta.mkdir(parents=True, exist_ok=True)
    total = sum(m["tamanho"] for m in faltam)
    ja = sum((pasta / (m["arquivo"] + ".part")).stat().st_size for m in faltam
             if (pasta / (m["arquivo"] + ".part")).is_file())
    livre = shutil.disk_usage(pasta).free
    if livre < total - ja + 200 * 1024 ** 2:
        raise VozErro(f"falta espaço para os modelos de voz: precisa de {_mb(total - ja + 200 * 1024 ** 2)} MB "
                      f"livres em {pasta} e há {_mb(livre)} MB")
    feito = [ja]

    def andou(n: int) -> None:
        feito[0] += n
        if ao_andar:
            ao_andar(feito[0], total)

    for m in faltam:
        _baixar(m, pasta / m["arquivo"], andou)
    return pasta


def _mb(n: int) -> int:
    return round(n / 1024 ** 2)


# ---- áudio (pelo ffmpeg) ----
def _ffmpeg(args: list[str], entrada: bytes | None = None) -> bytes:
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args], input=entrada, capture_output=True)
    if r.returncode != 0:
        msg = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise VozErro(f"o ffmpeg falhou: {msg[-1] if msg else r.returncode}")
    return r.stdout


def hash_audio(video: Path) -> str:
    """O sha256 dos pacotes do som (sem decodificar): o mesmo som dá o mesmo hash, mesmo que a
    imagem ou o arquivo mudem. É o que diz se o preparo vale para o vídeo de agora."""
    try:
        out = _ffmpeg(["-i", str(video), "-map", "0:a:0", "-c", "copy", "-f", "hash", "-hash", "sha256", "-"])
    except VozErro as e:
        if "matches no streams" in str(e):
            raise VozErro("o vídeo não tem som") from None
        raise
    m = re.search(rb"SHA256=([0-9a-f]{64})", out)
    if not m:
        raise VozErro("não consegui ler o som do vídeo")
    return m.group(1).decode()


def ler_audio(arq: Path) -> np.ndarray:
    """O som em mono, 48 kHz: a média dos canais que o arquivo TEM (gravação de celular é quase mono).
    Nunca pedir `-ac` ao ffmpeg aqui: ele abre um arquivo mono em estéreo a −3 dB por canal, e a voz
    limpa (mono, do DeepFilterNet) chegava 3 dB abaixo do original estéreo, deixando 29% da voz no
    fundo (medido em 23/10 contra as faixas da página aprovada)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels",
                        "-of", "csv=p=0", str(arq)], capture_output=True, text=True)
    try:
        canais = int(r.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        raise VozErro(f"não consegui ler o som de {Path(arq).name}") from None
    b = _ffmpeg(["-i", str(arq), "-map", "0:a:0", "-ar", str(SR), "-f", "f32le", "-"])
    return np.frombuffer(b, np.float32).reshape(-1, canais).astype(np.float64).mean(axis=1)


_PCM = ["-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-"]  # mono float de 48 kHz pelo cano


def reamostrar(x: np.ndarray, de: int, para: int) -> np.ndarray:
    b = _ffmpeg(["-f", "f32le", "-ar", str(de), "-ac", "1", "-i", "-", "-ar", str(para), "-f", "f32le", "-"],
                x.astype(np.float32).tobytes())
    return np.frombuffer(b, np.float32).astype(np.float64)


def lufs(x: np.ndarray) -> float | None:
    """Volume integrado (EBU R128). None quando não há o que medir (silêncio)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-nostdin", *_PCM, "-af", "ebur128",
                        "-f", "null", "-"], input=x.astype(np.float32).tobytes(), capture_output=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr.decode("utf-8", "replace"))
    i = float(m[-1]) if m else None
    return i if i is not None and i > -60 else None


def _ganho(x: np.ndarray) -> float:
    i = lufs(x)
    return 1.0 if i is None else 10 ** ((ALVO - i) / 20)


def gravar_flac(p: Path, x: np.ndarray) -> None:
    tmp = p.with_name(f".{p.name}.{os.getpid()}.flac")
    _ffmpeg(["-y", *_PCM, "-c:a", "flac", "-sample_fmt", "s16", str(tmp)], x.astype(np.float32).tobytes())
    _trocar(tmp, p)


def _trocar(tmp: Path, destino: Path, tentativas: int = 20) -> None:
    """os.replace com paciência: no Windows, quem está lendo o destino segura a troca por um instante."""
    for i in range(tentativas):
        try:
            tmp.replace(destino)
            return
        except PermissionError:
            if i == tentativas - 1:
                tmp.unlink(missing_ok=True)
                raise VozErro(f"{destino.name} está aberto em outro programa; feche e tente de novo") from None
            time.sleep(0.25)


def _no_tamanho(x: np.ndarray, n: int) -> np.ndarray:
    return x[:n] if len(x) >= n else np.pad(x, (0, n - len(x)))


def _deslocar(x: np.ndarray, k: int) -> np.ndarray:
    """Adianta `x` em k amostras (atrasa se k < 0), completando com silêncio."""
    if k == 0:
        return x
    y = np.zeros_like(x)
    if k > 0:
        y[:-k] = x[k:]
    else:
        y[-k:] = x[:k]
    return y


def atraso(ref: np.ndarray, x: np.ndarray, maximo_ms: int = 40) -> int:
    """Em amostras, quanto `x` está atrasado em relação a `ref`, pelo envelope de 1 ms.
    Sem som para comparar, 0."""
    h = SR // 1000
    n = min(len(ref), len(x)) // h
    if n < 2 * maximo_ms:
        return 0
    e1 = np.sqrt((ref[:n * h].reshape(n, h) ** 2).mean(1))
    e2 = np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(1))
    e1, e2 = e1 - e1.mean(), e2 - e2.mean()
    nota = {k: float(np.dot(e1[max(0, -k):n - max(0, k)], e2[max(0, k):n - max(0, -k)]))
            for k in range(-maximo_ms, maximo_ms + 1)}
    melhor = max(nota, key=lambda k: (nota[k], -abs(k)))
    return melhor * h if nota[melhor] > 0 else 0


def _atraso_fino(ref: np.ndarray, x: np.ndarray, maximo: int = SR // 20) -> int:
    """Atraso exato, em amostras, pela correlação cruzada (até 50 ms, nos primeiros 20 s)."""
    m = min(len(ref), len(x), SR * 20)
    if m < 2 * maximo or not np.any(ref[:m]) or not np.any(x[:m]):
        return 0
    t = 1 << int(np.ceil(np.log2(2 * m)))
    c = np.fft.irfft(np.fft.rfft(x[:m], t) * np.conj(np.fft.rfft(ref[:m], t)), t)
    cand = np.concatenate([c[-maximo:], c[:maximo + 1]])
    return int(np.argmax(cand)) - maximo


# ---- os modelos rodando ----
def limpar_deepfilter(orig: np.ndarray, comando: list[str]) -> np.ndarray:
    """A voz limpa: DeepFilterNet com redução total (-a 100) e o atraso compensado (-D).
    `comando` é o executável (uma lista, para o teste pôr um falso no lugar)."""
    with tempfile.TemporaryDirectory(prefix="cutmind-voz-") as tmp:
        ent, sai = Path(tmp) / "voz.wav", Path(tmp) / "saida"
        x = np.pad(orig, (0, int(FOLGA_DF * SR)))
        _ffmpeg(["-y", *_PCM, "-c:a", "pcm_f32le", str(ent)], x.astype(np.float32).tobytes())
        try:
            r = subprocess.run([*comando, "-D", "-a", "100", "-o", str(sai), str(ent)], capture_output=True,
                               stdin=subprocess.DEVNULL)
        except OSError as e:
            raise VozErro(f"o sistema não deixou rodar o DeepFilterNet ({Path(comando[-1]).name}: {e})") from None
        if r.returncode != 0 or not (sai / ent.name).is_file():
            msg = r.stderr.decode("utf-8", "replace").strip().splitlines()
            raise VozErro(f"o DeepFilterNet falhou: {msg[-1] if msg else r.returncode}")
        return ler_audio(sai / ent.name)


_EXTRATOR = []


def caracteristicas(x16: np.ndarray) -> np.ndarray:
    """As características do w2v-BERT 2.0 do áudio inteiro, como o extrator publicado as faz
    (conferido no teste), com a normalização separada: o extrator cru empilha as janelas de 10 ms
    de duas em duas e completa o fim com uma janela de enchimento (1,0); só as janelas reais são
    normalizadas, e o enchimento fica como o extrator o deixaria."""
    if not _EXTRATOR:
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        from transformers import SeamlessM4TFeatureExtractor

        _EXTRATOR.append(SeamlessM4TFeatureExtractor(feature_size=80, num_mel_bins=80, sampling_rate=SR_SIDON,
                                                     stride=2, padding_value=1.0, padding_side="right",
                                                     return_attention_mask=True))
    f = _EXTRATOR[0](x16.astype(np.float32), sampling_rate=SR_SIDON, do_normalize_per_mel_bins=False,
                     return_tensors="np")["input_features"][0]
    k = f.reshape(-1, f.shape[1] // 2).astype(np.float64)  # cada janela de 10 ms
    t = min(len(k), 1 + (len(x16) - 400) // 160)  # janelas reais: 25 ms a cada 10 ms, sem centralizar
    k[:t] = (k[:t] - k[:t].mean(0)) / np.sqrt(k[:t].var(0, ddof=1) + 1e-7)
    return k.reshape(f.shape).astype(np.float32)


class Sidon:
    """O Sidon pelo ONNX, no processador, em duas etapas: `caracteristicas` do vídeo inteiro e
    `gerar` a voz de um trecho delas (`quadro` amostras de 48 kHz por linha).

    O extrator é o do w2v-BERT 2.0, montado com a configuração publicada (conferido: igual ao
    baixado, diferença 0; ver `caracteristicas`). Ele normaliza cada faixa de frequência pela média e pela variância do
    que recebe; rodando pedaço a pedaço, cada um saía normalizado de um jeito e o timbre mudava
    longe da emenda (correlação 0,44 com a rodada única, medido em 23/10). Por isso a
    normalização é a do vídeo inteiro, e os pedaços são fatias dela."""

    quadro = 960  # 20 ms: duas janelas de 10 ms do extrator viram uma linha

    def __init__(self, pasta: Path):
        import onnxruntime as ort

        cpu = ["CPUExecutionProvider"]
        op = ort.SessionOptions()
        op.enable_cpu_mem_arena = False  # a reserva guarda o que já foi solto: 6,6 GB → 3,8 GB, ~25% mais lento
        try:
            self.preditor = ort.InferenceSession(str(pasta / SIDON["preditor"]["arquivo"]), op, providers=cpu)
            self.vocoder = ort.InferenceSession(str(pasta / SIDON["vocoder"]["arquivo"]), op, providers=cpu)
        except Exception as e:  # noqa: BLE001 - o onnxruntime tem uma exceção por tipo de falha
            apagados = _apagar_se_estragado(pasta)
            raise VozErro(f"não consegui abrir o Sidon ({e.__class__.__name__}: {str(e)[:160]})" +
                          (f"; {', '.join(apagados)} estava estragado, foi apagado e baixa de novo na próxima vez"
                           if apagados else "")) from None

    def caracteristicas(self, x16: np.ndarray) -> np.ndarray:
        return caracteristicas(x16)

    def gerar(self, f: np.ndarray) -> np.ndarray:
        g = self.preditor.run(None, {"input_features": f[None].astype(np.float32)})[0]
        return self.vocoder.run(None, {"features": g.astype(np.float32)})[0].reshape(-1).astype(np.float64)


def _apagar_se_estragado(pasta: Path) -> list[str]:
    apagados = []
    for m in SIDON.values():
        p = pasta / m["arquivo"]
        if p.is_file() and _sha256(p) != m["sha256"]:
            p.unlink()
            apagados.append(m["arquivo"])
    return apagados


def memoria_gb() -> float | None:
    """A memória física do computador, em GB (None se não der para saber)."""
    try:
        if sys.platform == "win32":
            import ctypes

            class Estado(ctypes.Structure):
                _fields_ = [("tamanho", ctypes.c_ulong), ("carga", ctypes.c_ulong),
                            *((k, ctypes.c_ulonglong) for k in ("total", "livre", "pt", "pl", "vt", "vl", "vx"))]

            e = Estado()
            e.tamanho = ctypes.sizeof(Estado)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e)):
                return None
            return e.total / 1024 ** 3
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except (OSError, ValueError, AttributeError):
        return None


def pedaco_do_computador() -> tuple[float, float]:
    gb = memoria_gb()
    return PEDACO["grande" if gb is not None and gb >= MEMORIA_GRANDE else "pequeno"]


def pedacos(voz: np.ndarray, bloco: float) -> list[tuple[int, int]]:
    """Corta em pedaços do mesmo tamanho, o menor número deles que cabe em `bloco` s cada: um
    pedaço curto sobrando no fim ouve pouco contexto (82,6 s em blocos fixos de 30 s deixavam um
    último de 4,8 s). Cada corte cai no meio dos 100 ms mais quietos da voz a até 15% do ponto
    ideal, nunca deixando o resto maior do que cabe; e em múltiplo de 3 amostras (16 kHz exato)."""
    n, passo, b = len(voz), SR // 10, int(bloco * SR)
    k = -(-n // b)
    if k <= 1:
        return [(0, n)]
    ideal = n / k
    cortes = [0]
    for j in range(1, k):
        alvo = j * ideal
        lo = max(cortes[-1] + passo, int(alvo - 0.15 * ideal), n - (k - j) * b)
        hi = min(cortes[-1] + b, int(alvo + 0.15 * ideal))
        if hi - lo >= passo:
            q = voz[lo:lo + (hi - lo) // passo * passo].reshape(-1, passo)
            c = lo + int(np.argmin((q ** 2).mean(1))) * passo + passo // 2
        else:
            c = lo
        cortes.append(-(-c // 3) * 3)  # para cima: o resto nunca passa do bloco
    cortes.append(n)
    return list(zip(cortes[:-1], cortes[1:]))


def estudio_em_pedacos(orig: np.ndarray, limpa: np.ndarray, modelo, bloco: float, contexto: float,
                       ao_andar: Callable[[int, int], None] | None = None) -> np.ndarray:
    """O timbre de estúdio do vídeo inteiro, pedaço a pedaço, cada um alinhado com a voz limpa.
    As características saem do vídeo inteiro (ver Sidon); os pedaços se emendam no ponto mais
    quieto, com 10 ms de transição. `modelo` tem `quadro`, `caracteristicas` e `gerar`."""
    n, q = len(orig), modelo.quadro
    f = modelo.caracteristicas(reamostrar(orig, SR, SR_SIDON))
    jn = len(f)
    cortes = [0, *(round(a / q) for a, _ in pedacos(limpa, bloco)[1:]), jn]
    ctx, r = round(contexto * SR / q), int(EMENDA * SR)
    m = max(n, jn * q)
    soma, peso = np.zeros(m), np.zeros(m)
    ref = _no_tamanho(limpa, m)
    for i, (ja, jb) in enumerate(zip(cortes[:-1], cortes[1:])):
        j0, j1 = max(0, ja - ctx), min(jn, jb + ctx)
        ini, a, b = j0 * q, ja * q, jb * q
        y = _no_tamanho(modelo.gerar(f[j0:j1]), (j1 - j0) * q)
        y = _deslocar(y, atraso(ref[ini:ini + len(y)], y))
        w = np.zeros(len(y))
        w[max(0, a - ini - (r if ja > 0 else 0)):b - ini + (r if jb < jn else 0)] = 1.0
        if ja > 0:
            w[a - ini - r:a - ini + r] = np.linspace(0, 1, 2 * r)
        if jb < jn:
            w[b - ini - r:b - ini + r] = np.linspace(1, 0, 2 * r)
        soma[ini:ini + len(y)] += w * y
        peso[ini:ini + len(y)] += w
        if ao_andar:
            ao_andar(i + 1, len(cortes) - 1)
    return (soma / np.maximum(peso, 1e-9))[:n]


# ---- a mistura espectral ----
def _janela() -> np.ndarray:
    return np.hanning(N + 1)[:-1]


def vozes(limpa: np.ndarray, estudio: np.ndarray, niveis: list[float], lote: int = 512) -> list[np.ndarray]:
    """A Voz em cada nível (0 = limpa, 1 = estúdio): magnitude interpolada em log, fase da limpa
    (onde a limpa não tem som, a do Sidon). Todos os níveis saem com a MESMA fase: misturar
    dois deles é misturar magnitudes, e o regulador nunca dobra. Em lotes de quadros, sem
    guardar o espectro inteiro na memória."""
    n = len(limpa)
    w = _janela()
    pad = (N // 2, N // 2 + N)
    lp, ep = np.pad(limpa, pad), np.pad(_no_tamanho(estudio, n), pad)
    q = 1 + (len(lp) - N) // H
    tam = H * (q - 1) + N
    tam += -tam % H
    saidas = [np.zeros(tam, np.float32) for _ in niveis]  # float32: metade da memória, erro ~1e-7
    soma = np.zeros(tam, np.float32)
    piso = 10 ** (PISO_DB / 20)
    for i0 in range(0, q, lote):
        i1 = min(q, i0 + lote)
        idx = np.arange(N)[None, :] + H * np.arange(i0, i1)[:, None]
        L = np.fft.rfft(lp[idx] * w, axis=1)
        S = np.fft.rfft(ep[idx] * w, axis=1)
        aL, aS = np.abs(L), np.abs(S)
        tem = aL >= aL.max(axis=1, keepdims=True) * piso
        fase = np.where(tem, L / np.maximum(aL, 1e-30), S / np.maximum(aS, 1e-30))
        fase[(~tem) & (aS == 0)] = 1.0
        logL, logS = np.log(aL + 1e-9), np.log(aS + 1e-9)
        for s, a in zip(saidas, niveis):
            quadros = np.fft.irfft(np.exp((1 - a) * logL + a * logS) * fase, n=N, axis=1) * w
            _somar(s, quadros, i0)
        _somar(soma, np.broadcast_to(w ** 2, (i1 - i0, N)), i0)
    return [(s / np.maximum(soma, 1e-8))[N // 2:N // 2 + n] for s in saidas]


def _somar(dest: np.ndarray, quadros: np.ndarray, i0: int) -> None:
    """Sobrepõe e soma os quadros `i0…` (passo H) em `dest`, sem laço por quadro."""
    blocos = dest.reshape(-1, H)
    k = len(quadros)
    for j in range(N // H):
        blocos[i0 + j:i0 + j + k] += quadros[:, j * H:(j + 1) * H]


# ---- andamento (o editor mostra; o servidor sabe se o preparo ainda vive) ----
class Andamento:
    def __init__(self, pasta: Path, etapas: list[str], eco: bool = True):
        self.arq = pasta / "andamento.json"
        self.etapas = etapas
        self.eco = eco
        self.dados = {"pid": os.getpid(), "inicio": time.time(), "etapa": etapas[0], "n": 1, "de": len(etapas),
                      "texto": ETAPAS[etapas[0]], "fracao": 0.0}
        self._trava = threading.Lock()
        self._fim = threading.Event()
        self._gravar()
        threading.Thread(target=self._pulso, daemon=True).start()

    def _pulso(self) -> None:
        while not self._fim.wait(5.0):
            self._gravar()

    def _gravar(self, insistir: bool = False) -> None:
        with self._trava:
            self.dados["atualizado"] = time.time()
            tmp = self.arq.with_name(f".andamento.{os.getpid()}.json")
            tmp.write_bytes(json.dumps(self.dados, ensure_ascii=False).encode("utf-8"))
            for _ in range(40 if insistir else 4):
                try:
                    tmp.replace(self.arq)
                    return
                except PermissionError:
                    time.sleep(0.05)
            tmp.unlink(missing_ok=True)

    def etapa(self, chave: str, texto: str | None = None) -> None:
        self.dados.update(etapa=chave, n=self.etapas.index(chave) + 1, texto=texto or ETAPAS[chave], fracao=0.0)
        if self.eco:
            print(f"[{self.dados['n']}/{self.dados['de']}] {self.dados['texto']}", flush=True)
        self._gravar()

    def andou(self, fracao: float, texto: str | None = None) -> None:
        self.dados["fracao"] = round(min(1.0, max(0.0, fracao)), 3)
        if texto:
            self.dados["texto"] = texto
        self._gravar()

    def fim(self, erro: str | None = None) -> None:
        self._fim.set()
        self.dados.update(etapa="falhou" if erro else "pronto", fracao=1.0, fim=time.time())
        if erro:
            self.dados["erro"] = erro
        self._gravar(insistir=True)


def _ler_json(p: Path) -> dict | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def andamento(edit: Path) -> dict | None:
    """O último andamento, com `vivo` dizendo se o preparo ainda está rodando."""
    a = _ler_json(Path(edit) / PASTA / "andamento.json")
    if a is None:
        return None
    a["vivo"] = a.get("etapa") not in ("pronto", "falhou") and time.time() - float(a.get("atualizado", 0)) < VIVO
    return a


# ---- o projeto ----
def video(edit: Path) -> Path:
    """O vídeo do corte (state.json `video`, normalmente cut.mp4), sempre dentro do edit."""
    edit = Path(edit).resolve()
    rel = (_ler_json(edit / "state.json") or {}).get("video") or "cut.mp4"
    p = (edit / str(rel)).resolve()
    if not p.is_relative_to(edit):
        raise VozErro("o state.json aponta o vídeo para fora do projeto")
    if not p.is_file():
        raise VozErro(f"o vídeo do corte ainda não existe ({p.name})")
    return p


def ler_estado(edit: Path) -> dict | None:
    e = _ler_json(Path(edit) / PASTA / "estado.json")
    return e if e and e.get("versao") == VERSAO and isinstance(e.get("fonte"), dict) else None


def _gravar_estado(pasta: Path, e: dict) -> None:
    tmp = pasta / f".estado.{os.getpid()}.json"
    tmp.write_bytes(json.dumps(e, ensure_ascii=False, indent=1).encode("utf-8"))
    _trocar(tmp, pasta / "estado.json")


ARQUIVOS = ("limpa.npy", "estudio.npy", "fundo.npy", "original.m4a",
            *(f"previa/voz-{d:03d}.flac" for d in DEGRAUS), "previa/fundo.flac", "previa/original.flac")


def _completo(pasta: Path) -> bool:
    return all((pasta / a).is_file() for a in ARQUIVOS)


def situacao(edit: Path) -> dict:
    """Tudo o que o editor e o agente precisam saber, sem rodar nada pesado.

    preparo: nenhum | preparando | pronto | velho (o corte mudou: preparar de novo).
    aplicado: a Voz e o Fundo que o cut.mp4 de agora tem (None = o som original).
    escolha: o que a pessoa escolheu por último (ou o padrão).
    reaplicar: a escolha já foi aplicada, mas o cut.mp4 de agora não a tem (render novo)."""
    edit = Path(edit)
    pasta = edit / PASTA
    e = ler_estado(edit)
    a = andamento(edit)
    try:
        h = hash_audio(video(edit))
    except VozErro:
        h = None
    ap = (e or {}).get("aplicado")
    if a and a["vivo"]:
        preparo = "preparando"
    elif e is None:
        preparo = "nenhum"
    elif h is not None and h in (e["fonte"]["hash"], (ap or {}).get("hash")) and _completo(pasta):
        preparo = "pronto"
    else:
        preparo = "velho"
    tem = bool(ap and h and ap["hash"] == h)
    out = {"preparo": preparo, "escolha": (e or {}).get("escolha") or dict(PADRAO),
           "aplicado": {"voz": ap["voz"], "fundo": ap["fundo"]} if tem else None,
           "reaplicar": bool(ap) and not tem, "degraus": list(DEGRAUS),
           "duracao": (e or {}).get("fonte", {}).get("duracao")}
    if a and (a["vivo"] or a.get("etapa") == "falhou"):
        out["andamento"] = {k: a.get(k) for k in ("etapa", "n", "de", "texto", "fracao", "erro", "vivo")}
    if preparo == "pronto":
        out["preparado"] = e["preparado"]  # mudou: o editor busca as faixas de novo
        out["previa"] = {**{f"voz-{d:03d}": f"{PASTA}/previa/voz-{d:03d}.flac" for d in DEGRAUS},
                         "fundo": f"{PASTA}/previa/fundo.flac", "original": f"{PASTA}/previa/original.flac"}
    try:
        falta = sum(m["tamanho"] for m in _faltam(pasta_modelos()))
        out["modelos"] = {"prontos": falta == 0, "faltam_mb": _mb(falta)}
    except VozErro as ex:
        out["modelos"] = {"prontos": False, "erro": str(ex)}
    return out


def preparar(edit: Path, de_novo: bool = False, eco: bool = True, pedaco: tuple[float, float] | None = None,
             limpar: Callable[[np.ndarray], np.ndarray] | None = None,
             estudio=None) -> dict:
    """Prepara as faixas para o cut.mp4 de agora. `limpar` e `estudio` trocam os modelos
    (testes): `limpar(original 48 kHz)` → voz limpa; `estudio` no formato do Sidon
    (`quadro`, `caracteristicas(16 kHz)`, `gerar(trecho)` → 48 kHz)."""
    edit = Path(edit).resolve()
    pasta = edit / PASTA
    corte = video(edit)
    h = hash_audio(corte)
    e = ler_estado(edit)
    ap = (e or {}).get("aplicado")
    if e and ap and ap.get("hash") == h:
        fonte, h = pasta / "original.m4a", e["fonte"]["hash"]  # o corte já tem a voz melhorada
        if not fonte.is_file():
            raise VozErro("o cut.mp4 tem a voz melhorada e o som original sumiu da pasta .melhorar")
    else:
        fonte = corte
    if e and e["fonte"]["hash"] == h and _completo(pasta) and not de_novo:
        return e
    a = andamento(edit)
    if a and a["vivo"] and a.get("pid") != os.getpid():
        raise VozErro("já tem um preparo rodando neste projeto")

    pasta.mkdir(exist_ok=True)
    (pasta / "previa").mkdir(exist_ok=True)
    precisa = limpar is None or estudio is None
    baixar = precisa and bool(_faltam(pasta_modelos()))
    prog = Andamento(pasta, (["baixar"] if baixar else []) + ["limpar", "estudio", "degraus"], eco=eco)
    try:
        t = {}
        orig = ler_audio(fonte)  # antes de baixar 1 GB: o vídeo serve?
        n = len(orig)
        if n < SR // 2:
            raise VozErro("o som do vídeo é curto demais (menos de meio segundo)")
        if n > MAX_DURACAO * SR:
            raise VozErro(f"o vídeo passa de {MAX_DURACAO // 60} minutos")
        if precisa:
            if baixar:
                def baixou(feito: int, total: int) -> None:
                    prog.andou(feito / total, f"{ETAPAS['baixar']}: {_mb(feito)} de {_mb(total)} MB")
                t0 = time.time()
                baixar_modelos(baixou)
                t["baixar"] = time.time() - t0
            pm = pasta_modelos()
            binario = pm / modelos()[0]["arquivo"]
            limpar = limpar or (lambda x: limpar_deepfilter(x, [str(binario)]))

        prog.etapa("limpar")
        t0 = time.time()
        lp = _no_tamanho(np.asarray(limpar(orig), dtype=np.float64), n)
        lp = _deslocar(lp, _atraso_fino(orig, lp))  # o DeepFilterNet com -D sai no tempo; confere
        fundo = orig - lp
        t["limpar"] = time.time() - t0

        prog.etapa("estudio")
        t0 = time.time()
        modelo = estudio or Sidon(pasta_modelos())
        bloco, contexto = pedaco or pedaco_do_computador()
        es = estudio_em_pedacos(orig, lp, modelo, bloco, contexto, lambda i, k: prog.andou(
            i / k, f"{ETAPAS['estudio']}" + (f", parte {min(i + 1, k)} de {k}" if k > 1 else "")))
        del modelo  # o Sidon solta ~1 GB de memória antes dos degraus
        t["estudio"] = time.time() - t0

        prog.etapa("degraus")
        t0 = time.time()
        vs = vozes(lp, es, [d / 100 for d in DEGRAUS])
        prog.andou(0.5)
        ganhos = [_ganho(v) for v in vs]
        g0 = ganhos[0]
        faixas = [*vs, fundo, orig]
        gs = [*ganhos, g0, g0]  # fundo e original com o ganho da voz limpa: 0% + fundo = o original
        margem = min(1.0, TETO / max(max(float(np.abs(x).max()) * g for x, g in zip(faixas, gs)), 1e-9))
        nomes = [f"voz-{d:03d}" for d in DEGRAUS] + ["fundo", "original"]
        for nome, x, g in zip(nomes, faixas, gs):
            gravar_flac(pasta / "previa" / f"{nome}.flac", x * (g * margem))
        for nome, x in (("limpa", lp), ("estudio", es), ("fundo", fundo)):
            tmp = pasta / f".{nome}.{os.getpid()}.npy"
            np.save(tmp, x.astype(np.float32))
            _trocar(tmp, pasta / f"{nome}.npy")
        if fonte == corte:
            tmp = pasta / f".original.{os.getpid()}.m4a"
            _ffmpeg(["-y", "-i", str(corte), "-map", "0:a:0", "-c", "copy", str(tmp)])
            _trocar(tmp, pasta / "original.m4a")
        t["degraus"] = time.time() - t0

        novo = {"versao": VERSAO, "fonte": {"hash": h, "duracao": round(n / SR, 3)},
                "preparado": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "segundos": {k: round(v, 1) for k, v in t.items()}, "pedaco": [bloco, contexto],
                "ganhos": {"voz": [round(g, 6) for g in ganhos], "margem": round(margem, 6)},
                "escolha": (e or {}).get("escolha") or dict(PADRAO)}
        if e and e["fonte"]["hash"] == h and ap:
            novo["aplicado"] = ap  # preparo refeito do mesmo corte: o que está aplicado continua
        elif ap:
            novo["aplicado"] = {**ap, "hash": None}  # corte novo: a escolha fica, a aplicação não
        _gravar_estado(pasta, novo)
        prog.fim()
        return novo
    except BaseException as ex:
        prog.fim(str(ex) if isinstance(ex, VozErro) else f"{ex.__class__.__name__}: {ex}")
        raise


def _numero(v: object, nome: str) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
        raise VozErro(f"{nome} vai de 0 a 100")
    return int(round(v))


def normalizar_escolha(v: object) -> dict:
    """O que o editor manda no Salvar: {"voz": 0–100, "fundo": 0–100}, ou {"desligar": true} para
    o vídeo voltar ao som original."""
    if v == {"desligar": True}:
        return {"desligar": True}
    if not isinstance(v, dict) or set(v) != {"voz", "fundo"}:
        raise VozErro("a escolha é {voz, fundo} de 0 a 100, ou {desligar: true}")
    return {"voz": _numero(v["voz"], "a Voz"), "fundo": _numero(v["fundo"], "o Fundo")}


def mistura(edit: Path, voz: int, fundo: int) -> np.ndarray:
    """O som melhorado no número exato: Voz pela mistura espectral, no mesmo volume dos degraus;
    Fundo com o ganho da voz limpa, como na prévia."""
    pasta = Path(edit) / PASTA
    e = ler_estado(edit)
    lp, es, fd = (np.load(pasta / f"{k}.npy").astype(np.float64) for k in ("limpa", "estudio", "fundo"))
    v = vozes(lp, es, [voz / 100])[0]
    return v * _ganho(v) + fd * e["ganhos"]["voz"][0] * (fundo / 100)


def _normalizar(entrada: Path, saida: Path) -> None:
    """O loudnorm de duas passadas do kit (as constantes e a medição do render.py), sem o `-shortest`
    do render: aqui o som já tem o tamanho do original, e o `-shortest` com o loudnorm cortava os 2
    últimos quadros de AAC (43 ms; medido em 23/10)."""
    m = render.measure_loudness(entrada)
    filtro = f"loudnorm=I={render.LOUDNORM_I}:TP={render.LOUDNORM_TP}:LRA={render.LOUDNORM_LRA}"
    if m:
        filtro += (f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                   f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    _ffmpeg(["-y", "-i", str(entrada), "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", filtro,
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(saida)])


def _remux(video_de: Path, audio_de: Path, destino: Path) -> None:
    """A imagem de um arquivo e o som de outro, sem recodificar nada."""
    tmp = destino.with_name(f".{destino.stem}.{os.getpid()}.mp4")
    _ffmpeg(["-y", "-i", str(video_de), "-i", str(audio_de), "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
             "-movflags", "+faststart", str(tmp)])
    _trocar(tmp, destino)


def _acertar_public(edit: Path, sons_do_corte: set[str]) -> bool:
    """O remotion/public/cut.mp4 (cópia do corte, às vezes com os efeitos já desenhados) ganha o
    mesmo som, se for do mesmo corte. Cópia de outro corte fica como está: é a Fase 2 que a refaz."""
    pub = Path(edit) / "remotion" / "public" / "cut.mp4"
    if not pub.is_file():
        return False
    try:
        if hash_audio(pub) not in sons_do_corte:
            return False
    except VozErro:
        return False
    _remux(pub, video(edit), pub)
    return True


def aplicar(edit: Path, voz: int | None = None, fundo: int | None = None, eco: bool = True) -> dict:
    edit = Path(edit).resolve()
    pasta = edit / PASTA
    e = ler_estado(edit)
    escolha = (e or {}).get("escolha") or dict(PADRAO)
    voz = escolha["voz"] if voz is None else _numero(voz, "a Voz")
    fundo = escolha["fundo"] if fundo is None else _numero(fundo, "o Fundo")
    if situacao(edit)["preparo"] != "pronto":
        e = preparar(edit, eco=eco)
    corte = video(edit)
    antes = {e["fonte"]["hash"], (e.get("aplicado") or {}).get("hash")} - {None}
    e["escolha"] = {"voz": voz, "fundo": fundo}
    if voz == 0 and fundo == 100:  # é o original: devolve o som exato, sem recodificar
        if hash_audio(corte) != e["fonte"]["hash"]:
            _remux(corte, pasta / "original.m4a", corte)
        e["aplicado"] = None
        _acertar_public(edit, antes)
        _gravar_estado(pasta, e)
        if eco:
            print("Voz 0% e Fundo 100%: o cut.mp4 ficou com o som original")
        return e

    y = mistura(edit, voz, fundo)
    y *= 0.89 / max(float(np.abs(y).max()), 1e-9)  # o nível final quem decide é o loudnorm
    with tempfile.TemporaryDirectory(prefix="cutmind-voz-", dir=pasta) as tmp:
        com_som = Path(tmp) / "com-som.mp4"
        _ffmpeg(["-y", "-i", str(corte), *_PCM, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                 "-af", "pan=stereo|c0=c0|c1=c0", "-c:a", "alac", "-sample_fmt", "s32p", str(com_som)], y.astype(np.float32).tobytes())
        pronto = Path(tmp) / "pronto.mp4"
        _normalizar(com_som, pronto)
        _trocar(pronto, corte)
    e["aplicado"] = {"voz": voz, "fundo": fundo, "hash": hash_audio(corte),
                     "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}
    pub = _acertar_public(edit, antes)
    _gravar_estado(pasta, e)
    if eco:
        print(f"Voz {voz}% e Fundo {fundo}% no {corte.name}" + (" e no remotion/public/cut.mp4" if pub else ""))
    return e


def restaurar(edit: Path) -> bool:
    """O cut.mp4 volta ao som original (o mesmo fluxo de bytes de antes). False se já estava."""
    edit = Path(edit).resolve()
    pasta = edit / PASTA
    e = ler_estado(edit)
    corte = video(edit)
    ap = (e or {}).get("aplicado")
    if not ap or hash_audio(corte) != ap.get("hash"):
        return False
    _remux(corte, pasta / "original.m4a", corte)
    e["aplicado"] = None
    _acertar_public(edit, {ap["hash"]})
    _gravar_estado(pasta, e)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar")
    p.add_argument("edit", type=Path)
    p.add_argument("--de-novo", action="store_true", help="refaz mesmo com o preparo valendo")
    p = sub.add_parser("aplicar")
    p.add_argument("edit", type=Path)
    p.add_argument("--voz", type=float, help="0 = voz limpa, 100 = estúdio (padrão: a última escolha)")
    p.add_argument("--fundo", type=float, help="0 = só a voz, 100 = o ambiente original")
    sub.add_parser("restaurar").add_argument("edit", type=Path)
    sub.add_parser("estado").add_argument("edit", type=Path)
    sub.add_parser("baixar")
    a = ap.parse_args()
    try:
        if a.cmd == "preparar":
            t0 = time.time()
            e = preparar(a.edit, de_novo=a.de_novo)
            print(f"pronto: {e['fonte']['duracao']:.1f} s de voz · " +
                  " · ".join(f"{k} {v:.0f} s" for k, v in e.get("segundos", {}).items()) +
                  f" · {time.time() - t0:.0f} s agora → {PASTA}/previa")
        elif a.cmd == "aplicar":
            aplicar(a.edit, a.voz, a.fundo)
        elif a.cmd == "restaurar":
            print("o cut.mp4 voltou ao som original" if restaurar(a.edit) else "o cut.mp4 já está com o som original")
        elif a.cmd == "estado":
            print(json.dumps(situacao(a.edit), ensure_ascii=False, indent=1))
        else:
            ultimo = [0]

            def andou(feito: int, total: int) -> None:
                if feito - ultimo[0] >= 50 * 1024 ** 2 or feito == total:
                    ultimo[0] = feito
                    print(f"  {_mb(feito)} de {_mb(total)} MB", flush=True)
            print(f"modelos de voz em {baixar_modelos(andou)}")
    except VozErro as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
