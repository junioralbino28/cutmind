#!/usr/bin/env python3
"""Os modelos de estilo (aba Modelos do Estilo): o visual de um vídeo, guardado com nome
para aplicar em outro. Um por marca ou cliente.

Ficam em `~/.cutmind/modelos/<id>.json` (a pasta de `CUTMIND_HOME`), fora de qualquer
projeto. Um modelo leva só o VISUAL, nunca o conteúdo (cortes, textos, imagens, frases
arrastadas):

    {"versao": 1, "id": "canal-de-receitas", "nome": "Canal de Receitas", "criado": <epoch>,
     "estilo": {"edit": "limpa", "headline": "realce", "captions": "karaoke",
                "accent": "#ff5200", "elements": {"zoomAuto": true, "zoomCuts": true}},
     "legenda": {"estilo": {"fonte": "Anton", "cor": "#ffffff", "tamanho": 1.2,
                            "contorno": 6, "corContorno": "#000000"}, "acompanhar": false},
     "filtro": {"pacote": "filme-pb", "intensidade": 0.8},
     "transicao": {"pacote": "zoom-central", "duracao": 0.6},
     "ajuste": {"brilho": 10, "vinheta": -20},
     "trilha": {"pacote": "<id do catálogo>", "volume": 0.3}}

Tudo depois de `estilo` é opcional (null = o modelo não mexe naquilo). Aplicar: o Estilo
vira o do modelo; o filtro e o ajuste vão em todas as tomadas, a transição em todos os
cortes, e a trilha entra do começo ao fim (o editor faz e manda pelo Salvar).

    python modelos.py listar
    python modelos.py mostrar <id>
    python modelos.py apagar <id>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import camadas as cam  # mesma pasta deste arquivo
import efeitos as ef  # mesma pasta deste arquivo
import projetos as pj  # mesma pasta deste arquivo

VERSAO = 1
MAX_MODELOS = 200
NOME_MAX = 60
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")  # ids do catálogo de estilos (estilos.js)
_ELEMENTO = re.compile(r"[A-Za-z][A-Za-z0-9]{0,29}")
_COR = re.compile(r"#[0-9a-fA-F]{6}")


class ModeloInvalido(ValueError):
    pass


def pasta() -> Path:
    return pj.casa() / "modelos"


def id_do_nome(nome: str) -> str:
    """'Canal de Receitas' → 'canal-de-receitas' (sem acento, só letra, número e hífen)."""
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40].strip("-")
    if not s:
        raise ModeloInvalido("nome sem letra nem número")
    return s


def _nome(v: object) -> str:
    if not isinstance(v, str):
        raise ModeloInvalido("nome não é um texto")
    s = re.sub(r"\s+", " ", v).strip()
    if not s or len(s) > NOME_MAX or any(ord(c) < 32 for c in s):
        raise ModeloInvalido(f"nome: de 1 a {NOME_MAX} letras, sem caractere de controle")
    return s


def _num(v: object, nome: str, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= float(v) <= hi):
        raise ModeloInvalido(f"{nome}: número de {lo:g} a {hi:g}")
    return round(float(v), 3)


def _pacote(v: object, nome: str) -> str:
    if not isinstance(v, str) or not ef._PACOTE.fullmatch(v):
        raise ModeloInvalido(f"{nome}: id de pacote do catálogo")
    return v


def _estilo(e: object) -> dict:
    if not isinstance(e, dict):
        raise ModeloInvalido("estilo não é um objeto")
    out: dict = {}
    for k in ("edit", "headline", "captions"):
        v = e.get(k)
        if v is None:
            continue
        if not isinstance(v, str) or not _TOKEN.fullmatch(v):
            raise ModeloInvalido(f"estilo.{k}: id de estilo")
        out[k] = v
    if e.get("accent") is not None:
        if not isinstance(e["accent"], str) or not _COR.fullmatch(e["accent"]):
            raise ModeloInvalido("estilo.accent: cor no formato #rrggbb")
        out["accent"] = e["accent"].lower()
    els = e.get("elements") or {}
    if not isinstance(els, dict) or len(els) > 20:
        raise ModeloInvalido("estilo.elements: até 20 ligados/desligados")
    out["elements"] = {}
    for k, v in els.items():
        if not isinstance(k, str) or not _ELEMENTO.fullmatch(k) or not isinstance(v, bool):
            raise ModeloInvalido("estilo.elements: nome → verdadeiro/falso")
        out["elements"][k] = v
    return out


def _legenda(v: object) -> dict | None:
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ModeloInvalido("legenda não é um objeto")
    try:
        est = cam._estilo_texto(v.get("estilo"))
    except cam.CamadasInvalidas as e:
        raise ModeloInvalido(f"legenda: {e}") from None
    return {"estilo": est or None, "acompanhar": bool(v.get("acompanhar", False))}


def _ajuste(v: object) -> dict | None:
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ModeloInvalido("ajuste não é um objeto")
    out = {}
    for k, n in v.items():
        if k not in ef.AJUSTES:
            raise ModeloInvalido(f"ajuste: {k} não existe")
        n = int(_num(n, f"ajuste.{k}", -100, 100))
        if n:
            out[k] = n
    return out or None


def normalize(obj: object) -> dict:
    """O modelo como ele é gravado; recusa (ModeloInvalido) o que não for do formato."""
    if not isinstance(obj, dict):
        raise ModeloInvalido("modelo não é um objeto")
    out = {"versao": VERSAO, "nome": _nome(obj.get("nome")), "estilo": _estilo(obj.get("estilo"))}
    out["id"] = id_do_nome(out["nome"])
    out["criado"] = float(obj["criado"]) if isinstance(obj.get("criado"), (int, float)) else time.time()
    out["legenda"] = _legenda(obj.get("legenda"))
    f = _objeto(obj.get("filtro"), "filtro")
    out["filtro"] = None if f is None else {
        "pacote": _pacote(f.get("pacote"), "filtro.pacote"), **_rotulo(f, "filtro"),
        **({"intensidade": _num(f["intensidade"], "filtro.intensidade", 0, 1)} if f.get("intensidade") is not None else {})}
    t = _objeto(obj.get("transicao"), "transicao")
    out["transicao"] = None if t is None else {
        "pacote": _pacote(t.get("pacote"), "transicao.pacote"), **_rotulo(t, "transicao"),
        "duracao": _num(t.get("duracao", 1.0), "transicao.duracao", ef.TRANSICAO_MIN, ef.TRANSICAO_MAX)}
    out["ajuste"] = _ajuste(obj.get("ajuste"))
    tr = _objeto(obj.get("trilha"), "trilha")
    out["trilha"] = None if tr is None else {"pacote": _pacote(tr.get("pacote"), "trilha.pacote"), **_rotulo(tr, "trilha"),
                                             "volume": _num(tr.get("volume", 0.3), "trilha.volume", 0, 2)}
    return out


def _rotulo(d: dict, nome: str) -> dict:
    """O nome do pacote na biblioteca ("Âmbar"), para o cartão do modelo em qualquer projeto."""
    v = d.get("nome")
    if v is None:
        return {}
    if not isinstance(v, str) or not v.strip() or len(v) > NOME_MAX or any(ord(c) < 32 for c in v):
        raise ModeloInvalido(f"{nome}.nome: de 1 a {NOME_MAX} letras")
    return {"nome": v.strip()}


def _objeto(v: object, nome: str) -> dict | None:
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ModeloInvalido(f"{nome} não é um objeto")
    return v


def _ler(p: Path) -> dict | None:
    try:
        return normalize(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def listar() -> list[dict]:
    """Os modelos válidos, o mais novo primeiro (arquivo estragado fica de fora)."""
    p = pasta()
    if not p.is_dir():
        return []
    ms = [m for m in (_ler(x) for x in p.glob("*.json")) if m]
    return sorted(ms, key=lambda m: m["criado"], reverse=True)


def obter(mid: str) -> dict | None:
    if not isinstance(mid, str) or not _ID.fullmatch(mid):
        return None
    return _ler(pasta() / f"{mid}.json")


def salvar(obj: dict) -> dict:
    """Grava (ou troca, se o nome já existe) e devolve o modelo gravado."""
    m = normalize(obj)
    antigo = obter(m["id"])
    if antigo:
        m["criado"] = antigo["criado"]  # trocar o conteúdo não muda o lugar na lista
    elif len(listar()) >= MAX_MODELOS:
        raise ModeloInvalido(f"já são {MAX_MODELOS} modelos: apague um antes")
    p = pasta()
    p.mkdir(parents=True, exist_ok=True)
    tmp = p / f"{m['id']}.json.tmp"
    tmp.write_bytes(json.dumps(m, ensure_ascii=False, indent=2).encode("utf-8"))
    tmp.replace(p / f"{m['id']}.json")
    return m


def apagar(mid: str) -> bool:
    if not obter(mid):
        return False
    (pasta() / f"{mid}.json").unlink()
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar")
    for c in ("mostrar", "apagar"):
        sub.add_parser(c).add_argument("id")
    a = ap.parse_args()
    if a.cmd == "listar":
        for m in listar():
            partes = [f"legenda {m['estilo'].get('captions', '?')}"]
            partes += [f"{k} {m[k]['pacote']}" for k in ("filtro", "transicao", "trilha") if m.get(k)]
            print(f"{m['id']}  {m['nome']}  · {' · '.join(partes)}")
    elif a.cmd == "mostrar":
        m = obter(a.id)
        print(json.dumps(m, ensure_ascii=False, indent=2) if m else "não existe")
    else:
        print("apagado" if apagar(a.id) else "não existe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
