"""Os efeitos que tiram a pessoa do fundo: o `cenas[]` do edit-data.json.

Sete tipos: `fundo` (troca o cenário), `vidro` (Letra de vidro), `capa` (Capa de revista), `mural`
(Mural de manchete), `parede` (Parede de fotos), `grafico` (Gráfico subindo) e `chroma` (Site).
Cada um redesenha a janela dele, normalmente a tomada inteira: um fundo novo, coisas sobre ele e a
pessoa recortada na frente.

Este módulo diz:
- o que cada tipo pede e em que faixa (`TIPOS`, `validar`);
- onde a pessoa está no recorte (`medir_pessoa`, a única parte que lê arquivo, pelo ffmpeg);
- o lugar padrão de cada coisa na tela (`layout`), calculado a partir da pessoa.

Tudo em px do quadro 1080x1920: o mesmo espaço do `texto: {x, y}` que o editor grava e do template
(`src/cenas/`), que lê o `layout`. Dentro de um efeito a câmera do corte não age (sem o zoom nem o
rastreio da tomada), então a medida tirada do recorte vale direto na tela. O `zoom` do efeito
aproxima a pessoa em volta do topo da cabeça, que fica parado.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path, PurePosixPath

import numpy as np

W, H = 1080, 1920
FUNDOS = ("concreto", "parede", "kraft", "lousa", "estudio", "neon")
FUNDO_PADRAO = {"mural": "fundos/parede", "parede": "fundos/concreto"}  # os que o tipo usa sem pedir
PAREDE_FOTOS = 14  # os lugares de foto da Parede
PRESENCA_MINIMA = 0.6  # abaixo disso a pessoa sai do quadro boa parte da janela: o efeito não serve

# `obrigatorios`: textos que não podem faltar (nenhum texto tem padrão: campo vazio não desenha
# nada); `numeros`: a faixa de cada número. As listas são conferidas em `_CONFERE`.
TIPOS: dict[str, dict] = {
    "fundo": {"nome": "Fundo", "obrigatorios": ("fundo",), "numeros": {"escurecer": (0, 0.6), "desfoque": (0, 20)}},
    "vidro": {"nome": "Letra de vidro", "obrigatorios": ("palavra",),
              "numeros": {"tamanho": (60, 600), "largura": (200, 1080)}},
    "capa": {"nome": "Capa de revista", "obrigatorios": ("nome",),
             "numeros": {"tamanho": (120, 500), "largura": (300, 1080)}},
    "mural": {"nome": "Mural de manchete", "obrigatorios": (), "numeros": {}},
    "parede": {"nome": "Parede de fotos", "obrigatorios": (), "numeros": {"cada": (0.03, 1), "inicio": (0, 5)}},
    "grafico": {"nome": "Gráfico subindo", "obrigatorios": (), "numeros": {"inicio": (0, 5), "passo": (0.03, 1)}},
    "chroma": {"nome": "Site", "obrigatorios": ("titulo",), "numeros": {"escala": (0.45, 0.85), "entrada": (0, 5)}},
}
# instantes em segundos do corte (como `start`/`end`): têm de cair dentro da janela
INSTANTES = {"vidro": ("at",), "mural": ("circuloAt",), "parede": ("pequenoAt", "giganteAt")}


# ---------------------------------------------------------------- validação

def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _texto(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _textos(v, ate: int) -> bool:
    return isinstance(v, list) and len(v) <= ate and all(isinstance(s, str) for s in v)


def midia(v) -> bool:
    """Um arquivo do projeto, relativo à pasta do edit: `midia/<arquivo>`."""
    if not isinstance(v, str) or "\\" in v or v.startswith("/"):
        return False
    partes = PurePosixPath(v).parts
    return len(partes) >= 2 and partes[0] == "midia" and ".." not in partes


def fundo_pronto(v) -> str | None:
    """O id de `fundos/<id>` quando é um dos fundos prontos do kit."""
    if isinstance(v, str) and v.startswith("fundos/"):
        i = v[len("fundos/"):].removesuffix(".jpg")
        return i if i in FUNDOS else None
    return None


def _fundo(c, obrigatorio: bool) -> list[str]:
    v = c.get("fundo")
    if v is None or (obrigatorio and not _texto(v)):  # o que falta já foi dito
        return []
    if fundo_pronto(v) or midia(v):
        return []
    return [f"`fundo` é `fundos/<{'|'.join(FUNDOS)}>` ou `midia/<arquivo do projeto>`"]


def _c_capa(c) -> list[str]:
    erros = []
    if c.get("topo") is not None and not _textos(c["topo"], 3):
        erros.append("`topo` é uma lista de até 3 textos")
    for k in ("esquerda", "direita"):
        v = c.get(k)
        par = lambda p: isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) for s in p)  # noqa: E731
        if v is not None and not (isinstance(v, list) and len(v) <= 3 and all(par(p) for p in v)):
            erros.append(f"`{k}` é uma lista de até 3 pares [linha de cima, linha de baixo]")
    return erros


def _c_mural(c) -> list[str]:
    ms = c.get("manchetes")
    if not isinstance(ms, list) or not 1 <= len(ms) <= 4:
        return ["`manchetes` é uma lista de 1 a 4 itens {kicker, t, at}"]
    erros = [f"`manchetes[{i}]` sem `t`" for i, m in enumerate(ms) if not (isinstance(m, dict) and _texto(m.get("t")))]
    ci = c.get("circulo")
    if ci is not None and not (isinstance(ci, int) and not isinstance(ci, bool) and 0 <= ci < len(ms)):
        erros.append(f"`circulo` é o número de uma manchete, de 0 a {len(ms) - 1}")
    return erros + _fundo(c, False)


def _c_parede(c) -> list[str]:
    fotos, erros = c.get("fotos"), []
    if fotos is not None:
        if not isinstance(fotos, list) or len(fotos) > PAREDE_FOTOS:
            erros.append(f"`fotos` é uma lista de até {PAREDE_FOTOS} itens {{src, legenda}}")
        else:
            erros += [f"`fotos[{i}].src` é `midia/<arquivo do projeto>`" for i, f in enumerate(fotos)
                      if not (isinstance(f, dict) and midia(f.get("src")))]
    return erros + _fundo(c, False)


def _c_grafico(c) -> list[str]:
    v = c.get("valores")
    if not isinstance(v, list) or not 2 <= len(v) <= 12 or not all(_num(x) and 0 <= x <= 1 for x in v):
        return ["`valores` é uma lista de 2 a 12 números de 0 a 1"]
    r = c.get("rotulos")
    if r is not None and not (_textos(r, len(v)) and len(r) == len(v)):
        return [f"`rotulos` é uma lista de {len(v)} textos, um por valor"]
    return []


def _c_chroma(c) -> list[str]:
    erros = []
    if c.get("lado") not in (None, "direita", "esquerda"):
        erros.append("`lado` é `direita` ou `esquerda`")
    if c.get("menu") is not None and not _textos(c["menu"], 4):
        erros.append("`menu` é uma lista de até 4 textos")
    return erros


_CONFERE = {"fundo": lambda c: _fundo(c, True), "vidro": lambda c: [], "capa": _c_capa, "mural": _c_mural,
            "parede": _c_parede, "grafico": _c_grafico, "chroma": _c_chroma}


def _instantes(c):
    for k in INSTANTES.get(c["tipo"], ()):
        if c.get(k) is not None:
            yield k, c[k]
    if c["tipo"] == "mural" and isinstance(c.get("manchetes"), list):
        for i, m in enumerate(c["manchetes"]):
            if isinstance(m, dict) and m.get("at") is not None:
                yield f"manchetes[{i}].at", m["at"]


def validar(c) -> list[str]:
    """O que está errado no item, uma frase por problema (vazio = pode seguir). Não confere se os
    arquivos existem: isso é do helper, que conhece a pasta do projeto."""
    if not isinstance(c, dict):
        return ["o item não é um objeto"]
    tipo = c.get("tipo")
    if tipo not in TIPOS:
        return [f"tipo `{tipo}` não existe no template; os que existem: {', '.join(TIPOS)}"]
    t, erros = TIPOS[tipo], []
    ini, fim = c.get("start"), c.get("end")
    janela = _num(ini) and _num(fim) and ini >= 0 and fim - ini >= 0.3
    if not janela:
        erros.append("`start` e `end` são segundos do corte, com `end` pelo menos 0,3 s depois de `start`")
    erros += [f"falta `{k}`" for k in t["obrigatorios"] if not _texto(c.get(k))]
    for k, (lo, hi) in {"zoom": (1, 1.6), **t["numeros"]}.items():
        v = c.get(k)
        if v is not None and not (_num(v) and lo <= v <= hi):
            erros.append(f"`{k}` vai de {lo} a {hi}")
    erros += [f"`{k}` é true ou false" for k in ("desligada", "aproximar", "sombra")
              if k in c and not isinstance(c[k], bool)]
    tx = c.get("texto")
    if tx is not None and not (isinstance(tx, dict) and _num(tx.get("x")) and _num(tx.get("y"))):
        erros.append("`texto` é {x, y} em px do quadro, ou null")
    if c.get("estilo") is not None and not isinstance(c["estilo"], dict):
        erros.append("`estilo` é um objeto")
    erros += _CONFERE[tipo](c)
    if janela:
        erros += [f"`{k}` ({v}) fica fora da janela ({ini} a {fim})" for k, v in _instantes(c)
                  if not (_num(v) and ini <= v <= fim)]
    return erros


# ---------------------------------------------------------------- a pessoa no recorte

MW, MH = 270, 480  # a medida decodifica só o alfa, nesse tamanho: cada px vale 4 do quadro
FAIXAS = 16  # o perfil da pessoa em faixas de 120 px de altura
_MIN_PX = MW * MH // 200  # menos que 0,5 % do quadro: não tem ninguém


def _quadro(m: np.ndarray):
    """A pessoa num quadro (máscara MH x MW): caixa, topo da cabeça, centro dela e o perfil."""
    if m.sum() < _MIN_PX:
        return None
    col, lin = m.sum(axis=0), m.sum(axis=1)
    xs, ys = np.flatnonzero(col >= 2), np.flatnonzero(lin >= 2)  # >= 2 px: um ponto solto não conta
    if not len(xs) or not len(ys):
        return None
    # a cabeça é o que está mais alto na faixa central (em volta do centro de massa, que é o
    # tronco): uma mão erguida ao lado não vira o topo da cabeça
    cx = int((col * np.arange(MW)).sum() / col.sum())
    a, b = max(0, cx - 30), min(MW, cx + 31)
    yt = np.flatnonzero(m[:, a:b].sum(axis=1) >= 2)
    topo = int(yt[0]) if len(yt) else int(ys[0])
    a2, b2 = max(0, cx - 45), min(MW, cx + 46)
    _, xc = np.nonzero(m[topo:topo + 20, a2:b2])
    cabeca = a2 + float(xc.mean()) if len(xc) else float(cx)
    alt = MH // FAIXAS
    faixas = []
    for f in range(FAIXAS):
        xf = np.flatnonzero(m[f * alt:(f + 1) * alt].sum(axis=0) >= 2)
        faixas.append((int(xf[0]), int(xf[-1]) + 1) if len(xf) else None)
    return int(xs[0]), int(xs[-1]) + 1, int(ys[-1]) + 1, topo, cabeca, faixas


def medir_pessoa(matte: Path) -> dict:
    """Onde a pessoa está no recorte (o .mov com alfa do person_matte.py), em px do quadro:
    `x0`, `x1`, `topo`, `base` (a caixa, dos percentis 5 a 95 % das caixas de cada quadro, com o
    topo da cabeça tirado da faixa central), `cabecaX` (o centro da cabeça), `presenca` (a fração dos
    quadros em que ela aparece) e `perfil` ([y0, y1, x0, x1] de cada faixa de 120 px em que ela
    aparece, para achar o espaço livre do lado da cabeça, que é mais estreita que os ombros).

    Lê só o alfa, já reduzido, um quadro por vez: o recorte inteiro não cabe na memória."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(matte),
           "-vf", f"scale={MW}:{MH}:flags=area,format=yuva444p,alphaextract", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    tam, quadros, com = MW * MH, 0, []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as pr:
        while True:
            buf = pr.stdout.read(tam)
            if len(buf) < tam:
                break
            quadros += 1
            q = _quadro(np.frombuffer(buf, np.uint8).reshape(MH, MW) > 127)
            if q:
                com.append(q)
        erro = pr.stderr.read().decode("utf-8", "replace").strip()
    if pr.returncode or not quadros:
        raise RuntimeError(f"o ffmpeg não leu o recorte {Path(matte).name}: {erro[-300:] or 'nenhum quadro'}")
    if not com:
        return {"presenca": 0.0, "quadros": quadros}
    sx, sy = W / MW, H / MH
    pct = lambda v, p: float(np.percentile(v, p))  # noqa: E731
    alt = MH // FAIXAS
    perfil = []
    for f in range(FAIXAS):
        lados = [q[5][f] for q in com if q[5][f]]
        if len(lados) >= 0.15 * len(com):  # a faixa em que ela aparece de vez em quando não conta
            perfil.append([round(f * alt * sy), round((f + 1) * alt * sy),
                           round(pct([l[0] for l in lados], 5) * sx), round(pct([l[1] for l in lados], 95) * sx)])
    return {"x0": round(pct([q[0] for q in com], 5) * sx), "x1": round(pct([q[1] for q in com], 95) * sx),
            "topo": round(pct([q[3] for q in com], 5) * sy), "base": round(pct([q[2] for q in com], 95) * sy),
            "cabecaX": round(float(np.median([q[4] for q in com])) * sx),
            "presenca": round(len(com) / quadros, 3), "quadros": quadros, "perfil": perfil}


