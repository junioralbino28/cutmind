#!/usr/bin/env python3
"""Troca o código de template de um projeto (`<edit>/remotion/`) pelo deste kit.

O template é imutável (SKILL.md, regra 11): o vídeo mora em `public/edit-data.json` e só o
`src/CustomGraphics.tsx` é do projeto. Um projeto montado com um kit anterior continua com o código
de quando foi montado, e o que o kit ganhou depois (os efeitos de `cenas[]`, por exemplo) não aparece
no render, sem erro nenhum. O `cenas_edit_data.py` para e manda rodar este helper.

- Copia do kit: `src/` (menos o `CustomGraphics.tsx`), `scripts/`, `package.json`,
  `remotion.config.ts` e `tsconfig.json`. Não toca em `public/` (os dados do vídeo) nem em
  `node_modules/`.
- Antes de trocar, guarda os arquivos que mudam em `<edit>/.template-anterior/<data e hora>/`.
- Recusa, sem mexer em nada, quando o projeto tem em `src/cenas/` um arquivo que o kit não tem: é
  efeito feito à mão, e o `index.tsx` do kit não o desenharia mais. `--forcar` troca assim mesmo (o
  arquivo fica, só deixa de ser usado).
- Com o `package.json` diferente, roda `npm install` na pasta (`--sem-npm`: só avisa).

    python atualizar_template.py <edit> [--simular] [--forcar] [--sem-npm]

`--simular` mostra o que mudaria e não grava nada.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets"
COPIA = ("src", "scripts", "package.json", "remotion.config.ts", "tsconfig.json")
DO_PROJETO = {"src/CustomGraphics.tsx"}  # o único código que o projeto escreve
ANTERIOR = ".template-anterior"  # em <edit>/: fora do remotion/, longe do bundle


class ErroTemplate(Exception):
    pass


def trilha(remotion: Path) -> str:
    """shortform ou longform: só o template curto tem `src/CustomGraphics.tsx`."""
    return "shortform" if (remotion / "src" / "CustomGraphics.tsx").is_file() else "longform"


def _arquivos(kit: Path) -> list[str]:
    out = []
    for nome in COPIA:
        p = kit / nome
        if p.is_file():
            out.append(nome)
        elif p.is_dir():
            out += sorted(q.relative_to(kit).as_posix() for q in p.rglob("*")
                          if q.is_file() and not any(s.startswith(".") for s in q.relative_to(kit).parts))
    return [r for r in out if r not in DO_PROJETO]


def _igual(a: Path, b: Path) -> bool:
    """O mesmo texto, com qualquer fim de linha (uma cópia por git no Windows pode ter virado CRLF)."""
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def planejar(edit: Path, assets: Path = ASSETS) -> dict:
    """O que a troca faria, sem gravar nada."""
    remotion = Path(edit) / "remotion"
    if not (remotion / "package.json").is_file() or not (remotion / "src").is_dir():
        raise ErroTemplate(f"{remotion} não é um projeto Remotion do kit (falta package.json ou src/)")
    t = trilha(remotion)
    kit = assets / t
    novos, trocados = [], []
    for rel in _arquivos(kit):
        destino = remotion / rel
        if not destino.is_file():
            novos.append(rel)
        elif not _igual(kit / rel, destino):
            trocados.append(rel)
    cenas_p = remotion / "src" / "cenas"
    a_mao = sorted(f"src/cenas/{p.name}" for p in cenas_p.glob("*")
                   if p.is_file() and not (kit / "src" / "cenas" / p.name).is_file()) if cenas_p.is_dir() else []
    return {"trilha": t, "kit": kit, "remotion": remotion, "novos": novos, "trocados": trocados, "a_mao": a_mao,
            "npm": "package.json" in novos + trocados}


def aplicar(edit: Path, forcar: bool = False, npm: bool = True, assets: Path = ASSETS, rodar=subprocess.run) -> dict:
    pl = planejar(edit, assets)
    if pl["a_mao"] and not forcar:
        raise ErroTemplate("o projeto tem efeitos feitos à mão em src/cenas/ que o kit não desenha: "
                           f"{', '.join(pl['a_mao'])}. Nada foi trocado; com --forcar, eles ficam lá sem uso")
    remotion, kit = pl["remotion"], pl["kit"]
    pl["copia"] = None
    if pl["trocados"]:
        copia = Path(edit) / ANTERIOR / time.strftime("%Y%m%d-%H%M%S")
        for rel in pl["trocados"]:
            (copia / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(remotion / rel, copia / rel)
        pl["copia"] = copia
    for rel in pl["novos"] + pl["trocados"]:
        (remotion / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(kit / rel, remotion / rel)
    pl["npm_feito"] = False
    if pl["npm"] and npm:
        exe = shutil.which("npm")
        if not exe:
            raise ErroTemplate("o package.json mudou e o npm não está no PATH: instale o Node e rode `npm install` "
                               f"em {remotion}")
        if rodar([exe, "install"], cwd=str(remotion)).returncode != 0:
            raise ErroTemplate(f"o `npm install` falhou em {remotion}; o código novo já foi copiado: rode de novo")
        pl["npm_feito"] = True
    return pl


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--simular", action="store_true", help="só mostra o que mudaria")
    ap.add_argument("--forcar", action="store_true", help="troca mesmo com efeitos feitos à mão em src/cenas/")
    ap.add_argument("--sem-npm", action="store_true", help="não roda o npm install; só avisa")
    a = ap.parse_args()
    try:
        pl = planejar(a.edit.resolve()) if a.simular else aplicar(a.edit.resolve(), a.forcar, not a.sem_npm)
    except ErroTemplate as e:
        print(f"ERRO {e}", file=sys.stderr)
        return 1
    if not pl["novos"] and not pl["trocados"]:
        print(f"o template do projeto já é o deste kit ({pl['trilha']}); nada a trocar")
        return 0
    verbo = "trocaria" if a.simular else "trocou"
    print(f"{verbo} o template ({pl['trilha']}): {len(pl['novos'])} arquivo(s) novo(s), {len(pl['trocados'])} trocado(s); "
          "o CustomGraphics.tsx e o public/ ficaram como estavam")
    for rel in pl["novos"]:
        print(f"  novo: {rel}")
    for rel in pl["trocados"]:
        print(f"  trocado: {rel}")
    if a.simular:
        if pl["a_mao"]:
            print(f"  RECUSARIA sem --forcar: efeitos feitos à mão em {', '.join(pl['a_mao'])}", file=sys.stderr)
        return 0
    if pl["copia"]:
        print(f"  os anteriores estão em {pl['copia']}")
    if pl["npm"] and not pl["npm_feito"]:
        print(f"  FALTA rodar `npm install` em {pl['remotion']} (o package.json mudou)", file=sys.stderr)
        return 1
    if pl["npm_feito"]:
        print("  npm install feito (o package.json mudou)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
