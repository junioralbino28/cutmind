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
GUIA = RAIZ / "references" / "cenas.md"


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


def test_a_moldura_do_editor_parte_do_layout_medido_na_pessoa():
    """O lugar padrão do texto destes efeitos é o `layout` que o helper mede na pessoa: a moldura
    do editor que partisse do número fixo do componente ficaria longe do texto do vídeo."""
    js = CELULAR.read_text(encoding="utf-8")
    m = re.search(r"const CENA_BLOCO = \{(.*?)\n\};", js, re.S)
    assert m, "não achei o CENA_BLOCO"
    entradas = dict(re.findall(r"^  (\w+): (.*)$", m.group(1), re.M))
    assert "zoomDigital" in entradas  # o detector acha as entradas (essa não tem layout)
    for tipo in ("vidro", "capa", "parede", "grafico", "chroma"):
        assert "lay(c)" in entradas.get(tipo, ""), f"a moldura de `{tipo}` não lê o layout"


def test_o_editor_oferece_os_fundos_prontos_do_kit():
    """Os cartões do painel Fundo são os fundos que o helper aceita, e cada um tem a imagem."""
    js = CELULAR.read_text(encoding="utf-8")
    m = re.search(r"const FUNDOS_PRONTOS = \[(.*?)\];", js)
    assert m, "não achei o FUNDOS_PRONTOS"
    ids = re.findall(r"\['(\w+)', (?:t\()?'", m.group(1))
    assert ids == list(cenas.FUNDOS)
    assert all((RAIZ / "assets" / "preview" / "fundos" / f"{i}.jpg").is_file() for i in ids)


def test_o_veu_e_o_desfoque_padrao_do_editor_sao_os_do_template():
    js = CELULAR.read_text(encoding="utf-8")
    tsx = (RAIZ / "assets" / "shortform" / "src" / "cenas" / "fundo.tsx").read_text(encoding="utf-8")
    m = re.search(r"const FUNDO_PADRAO = \{ escurecer: ([\d.]+), desfoque: ([\d.]+) \};", js)
    assert m, "não achei o FUNDO_PADRAO"
    assert f"c.escurecer ?? {m.group(1)}" in tsx
    assert m.group(2) == "0" and "Number(c.desfoque) || 0" in tsx


def test_o_guia_do_agente_explica_cada_tipo():
    """references/cenas.md tem uma seção `### \\`tipo\\`` por tipo: o agente de outra pessoa só
    usa o efeito que o guia ensina."""
    secoes = re.findall(r"^### `(\w+)`", GUIA.read_text(encoding="utf-8"), re.M)
    assert "vidro" in secoes  # o detector funciona
    assert sorted(secoes) == sorted(cenas.TIPOS)
    assert "references/cenas.md" in (RAIZ / "references" / "shortform.md").read_text(encoding="utf-8")


def test_main_monta_os_efeitos_entre_os_inserts_e_o_custom_graphics():
    t = MAIN.read_text(encoding="utf-8")
    i, c, g = t.find("<Inserts />"), t.find("<Cenas />"), t.find("<CustomGraphics />")
    assert min(i, c, g) > 0 and i < c < g
    assert re.search(r"^import \{Cenas\} from '\./cenas';", t, re.M)