def com_zoom(p: dict, zoom: float | None) -> dict:
    """A pessoa com o `zoom` do efeito: escala em volta do topo da cabeça (`cabecaX`, `topo`), que fica
    parado; o resto cresce para os lados e para baixo, cortado pelo quadro."""
    z = min(1.6, max(1.0, float(zoom or 1)))
    if not p.get("presenca") or z == 1:
        return dict(p)
    cx, ty = p["cabecaX"], p["topo"]
    fx = lambda x: min(W, max(0, cx + (x - cx) * z))  # noqa: E731
    fy = lambda y: min(H, max(0, ty + (y - ty) * z))  # noqa: E731
    perfil = []
    for y0, y1, x0, x1 in _perfil(p):
        r = [round(fy(y0)), round(fy(y1)), round(fx(x0)), round(fx(x1))]
        if r[1] > r[0] and r[3] > r[2]:
            perfil.append(r)
    return {**p, "x0": round(fx(p["x0"])), "x1": round(fx(p["x1"])), "base": round(fy(p["base"])), "perfil": perfil}


def resumo(p: dict) -> dict:
    """O que vai para o edit-data.json (o perfil fica no cache das medidas)."""
    return {k: p[k] for k in ("x0", "x1", "topo", "base", "cabecaX", "presenca") if k in p}


