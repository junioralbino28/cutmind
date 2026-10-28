#!/usr/bin/env python3
"""O agente aprende o jeito de editar da pessoa: o que ela muda à mão depois de cada entrega vira regra numa
skill dela, e a regra que já existe é ATUALIZADA, nunca duplicada (como as skills do Hermes).

O manual existe para isso: com o tempo a pessoa mexe cada vez menos, porque o agente já começa do jeito dela.
Três passos, sem IA nos dois primeiros:

1. `guardar`: o que o agente entregou (edl.json, camadas.json, efeitos.json, velocidade.json, o edit-data e o
   estilo) fica em `<edit>/.cutmind/entregas/<n>/`. O `agente.py livre` chama sozinho, no fim de cada trabalho.
2. `diferenca`: o que a pessoa mudou desde a última entrega, em NÚMEROS e por assunto (corte, velocidade,
   enquadre, filtro, transição, texto, legenda, imagem, trilha, estilo). O `agente.py trabalhando` mostra sozinho,
   no começo do trabalho seguinte.
3. `regra`: o agente decide o que é hábito (não um conserto de conteúdo daquele vídeo) e grava na skill da pessoa,
   `~/.cutmind/jeito/` (a pasta de `CUTMIND_HOME`): `regras.json` é a fonte, `SKILL.md` o que se lê. Mesma chave =
   a mesma regra: conta mais um vídeo, guarda a prova, ajusta o texto. A regra guarda a PROVA medida, não só a
   conclusão do agente (um agente que grava a própria skill sem conferir pode guardar uma conclusão errada).

    uv run python -X utf8 helpers/aprender.py guardar <edit>
    uv run python -X utf8 helpers/aprender.py diferenca <edit> [--json]
    uv run python -X utf8 helpers/aprender.py regra <assunto> <chave> --texto "..." --prova "..." --video <nome>
    uv run python -X utf8 helpers/aprender.py regras            # a skill inteira, para ler no começo
    uv run python -X utf8 helpers/aprender.py esquecer <chave>  # a pessoa não quer mais essa regra
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ASSUNTOS = ("corte", "velocidade", "enquadre", "filtro", "transicao", "texto", "legenda", "imagem", "trilha", "estilo")
ARQUIVOS = ("edl.json", "camadas.json", "efeitos.json", "velocidade.json")
MAX_ENTREGAS = 20
MAX_PROVAS = 5
VIRA_REGRA = 2  # a partir de quantos vídeos o hábito vira "sempre faço"
_CHAVE = re.compile(r"[a-z0-9][a-z0-9_.-]{1,60}")


def casa() -> Path:
    return Path(os.environ.get("CUTMIND_HOME") or Path.home() / ".cutmind")


def pasta_jeito() -> Path:
    return casa() / "jeito"


def _ler(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _gravar(p: Path, dados) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes((json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    os.replace(tmp, p)


# ---------- 1. guardar o que o agente entregou ----------

def _entregas(edit: Path) -> Path:
    return Path(edit) / ".cutmind" / "entregas"


def _foto(edit: Path) -> dict:
    """O estado do projeto que importa para o jeito de editar, como está agora."""
    edit = Path(edit)
    st = _ler(edit / "state.json") or {}
    f = {nome: _ler(edit / nome) for nome in ARQUIVOS}
    ed = st.get("editData") if isinstance(st.get("editData"), str) else None
    f["edit-data.json"] = _ler(edit / ed) if ed else None
    f["estilo"] = st.get("style") if isinstance(st.get("style"), dict) else None
    return f


def guardar(edit: Path, agora: float | None = None) -> int:
    """Guarda a foto de agora como a entrega n (a próxima) e devolve n. Ficam as últimas MAX_ENTREGAS."""
    base = _entregas(edit)
    base.mkdir(parents=True, exist_ok=True)
    ns = sorted(int(p.name) for p in base.iterdir() if p.is_dir() and p.name.isdigit())
    n = (ns[-1] + 1) if ns else 1
    _gravar(base / str(n) / "foto.json", {"n": n, "quando": time.time() if agora is None else agora, "foto": _foto(edit)})
    for velho in ns[: max(0, len(ns) + 1 - MAX_ENTREGAS)]:
        shutil.rmtree(base / str(velho), ignore_errors=True)
    return n


def ultima_entrega(edit: Path) -> dict | None:
    base = _entregas(edit)
    if not base.is_dir():
        return None
    ns = sorted(int(p.name) for p in base.iterdir() if p.is_dir() and p.name.isdigit())
    return _ler(base / str(ns[-1]) / "foto.json") if ns else None


# ---------- 2. a diferença, em números ----------

def _r(v, casas=3):
    return round(float(v), casas) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def _mud(assunto: str, chave: str, de, para, onde: str = "") -> dict:
    return {"assunto": assunto, "chave": chave, "de": de, "para": para, **({"onde": onde} if onde else {})}


def _corte(a: dict | None, b: dict | None) -> list[dict]:
    out: list[dict] = []
    ra, rb = (a or {}).get("ranges") or [], (b or {}).get("ranges") or []
    if len(ra) != len(rb):
        out.append(_mud("corte", "tomadas", len(ra), len(rb)))
    for i, (x, y) in enumerate(zip(ra, rb)):
        onde = f"tomada {i + 1}"
        if x.get("source") != y.get("source"):
            out.append(_mud("corte", "tomada_trocada", x.get("source"), y.get("source"), onde))
            continue
        for ponta in ("start", "end"):
            d = _r(float(y.get(ponta, 0)) - float(x.get(ponta, 0)))
            if abs(d) >= 0.01:  # 10 ms: abaixo disso é arredondamento do editor
                out.append(_mud("corte", f"ponta_{'inicio' if ponta == 'start' else 'fim'}", _r(x.get(ponta)), _r(y.get(ponta)),
                                f"{onde}, {'+' if d > 0 else ''}{d} s"))
        if (x.get("volume") or 1) != (y.get("volume") or 1):
            out.append(_mud("corte", "volume_tomada", x.get("volume") or 1, y.get("volume") or 1, onde))
        if (x.get("velocidade") or 1) != (y.get("velocidade") or 1) or x.get("curva") != y.get("curva"):
            out.append(_mud("velocidade", "velocidade_tomada", x.get("curva") or x.get("velocidade") or 1,
                            y.get("curva") or y.get("velocidade") or 1, onde))
        if x.get("enquadre") != y.get("enquadre"):
            e = y.get("enquadre")
            para = None if not e else {"escala": _r(e["largura"] / 1080, 2), "x": e["x"], "y": e["y"],
                                       "formato": (e.get("recorte") or {}).get("formato")}
            out.append(_mud("enquadre", "enquadre_tomada", bool(x.get("enquadre")), para, onde))
    return out


def _itens(c: dict | None, tipo: str) -> dict:
    return {it["id"]: it for f in (c or {}).get("faixas") or [] if f.get("tipo") == tipo for it in f.get("itens") or []}


def _camadas(a: dict | None, b: dict | None) -> list[dict]:
    out: list[dict] = []
    ta, tb = _itens(a, "texto"), _itens(b, "texto")
    for iid, t in tb.items():
        if iid not in ta:
            out.append(_mud("texto", "texto_novo", None, {"estilo": t.get("estilo") or {}, "x": t.get("x"), "y": t.get("y")}, t.get("texto", "")[:40]))
            continue
        ea, eb = ta[iid].get("estilo") or {}, t.get("estilo") or {}
        for k in sorted(set(ea) | set(eb)):
            if ea.get(k) != eb.get(k):
                out.append(_mud("texto", f"texto_{k}", ea.get(k), eb.get(k), t.get("texto", "")[:40]))
        if (ta[iid].get("x"), ta[iid].get("y")) != (t.get("x"), t.get("y")):
            out.append(_mud("texto", "texto_lugar", [ta[iid].get("x"), ta[iid].get("y")], [t.get("x"), t.get("y")], t.get("texto", "")[:40]))
    for iid in ta.keys() - tb.keys():
        out.append(_mud("texto", "texto_apagado", ta[iid].get("texto", "")[:40], None))
    ia, ib = _itens(a, "imagem"), _itens(b, "imagem")
    for iid, it in ib.items():
        x = ia.get(iid) or {}
        for k in ("largura", "x", "y", "recorte", "volume"):
            if x.get(k) != it.get(k) and iid in ia:
                out.append(_mud("imagem", f"imagem_{k}", x.get(k), it.get(k), it.get("arquivo", "")))
    aa, ab = _itens(a, "audio"), _itens(b, "audio")
    for iid, it in ab.items():
        x = aa.get(iid)
        if it.get("trilha") and (not x or x.get("volume") != it.get("volume")):
            out.append(_mud("trilha", "trilha_volume", x and x.get("volume"), it.get("volume"), it.get("trilha")))
    return out


def _efeitos(a: dict | None, b: dict | None) -> list[dict]:
    out: list[dict] = []
    ea = {it["id"]: it for it in (a or {}).get("itens") or []}
    eb = {it["id"]: it for it in (b or {}).get("itens") or []}
    for iid, it in eb.items():
        assunto = "transicao" if it.get("tipo") == "transicao" else "filtro"
        x = ea.get(iid)
        if not x:
            out.append(_mud(assunto, f"{assunto}_novo", None, {k: it.get(k) for k in ("pacote", "intensidade", "duracao") if k in it}))
            continue
        for k in ("pacote", "intensidade", "duracao"):
            if x.get(k) != it.get(k):
                out.append(_mud(assunto, f"{assunto}_{k}", x.get(k), it.get(k)))
    for iid in ea.keys() - eb.keys():
        assunto = "transicao" if ea[iid].get("tipo") == "transicao" else "filtro"
        out.append(_mud(assunto, f"{assunto}_apagado", ea[iid].get("pacote"), None))
    return out


def _legenda(a: dict | None, b: dict | None) -> list[dict]:
    ca, cb = (a or {}).get("captions") or {}, (b or {}).get("captions") or {}
    return [_mud("legenda", f"legenda_{k}", ca.get(k), cb.get(k)) for k in sorted(set(ca) | set(cb))
            if k != "words" and ca.get(k) != cb.get(k) and not isinstance(cb.get(k), list)]


def diferenca(edit: Path) -> list[dict]:
    """O que a pessoa mudou à mão desde a última entrega do agente; vazio sem entrega guardada."""
    ult = ultima_entrega(edit)
    if not ult:
        return []
    a, b = ult.get("foto") or {}, _foto(edit)
    out = _corte(a.get("edl.json"), b.get("edl.json"))
    out += _camadas(a.get("camadas.json"), b.get("camadas.json"))
    out += _efeitos(a.get("efeitos.json"), b.get("efeitos.json"))
    ta = [(t.get("inicio"), t.get("fim"), t.get("fator")) for t in (a.get("velocidade.json") or {}).get("trechos") or []]
    tb = [(t.get("inicio"), t.get("fim"), t.get("fator")) for t in (b.get("velocidade.json") or {}).get("trechos") or []]
    if ta != tb:
        out.append(_mud("velocidade", "trechos_velocidade", ta, tb))
    out += _legenda(a.get("edit-data.json"), b.get("edit-data.json"))
    sa, sb = a.get("estilo") or {}, b.get("estilo") or {}
    for k in sorted(set(sa) | set(sb)):
        if sa.get(k) != sb.get(k):
            out.append(_mud("estilo", f"estilo_{k}", sa.get(k), sb.get(k)))
    return out


def texto_diferenca(mud: list[dict]) -> str:
    if not mud:
        return ""
    linhas = ["O QUE A PESSOA MUDOU À MÃO desde a sua última entrega (aprender.py). Para cada HÁBITO (não um conserto",
              "de conteúdo deste vídeo), grave ou atualize a regra: aprender.py regra <assunto> <chave> --texto --prova --video.",
              "Leia antes `aprender.py regras` e reuse a chave que já existe."]
    for m in mud:
        onde = f" ({m['onde']})" if m.get("onde") else ""
        linhas.append(f"  - {m['assunto']} · {m['chave']}{onde}: {json.dumps(m['de'], ensure_ascii=False)} → "
                      f"{json.dumps(m['para'], ensure_ascii=False)}")
    return "\n".join(linhas)


# ---------- 3. a skill do jeito da pessoa ----------

def carregar_regras() -> dict:
    d = _ler(pasta_jeito() / "regras.json")
    return d if isinstance(d, dict) and isinstance(d.get("regras"), dict) else {"versao": 1, "regras": {}}


def regra(assunto: str, chave: str, texto: str | None, prova: str, video: str, agora: float | None = None) -> dict:
    """Cria ou ATUALIZA a regra `chave`. Mesmo vídeo de novo não conta outra vez; a prova entra (as últimas
    MAX_PROVAS); `texto`, quando vem, troca o da regra (o agente ajustou o que entendeu)."""
    if assunto not in ASSUNTOS:
        raise ValueError(f"assunto: um de {', '.join(ASSUNTOS)}")
    if not _CHAVE.fullmatch(chave):
        raise ValueError("chave: minúsculas, números, ponto, traço ou sublinhado (ex.: corte.respiro_antes_da_frase)")
    if not prova.strip() or not video.strip():
        raise ValueError("toda regra precisa da prova medida e do vídeo de onde ela veio")
    d = carregar_regras()
    hoje = time.strftime("%Y-%m-%d", time.localtime(agora))
    r = d["regras"].get(chave)
    if r is None:
        if not texto:
            raise ValueError(f"regra nova ({chave}): diga o --texto")
        r = d["regras"][chave] = {"assunto": assunto, "texto": texto, "videos": [], "provas": [], "desde": hoje}
    elif texto:
        r["texto"] = texto
    r["assunto"] = assunto
    if video not in r["videos"]:
        r["videos"].append(video)
    r["provas"] = (r["provas"] + [f"{hoje} · {video}: {prova}"])[-MAX_PROVAS:]
    r["atualizada"] = hoje
    _gravar(pasta_jeito() / "regras.json", d)
    escrever_skill(d)
    return r


def esquecer(chave: str) -> bool:
    d = carregar_regras()
    if d["regras"].pop(chave, None) is None:
        return False
    _gravar(pasta_jeito() / "regras.json", d)
    escrever_skill(d)
    return True


def escrever_skill(d: dict | None = None) -> Path:
    """O SKILL.md que o agente lê no começo de cada edição: as regras por assunto, com quantos vídeos e a prova."""
    d = d or carregar_regras()
    linhas = ["---", "name: cutmind-meu-jeito",
              "description: O jeito de editar desta pessoa, aprendido com o que ela mudou à mão nas edições do CutMind. "
              "Ler no começo de cada edição e começar já desse jeito.", "---", "",
              "# O jeito de editar desta pessoa", "",
              f"Gerado por `aprender.py` (não editar à mão: a fonte é `regras.json`). **Regra** = aconteceu em {VIRA_REGRA} ou mais",
              "vídeos: aplique de saída e diga numa linha que aplicou. **Visto 1 vez** = só uma pista: aplique se combinar com o",
              "pedido, e confira com a pessoa.", ""]
    por = {}
    for chave, r in sorted(d["regras"].items()):
        por.setdefault(r["assunto"], []).append((chave, r))
    for assunto in ASSUNTOS:
        if assunto not in por:
            continue
        linhas += [f"## {assunto}", ""]
        for chave, r in por[assunto]:
            n = len(r["videos"])
            selo = "Regra" if n >= VIRA_REGRA else "Visto 1 vez"
            linhas.append(f"- **{selo}** ({n} vídeo{'s' if n != 1 else ''}) `{chave}`: {r['texto']}")
            linhas += [f"  - prova: {p}" for p in r["provas"][-2:]]
        linhas.append("")
    p = pasta_jeito() / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes("\n".join(linhas).encode("utf-8"))
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="acao", required=True)
    g = sub.add_parser("guardar")
    g.add_argument("edit", type=Path)
    df = sub.add_parser("diferenca")
    df.add_argument("edit", type=Path)
    df.add_argument("--json", action="store_true")
    rg = sub.add_parser("regra")
    rg.add_argument("assunto", choices=ASSUNTOS)
    rg.add_argument("chave")
    rg.add_argument("--texto")
    rg.add_argument("--prova", required=True)
    rg.add_argument("--video", required=True)
    sub.add_parser("regras")
    es = sub.add_parser("esquecer")
    es.add_argument("chave")
    a = ap.parse_args()
    if a.acao == "guardar":
        print(f"entrega {guardar(a.edit)} guardada")
    elif a.acao == "diferenca":
        mud = diferenca(a.edit)
        print(json.dumps(mud, ensure_ascii=False, indent=2) if a.json else (texto_diferenca(mud) or "nada mudou à mão"))
    elif a.acao == "regra":
        try:
            r = regra(a.assunto, a.chave, a.texto, a.prova, a.video)
        except ValueError as e:
            print(f"ERRO {e}", file=sys.stderr)
            return 1
        print(f"{a.chave}: {len(r['videos'])} vídeo(s) — {r['texto']}")
    elif a.acao == "regras":
        p = pasta_jeito() / "SKILL.md"
        print(p.read_text(encoding="utf-8") if p.is_file() else "ainda sem regras: nada aprendido")
    elif a.acao == "esquecer":
        print("esquecida" if esquecer(a.chave) else "não existe essa regra")
    return 0


if __name__ == "__main__":
    sys.exit(main())
