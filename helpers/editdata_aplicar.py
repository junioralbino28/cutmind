#!/usr/bin/env python3
"""Os dados da Fase 2 que o Salvar do editor manda (`editData`), gravados no edit-data.json sem o agente.

São as regras que o SKILL.md dava ao agente a cada Salvar ("When the user saves timeline edits",
`editData`), uma por chave:

  - blocos por `ref` (o índice na lista do edit-data), com os nomes do editor: `inserts`,
    `splitInserts`, `splitVideos` e `wordAccents` com `start`/`end`; `behind` com `start`/`dur`;
    `numeros` com `at`/`end`; `hook.endSec`;
  - `cenas`: com `ref`, o que veio (`desligada`, `texto`, `textos`, `estilo` e os `campos` do Fundo)
    no item; `nova`, um Fundo novo no fim da lista (o desligado nunca chegou ao vídeo e fica de fora);
  - `destaques`: o gancho (`alvo: "hook"`) e os números (`alvo: "numero"`, `ref`), com texto, lugar e
    estilo;
  - `camera.zooms`, a lista inteira; `legenda`: `captions.estilo` e `captions.acompanhar`, e os
    pedaços arrastados no tempo (`tempos`), que andam no captions.json na hora (legenda_tempos.py).

O resto (os recortes da pessoa, o rastreio do rosto) roda no Baixar: o gerar.py passa o
cenas_edit_data.py e o camadas_edit_data.py em todo vídeo final com a Fase 2.

    uv run python -X utf8 helpers/editdata_aplicar.py <edit> --pedido <arquivo com o editData>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import legenda_tempos as lt  # mesma pasta deste arquivo
from aplicar_corte import _grava_json, anotar_feito

# o nome de cada bloco no edit-data e os campos de tempo que o editor manda dele
BLOCOS = {"inserts": ("start", "end"), "splitInserts": ("start", "end"), "splitVideos": ("start", "end"),
          "behind": ("start", "dur"), "wordAccents": ("start", "end", "text"), "numeros": ("at", "end")}
NOMES = {"inserts": "imagem", "splitInserts": "tela dividida", "splitVideos": "vídeo dividido",
         "behind": "fundo atrás da pessoa", "wordAccents": "palavra", "numeros": "número"}


def _ref(v: object, lista: list) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(lista) else None


def _num(v: object) -> float | int:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"número inválido: {v!r}")
    return v


def _valor(v: object) -> object:
    """O valor de um número na tela: "12,5" vira 12.5; o que não é número fica como veio."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    s = str(v).strip().replace(" ", "").replace(",", ".")
    try:
        x = float(s)
    except ValueError:
        return v
    return int(x) if x.is_integer() and "." not in s else x


def _posicao_e_estilo(alvo: dict, v: dict) -> None:
    """`texto` (o centro do bloco em px do quadro) e `estilo`: None volta ao do próprio efeito."""
    for k in ("texto", "estilo"):
        if k not in v:
            continue
        if v[k] is None or v[k] == {}:
            alvo.pop(k, None)
        else:
            alvo[k] = v[k]


def _cena(c: dict, v: dict) -> None:
    if "desligada" in v:
        if v["desligada"]:
            c["desligada"] = True
        else:
            c.pop("desligada", None)
    _posicao_e_estilo(c, v)
    for k, x in (v.get("textos") or {}).items():
        if k == "batidas" and isinstance(c.get("batidas"), list) and isinstance(x, list):
            for b, palavra in zip(c["batidas"], x):  # só a palavra de cada batida; o tempo é do agente
                if isinstance(b, dict):
                    b["palavra"] = palavra
        else:
            c[k] = x
    for k, x in (v.get("campos") or {}).items():  # o Fundo: a imagem, o véu e o desfoque
        c[k] = x