# ---------------------------------------------------------------- o lugar de cada coisa

def _perfil(p: dict) -> list:
    return p.get("perfil") or [[p["topo"], p["base"], p["x0"], p["x1"]]]


def _inter(a: tuple, b: tuple) -> float:
    """Área em comum de dois retângulos (x, y, w, h)."""
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def cobre(p: dict, r: tuple) -> float:
    """A fração do retângulo (x, y, w, h) que a pessoa cobre, faixa a faixa do perfil."""
    return sum(_inter(r, (x0, y0, x1 - x0, y1 - y0)) for y0, y1, x0, x1 in _perfil(p)) / (r[2] * r[3])


def _lado(p: dict, ya: float, yb: float) -> tuple[float, float]:
    """Onde a pessoa começa e termina na horizontal entre as alturas ya e yb (W, 0 = não está)."""
    rs = [(x0, x1) for y0, y1, x0, x1 in _perfil(p) if y1 > ya and y0 < yb]
    return (min(r[0] for r in rs), max(r[1] for r in rs)) if rs else (W, 0)


def _cabeca(p: dict) -> tuple:
    return (p["cabecaX"] - 170, p["topo"], 340, 420)


def _letras(s) -> float:
    return max(1.0, sum(0.3 if ch == " " else 1.0 for ch in str(s or "").strip()))


