"""Leva um instante do corte antigo para o corte novo, pelo instante da gravação.

Camadas, efeitos e trechos de velocidade moram no relógio do cut.mp4. Quando o Salvar muda as
tomadas, cada instante volta à gravação pela tomada antiga em que caía e reaparece no corte novo pela
tomada que veio dela (`origem`: o índice da tomada antiga de cada tomada nova; None = sem origem). O que
caía num pedaço que saiu do corte não tem para onde ir: volta None, e quem chamou deixa o item de fora e
avisa (references/shortform.md, "Same save re-cuts?").
"""
from __future__ import annotations

import copy
from typing import Callable, Optional

import tempo  # mesma pasta deste arquivo

FOLGA = 1e-3
Levar = Callable[[float], Optional[float]]


def _na_gravacao(span: dict, t: float) -> float:
    """O instante da gravação que o instante `t` do corte mostra, dentro da tomada `span`."""
    d = t - span["out"]
    if span.get("vel") is not None:
        return span["v_in"] + d * span["vel"]
    peds = span["peds"]
    return tempo.gravacao_em(peds, tempo.corte_ate(peds, span["v_in"]) + d)


def mapa(edl_velho: dict, edl_novo: dict, origem: list[int | None]) -> Levar:
    """A função que leva um instante do corte velho para o novo (None = o instante saiu do corte)."""
    velhas = tempo.tomadas_no_corte(edl_velho)
    novas = tempo.tomadas_no_corte(edl_novo)

    def levar(t: float) -> float | None:
        k = next((i for i, s in enumerate(velhas)
                  if s["out"] - FOLGA <= t < s["out"] + s["dur"] + FOLGA), None)
        if k is None:
            return None
        at = _na_gravacao(velhas[k], t)
        candidatas = [j for j, o in enumerate(origem) if o == k] or \
                     [j for j, s in enumerate(novas) if s["source"] == velhas[k]["source"]]
        for j in candidatas:
            s = novas[j]
            if s["v_in"] - FOLGA <= at <= s["v_out"] + FOLGA:
                return max(0.0, tempo.no_corte(s, min(max(at, s["v_in"]), s["v_out"])))
        return None
    return levar


def _janela(levar: Levar, ini: float, dur: float, total: float) -> tuple[float, float] | None:
    """O começo e a duração de um item no corte novo; o fim que saiu do corte deixa a duração como
    estava, cortada no fim do vídeo."""
    a = levar(ini)
    if a is None:
        return None
    b = levar(ini + dur - FOLGA)
    nova = b + FOLGA - a if b is not None and b > a else dur
    return a, max(0.0, min(nova, total - a))


def camadas(cam: dict, levar: Levar, total: float) -> tuple[dict, list[str]]:
    """camadas.json no corte novo, e o que caiu fora (uma linha por item, para avisar)."""
    novo, fora = copy.deepcopy(cam), []
    for f in novo.get("faixas") or []:
        manter = []
        for it in f.get("itens") or []:
            j = _janela(levar, float(it.get("inicio", 0)), float(it.get("duracao", 0)), total)
            if j is None:
                nome = it.get("texto") or str(it.get("arquivo", "")).removeprefix("midia/")
                fora.append(f'{f.get("tipo")} "{nome}" em {float(it.get("inicio", 0)):.2f} s')
                continue
            it["inicio"], it["duracao"] = round(j[0], 3), round(j[1], 3)
            manter.append(it)
        f["itens"] = manter
    return novo, fora


def efeitos(ef: dict, levar: Levar, emendas: list[float], total: float, fps: float = 30.0) -> tuple[dict, list[str]]:
    """efeitos.json no corte novo. `emendas`: os instantes do corte novo em que uma tomada encontra a
    seguinte; a transição vai para a emenda nova mais perto, ou sai se a emenda dela sumiu."""
    novo, fora, manter = copy.deepcopy(ef), [], []
    for it in novo.get("itens") or []:
        if it.get("tipo") == "transicao":
            c = levar(float(it.get("corte", 0)))
            perto = min(emendas, key=lambda e: abs(e - c)) if c is not None and emendas else None
            if perto is None or abs(perto - c) > 2.0 / fps:
                fora.append(f'transição "{it.get("pacote")}" no corte de {float(it.get("corte", 0)):.2f} s')
                continue
            it["corte"] = round(perto, 3)
        else:
            j = _janela(levar, float(it.get("inicio", 0)), float(it.get("duracao", 0)), total)
            if j is None:
                fora.append(f'{it.get("tipo")} "{it.get("pacote", "ajuste")}" em {float(it.get("inicio", 0)):.2f} s')
                continue
            it["inicio"], it["duracao"] = round(j[0], 3), round(j[1], 3)
        manter.append(it)
    novo["itens"] = manter
    return novo, fora


def velocidade(vel: dict, levar: Levar, total: float) -> tuple[dict, list[str]]:
    """velocidade.json no corte novo. Os trechos ficam no relógio do final, que é o do corte (o final é
    desenhado sobre ele); a duração passa a ser a do corte novo."""
    novo, fora, manter = copy.deepcopy(vel), [], []
    for t in novo.get("trechos") or []:
        a, b = levar(float(t["inicio"])), levar(float(t["fim"]) - FOLGA)
        if a is None or b is None or b <= a:
            fora.append(f'trecho de velocidade {float(t["inicio"]):.2f}–{float(t["fim"]):.2f} s')
            continue
        t["inicio"], t["fim"] = round(a, 3), round(b + FOLGA, 3)
        manter.append(t)
    novo["trechos"], novo["duracao"] = manter, round(total, 3)
    return novo, fora
