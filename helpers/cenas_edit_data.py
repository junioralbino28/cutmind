#!/usr/bin/env python3
"""Prepara para o render os efeitos que tiram a pessoa do fundo (`cenas[]` do edit-data.json).

Para cada efeito, em cada rodada:
1. confere os campos (cenas.validar); com qualquer erro, nada é gravado;
2. faz o recorte da pessoa na janela dele (person_matte.py →
   `public/cena-<quadro inicial>-<quadros>.mov`; a mesma janela usa o mesmo arquivo);
3. mede a pessoa no recorte (cenas.medir_pessoa, guardado em `public/cenas/medidas.json`);
4. calcula o lugar padrão de cada coisa (`layout`), com o `zoom` do efeito;
5. copia para `public/cenas/` os fundos prontos e as imagens do projeto, com nomes sem espaço nem
   acento; a Parede sem `fotos` ganha quadros do próprio corte, num recorte quadrado em volta do rosto;
6. grava `matte`, `pessoa` e `layout` no item.

Rodar de novo não refaz o recorte nem a medida de uma janela que não mudou. Os recortes
(`cena-*.mov`) e as cópias de `public/cenas/` que não servem mais são apagados; os `pessoa-*.mov`
são do camadas_edit_data.py e ficam. Um efeito desligado no editor guarda o recorte que tem, mas
não ganha um novo. Um efeito sem recorte fica fora do vídeo até o recorte existir.

    python cenas_edit_data.py <edit> [--edit-data <caminho do edit-data.json>] [--sem-recorte]

Sem --edit-data, usa o `editData` do state.json. Com --sem-recorte, só avisa o comando do recorte.
Sem o extra de recorte (torch + torchvision), sai com exit 1 e diz como instalar. Depois,
renderize (ou refaça só as janelas dos efeitos).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cenas  # mesma pasta deste arquivo
from camadas_edit_data import _cmd_recorte, _linha, _rodar, edit_data_do_projeto

RECORTE = "cena-"
PASTA = "cenas"  # em public/
MEDIDAS = "medidas.json"  # em public/cenas/
KIT = Path(__file__).resolve().parents[1]
FUNDOS_DIR = KIT / "assets" / "preview" / "fundos"
FOTO_PX = 448  # o quadrado de cada foto da Parede: o cartão mostra 222 px, o dobro fica nítido


def _tem_recorte() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("torch", "torchvision"))


def _janela(c: dict, fps: float) -> tuple[str, int, int]:
    """O recorte do efeito, com a janela em quadros no nome: mudou a janela, o velho sai."""
    q0 = round(c["start"] * fps)
    n = max(1, round(c["end"] * fps) - q0)
    return f"{RECORTE}{q0}-{n}.mov", q0, n


def _copia(origem: Path, destino: Path) -> None:
    """Copia só quando mudou (tamanho ou data)."""
    if destino.is_file():
        a, b = origem.stat(), destino.stat()
        if a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime):
            return
    shutil.copy2(origem, destino)


def _nome(prefixo: str, rel: str) -> str:
    """O nome da cópia de `midia/<arquivo>`: sem espaço nem acento, o mesmo para o mesmo arquivo."""
    return f"{prefixo}-{hashlib.sha1(rel.encode('utf-8')).hexdigest()[:10]}{Path(rel).suffix.lower()}"


class _Medidas:
    """A pessoa medida em cada recorte, guardada com o tamanho e a data do arquivo: um recorte
    refeito com o mesmo nome é medido de novo."""

    def __init__(self, pasta: Path):
        self.arq = pasta / MEDIDAS
        try:
            self.dados = json.loads(self.arq.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.dados = {}
        self.medidos: list[str] = []

    def de(self, matte: Path) -> dict:
        st = matte.stat()
        marca = [st.st_size, st.st_mtime_ns]
        d = self.dados.get(matte.name)
        if not d or d.get("marca") != marca:
            d = self.dados[matte.name] = {"marca": marca, "pessoa": cenas.medir_pessoa(matte)}
            self.medidos.append(matte.name)
        return d["pessoa"]

    def gravar(self, validos: set[str]) -> None:
        self.dados = {k: v for k, v in self.dados.items() if k in validos}
        self.arq.write_text(json.dumps(self.dados, ensure_ascii=False), encoding="utf-8")


def _sonda(cut: Path) -> tuple[float, int, int] | None:
    """Duração, largura e altura do corte; None se não deu para ler."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", str(cut)], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        return float(j["format"]["duration"]), int(j["streams"][0]["width"]), int(j["streams"][0]["height"])
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def _tempos(dur: float, ini: float, fim: float, n: int) -> list[float]:
    """n instantes espalhados pelo corte, fora da janela do efeito (com 0,1 s de folga) e a meio
    segundo das pontas."""
    trechos = [(a, b) for a, b in ((0.5, ini - 0.1), (fim + 0.1, dur - 0.5)) if b - a > 0.2] or [(0.0, dur)]
    total, out = sum(b - a for a, b in trechos), []
    for k in range(n):
        s = (k + 0.5) / n * total
        for a, b in trechos:
            if s <= b - a:
                out.append(round(a + s, 3))
                break
            s -= b - a
    return out