def aplicar(ed: dict, pedido: dict) -> tuple[list[str], list[str]]:
    """Aplica o `editData` do Salvar em `ed` (no lugar). Devolve (os helpers que o vídeo final precisa
    rodar de novo, avisos do que não deu para aplicar)."""
    depois: set[str] = set()
    avisos: list[str] = []
    for chave, campos in BLOCOS.items():
        lista = ed.get(chave) or []
        for b in pedido.get(chave) or []:
            i = _ref(b.get("ref"), lista)
            if i is None:
                avisos.append(f"{chave}: o bloco {b.get('ref')!r} não existe mais no vídeo final")
                continue
            for k in campos:
                if k in b:
                    lista[i][k] = b[k] if k == "text" else _num(b[k])
    if isinstance(pedido.get("hook"), dict) and "endSec" in pedido["hook"] and isinstance(ed.get("hook"), dict):
        ed["hook"]["endSec"] = _num(pedido["hook"]["endSec"])

    cenas = ed.setdefault("cenas", []) if pedido.get("cenas") else ed.get("cenas") or []
    for v in pedido.get("cenas") or []:
        if v.get("nova"):
            if not v.get("desligada"):  # o Fundo feito no editor e desligado nunca chegou ao vídeo
                c = {"tipo": v.get("tipo"), "start": _num(v.get("start")), "end": _num(v.get("end"))}
                _cena(c, {k: x for k, x in v.items() if k in ("texto", "textos", "estilo", "campos")})
                cenas.append(c)
                depois.add("cenas")
            continue
        i = _ref(v.get("ref"), cenas)
        if i is None:
            avisos.append(f"cenas: o efeito {v.get('ref')!r} não existe mais no vídeo final")
            continue
        _cena(cenas[i], v)
        depois.add("cenas")

    for v in pedido.get("destaques") or []:
        if v.get("alvo") == "hook" and isinstance(ed.get("hook"), dict):
            h = ed["hook"]
            _posicao_e_estilo(h, v)
            texto = (v.get("textos") or {}).get("text")
            antes = str(h["text"]) if h.get("text") is not None else " ".join(h.get("lines") or [])
            if texto is not None and texto != antes:  # o editor manda o texto junto; mudou de verdade?
                h["text"] = texto
                h.pop("lines", None)
        elif v.get("alvo") == "numero":
            nums = ed.get("numeros") or []
            i = _ref(v.get("ref"), nums)
            if i is None:
                avisos.append(f"numeros: o número {v.get('ref')!r} não existe mais no vídeo final")
                continue
            _posicao_e_estilo(nums[i], v)
            for k, x in (v.get("textos") or {}).items():
                if k in ("prefixo", "sufixo", "rotulo"):
                    nums[i][k] = x
                elif k == "valor":
                    nums[i]["valor"] = _valor(x)

    cam = pedido.get("camera")
    if isinstance(cam, dict) and isinstance(cam.get("zooms"), list):
        ed.setdefault("camera", {})["zooms"] = [_num(z) for z in cam["zooms"]]

    leg = pedido.get("legenda")
    if isinstance(leg, dict) and isinstance(ed.get("captions"), dict):
        cap = ed["captions"]
        if "estilo" in leg:
            if leg["estilo"]:
                cap["estilo"] = leg["estilo"]
            else:
                cap.pop("estilo", None)
        if "acompanhar" in leg:
            cap["acompanhar"] = bool(leg["acompanhar"])
            if cap["acompanhar"]:
                depois.add("camadas")  # o rastreio do rosto (camadas_edit_data.py)
    return sorted(depois), avisos


def _resumo(pedido: dict) -> str:
    partes = []
    for chave in BLOCOS:
        if pedido.get(chave):
            partes.append(f"{len(pedido[chave])} {NOMES[chave]}(s)")
    if pedido.get("hook"):
        partes.append("tempo do gancho")
    if pedido.get("cenas"):
        partes.append(f"{len(pedido['cenas'])} efeito(s)")
    if pedido.get("destaques"):
        partes.append(f"{len(pedido['destaques'])} texto(s) de gancho ou número")
    if pedido.get("camera"):
        partes.append("zoom")
    if pedido.get("legenda"):
        partes.append("legenda")
    return "vídeo final: " + (", ".join(partes) or "nada")


def gravar(edit: Path, pedido: dict) -> dict:
    """O `editData` do Salvar no edit-data.json do projeto (state.json `editData`) e os tempos da legenda
    no captions.json. Rápido: roda na própria requisição. Devolve {avisos, depois, legenda}."""
    edit = Path(edit)
    st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    if not st.get("editData"):
        raise ValueError("o projeto ainda não tem o vídeo final da Fase 2 (state.json sem editData)")
    ed_p = edit / st["editData"]
    ed = json.loads(ed_p.read_text(encoding="utf-8"))
    depois, avisos = aplicar(ed, pedido)
    _grava_json(ed_p, ed)
    movidos = 0
    tempos = (pedido.get("legenda") or {}).get("tempos") if isinstance(pedido.get("legenda"), dict) else None
    if tempos:
        cap_p = edit / (st.get("captions") or "remotion/public/captions.json")
        caps = json.loads(cap_p.read_text(encoding="utf-8"))
        feitos, fora = lt.aplicar(caps, tempos)
        movidos = sum(1 for f in feitos if "→" in f)
        if movidos:
            _grava_json(cap_p, caps)
        avisos += [f"legenda: {f}" for f in fora]
    anotar_feito(edit, _resumo(pedido))
    return {"avisos": avisos, "depois": depois, "legenda": movidos}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--pedido", type=Path, required=True, help="o `editData` do Salvar, em JSON")
    a = ap.parse_args()
    r = gravar(a.edit.resolve(), json.loads(a.pedido.read_text(encoding="utf-8")))
    for x in r["avisos"]:
        print(f"  AVISO {x}", file=sys.stderr)
    print(f"edit-data.json gravado; {r['legenda']} pedaço(s) da legenda no lugar novo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
