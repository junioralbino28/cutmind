"""As camadas do projeto: imagens e áudios que a pessoa põe na linha do tempo do editor.

`<edit>/camadas.json` é o arquivo do projeto, como num editor de vídeo: o editor grava
pelo Salvar (o servidor valida aqui) e o agente lê para montar a Fase 2 (as imagens
viram `inserts` no edit-data, `camadas_edit_data.py`) e o som do vídeo final
(`mixar_final.py`). Tempos em segundos do cut.mp4.

    {"versao": 1,
     "video": {"mudo": false},
     "faixas": [
       {"id": "a1", "tipo": "audio", "mudo": false, "travado": false,
        "itens": [{"id": "a1-1", "arquivo": "midia/voz.m4a", "inicio": 0.0, "corte": 0.0,
                   "duracao": 12.3, "volume": 1.0, "melhorar": false}]},
       {"id": "i1", "tipo": "imagem", "oculto": false, "travado": false,
        "itens": [{"id": "i1-1", "arquivo": "midia/print.jpg", "inicio": 5.0, "duracao": 3.0}]},
       {"id": "t1", "tipo": "texto", "oculto": false, "travado": false,
        "itens": [{"id": "t1-1", "texto": "Seu texto", "inicio": 2.0, "duracao": 3.0,
                   "x": 540, "y": 960, "estilo": {"fonte": "Anton", "cor": "#ffffff"},
                   "atras": false, "acompanhar": false, "curva": 0}]}]}

Cada faixa é uma camada: áudio tem "mudo", imagem e texto têm "oculto", todas têm "travado".
Uma imagem com `"atras": true` vira o cartão grande atrás da pessoa, em vez do cartão de cima.
Um texto tem o centro em `x`/`y` (px do quadro 1080x1920, podendo sair um pouco dele), quebra
de linha com "\n" e o `estilo` do painel de Texto: `fonte` (uma família do catálogo de
fontes), `peso`, `cor` e `corContorno` (#rrggbb), `tamanho` (× 96 px) e `contorno` (px). Com
`atras` ele fica atrás da pessoa (o agente faz o recorte da janela), com `acompanhar` ele anda
junto com ela (o rastreio do rosto), e `curva` (−100 a 100) o dobra num arco.
`corte` é de onde o arquivo de áudio começa a tocar; `volume` vai de 0 a 2. Um áudio que
veio da biblioteca de trilhas leva `"trilha": "<id do catálogo>"` (pacotes.py): o som
final dá a ele a entrada e a saída lentas de música.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac", ".weba"}
MIDIA_DIR = "midia"
MAX_FAIXAS = 40
MAX_ITENS = 200
MAX_T = 6 * 3600.0
MAX_TEXTO = 400

_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
_COR = re.compile(r"#[0-9a-fA-F]{6}")
_FONTE = re.compile(r"[A-Za-z0-9 ]{1,60}")
_ARQ = re.compile(r"midia/[^/\\]+")


class CamadasInvalidas(ValueError):
    pass


def vazio() -> dict:
    return {"versao": 1, "video": {"mudo": False}, "faixas": []}


def _num(v: object, nome: str, lo: float = 0.0, hi: float = MAX_T) -> float:
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise CamadasInvalidas(f"{nome} não é número") from None
    if not math.isfinite(x) or x < lo or x > hi:
        raise CamadasInvalidas(f"{nome} fora da faixa ({lo} a {hi})")
    return round(x, 3)


def _id(v: object, nome: str) -> str:
    if not isinstance(v, str) or not _ID.fullmatch(v):
        raise CamadasInvalidas(f"{nome} inválido")
    return v


def _arquivo(v: object, tipo: str) -> str:
    """Só um arquivo direto da pasta midia/ do projeto, com a extensão do tipo."""
    if not isinstance(v, str) or not _ARQ.fullmatch(v) or v.endswith((".", " ")):
        raise CamadasInvalidas("arquivo fora de midia/")
    nome = v.split("/", 1)[1]
    if nome in (".", "..") or nome.startswith("."):
        raise CamadasInvalidas("arquivo fora de midia/")
    ext = Path(nome).suffix.lower()
    if ext not in (AUDIO_EXTS if tipo == "audio" else IMAGE_EXTS):
        raise CamadasInvalidas(f"{v} não é {'áudio' if tipo == 'audio' else 'imagem'}")
    return v


def _cor(v: object, nome: str) -> str:
    if not isinstance(v, str) or not _COR.fullmatch(v):
        raise CamadasInvalidas(f"{nome}: cor no formato #rrggbb")
    return v.lower()


def _estilo_texto(e: object) -> dict:
    """O que o painel de Texto escolheu; o que não veio fica com o padrão do texto."""
    if e is None:
        return {}
    if not isinstance(e, dict):
        raise CamadasInvalidas("estilo não é um objeto")
    out: dict = {}
    if e.get("fonte") is not None:
        if not isinstance(e["fonte"], str) or not _FONTE.fullmatch(e["fonte"]):
            raise CamadasInvalidas("fonte: o nome de uma família, só letras, números e espaço")
        out["fonte"] = e["fonte"]
    if e.get("peso") is not None:
        out["peso"] = int(_num(e["peso"], "peso", 100, 900))
    for k in ("cor", "corContorno"):
        if e.get(k) is not None:
            out[k] = _cor(e[k], k)
    if e.get("tamanho") is not None:
        out["tamanho"] = _num(e["tamanho"], "tamanho", 0.2, 5.0)
    if e.get("contorno") is not None:
        out["contorno"] = _num(e["contorno"], "contorno", 0.0, 60.0)
    return out


def _item_texto(it: dict, iid: str) -> dict:
    t = it.get("texto")
    if not isinstance(t, str):
        raise CamadasInvalidas("texto não é um texto")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    if not t.strip() or len(t) > MAX_TEXTO or any(ord(ch) < 32 and ch != "\n" for ch in t):
        raise CamadasInvalidas(f"texto: de 1 a {MAX_TEXTO} letras, sem caractere de controle")
    return {"id": iid, "texto": t,
            "inicio": _num(it.get("inicio", 0), "inicio"),
            "duracao": _num(it.get("duracao", 0), "duracao", 0.05),
            "x": _num(it.get("x", 540), "x", -1080, 2160),
            "y": _num(it.get("y", 960), "y", -1920, 3840),
            "estilo": _estilo_texto(it.get("estilo")),
            "atras": bool(it.get("atras", False)),
            "acompanhar": bool(it.get("acompanhar", False)),
            "curva": _num(it.get("curva", 0), "curva", -100, 100)}


def normalize(obj: object) -> dict:
    """Confere e limpa o que veio do editor. Levanta CamadasInvalidas com o motivo."""
    if not isinstance(obj, dict):
        raise CamadasInvalidas("camadas não é um objeto")
    video = obj.get("video") or {}
    if not isinstance(video, dict):
        raise CamadasInvalidas("video não é um objeto")
    faixas_in = obj.get("faixas") or []
    if not isinstance(faixas_in, list) or len(faixas_in) > MAX_FAIXAS:
        raise CamadasInvalidas(f"faixas: lista de até {MAX_FAIXAS}")
    faixas, total, ids = [], 0, set()
    for f in faixas_in:
        if not isinstance(f, dict):
            raise CamadasInvalidas("faixa não é um objeto")
        tipo = f.get("tipo")
        if tipo not in ("audio", "imagem", "texto"):
            raise CamadasInvalidas("tipo da faixa: audio, imagem ou texto")
        fid = _id(f.get("id"), "id da faixa")
        if fid in ids:
            raise CamadasInvalidas(f"id repetido: {fid}")
        ids.add(fid)
        itens_in = f.get("itens") or []
        if not isinstance(itens_in, list):
            raise CamadasInvalidas("itens não é uma lista")
        total += len(itens_in)
        if total > MAX_ITENS:
            raise CamadasInvalidas(f"mais de {MAX_ITENS} itens")
        itens = []
        for it in itens_in:
            if not isinstance(it, dict):
                raise CamadasInvalidas("item não é um objeto")
            iid = _id(it.get("id"), "id do item")
            if iid in ids:
                raise CamadasInvalidas(f"id repetido: {iid}")
            ids.add(iid)
            if tipo == "texto":
                itens.append(_item_texto(it, iid))
                continue
            item = {"id": iid, "arquivo": _arquivo(it.get("arquivo"), tipo),
                    "inicio": _num(it.get("inicio", 0), "inicio"),
                    "duracao": _num(it.get("duracao", 0), "duracao", 0.05)}
            if tipo == "imagem" and it.get("atras"):  # o cartão grande, atrás da pessoa
                item["atras"] = True
            if tipo == "audio":
                item["corte"] = _num(it.get("corte", 0), "corte")
                item["volume"] = _num(it.get("volume", 1), "volume", 0.0, 2.0)
                item["melhorar"] = bool(it.get("melhorar", False))
                if it.get("trilha") is not None:
                    item["trilha"] = _id(it.get("trilha"), "trilha")
            itens.append(item)
        faixa = {"id": fid, "tipo": tipo, "travado": bool(f.get("travado", False)), "itens": itens}
        faixa["mudo" if tipo == "audio" else "oculto"] = bool(f.get("mudo" if tipo == "audio" else "oculto", False))
        faixas.append(faixa)
    return {"versao": 1, "video": {"mudo": bool(video.get("mudo", False))}, "faixas": faixas}


def load(path: Path) -> dict:
    """O camadas.json do projeto, conferido. Sem arquivo, camadas vazias."""
    try:
        return normalize(json.loads(Path(path).read_text(encoding="utf-8")))
    except FileNotFoundError:
        return vazio()


def save(path: Path, camadas: dict) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(normalize(camadas), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def tocam(camadas: dict) -> list[dict]:
    """Os itens de áudio que entram no som final: de faixa não silenciada e com volume."""
    return [{**it, "faixa": f["id"]} for f in camadas["faixas"]
            if f["tipo"] == "audio" and not f["mudo"] for it in f["itens"] if it["volume"] > 0]


def aparecem(camadas: dict) -> list[dict]:
    """Os itens de imagem que entram no vídeo: de faixa que não está escondida."""
    return [{**it, "faixa": f["id"]} for f in camadas["faixas"]
            if f["tipo"] == "imagem" and not f["oculto"] for it in f["itens"]]


def textos(camadas: dict) -> list[dict]:
    """Os textos que entram no vídeo, de faixa que não está escondida, na ordem das faixas:
    a faixa que vem depois fica por cima, como no editor."""
    return [{**it, "faixa": f["id"]} for f in camadas["faixas"]
            if f["tipo"] == "texto" and not f["oculto"] for it in f["itens"]]
