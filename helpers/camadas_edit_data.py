#!/usr/bin/env python3
"""Leva as camadas do editor (camadas.json) para o edit-data.json da Fase 2.

Imagens: cada imagem visível vira um item de `inserts[]` — o cartão arredondado da zona de
cima, o mesmo dos inserts do agente — com `"camada": <id do item>`. A imagem que a pessoa moveu ou
redimensionou no editor (livre, com `largura`) leva `x`, `y` e `w` (px do quadro): o Main.tsx a desenha
inteira, nesse lugar e nesse tamanho; um template de kit anterior não sabe, e o helper para. Só esses são mexidos: os
inserts do agente ficam como estão, e as camadas entram por último (ficam por cima, como no
editor). A imagem com `atras` vira um item de `behind[]` (o cartão grande atrás da pessoa),
com o recorte da janela dela. O arquivo é copiado para `public/midia/camada-<id>.<ext>`, um
nome sem espaço nem acento para o `staticFile` do Remotion.

Textos: cada texto visível vira um item de `textos[]` (src/CamadasTexto.tsx desenha), na
ordem das faixas. A lista inteira é deste helper. Um texto "atrás da pessoa" precisa do
recorte dela na janela dele, `public/pessoa-<id>-<quadro inicial>-<quadros>.mov`
(person_matte.py); um texto que "acompanha", e a legenda com `captions.acompanhar`, precisam
do rosto rastreado no corte, `public/rastreio.json` (face_track.py). O helper faz os dois
quando faltam ou ficaram velhos
(mudou a janela, mudou o cut.mp4) e apaga os recortes que não servem mais. Com
--sem-recorte, só avisa o comando, e o texto sai na frente até o recorte existir.

Rodar de novo refaz do zero: o que a pessoa excluiu ou escondeu sai do edit-data e a
cópia antiga é apagada.

    python camadas_edit_data.py <edit> [--edit-data <caminho do edit-data.json>] [--sem-recorte]

Sem --edit-data, usa o `editData` do state.json. Depois, renderize de novo.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import camadas as cam  # mesma pasta deste arquivo

PREFIXO = "camada-"
RECORTE = "pessoa-"
RASTREIO = "rastreio.json"
HELPERS = Path(__file__).resolve().parent


MARCA_LIVRE = "INSERT_LIVRE"  # no src/Main.tsx do template que desenha a imagem livre
MARCA_RECORTE = "INSERT_RECORTE"  # ... e que desenha só o pedaço recortado dela
MARCA_VIDEO = "INSERT_VIDEO"  # ... e que desenha o vídeo posto por cima


class TemplateVelho(RuntimeError):
    """O template do projeto não desenha o que a camada pede."""


def template_sem_imagem_livre(ed_p: Path) -> bool:
    """O projeto (<remotion>/src/Main.tsx ao lado do public/ do edit-data) é de um kit que não desenha a
    imagem livre: ela sairia no cartão de cima, sem erro nenhum. Sem Main.tsx (edit-data avulso), não há o
    que conferir."""
    return template_sem(ed_p, MARCA_LIVRE)


def template_sem(ed_p: Path, marca: str) -> bool:
    """O src/Main.tsx do projeto não tem a marca de um recurso (MARCA_LIVRE, MARCA_RECORTE)."""
    main = Path(ed_p).parent.parent / "src" / "Main.tsx"
    return main.is_file() and marca not in main.read_text(encoding="utf-8")


def edit_data_do_projeto(edit: Path) -> Path:
    state = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    if not state.get("editData"):
        raise SystemExit("state.json sem editData: passe --edit-data")
    return edit / state["editData"]


def _rodar(cmd: list[str]) -> bool:
    """Roda um helper do kit com o mesmo Python; a saída dele passa direto."""
    return subprocess.run(cmd).returncode == 0


def _linha(cmd: list[str]) -> str:
    """O comando para colar no terminal, com aspas onde o caminho tem espaço."""
    return " ".join(f'"{c}"' if " " in c else c for c in cmd)


def _cmd_recorte(cut: Path, saida: Path, ini_f: int, n_f: int, fps: float) -> list[str]:
    # em quadros, para o quadro 0 do recorte cair no quadro em que o texto entra
    return [sys.executable, "-X", "utf8", str(HELPERS / "person_matte.py"), str(cut), "-o", str(saida),
            "--start", f"{ini_f / fps:.6f}", "--duration", f"{n_f / fps:.6f}"]


def _rastreio_serve(arq: Path, cut: Path) -> bool:
    try:
        r = json.loads(arq.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return False
    if r.get("neutral") or not r.get("points"):
        return False
    return not cut.is_file() or arq.stat().st_mtime >= cut.stat().st_mtime


class _Recortes:
    """Os recortes da pessoa que valem agora, por id do item (texto ou imagem com `atras`; um
    escondido guarda o seu), com a janela em quadros no nome: mudou a janela, o velho sai."""

    def __init__(self, public: Path, camadas: dict, fps: float, recortar: bool):
        self.public, self.fps, self.recortar = public, fps, recortar
        self.cut = public / "cut.mp4"
        self.validos: dict[str, tuple[str, int, int]] = {}
        for f in camadas["faixas"]:
            for it in f["itens"]:
                if f["tipo"] in ("texto", "imagem") and it.get("atras"):
                    ini_f = round(it["inicio"] * fps)
                    n_f = max(1, round((it["inicio"] + it["duracao"]) * fps) - ini_f)
                    self.validos[it["id"]] = (f"{RECORTE}{it['id']}-{ini_f}-{n_f}.mov", ini_f, n_f)
        nomes = {v[0] for v in self.validos.values()}
        for velho in public.glob(f"{RECORTE}*.mov"):  # só os recortes que este helper fez
            if velho.name not in nomes:
                velho.unlink()
        self.feitos: list[str] = []
        self.pendentes: list[str] = []

    def de(self, iid: str) -> str | None:
        """O recorte do item, feito agora se faltava; None se ficou por fazer."""
        nome, ini_f, n_f = self.validos[iid]
        if not (self.public / nome).is_file():
            cmd = _cmd_recorte(self.cut, self.public / nome, ini_f, n_f, self.fps)
            if self.recortar and self.cut.is_file() and _rodar(cmd) and (self.public / nome).is_file():
                self.feitos.append(nome)
            else:
                self.pendentes.append(_linha(cmd))
        return nome if (self.public / nome).is_file() else None

    def janela(self, iid: str) -> tuple[float, float]:
        """Começo e duração do recorte em segundos, no quadro exato dele."""
        _, ini_f, n_f = self.validos[iid]
        return round(ini_f / self.fps, 6), round(n_f / self.fps, 6)


def _textos(public: Path, d: dict, camadas: dict, rec: _Recortes) -> list:
    """Os textos do edit-data; o rastreio do rosto quando um texto ou a legenda acompanham."""
    cut = public / "cut.mp4"
    textos = []
    for it in cam.textos(camadas):
        t = {"id": it["id"], "texto": it["texto"], "start": it["inicio"],
             "end": round(it["inicio"] + it["duracao"], 3), "x": it["x"], "y": it["y"]}
        if it["estilo"]:
            t["estilo"] = it["estilo"]
        if it["curva"]:
            t["curva"] = it["curva"]
        if it["acompanhar"]:
            t["acompanhar"] = True
        if it["atras"]:
            matte = rec.de(it["id"])
            if matte:
                t["matte"] = matte
        textos.append(t)

    rastreio = public / RASTREIO
    # o rosto serve aos textos que acompanham e à legenda que acompanha (`captions.acompanhar`)
    segue = any(t.get("acompanhar") for t in textos) or bool((d.get("captions") or {}).get("acompanhar"))
    if segue and not _rastreio_serve(rastreio, cut):
        cmd = [sys.executable, "-X", "utf8", str(HELPERS / "face_track.py"), str(cut), "-o", str(rastreio)]
        if rec.recortar and cut.is_file() and _rodar(cmd) and _rastreio_serve(rastreio, cut):
            rec.feitos.append(RASTREIO)
        else:
            rec.pendentes.append(_linha(cmd))
    if not rastreio.is_file():  # o template importa o arquivo: sem rastreio, ele fica neutro
        rastreio.write_text(json.dumps({"neutral": True, "points": []}), encoding="utf-8")
    return textos


def aplicar(edit: Path, edit_data: Path | None = None, recortar: bool = True) -> dict:
    edit = Path(edit)
    ed_p = Path(edit_data) if edit_data else edit_data_do_projeto(edit)
    d = json.loads(ed_p.read_text(encoding="utf-8"))
    camadas = cam.load(edit / "camadas.json")
    destino = ed_p.parent / cam.MIDIA_DIR
    destino.mkdir(exist_ok=True)
    for velho in destino.glob(f"{PREFIXO}*"):  # só as cópias que este helper fez
        velho.unlink()
    rec = _Recortes(ed_p.parent, camadas, float(d.get("fps") or 30), recortar)
    inserts = [i for i in d.get("inserts") or [] if "camada" not in i]
    behind = [b for b in d.get("behind") or [] if "camada" not in b]
    faltando = []
    for it in cam.aparecem(camadas):
        origem = edit / it["arquivo"]
        if not origem.is_file():
            faltando.append(it["arquivo"])
            continue
        nome = f"{PREFIXO}{it['id']}{origem.suffix.lower()}"
        shutil.copy2(origem, destino / nome)
        src = f"{cam.MIDIA_DIR}/{nome}"
        matte = rec.de(it["id"]) if it.get("atras") else None
        if matte:  # o cartão grande atrás da pessoa (BehindSubject), no quadro exato do recorte
            start, dur = rec.janela(it["id"])
            behind.append({"kind": "image", "src": src, "matte": matte, "start": start, "dur": dur, "camada": it["id"]})
        else:  # o cartão de cima (ou a imagem livre); com o recorte por fazer, também (e o comando fica avisado)
            ins = {"src": src, "start": it["inicio"], "end": round(it["inicio"] + it["duracao"], 3), "camada": it["id"]}
            if "largura" in it and not it.get("atras"):
                ins.update({"x": it["x"], "y": it["y"], "w": it["largura"]})
                if it.get("recorte"):  # só o pedaço: o Main.tsx recorta, a largura é a do pedaço
                    ins["crop"] = {k: it["recorte"][k] for k in ("x", "y", "w", "h")}
            if cam.eh_video(it["arquivo"]):  # o vídeo por cima: mudo no Remotion (o som vai no mixar_final)
                ins.update({"video": True, "from": it.get("corte", 0.0)})
            inserts.append(ins)
    if any("w" in i for i in inserts) and template_sem_imagem_livre(ed_p):
        raise TemplateVelho(f"o template deste projeto é de um kit anterior e não desenha a imagem no lugar e no "
                            f"tamanho que você pôs: rode `atualizar_template.py {edit}` e depois este de novo")
    if any(i.get("video") for i in inserts) and template_sem(ed_p, MARCA_VIDEO):
        raise TemplateVelho(f"o template deste projeto é de um kit anterior e não desenha vídeo por cima: rode "
                            f"`atualizar_template.py {edit}` e depois este de novo")
    if any("crop" in i for i in inserts) and template_sem(ed_p, MARCA_RECORTE):
        raise TemplateVelho(f"o template deste projeto é de um kit anterior e não recorta a imagem: rode "
                            f"`atualizar_template.py {edit}` e depois este de novo")
    d["inserts"] = inserts
    if behind or "behind" in d:
        d["behind"] = behind
    textos = _textos(ed_p.parent, d, camadas, rec)
    if textos or "textos" in d:
        d["textos"] = textos
    tmp = ed_p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ed_p)
    return {"inserts": sum(1 for i in inserts if "camada" in i) + sum(1 for b in behind if "camada" in b),
            "textos": len(textos), "faltando": faltando, "pendentes": rec.pendentes, "feitos": rec.feitos}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--edit-data", type=Path)
    ap.add_argument("--sem-recorte", action="store_true",
                    help="não roda o recorte da pessoa nem o rastreio do rosto; só avisa o comando")
    a = ap.parse_args()
    try:
        r = aplicar(a.edit.resolve(), a.edit_data, recortar=not a.sem_recorte)
    except TemplateVelho as e:
        print(f"  ERRO {e}", file=sys.stderr)
        return 1
    print(f"{r['inserts']} imagem(ns) e {r['textos']} texto(s) de camada no edit-data.json")
    for f in r["feitos"]:
        print(f"  feito: {f}")
    for f in r["faltando"]:
        print(f"  FALTA {f} — o arquivo não está em midia/; a camada ficou fora", file=sys.stderr)
    for c in r["pendentes"]:
        print(f"  FALTA rodar (até lá, o que vai atrás da pessoa sai na frente, e o que acompanha fica parado): {c}",
              file=sys.stderr)
    return 1 if r["faltando"] or r["pendentes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