def _vidro(p: dict, c: dict) -> dict:
    """`y`: o centro da palavra (o template põe o pé das letras em y + 0,36·tamanho, e a letra tem
    0,72·tamanho de altura). Só o pé das letras fica atrás do topo da cabeça, entre `topo` e
    `topo + 0,3·tamanho`, e o topo delas a 60 px ou mais da borda. `tamanho`: o pedido, ou o maior que
    cabe nessas regras e na `largura` sem apertar a palavra a menos de 70 % da largura dela."""
    topo = p["topo"]
    t = c.get("tamanho") or max(120.0, min(300.0, (topo - 60) / 0.59,
                                           float(c.get("largura") or 1000) / (0.46 * _letras(c.get("palavra")))))
    return {"y": round(max(60 + 0.37 * t, topo - 0.22 * t)), "tamanho": round(t)}


def _capa(p: dict, c: dict) -> dict:
    """`baseline` e `tamanho` do nome da revista: atrás da cabeça, que cobre o pé dele, e abaixo da
    linha do topo (o nome começa em 300 ou mais). `colunas`: onde fica cada lista de chamadas
    (`esquerda`, `direita`), abaixo do nome e fora da pessoa, com o `lado` do quadro em que ficou. A
    lista cujo lado não tem espaço vai para o outro, se ele está livre; sem lugar, fica `null`."""
    topo = p["topo"]
    tam = c.get("tamanho") or max(220.0, min(330.0, (topo - 300) / 0.54))
    baseline = max(topo + 0.18 * tam, 300 + 0.72 * tam)
    y = max(820.0, baseline + 80)
    x0, x1 = _lado(p, y, y + 460)
    we, wd = min(262.0, x0 - 40), min(180.0, W - 22 - x1)
    lados = {"esquerda": {"x": 40, "y": round(y), "w": round(we), "lado": "esquerda"} if we >= 140 else None,
             "direita": {"x": round(W - 22 - wd), "y": round(y), "w": round(wd), "lado": "direita"} if wd >= 120 else None}
    colunas = dict(lados)
    for k, outro in (("esquerda", "direita"), ("direita", "esquerda")):
        if c.get(k) and not lados[k] and lados[outro] and not c.get(outro):
            colunas = {k: lados[outro], outro: None}
    return {"baseline": round(baseline), "tamanho": round(tam), "colunas": colunas}


