"""Leva um instante do corte antigo para o corte novo, pelo instante da gravação.

Camadas, efeitos, trechos de velocidade e a Fase 2 inteira moram no relógio do cut.mp4. Quando o
Salvar muda as tomadas, cada instante volta à gravação pela tomada antiga em que caía e reaparece no
corte novo pela tomada que veio dela (`origem`: o índice da tomada antiga de cada tomada nova; None = sem
origem). O que caía num pedaço que saiu do corte não tem para onde ir: volta None, e quem chamou deixa o
item de fora e avisa (references/shortform.md, "Same save re-cuts?").

Uma JANELA (um item com começo e fim) vai pelo que ficou dela: a parte da gravação que ainda está no
corte. Um filtro ou um efeito que cobre a tomada inteira começa no começo dela; aparado o começo, ele
encolhe com a tomada em vez de sair. Um INSTANTE dentro de uma janela (a palavra em que o efeito
aparece) que caiu no pedaço tirado vai para a borda mais perto da tomada (`perto`).
"""
from __future__ import annotations

import copy
import re
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

    def _da(k: int) -> list[int]:
        return [j for j, o in enumerate(origem) if o == k] or \
               [j for j, s in enumerate(novas) if s["source"] == velhas[k]["source"]]

    def _velha(t: float) -> int | None:
        return next((i for i, s in enumerate(velhas) if s["out"] - FOLGA <= t < s["out"] + s["dur"] + FOLGA), None)

    def levar(t: float) -> float | None:
        k = _velha(t)
        if k is None:
            return None
        at = _na_gravacao(velhas[k], t)
        for j in _da(k):
            s = novas[j]
            if s["v_in"] - FOLGA <= at <= s["v_out"] + FOLGA:
                return max(0.0, tempo.no_corte(s, min(max(at, s["v_in"]), s["v_out"])))
        return None

    def perto(t: float) -> float | None:
        """Como `levar`, mas o instante que caiu no pedaço tirado vai para a borda mais perto da tomada
        que veio da mesma; None só quando a tomada inteira saiu."""
        k = _velha(t)
        if k is None:
            return None
        at = _na_gravacao(velhas[k], t)
        cands = [j for j, o in enumerate(origem) if o == k]
        if not cands:  # sem tomada que veio desta: só o instante que ainda está no corte
            return levar(t)
        j = min(cands, key=lambda j: 0.0 if novas[j]["v_in"] <= at <= novas[j]["v_out"]
                else min(abs(at - novas[j]["v_in"]), abs(at - novas[j]["v_out"])))
        s = novas[j]
        return max(0.0, tempo.no_corte(s, min(max(at, s["v_in"]), s["v_out"])))

    def janela(ini: float, fim: float) -> tuple[float, float] | None:
        """A janela [ini, fim] do corte velho no novo: a parte dela que ainda está no corte, de cada
        tomada velha por onde ela passa (na 1ª tomada nova que veio de cada uma). None = nada ficou."""
        pedacos = []
        for k, sv in enumerate(velhas):
            a, b = max(ini, sv["out"]), min(fim, sv["out"] + sv["dur"])
            if b - a <= FOLGA:
                continue
            ga, gb = _na_gravacao(sv, a), _na_gravacao(sv, b)
            for j in _da(k):
                n = novas[j]
                x, y = max(ga, n["v_in"]), min(gb, n["v_out"])
                if y - x > FOLGA:
                    pedacos.append((tempo.no_corte(n, x), tempo.no_corte(n, y)))
                    break
        if not pedacos:
            return None
        return max(0.0, min(p[0] for p in pedacos)), max(p[1] for p in pedacos)

    levar.perto, levar.janela = perto, janela  # type: ignore[attr-defined]
    return levar


