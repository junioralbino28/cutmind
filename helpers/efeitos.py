"""Os efeitos do projeto: filtros e transições da biblioteca, aplicados no corte.

`<edit>/efeitos.json` é o arquivo do projeto: o editor grava pelo Salvar (o servidor
confere aqui) e o `efeitos_render.py` lê antes do render final, desenhando cada janela
com o mesmo motor da prévia (assets/efeitos/motor.js). Tempos em segundos do cut.mp4.

    {"versao": 1,
     "itens": [
       {"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 2.0, "duracao": 3.5,
        "intensidade": 0.8},
       {"id": "t1", "tipo": "transicao", "pacote": "zoom-central", "corte": 4.2, "duracao": 1.1},
       {"id": "a1", "tipo": "ajuste", "inicio": 2.0, "duracao": 3.5,
        "ajustes": {"brilho": 20, "vinheta": -35}}]}

Filtro: de `inicio` por `duracao`; `intensidade` de 0 a 1 (sem ela, vale a do pacote).
Ajuste (a ferramenta Ajustar da tomada): de `inicio` por `duracao`, sem pacote: é um
shader do próprio motor. Cada valor de AJUSTES vai de −100 a 100, inteiro; 0 é neutro e
não é gravado, e um ajuste todo neutro sai do arquivo. Um por tomada.
Transição: centrada no `corte` (o encontro de duas tomadas), por `duracao`. Antes do
corte, o lado A é o vídeo andando e o B fica parado no primeiro quadro depois do corte;
depois do corte, o A fica parado no último quadro antes dele e o B anda.
Um quadro que cai numa transição, num filtro e num ajuste recebe a transição primeiro, o
filtro por cima e o ajuste por último, na prévia e no vídeo final. Neste primeiro passo,
um filtro por vez.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

MAX_ITENS = 1000  # um modelo de estilo põe filtro, ajuste e transição em cada tomada
MAX_T = 6 * 3600.0
# Duas janelas que se encostam (o fim de uma tomada e o começo da seguinte) passam até 1 ms
# uma na outra depois do arredondamento de 3 casas, com início e duração arredondados à
# parte (47,967 + 4,667 = 52,634 contra o 52,633 da seguinte). Isso é encostar, não
# sobrepor: o render (efeitos_render.FOLGA) e a prévia (fxDentro, no celular.js) já
# descontam essa sobra. 2 ms ou mais é sobreposição de verdade.
ENCOSTA = 1.5e-3
TRANSICAO_MIN, TRANSICAO_MAX = 0.1, 5.0
# a ordem é a da fileira de ferramentas do editor; o motor (assets/efeitos/motor.js) lê as mesmas chaves
AJUSTES = ("brilho", "contraste", "saturacao", "exposicao", "temperatura", "matiz", "realces", "sombras", "vinheta")

_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
_PACOTE = re.compile(r"[a-z0-9][a-z0-9-]{0,60}")  # o id do catálogo (pacotes.py)


class EfeitosInvalidos(ValueError):
    pass


def vazio() -> dict:
    return {"versao": 1, "itens": []}


def _num(v: object, nome: str, lo: float = 0.0, hi: float = MAX_T) -> float:
    if isinstance(v, bool):
        raise EfeitosInvalidos(f"{nome} não é número")
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise EfeitosInvalidos(f"{nome} não é número") from None
    if not math.isfinite(x) or x < lo or x > hi:
        raise EfeitosInvalidos(f"{nome} fora da faixa ({lo} a {hi})")
    return round(x, 3)


def janela(item: dict) -> tuple[float, float]:
    """O trecho do cut.mp4 que o efeito toca, em segundos (início, fim)."""
    if item["tipo"] == "transicao":
        meio = item["duracao"] / 2
        return item["corte"] - meio, item["corte"] + meio
    return item["inicio"], item["inicio"] + item["duracao"]


def _sem_sobrepor(itens: list[dict], tipo: str, motivo: str) -> None:
    js = sorted(janela(i) for i in itens if i["tipo"] == tipo)
    for (_, fim), (ini, _) in zip(js, js[1:]):
        if ini < fim - ENCOSTA:
            raise EfeitosInvalidos(motivo)


def normalize(obj: object) -> dict:
    """Confere e limpa o que veio do editor. Levanta EfeitosInvalidos com o motivo."""
    if not isinstance(obj, dict):
        raise EfeitosInvalidos("efeitos não é um objeto")
    itens_in = obj.get("itens") or []
    if not isinstance(itens_in, list) or len(itens_in) > MAX_ITENS:
        raise EfeitosInvalidos(f"itens: lista de até {MAX_ITENS}")
    itens, ids = [], set()
    for it in itens_in:
        if not isinstance(it, dict):
            raise EfeitosInvalidos("item não é um objeto")
        iid = it.get("id")
        if not isinstance(iid, str) or not _ID.fullmatch(iid) or iid in ids:
            raise EfeitosInvalidos(f"id inválido ou repetido: {str(iid)[:40]!r}")
        ids.add(iid)
        tipo = it.get("tipo")
        if tipo not in ("filtro", "transicao", "ajuste"):
            raise EfeitosInvalidos("tipo do efeito: filtro, transicao ou ajuste")
        if tipo == "ajuste":
            item = {"id": iid, "tipo": tipo, "inicio": _num(it.get("inicio", 0), "inicio"),
                    "duracao": _num(it.get("duracao", 0), "duracao", 0.05), "ajustes": _ajustes(it.get("ajustes"))}
            if item["ajustes"]:  # todo neutro: não muda nada, não fica no arquivo
                itens.append(item)
            continue
        pacote = it.get("pacote")
        if not isinstance(pacote, str) or not _PACOTE.fullmatch(pacote):
            raise EfeitosInvalidos("pacote inválido")
        item = {"id": iid, "tipo": tipo, "pacote": pacote}
        if tipo == "filtro":
            item["inicio"] = _num(it.get("inicio", 0), "inicio")
            item["duracao"] = _num(it.get("duracao", 0), "duracao", 0.05)
            if it.get("intensidade") is not None:
                item["intensidade"] = _num(it.get("intensidade"), "intensidade", 0.0, 1.0)
        else:
            item["corte"] = _num(it.get("corte", 0), "corte")
            item["duracao"] = _num(it.get("duracao", 0), "duracao", TRANSICAO_MIN, TRANSICAO_MAX)
        itens.append(item)
    _sem_sobrepor(itens, "filtro", "dois filtros ao mesmo tempo: neste passo, um filtro por vez")
    _sem_sobrepor(itens, "transicao", "duas transições se cruzam")
    _sem_sobrepor(itens, "ajuste", "dois ajustes ao mesmo tempo: um por tomada")
    return {"versao": 1, "itens": itens}


def _ajustes(obj: object) -> dict:
    """Os valores do Ajustar, inteiros de −100 a 100, sem os neutros, na ordem de AJUSTES."""
    if not isinstance(obj, dict):
        raise EfeitosInvalidos("ajustes não é um objeto")
    fora = set(obj) - set(AJUSTES)
    if fora:
        raise EfeitosInvalidos(f"ajuste desconhecido: {sorted(fora)[0][:20]!r}")
    vals = {k: round(_num(obj[k], k, -100.0, 100.0)) for k in AJUSTES if k in obj}
    return {k: v for k, v in vals.items() if v}


def load(path: Path) -> dict:
    """O efeitos.json do projeto, conferido. Sem arquivo, nenhum efeito."""
    try:
        return normalize(json.loads(Path(path).read_text(encoding="utf-8")))
    except FileNotFoundError:
        return vazio()


def save(path: Path, efeitos: dict) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(normalize(efeitos), ensure_ascii=False, indent=2).encode("utf-8"))
    tmp.replace(path)