# os recortes de jornal como foram desenhados (x, y, w, h, giro): dois em cima, dois dos lados
_MURAL = ((34, 170, 540, 300, -4), (560, 110, 490, 300, 3.5), (18, 640, 330, 380, 2.5), (730, 600, 330, 380, -3))


def _lugar(p: dict, x: float, y: float, w: float, h: float, outros: list) -> tuple[int, int]:
    """O lugar mais perto do desenhado em que a pessoa cobre até 12 % do recorte e os outros
    recortes até 20 % (no mural eles se sobrepõem um pouco); sem nenhum assim, o menos coberto."""
    def custo(cx, cy):
        r = (cx, cy, w, h)
        return cobre(p, r), max((_inter(r, (o["x"], o["y"], o["w"], o["h"])) / (w * h) for o in outros), default=0.0)

    cp, co = custo(x, y)
    if cp <= 0.12 and co <= 0.2:
        return round(x), round(y)
    melhor = None
    for cy in range(90, 1380 - int(h) + 1, 20):  # abaixo de 1380 ficam a legenda e o gancho
        for cx in range(-20, W + 20 - int(w) + 1, 20):
            cp, co = custo(cx, cy)
            d = math.hypot(cx - x, cy - y)
            ok = cp <= 0.12 and co <= 0.2
            chave = (0, d) if ok else (1, cp + co, d)
            if melhor is None or chave < melhor[0]:
                melhor = (chave, cx, cy)
    return melhor[1], melhor[2]


