"""O Whisper que o kit baixa para transcrever no processador: o large-v3 já em int8.

O transcribe.py roda o large-v3 em int8 no processador (sem placa NVIDIA, que é o caso do Windows comum e do
Mac). O modelo de sempre vem em float16 (2,9 GB) e vira int8 ao abrir. Este é o mesmo modelo já em int8, publicado
no cutmind-packs: metade do download.

Feito a partir do float16 de sempre, com a conta que o CTranslate2 faz ao abrir, deixando as convoluções em float16
(com oneDNN elas voltam a float32, e passar por int8 perderia precisão). Em 02/11/2026 deu a mesma transcrição,
palavra por palavra e com os mesmos tempos, nos dois vídeos inteiros do teste (837 e 961 palavras). A conversão a
partir dos pesos originais (`ct2-transformers-converter --model openai/whisper-large-v3 --quantization int8`) não
passou: 3 trechos diferentes em 900 palavras, por causa das convoluções. Refazer só com essa prova.

Com placa NVIDIA o Whisper roda em float16, e um modelo int8 mudaria o resultado: lá vale o de sempre. Sem
rede, ou com o download falhando, também: a transcrição nunca para por causa deste atalho.
"""
from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

NOME = "faster-whisper-large-v3-int8"
BASE = "https://github.com/junioralbino28/cutmind-packs/releases/download/whisper-large-v3-int8"
# arquivo: (bytes, sha256), do modelo provado em 02/11/2026
ARQUIVOS: dict[str, tuple[int, str]] = {
    "config.json": (2394, "a9306624f5ec14270a014b647e5c316b6e03a662c369758d1b90697a7b0655b9"),
    "model.bin": (1556722579, "6102b080cf9cfaf223896412cbd74202847e72112a723222698113f32fdc2eb2"),
    "preprocessor_config.json": (340, "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711"),
    "tokenizer.json": (2480617, "6d8cbd7cd0d8d5815e478dac67b85a26bbe77c1f5e0c6d76d1ce2abc0e5f21ca"),
    "vocabulary.json": (1068114, "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1"),
}


def casa() -> Path:
    return Path(os.environ.get("CUTMIND_HOME") or Path.home() / ".cutmind")


def pasta() -> Path:
    return casa() / "modelos" / NOME


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def pronto(p: Path | None = None) -> bool:
    """Todos os arquivos no tamanho certo (o sha256 foi conferido ao baixar; a marca .ok diz isso)."""
    p = p or pasta()
    return bool(ARQUIVOS) and (p / ".ok").is_file() and all(
        (p / n).is_file() and (p / n).stat().st_size == tam for n, (tam, _) in ARQUIVOS.items())


def _baixar_um(url: str, destino: Path, tam: int, sha: str, aviso) -> None:
    """Baixa com retomada (o download de 1,5 GB que cai no meio continua de onde parou) e confere o sha256."""
    parte = destino.with_name(destino.name + ".part")
    feito = parte.stat().st_size if parte.is_file() else 0
    if feito > tam:
        parte.unlink()
        feito = 0
    if feito < tam:
        req = urllib.request.Request(url, headers={"User-Agent": "cutmind", **({"Range": f"bytes={feito}-"} if feito else {})})
        with urllib.request.urlopen(req, timeout=60) as r:
            if feito and r.status != 206:  # o servidor ignorou a retomada: do começo
                feito = 0
            with open(parte, "ab" if feito else "wb") as f:
                marca = feito
                while True:
                    bloco = r.read(1 << 20)
                    if not bloco:
                        break
                    f.write(bloco)
                    feito += len(bloco)
                    if feito - marca >= 100 * 1024 ** 2:
                        aviso(f"  Whisper: {feito / 1024 ** 3:.1f} de {tam / 1024 ** 3:.1f} GB")
                        marca = feito
    if parte.stat().st_size != tam or _sha256(parte) != sha:
        parte.unlink(missing_ok=True)
        raise OSError(f"{destino.name}: o arquivo baixado não confere (tamanho ou sha256)")
    os.replace(parte, destino)


def baixar(aviso=print) -> Path:
    p = pasta()
    if pronto(p):
        return p
    p.mkdir(parents=True, exist_ok=True)
    (p / ".ok").unlink(missing_ok=True)
    aviso(f"baixando o Whisper em int8 ({sum(t for t, _ in ARQUIVOS.values()) / 1024 ** 3:.2f} GB, só na primeira vez)")
    for nome, (tam, sha) in ARQUIVOS.items():
        alvo = p / nome
        if alvo.is_file() and alvo.stat().st_size == tam and _sha256(alvo) == sha:
            continue
        _baixar_um(f"{BASE}/{nome}", alvo, tam, sha, aviso)
    (p / ".ok").write_text("ok", encoding="ascii")
    return p


def ja_tem_o_de_sempre() -> bool:
    """O float16 já baixado por um kit anterior: a transcrição é a mesma, não vale baixar mais 1,5 GB."""
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache("Systran/faster-whisper-large-v3", "model.bin"), str)
    except Exception:  # cache ilegível ou biblioteca faltando: baixar o menor é o caminho normal
        return False


def para_o_processador(aviso=print) -> str | None:
    """O caminho do modelo int8 pronto para o faster-whisper, ou None (vale o modelo de sempre)."""
    if not ARQUIVOS:
        return None
    if not pronto() and ja_tem_o_de_sempre():
        return None
    try:
        return str(baixar(aviso))
    except (OSError, ValueError) as e:
        aviso(f"  Whisper em int8 indisponível ({e}); usando o modelo de sempre")
        return None
