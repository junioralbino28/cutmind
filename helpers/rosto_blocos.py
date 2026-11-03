#!/usr/bin/env python3
"""O rosto de cada bloco: a tela dividida e o punch-in enquadrados pelo rosto medido naquele trecho.

Num Reels editado com o kit (edição real de 01/11), a altura do rosto mudava entre os cortes e o enquadramento
fixo da tela dividida cortava a testa num bloco e deixava sobra no outro; a cabeça cortada reta na divisão também
incomodava, e o punch-in precisava sair da gravação para continuar nítido. Tudo por dado do `edit-data.json`:

- `splitInserts[]` com `focusAuto: true`: grava `focusY` pelo rosto medido no trecho do bloco, com os olhos sempre na
  mesma altura da tela (o `zoom` do bloco, ou 1, entra na conta). Sem a marca, o bloco fica como está.
- `splitInserts[]` com `cabeca: true` (layout `top`): grava `matte` e `matteIni`, o recorte da pessoa, para a cabeça
  passar por cima da faixa e parar na divisão. Blocos colados dividem um recorte só (fg_split_<quadro>_<quadros>.mov).
  Com `focusAuto`, quem manda é o topo da cabeça medido no recorte (`matteTopo`): o cabelo passa sempre CABECA_PASSA px
  da divisão, com o rosto grande ou pequeno; os olhos numa altura fixa deixavam o rosto menor só encostando nela.
- `punchins[]`: grava `x` e `y`, o rosto medido no trecho, o ponto que fica parado no zoom. Com `fixo: true`, ficam
  os que o item já tem.

O rosto sai do track.json quando ele é de verdade e mais novo que o corte; senão, de verify/rosto.json (face_track.py).
Rodar de novo só refaz o que mudou. O gerar.py chama sozinho antes de cada render.

    uv run python -X utf8 helpers/rosto_blocos.py <edit>
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

import cenas  # mesma pasta deste arquivo
from camadas_edit_data import _cmd_recorte, edit_data_do_projeto

AQUI = Path(__file__).resolve().parent
W, H = 1080, 1920
BANDA = 750  # a faixa padrão da tela dividida (bandH em src/CustomGraphics.tsx)
OLHOS_ABAIXO_DA_DIVISAO = 370  # layout top: o cabelo passa ~200 px da divisão e a boca fica acima de y 1560
OLHOS_NA_JANELA = 0.42  # layout bottom: a altura dos olhos na janela do vídeo
CABECA_PASSA = 150  # layout top com recorte: quanto o cabelo passa da divisão
PREFIXO = "fg_split_"


class BlocosErro(RuntimeError):
    pass


def foco(olhos_y: float, layout: str, banda: float, zoom: float) -> int:
    """O `focusY` que põe os olhos na altura certa, sem deixar vão na janela do vídeo: um ponto y da fonte aparece em
    (y − focusY) · zoom a partir do topo da janela (CustomGraphics.tsx, SplitFrame)."""
    janela = H - banda
    alvo = OLHOS_ABAIXO_DA_DIVISAO if layout == "top" else OLHOS_NA_JANELA * janela
    return round(max(0.0, min(olhos_y - alvo / zoom, H - janela / zoom)))


def foco_da_cabeca(topo: float, banda: float, zoom: float) -> int:
    """O `focusY` que põe o topo da cabeça CABECA_PASSA px acima da divisão, sem deixar vão na janela do vídeo."""
    return round(max(0.0, min(topo + CABECA_PASSA / zoom, H - (H - banda) / zoom)))


def _rosto(edit: Path, public: Path) -> dict:
    cut = public / "cut.mp4"
    track = public / "track.json"
    try:
        t = json.loads(track.read_text(encoding="utf-8"))
        if t.get("points") and not t.get("neutral") and track.stat().st_mtime >= cut.stat().st_mtime:
            return t
    except (OSError, ValueError):
        pass
    arq = edit / "verify" / "rosto.json"
    if not arq.is_file() or arq.stat().st_mtime < cut.stat().st_mtime:
        arq.parent.mkdir(exist_ok=True)
        if subprocess.run([sys.executable, "-X", "utf8", str(AQUI / "face_track.py"), str(cut), "-o", str(arq)]).returncode != 0:
            raise BlocosErro("o rosto não foi medido (a saída do face_track.py está acima)")
    return json.loads(arq.read_text(encoding="utf-8"))


def rosto_no_trecho(rosto: dict, ini: float, fim: float) -> tuple[float, float] | None:
    """A mediana do rosto (x, y em px do quadro) entre dois segundos do corte."""
    fps = float(rosto.get("fps") or 30)
    pts = rosto.get("points") or []
    a, b = max(0, round(ini * fps)), round(fim * fps)
    trecho = pts[a:max(b, a + 1)]
    if not trecho:
        return None
    return statistics.median(p[0] for p in trecho) * W, statistics.median(p[1] for p in trecho) * H


def _grupos(itens: list[dict], fps: float) -> list[list[dict]]:
    """Os blocos com `cabeca` colados um no outro: dividem um recorte só."""
    grupos: list[list[dict]] = []
    for b in sorted((x for x in itens if x.get("cabeca") and (x.get("layout") or "top") == "top"), key=lambda x: float(x["start"])):
        if grupos and round(float(b["start"]) * fps) == round(float(grupos[-1][-1]["end"]) * fps):
            grupos[-1].append(b)
        else:
            grupos.append([b])
    return grupos


def template_velho(remotion: Path, ed: dict) -> list[str]:
    """O que o template do projeto não sabe desenhar destes campos (vazio = desenha)."""
    src = Path(remotion) / "src"
    ler = lambda n: (src / n).read_text(encoding="utf-8") if (src / n).is_file() else ""  # noqa: E731
    falta = []
    if ed.get("punchins") and "punchins" not in ler("Main.tsx"):
        falta.append("src/Main.tsx")
    if any(b.get("focusAuto") or b.get("cabeca") for b in ed.get("splitInserts") or []) and "matteIni" not in ler("CustomGraphics.tsx"):
        falta.append("src/CustomGraphics.tsx")
    return falta


def aplicar(edit: Path, recortar: bool = True) -> dict:
    edit = Path(edit)
    ed_p = edit_data_do_projeto(edit)
    public = ed_p.parent
    d = json.loads(ed_p.read_text(encoding="utf-8"))
    fps = float(d.get("fps") or 30)
    blocos, punchs = d.get("splitInserts") or [], d.get("punchins") or []
    r = {"focos": 0, "punchs": 0, "recortes": [], "pendentes": [], "template": []}
    medir = [b for b in blocos if b.get("focusAuto")] + [p for p in punchs if not p.get("fixo")]
    usados: set[str] = set()
    if not medir and not any(b.get("cabeca") for b in blocos):
        return r
    r["template"] = template_velho(ed_p.parent.parent, d)
    if r["template"]:
        return r
    antes = json.dumps(d, sort_keys=True)
    rosto = _rosto(edit, public) if medir else {}
    for b in blocos:
        if b.get("focusAuto"):
            m = rosto_no_trecho(rosto, float(b["start"]), float(b["end"]))
            if m:
                b["focusY"] = foco(m[1], b.get("layout") or "top", float(b.get("bandH") or BANDA), float(b.get("zoom") or 1))
                b.setdefault("zoom", 1.0)
                r["focos"] += 1
    for p in punchs:
        if not p.get("fixo"):
            m = rosto_no_trecho(rosto, float(p["start"]), float(p["end"]))
            if m:
                p["x"], p["y"] = round(m[0]), round(m[1])
                r["punchs"] += 1
    for g in _grupos(blocos, fps):
        ini = round(float(g[0]["start"]) * fps)
        n = max(1, round(float(g[-1]["end"]) * fps) - ini)
        nome = f"{PREFIXO}{ini}_{n}.mov"
        usados.add(nome)
        alvo = public / nome
        if not alvo.is_file():
            tmp = alvo.with_name(alvo.stem + ".refazendo.mov")
            cmd = _cmd_recorte(public / "cut.mp4", tmp, ini, n, fps)
            if not recortar:
                r["pendentes"].append(nome)
                continue
            if subprocess.run(cmd).returncode != 0 or not tmp.is_file():
                tmp.unlink(missing_ok=True)
                raise BlocosErro("o recorte da pessoa da tela dividida não saiu (a saída está acima)")
            tmp.replace(alvo)
            r["recortes"].append(nome)
        topo = g[0].get("matteTopo") if g[0].get("matte") == nome and nome not in r["recortes"] else None
        if topo is None and any(b.get("focusAuto") for b in g):
            topo = cenas.medir_pessoa(alvo).get("topo")
        for b in g:
            b["matte"], b["matteIni"] = nome, ini
            if topo is not None:
                b["matteTopo"] = topo
                if b.get("focusAuto"):
                    b["focusY"] = foco_da_cabeca(topo, float(b.get("bandH") or BANDA), float(b.get("zoom") or 1))
    for velho in public.glob(f"{PREFIXO}*.mov"):  # só os que este helper fez
        if velho.name not in usados:
            velho.unlink()
    if json.dumps(d, sort_keys=True) != antes:
        tmp = ed_p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(ed_p)
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    a = ap.parse_args()
    try:
        r = aplicar(a.edit.resolve())
    except BlocosErro as e:
        print(f"ERRO {e}", file=sys.stderr)
        return 1
    if r["template"]:
        print(f"ERRO o template deste projeto é de um kit anterior ({', '.join(r['template'])}): rode "
              f"`atualizar_template.py {a.edit}`; o CustomGraphics.tsx não é trocado por ele, então leve as mudanças da "
              "tela dividida do arquivo do kit para o do projeto", file=sys.stderr)
        return 1
    print(f"{r['focos']} bloco(s) de tela dividida e {r['punchs']} punch-in(s) medidos; {len(r['recortes'])} recorte(s) feito(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