def _janela(levar: Levar, ini: float, dur: float, total: float) -> tuple[float, float] | None:
    """O começo e a duração de um item no corte novo: o que ficou dele (`mapa`). Com um `levar` sem
    janela (os testes), o fim que saiu do corte deixa a duração como estava, cortada no fim do vídeo."""
    jan = getattr(levar, "janela", None)
    if jan is not None:
        r = jan(ini, ini + dur)
        if r is None:
            return None
        nova = min(r[1] - r[0], total - r[0])
        return (r[0], nova) if nova >= MINIMO else None
    a = levar(ini)
    if a is None:
        return None
    b = levar(ini + dur - FOLGA)
    nova = b + FOLGA - a if b is not None and b > a else dur
    nova = min(nova, total - a)
    return (a, nova) if nova >= MINIMO else None


MINIMO = 0.05  # o menor item que camadas.py e efeitos.py aceitam: menos que isso, o item saiu


def _fora(item: str, nome: str, inicio: float) -> dict:
    """O que caiu num trecho que saiu do corte: o tipo, o nome que a pessoa reconhece e onde estava
    (no corte velho). Quem avisa monta a frase no idioma dela."""
    return {"item": item, "nome": nome, "inicio": round(float(inicio), 3)}


def camadas(cam: dict, levar: Levar, total: float) -> tuple[dict, list[dict]]:
    """camadas.json no corte novo, e o que caiu fora."""
    novo, fora = copy.deepcopy(cam), []
    for f in novo.get("faixas") or []:
        manter = []
        for it in f.get("itens") or []:
            j = _janela(levar, float(it.get("inicio", 0)), float(it.get("duracao", 0)), total)
            if j is None:
                nome = " / ".join(str(it.get("texto")).split("\n")) if it.get("texto") else \
                    str(it.get("trilha") or it.get("arquivo", "")).removeprefix("midia/")
                fora.append(_fora(str(f.get("tipo")), nome, it.get("inicio", 0)))
                continue
            it["inicio"], it["duracao"] = round(j[0], 3), round(j[1], 3)
            manter.append(it)
        f["itens"] = manter
    return novo, fora


def efeitos(ef: dict, levar: Levar, emendas: list[float], total: float, fps: float = 30.0) -> tuple[dict, list[dict]]:
    """efeitos.json no corte novo. `emendas`: os instantes do corte novo em que uma tomada encontra a
    seguinte; a transição vai para a emenda nova mais perto, ou sai se a emenda dela sumiu."""
    novo, fora, manter = copy.deepcopy(ef), [], []
    for it in novo.get("itens") or []:
        if it.get("tipo") == "transicao":
            c = levar(float(it.get("corte", 0)))
            perto = min(emendas, key=lambda e: abs(e - c)) if c is not None and emendas else None
            if perto is None or abs(perto - c) > 2.0 / fps:
                fora.append(_fora("transicao", str(it.get("pacote")), it.get("corte", 0)))
                continue
            it["corte"] = round(perto, 3)
        else:
            j = _janela(levar, float(it.get("inicio", 0)), float(it.get("duracao", 0)), total)
            if j is None:
                fora.append(_fora(str(it.get("tipo")), str(it.get("pacote") or ""), it.get("inicio", 0)))
                continue
            it["inicio"], it["duracao"] = round(j[0], 3), round(j[1], 3)
        manter.append(it)
    novo["itens"] = manter
    return novo, fora


def velocidade(vel: dict, levar: Levar, total: float) -> tuple[dict, list[dict]]:
    """velocidade.json no corte novo. Os trechos ficam no relógio do final, que é o do corte (o final é
    desenhado sobre ele); a duração passa a ser a do corte novo."""
    novo, fora, manter = copy.deepcopy(vel), [], []
    for t in novo.get("trechos") or []:
        a, b = levar(float(t["inicio"])), levar(float(t["fim"]) - FOLGA)
        if a is None or b is None or b <= a:
            fora.append(_fora("velocidade", f'{float(t["fator"]):g}×', t["inicio"]))
            continue
        t["inicio"], t["fim"] = round(a, 3), round(b + FOLGA, 3)
        manter.append(t)
    novo["trechos"], novo["duracao"] = manter, round(total, 3)
    return novo, fora


# ---------------------------------------------------------------- a Fase 2 (edit-data.json)

