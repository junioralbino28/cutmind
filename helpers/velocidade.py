"""A velocidade do vídeo final: trechos acelerados (ou mais lentos) com tudo já montado.

`<edit>/velocidade.json` é o arquivo do projeto: o editor grava pelo Salvar (o servidor
confere aqui) e o `velocidade_final.py` lê depois do `mixar_final.py`. Tempos em segundos
do final.mp4, que é o relógio do cut.mp4 (a Fase 2 desenha por cima dele).

    {"versao": 1, "duracao": 82.567,
     "trechos": [{"inicio": 3.2, "fim": 20.5, "fator": 1.5}]}

É o "selecionar tudo e acelerar" do CapCut: imagem, voz, legenda, efeitos, camadas e trilha
andam no mesmo ritmo, porque o trecho é do vídeo já montado e nada sai do lugar. A
velocidade da tomada (a régua do Corte, `edl.json`) é outra coisa: ela muda o corte, e o
que foi posto por cima no relógio do corte teria de ser levado junto.

`fator` de 0,25 a 4; 1 não é gravado (o trecho some). Os trechos não se cruzam.
`duracao` é a do vídeo em que a pessoa marcou: se o final mudar de duração (corte
refeito), os trechos podem ter saído do lugar, e o velocidade_final.py para antes de
aplicar.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

MAX_TRECHOS = 200
MAX_T = 6 * 3600.0
FATOR_MIN, FATOR_MAX = 0.25, 4.0
TRECHO_MIN = 0.1  # segundos: menos que isso são 3 quadros, e a régua do editor não faz


class VelocidadeInvalida(ValueError):
    pass


def vazio() -> dict:
    return {"versao": 1, "trechos": []}


def _num(v: object, nome: str, lo: float = 0.0, hi: float = MAX_T) -> float:
    if isinstance(v, bool):
        raise VelocidadeInvalida(f"{nome} não é número")
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise VelocidadeInvalida(f"{nome} não é número") from None
    if not math.isfinite(x) or x < lo or x > hi:
        raise VelocidadeInvalida(f"{nome} fora da faixa ({lo} a {hi})")
    return round(x, 3)


def normalize(obj: object) -> dict:
    """Confere e limpa o que veio do editor. Levanta VelocidadeInvalida com o motivo."""
    if not isinstance(obj, dict):
        raise VelocidadeInvalida("velocidade não é um objeto")
    trechos_in = obj.get("trechos") or []
    if not isinstance(trechos_in, list) or len(trechos_in) > MAX_TRECHOS:
        raise VelocidadeInvalida(f"trechos: lista de até {MAX_TRECHOS}")
    trechos = []
    for t in trechos_in:
        if not isinstance(t, dict):
            raise VelocidadeInvalida("trecho não é um objeto")
        ini = _num(t.get("inicio", 0), "inicio")
        fim = _num(t.get("fim", 0), "fim")
        fator = _num(t.get("fator", 1), "fator", FATOR_MIN, FATOR_MAX)
        if fim - ini < TRECHO_MIN - 1e-6:
            raise VelocidadeInvalida(f"trecho de {ini} a {fim}: curto demais (mínimo {TRECHO_MIN} s)")
        if fator != 1:  # na velocidade normal o trecho não muda nada: não fica no arquivo
            trechos.append({"inicio": ini, "fim": fim, "fator": fator})
    trechos.sort(key=lambda t: t["inicio"])
    for a, b in zip(trechos, trechos[1:]):
        if b["inicio"] < a["fim"] - 1e-6:
            raise VelocidadeInvalida("dois trechos se cruzam")
    out: dict = {"versao": 1, "trechos": trechos}
    if obj.get("duracao") is not None:
        out["duracao"] = _num(obj["duracao"], "duracao")
    return out


def pedacos(vel: dict, total: float) -> list[tuple[float, float, float]]:
    """O vídeo inteiro em pedaços (início, fim, fator), os de velocidade normal entre os
    trechos. Trecho além do fim é cortado nele; o que sobra curto demais sai."""
    out: list[tuple[float, float, float]] = []
    t = 0.0
    for tr in vel.get("trechos") or []:
        ini, fim = max(t, tr["inicio"]), min(total, tr["fim"])
        if fim - ini < TRECHO_MIN - 1e-6:
            continue
        if ini > t + 1e-6:
            out.append((t, ini, 1.0))
        out.append((ini, fim, float(tr["fator"])))
        t = fim
    if total > t + 1e-6:
        out.append((t, total, 1.0))
    return out


def duracao_entregue(vel: dict, total: float) -> float:
    """Quanto o vídeo dura depois dos trechos acelerados."""
    return sum((b - a) / f for a, b, f in pedacos(vel, total))


def load(path: Path) -> dict:
    """O velocidade.json do projeto, conferido. Sem arquivo, nenhum trecho."""
    try:
        return normalize(json.loads(Path(path).read_text(encoding="utf-8")))
    except FileNotFoundError:
        return vazio()


def save(path: Path, vel: dict) -> None:
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(normalize(vel), ensure_ascii=False, indent=2).encode("utf-8"))
    tmp.replace(path)