def _rosto(public: Path, t: float) -> tuple[float, float]:
    """O ponto dos olhos no instante t, de 0 a 1 (track.json, o rastreio da câmera); sem rastreio,
    o meio do terço de cima."""
    try:
        r = json.loads((public / "track.json").read_text(encoding="utf-8"))
        pts = r["points"]
        i = min(len(pts) - 1, max(0, round(t * float(r.get("fps") or 30))))
        return float(pts[i][0]), float(pts[i][1])
    except (FileNotFoundError, ValueError, KeyError, IndexError, TypeError):
        return 0.5, 0.4


def _quadros(public: Path, pasta: Path, c: dict, usados: set[str]) -> list[dict]:
    """As fotos da Parede sem `fotos`: quadros do próprio corte, cada um num quadrado em volta do rosto."""
    cut = public / "cut.mp4"
    info = _sonda(cut) if cut.is_file() else None
    if not info:
        return []
    dur, wv, hv = info
    lado = min(wv, hv, 2 * round(wv / 4))  # metade da largura, par
    fotos = []
    for t in _tempos(dur, c["start"], c["end"], cenas.PAREDE_FOTOS):
        nome = f"quadro-{round(t * 1000)}.jpg"
        alvo = pasta / nome
        if not alvo.is_file() or alvo.stat().st_mtime < cut.stat().st_mtime:
            fx, fy = _rosto(public, t)
            x = min(wv - lado, max(0, round(fx * wv - lado / 2)))
            y = min(hv - lado, max(0, round(fy * hv - lado * 0.45)))
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{t:.3f}", "-i", str(cut), "-frames:v", "1",
                            "-vf", f"crop={lado}:{lado}:{x}:{y},scale={FOTO_PX}:{FOTO_PX}", "-q:v", "3", str(alvo)])
        if alvo.is_file():
            usados.add(nome)
            fotos.append({"src": f"{PASTA}/{nome}"})
    return fotos


def _arquivos(edit: Path, public: Path, pasta: Path, c: dict, usados: set[str], faltando: list[str]) -> dict:
    """O que o template carrega de public/: o fundo (Fundo, Mural e Parede) e as fotos (Parede)."""
    out: dict = {}
    v = (c.get("fundo") if c["tipo"] in ("fundo", "mural", "parede") else None) or cenas.FUNDO_PADRAO.get(c["tipo"])
    if v:
        pronto = cenas.fundo_pronto(v)
        origem = FUNDOS_DIR / f"{pronto}.jpg" if pronto else edit / v
        nome = f"fundo-{pronto}.jpg" if pronto else _nome("fundo", v)
        if origem.is_file():
            _copia(origem, pasta / nome)
            usados.add(nome)
            out["fundo"] = f"{PASTA}/{nome}"
        else:
            faltando.append(f"{v} (o kit não tem assets/preview/fundos/{origem.name})" if pronto else v)
    if c["tipo"] == "parede":
        if c.get("fotos"):
            fotos = []
            for f in c["fotos"]:
                origem = edit / f["src"]
                if not origem.is_file():
                    faltando.append(f["src"])
                    continue
                nome = _nome("parede", f["src"])
                _copia(origem, pasta / nome)
                usados.add(nome)
                fotos.append({"src": f"{PASTA}/{nome}", **({"legenda": f["legenda"]} if f.get("legenda") else {})})
        else:
            fotos = _quadros(public, pasta, c, usados)
        out["fotos"] = fotos
    return out


