#!/usr/bin/env python3
"""Monta (ou atualiza) o projeto do Remotion da Fase 2 em <edit>/remotion pelo mesmo caminho do editor.

Copia o modelo de Reels (`assets/shortform`), roda o `npm install`, confere que o Remotion carrega (instala de
novo, do zero, quando a instalação saiu quebrada) e abre o navegador dele uma vez. Tudo com a trava de um por
vez (`montagem.trava_remotion`): o "Gerar e baixar" do editor usa o mesmo caminho, e os dois instalando juntos
quebram o `node_modules` sem erro nenhum (teste de 28/10).

- Projeto que não existe: monta do zero.
- Projeto que o "Gerar e baixar" montou (`public/edit-data.json` com `"_gerar": "editor"`): não é Fase 2; os
  dados do modelo voltam para `public/`, como o `cp -R` fazia.
- Projeto com a Fase 2 do agente: só o código imutável acompanha o kit (`atualizar_template.py`); `public/` e o
  `CustomGraphics.tsx` ficam como estão.

    uv run python -X utf8 helpers/preparar_remotion.py <edit>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import montagem as mt  # mesma pasta deste arquivo


def do_editor(rem: Path) -> bool:
    """O public/ é o do "Gerar e baixar" (ou não há dados): pode ser trocado pelo do modelo."""
    try:
        ed = json.loads((rem / "public" / "edit-data.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        return False  # ilegível: na dúvida, não apaga nada do agente
    return isinstance(ed, dict) and ed.get("_gerar") == "editor"


def preparar(edit: Path) -> Path:
    edit = Path(edit).resolve()
    rem = edit / "remotion"
    novo = not (rem / "package.json").is_file()
    era_do_editor = not novo and do_editor(rem)
    rem = mt.projeto_remotion(edit)
    if era_do_editor:
        shutil.copytree(mt.TEMPLATE / "public", rem / "public", dirs_exist_ok=True)
        print("o projeto era do \"Gerar e baixar\" (sem Fase 2): os dados do modelo voltaram para public/", flush=True)
    return rem


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    a = ap.parse_args()
    try:
        rem = preparar(a.edit)
    except mt.ErroMontagem as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    print(f"projeto do Remotion pronto: {rem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