def _mural(p: dict, c: dict) -> dict:
    """`slots`: um recorte de jornal por manchete, onde a pessoa não está."""
    slots: list[dict] = []
    for x, y, w, h, r in _MURAL[:len(c.get("manchetes") or [])]:
        lx, ly = _lugar(p, x, y, w, h, slots)
        slots.append({"x": lx, "y": ly, "w": w, "h": h, "r": r})
    return {"slots": slots}


def _parede(p: dict, c: dict) -> dict:
    """`bloco`: o centro da fita com a palavra grande (~316 px de altura), no lugar desenhado
    (y 245) quando cabe acima da cabeça; com a cabeça alta, ele sobe junto, até 160."""
    return {"bloco": {"x": W // 2, "y": round(max(160.0, min(245.0, p["topo"] - 170)))}}


def _grafico(p: dict, c: dict) -> dict:
    """`base` e `altura` das barras: a base nunca abaixo da base da pessoa. `bloco`: a etiqueta, do
    lado oposto ao da cabeça, na altura desenhada (411) ou acima da cabeça quando bate nela."""
    base = min(1270.0, float(p["base"]))
    tw = min(1040, max(160, len(str(c.get("etiqueta") or "")) * 42)) + 128  # a largura que o editor usa
    x = 751 if p["cabecaX"] <= W / 2 else W - 751
    y = 411.0
    if _inter((x - tw / 2, y - 65, tw, 130), _cabeca(p)):
        y = max(110.0, p["topo"] - 90)
    return {"base": round(base), "altura": round(max(160.0, min(760.0, base - 240))), "bloco": {"x": x, "y": round(y)}}


# os três blocos de texto do Site, em volta do centro desenhado (514, 590): título, frase e botão
_SITE = ((64, 250, 900, 188), (66, 640, 560, 135), (64, 830, 496, 100))


def _chroma(p: dict, c: dict) -> dict:
    """A pessoa no canto do `lado` pedido, inteira no quadro: o quadro todo em `escala`, com o canto
    em (`x`, `y`) e o pé no chão. O lado que ela toca no vídeo original (um ombro cortado) fica na
    borda da tela, para a linha reta do corte não aparecer. `bloco`: o texto, que sobe quando bate
    nela."""
    esc = min(0.85, max(0.45, float(c.get("escala") or 0.7)))
    pw, ph = W * esc, H * esc
    if (c.get("lado") or "direita") == "direita":
        x = W - 120 - p["x1"] * esc
        if p["x1"] >= W - 8:
            x = max(x, W - pw)
    else:
        x = 120 - p["x0"] * esc
        if p["x0"] <= 8:
            x = min(x, 0.0)
    y = H - ph
    gente = (x + p["x0"] * esc - 24, y + p["topo"] * esc - 24, (p["x1"] - p["x0"]) * esc + 48, H)
    sobe = max([b[1] + b[3] - gente[1] for b in _SITE if _inter(b, gente)], default=0.0)
    return {"escala": round(esc, 3), "x": round(x), "y": round(y), "bloco": {"x": 514, "y": round(max(494.0, 590 - sobe))}}


_LAYOUTS = {"fundo": lambda p, c: {}, "vidro": _vidro, "capa": _capa, "mural": _mural, "parede": _parede,
            "grafico": _grafico, "chroma": _chroma}


def layout(tipo: str, p: dict, c: dict) -> dict:
    """As posições padrão do efeito para esta pessoa (já com o `zoom`). O `texto: {x, y}` que a
    pessoa arrasta no editor vale por cima do `bloco` daqui."""
    return _LAYOUTS[tipo](p, c)