def aplicar(edit: Path, edit_data: Path | None = None, recortar: bool = True) -> dict:
    edit = Path(edit)
    ed_p = Path(edit_data) if edit_data else edit_data_do_projeto(edit)
    d = json.loads(ed_p.read_text(encoding="utf-8"))
    lista = d.get("cenas") or []
    r = {"cenas": len(lista), "prontos": 0, "feitos": [], "medidos": [], "pendentes": [], "faltando": [],
         "avisos": [], "sem_extra": False,
         "erros": [f"cenas[{i}] ({c.get('tipo') if isinstance(c, dict) else '?'}): {m}"
                   for i, c in enumerate(lista) for m in cenas.validar(c)]}
    if r["erros"]:
        return r
    public = ed_p.parent
    pasta = public / PASTA
    pasta.mkdir(exist_ok=True)
    fps = float(d.get("fps") or 30)
    cut = public / "cut.mp4"
    janelas = [_janela(c, fps) for c in lista]
    validos = {j[0] for j in janelas}  # o desligado também guarda o seu
    for velho in public.glob(f"{RECORTE}*.mov"):  # só os recortes que este helper fez
        if velho.name not in validos:
            velho.unlink()
    extra = _tem_recorte()
    medidas, usados = _Medidas(pasta), set()
    for i, (c, (nome, q0, n)) in enumerate(zip(lista, janelas)):
        alvo = public / nome
        if not alvo.is_file() and not c.get("desligada"):
            cmd = _cmd_recorte(cut, alvo, q0, n, fps)
            if recortar and extra and cut.is_file() and _rodar(cmd) and alvo.is_file():
                r["feitos"].append(nome)
            else:
                r["pendentes"].append(_linha(cmd))
                r["sem_extra"] = r["sem_extra"] or not extra
        for k in ("matte", "pessoa", "layout"):  # são deste helper: refeitos a cada rodada
            c.pop(k, None)
        if not alvo.is_file():
            continue
        bruto = medidas.de(alvo)
        presenca = bruto.get("presenca", 0)
        if presenca < cenas.PRESENCA_MINIMA:
            r["avisos"].append(f"cenas[{i}] ({c['tipo']}): a pessoa aparece em {presenca:.0%} da janela; "
                               "escolha uma tomada em que ela fique no quadro" + ("" if presenca else " (efeito fora do vídeo)"))
            if not presenca:
                continue
        p = cenas.com_zoom(bruto, c.get("zoom"))
        c["matte"], c["pessoa"] = nome, cenas.resumo(p)
        c["layout"] = {**cenas.layout(c["tipo"], p, c), **_arquivos(edit, public, pasta, c, usados, r["faltando"])}
        r["prontos"] += 0 if c.get("desligada") else 1
        for k in ("esquerda", "direita") if c["tipo"] == "capa" else ():
            if c.get(k) and not c["layout"]["colunas"][k]:
                r["avisos"].append(f"cenas[{i}] ({c['tipo']}): as chamadas `{k}` não cabem fora da pessoa nesta tomada e "
                                   "ficam fora do vídeo; use um lado só ou outra tomada")
    medidas.gravar(validos)
    for velho in pasta.iterdir():  # a pasta é toda deste helper
        if velho.is_file() and velho.name != MEDIDAS and velho.name not in usados:
            velho.unlink()
    tmp = ed_p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ed_p)
    r["medidos"] = medidas.medidos
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--edit-data", type=Path)
    ap.add_argument("--sem-recorte", action="store_true", help="não roda o recorte da pessoa; só avisa o comando")
    a = ap.parse_args()
    r = aplicar(a.edit.resolve(), a.edit_data, recortar=not a.sem_recorte)
    if r["erros"]:
        for e in r["erros"]:
            print(f"  ERRO {e}", file=sys.stderr)
        print("nada foi gravado: corrija o cenas[] do edit-data.json e rode de novo", file=sys.stderr)
        return 1
    print(f"{r['cenas']} efeito(s) no edit-data.json, {r['prontos']} pronto(s) para o render")
    for f in r["feitos"]:
        print(f"  feito: {f}")
    for f in r["medidos"]:
        print(f"  medido: {f}")
    for w in r["avisos"]:
        print(f"  AVISO {w}", file=sys.stderr)
    for f in r["faltando"]:
        print(f"  FALTA {f}", file=sys.stderr)
    if r["sem_extra"]:
        print(f"  FALTA o extra de recorte (torch + torchvision): na pasta do kit ({KIT}), rode `uv sync --extra matting`",
              file=sys.stderr)
    for c in r["pendentes"]:
        print(f"  FALTA rodar (até lá, esse efeito fica fora do vídeo): {c}", file=sys.stderr)
    return 1 if r["faltando"] or r["pendentes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
