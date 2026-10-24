"""Os efeitos que tiram a pessoa do fundo falam o mesmo contrato em três lugares: o helper que
valida e prepara (`helpers/cenas.py`), o template que desenha (`src/cenas/index.tsx`) e o editor
que mostra e ajusta (`CENA_NOME` em `assets/preview/celular.js`). Um tipo que existe num e falta
no outro some do vídeo sem erro nenhum."""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import cenas  # noqa: E402

INDEX = RAIZ / "assets" / "shortform" / "src" / "cenas" / "index.tsx"
MAIN = RAIZ / "assets" / "shortform" / "src" / "Main.tsx"
CELULAR = RAIZ / "assets" / "preview" / "celular.js"


def _chaves(texto: str, inicio: str) -> set[str]:
    """As chaves do objeto literal que começa em `inicio` (até o primeiro `};`)."""
    m = re.search(re.escape(inicio) + r"(.*?)\n\};", texto, re.S)
    assert m, f"não achei `{inicio}`"
    return set(re.findall(r"^\s*(\w+)\s*:", m.group(1), re.M)) | set(re.findall(r"[{,]\s*(\w+)\s*:", m.group(1)))


def test_o_template_desenha_os_mesmos_tipos_que_o_helper_valida():
    do_template = _chaves(INDEX.read_text(encoding="utf-8"), "export const TIPOS: Record<string, React.FC<CenaProps>> = {")
    assert "vidro" in do_template  # o detector funciona: acha um tipo que sabidamente está lá
    assert do_template == set(cenas.TIPOS)


def test_o_editor_conhece_o_nome_de_todo_tipo():
    nomes = _chaves(CELULAR.read_text(encoding="utf-8"), "const CENA_NOME = {")
    assert {"vidro", "orbita", "corteZoom"} <= nomes  # o detector funciona
    assert set(cenas.TIPOS) <= nomes, f"falta no CENA_NOME do celular.js: {sorted(set(cenas.TIPOS) - nomes)}"


def test_main_monta_os_efeitos_entre_os_inserts_e_o_custom_graphics():
    t = MAIN.read_text(encoding="utf-8")
    i, c, g = t.find("<Inserts />"), t.find("<Cenas />"), t.find("<CustomGraphics />")
    assert min(i, c, g) > 0 and i < c < g
    assert re.search(r"^import \{Cenas\} from '\./cenas';", t, re.M)