# os blocos da Fase 2 pelo nome no edit-data, os campos de começo e de fim (ou duração) e o nome do item
# nos avisos (o editor monta a frase); `textos` e os blocos com `camada` são do camadas_edit_data.py
BLOCOS = {"inserts": ("start", "end", "insert"), "splitInserts": ("start", "end", "split"),
          "splitVideos": ("start", "end", "splitvideo"), "wordAccents": ("start", "end", "word"),
          "behind": ("start", "dur", "behind"), "numeros": ("at", "end", "numero")}
# instantes absolutos do corte dentro de um efeito ou gráfico: `at`, `ate` (até quando um item da
# lista fica) e todo campo terminado em `At` (kpiAt, circuloAt, fimAt...). Os relativos (`inicio`,
# `entrada`, `saiEm`, `cada`, `passo`, `fraseInicio`) ficam.
INSTANTE = re.compile(r"^(at|ate|[a-z][A-Za-z]*At)$")


def _r(x: float) -> float:
    return round(float(x), 4)


def _instantes(d: dict, levar: Levar, de: float, ate: float) -> None:
    """Os instantes do item (e das listas e objetos dentro dele, como `itens[].selecao.at`) na janela
    nova [de, ate]."""
    for k, v in list(d.items()):
        if INSTANTE.match(k) and isinstance(v, (int, float)) and not isinstance(v, bool):
            t = levar.perto(float(v)) if hasattr(levar, "perto") else levar(float(v))
            d[k] = _r(min(max(t if t is not None else de, de), ate))
        elif isinstance(v, dict):
            _instantes(v, levar, de, ate)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, dict):
                    _instantes(x, levar, de, ate)


def _nome_bloco(b: dict) -> str:
    return str(b.get("text") or b.get("label") or b.get("titulo") or str(b.get("src") or "").split("/")[-1] or "")


def fase2(ed: dict, levar: Levar, total: float, origem: list[int | None], n_velhas: int) -> tuple[dict, list[dict]]:
    """O edit-data.json no corte novo: os blocos, os efeitos (`cenas`) com os instantes deles, o gancho, as
    janelas e os lugares da legenda e o zoom de cada tomada (pela tomada de origem). Devolve o novo e o
    que caiu fora. A legenda (captions.json) e a transcrição do corte vão por `legenda` e `transcricao`."""
    novo, fora = copy.deepcopy(ed), []
    for chave, (k_ini, k_fim, item) in BLOCOS.items():
        manter = []
        for b in novo.get(chave) or []:
            if not isinstance(b, dict) or "camada" in b:
                manter.append(b)
                continue
            ini = float(b.get(k_ini, 0))
            dur = float(b[k_fim]) if k_fim == "dur" else float(b.get(k_fim, ini)) - ini
            j = _janela(levar, ini, max(dur, MINIMO), total)
            if j is None:
                fora.append(_fora(item, _nome_bloco(b), ini))
                continue
            # o 1º quadro do item, pela conta exata (um `levar` tolerante acharia um vizinho na outra tomada)
            r0 = levar.janela(ini, ini + 1 / 30) if hasattr(levar, "janela") else None
            comeco = r0[0] if r0 else (None if hasattr(levar, "janela") else levar(ini))
            b[k_ini] = _r(j[0])
            b[k_fim] = _r(j[1]) if k_fim == "dur" else _r(j[0] + j[1])
            for v in b.values():  # as palavras de dentro (behind.words[].at) andam junto
                for x in v if isinstance(v, list) else []:
                    if isinstance(x, dict):
                        _instantes(x, levar, j[0], j[0] + j[1])
            # o recorte da pessoa foi feito para a janela velha: com o começo aparado, ele mostraria os
            # quadros que saíram; o Baixar refaz (gerar.py)
            if b.get("matte") and (comeco is None or abs(comeco - j[0]) > 0.5 / 30):
                b["_refazerMatte"] = True
            manter.append(b)
        if chave in novo:
            novo[chave] = manter
    # os efeitos (`cenas`) e os gráficos animados (`graficos`): a janela e os instantes de dentro
    for chave, item in (("cenas", "cena"), ("graficos", "grafico")):
        manter = []
        for c in novo.get(chave) or []:
            if not isinstance(c, dict):
                continue
            if "start" in c and "end" in c:
                j = _janela(levar, float(c["start"]), float(c["end"]) - float(c["start"]), total)
                if j is None:
                    fora.append(_fora(item, str(c.get("tipo") or ""), c["start"]))
                    continue
                c["start"], c["end"] = _r(j[0]), _r(j[0] + j[1])
                _instantes(c, levar, c["start"], c["end"])
            elif "at" in c:  # um efeito de um instante só (o corte com zoom)
                t = levar(float(c["at"]))
                if t is None:
                    fora.append(_fora(item, str(c.get("tipo") or ""), c["at"]))
                    continue
                c["at"] = _r(t)
            manter.append(c)
        if chave in novo:
            novo[chave] = manter
    h = novo.get("hook")
    if isinstance(h, dict) and h.get("endSec") is not None:  # o gancho vai do 0 ao fim dele
        r = levar.janela(0.0, float(h["endSec"])) if hasattr(levar, "janela") else None
        h["endSec"] = _r(r[1]) if r else _r(min(float(h["endSec"]), total))
    cap = novo.get("captions")
    if isinstance(cap, dict):
        if isinstance(cap.get("windows"), list):
            ws = []
            for w in cap["windows"]:
                j = _janela(levar, float(w.get("start", 0)), float(w.get("end", 0)) - float(w.get("start", 0)), total)
                if j is not None:
                    ws.append({**w, "start": _r(j[0]), "end": _r(j[0] + j[1])})
            cap["windows"] = ws
        pos = cap.get("positions")
        if isinstance(pos, dict) and isinstance(pos.get("phrases"), list):
            ph = []
            for f in pos["phrases"]:
                t = levar.perto(float(f.get("at", 0))) if hasattr(levar, "perto") else levar(float(f.get("at", 0)))
                if t is not None:
                    ph.append({**f, "at": _r(t)})
            pos["phrases"] = ph
    zs = (novo.get("camera") or {}).get("zooms")
    if isinstance(zs, list) and zs and len(zs) == n_velhas:  # uma por tomada: segue a tomada de origem
        novo["camera"]["zooms"] = [zs[o] if o is not None and o < len(zs) else zs[min(i, len(zs) - 1)]
                                   for i, o in enumerate(origem)]
    return novo, fora


def legenda(caps: list[dict], levar: Levar) -> tuple[list[dict], int]:
    """As palavras do captions.json no corte novo (ms), na ordem nova; devolve quantas saíram."""
    novas, saiu = [], 0
    for c in caps:
        ini, fim = float(c.get("startMs", 0)) / 1000, float(c.get("endMs", 0)) / 1000
        r = levar.janela(ini, max(fim, ini + FOLGA)) if hasattr(levar, "janela") else None
        if r is None:
            saiu += 1
            continue
        d = dict(c)
        d["startMs"], d["endMs"] = round(r[0] * 1000), round(max(r[1], r[0]) * 1000)
        if c.get("timestampMs") is not None:
            t = levar.perto(float(c["timestampMs"]) / 1000)
            d["timestampMs"] = round(min(max(t if t is not None else r[0], r[0]), r[1]) * 1000)
        novas.append(d)
    novas.sort(key=lambda c: c["startMs"])
    return novas, saiu


def transcricao(tr: dict, levar: Levar) -> dict:
    """O transcripts/cut.json (as palavras do corte, em segundos) no corte novo."""
    novo = copy.deepcopy(tr)
    palavras = []
    for w in tr.get("words") or []:
        if w.get("start") is None:
            continue
        ini = float(w["start"])
        fim = float(w.get("end") if w.get("end") is not None else ini)
        r = levar.janela(ini, max(fim, ini + FOLGA)) if hasattr(levar, "janela") else None
        if r is None:
            continue
        palavras.append({**w, "start": round(r[0], 3), "end": round(max(r[1], r[0]), 3)})
    palavras.sort(key=lambda w: w["start"])
    novo["words"] = palavras
    novo["text"] = " ".join(str(w.get("text", "")).strip() for w in palavras if w.get("type", "word") == "word").strip()
    return novo
