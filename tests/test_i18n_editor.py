"""O editor em inglês (assets/preview/i18n.js): todo texto de tela tem tradução.

O português é a chave: `t('Salvar')` no código, `"Salvar": "Save"` no `i18n-en.js`. Este teste lê
todos os `t('...')` dos scripts do editor e todos os textos e atributos de ajuda do `celular.html`, e
cobra uma tradução para cada um. Texto sem tradução não quebra a tela (sai em português), mas apareceria
em português para quem usa o editor em inglês, e é isso que ele trava.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

PREVIEW = Path(__file__).resolve().parents[1] / "assets" / "preview"
SCRIPTS = ["celular.js", "estilos.js", "tempo.js", "fontes.js"]

# `t(` sem letra, ponto ou $ antes (não casa `split(` nem `obj.t(`), com o texto entre aspas simples,
# duplas ou crases
T_LITERAL = re.compile(r"(?<![\w.$])t\(\s*(['\"`])((?:\\.|(?!\1)[^\\])*)\1", re.S)
MARCADOR = re.compile(r"\{(\w+)\}")

# Iguais nos dois idiomas: o nome do kit e as teclas da lista de atalhos.
HTML_IGUAIS = {"CutMind", "Ctrl", "Shift", "Delete", "Esc", "A", "B", "D", "M", "N", "Y", "Z"}
ATRIBUTOS = {"title", "aria-label", "placeholder", "alt"}


def dicionario() -> dict[str, str]:
    texto = (PREVIEW / "i18n-en.js").read_text(encoding="utf-8")
    corpo = texto[texto.index("=", texto.index("window.I18N_EN")) + 1:texto.rindex("}") + 1]
    return json.loads(corpo)


def _desescapa(s: str) -> str:
    return re.sub(r"\\(u[0-9a-fA-F]{4}|.)",
                  lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1)[0] == "u" and len(m.group(1)) == 5
                  else {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def chamadas(nome: str) -> list[tuple[int, str, str]]:
    """(linha, aspas, texto) de cada `t('...')` do arquivo."""
    fonte = (PREVIEW / nome).read_text(encoding="utf-8")
    return [(fonte.count("\n", 0, m.start()) + 1, m.group(1), _desescapa(m.group(2)))
            for m in T_LITERAL.finditer(fonte)]


def _chaves_do_objeto(fonte: str, i: int) -> set[str] | None:
    """As chaves do 2º argumento de t(...) a partir de `i` (logo depois do texto); None se não for objeto."""
    while fonte[i].isspace():
        i += 1
    if fonte[i] != ",":
        return set()  # t('...') sem valores
    i += 1
    while fonte[i].isspace():
        i += 1
    if fonte[i] != "{":
        return None  # os valores vêm de uma variável: não há como conferir aqui
    chaves: set[str] = set()
    prof, comeco = 0, False
    while i < len(fonte):
        c = fonte[i]
        if c in "'\"`":
            i += 1
            while fonte[i] != c:
                i += 2 if fonte[i] == "\\" else 1
        elif c in "{[(":
            prof += 1
            comeco = prof == 1
        elif c in "}])":
            prof -= 1
            if prof == 0:
                return chaves
        elif c == "," and prof == 1:
            comeco = True
        elif comeco and not c.isspace():
            m = re.match(r"(\w+)\s*[:,}]", fonte[i:])
            if m:
                chaves.add(m.group(1))
            comeco = False
        i += 1
    return chaves


def marcadores_sem_valor(fonte: str) -> list[tuple[int, str, list[str]]]:
    """(linha, texto, marcadores) de cada t('...{x}...') que não passa {x} nos valores."""
    ruins = []
    for m in T_LITERAL.finditer(fonte):
        marc = set(MARCADOR.findall(m.group(2)))
        chaves = _chaves_do_objeto(fonte, m.end()) if marc else set()
        if marc and chaves is not None and marc - chaves:
            ruins.append((fonte.count("\n", 0, m.start()) + 1, m.group(2), sorted(marc - chaves)))
    return ruins


class _Html(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pilha: list[str] = []
        self.textos: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        self.pilha.append(tag)
        for k, v in attrs:
            if k in ATRIBUTOS and v and any(c.isalpha() for c in v):
                self.textos.append((self.getpos()[0], v))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.pilha.pop()

    def handle_endtag(self, tag):
        while self.pilha and self.pilha.pop() != tag:
            pass

    def handle_data(self, data):
        if self.pilha and self.pilha[-1] in ("script", "style", "title"):
            return
        s = data.strip()
        if s and any(c.isalpha() for c in s):
            self.textos.append((self.getpos()[0], s))


def test_o_dicionario_e_json_e_nao_tem_traducao_vazia():
    en = dicionario()
    assert en, "o i18n-en.js ficou sem nenhuma tradução"
    vazias = [k for k, v in en.items() if not isinstance(v, str) or not v.strip()]
    assert not vazias, f"tradução vazia: {vazias}"


def test_o_leitor_acha_os_t_do_editor():
    """Caso positivo: se o leitor parar de achar `t()`, todos os outros testes passariam à toa."""
    textos = {s for _, _, s in chamadas("celular.js")}
    assert "Salve ou descarte seus ajustes antes de trocar o idioma." in textos
    assert not T_LITERAL.search("x.split('a')") and not T_LITERAL.search("obj.t('a')")


def test_todo_t_do_editor_tem_traducao():
    en = dicionario()
    faltam = [f"{nome}:{linha}  {s!r}" for nome in SCRIPTS for linha, _, s in chamadas(nome) if s not in en]
    assert not faltam, ("texto de tela sem inglês no assets/preview/i18n-en.js:\n  "
                        + "\n  ".join(faltam))


def test_t_com_crase_nao_monta_texto_por_dentro():
    """`t(`Lugar ${n}`)` nunca casaria com o dicionário: o certo é `t('Lugar {n}', {n})`."""
    erradas = [f"{nome}:{linha}" for nome in SCRIPTS for linha, aspas, s in chamadas(nome)
               if aspas == "`" and "${" in s]
    assert not erradas, f"t() com ${{...}} dentro (use marcador {{n}}): {erradas}"


def test_os_marcadores_batem_entre_portugues_e_ingles():
    en = dicionario()
    diferentes = [k for k, v in en.items() if set(MARCADOR.findall(k)) != set(MARCADOR.findall(v))]
    assert not diferentes, f"marcador {{...}} diferente no inglês: {diferentes}"


def test_o_leitor_de_valores_acha_o_marcador_esquecido():
    fonte = ("t('a {x} b {y}', { x: f(1, 2) });\nt('ok {z} {w}', { z, w: `${q} }` });\n"
             "t('sem valores {v}');\nt('de variável {k}', valores);\n")
    assert marcadores_sem_valor(fonte) == [(1, "a {x} b {y}", ["y"]), (3, "sem valores {v}", ["v"])]


def test_todo_marcador_do_t_recebe_valor():
    """Sem o valor, a tela mostra o "{x}" cru, nos dois idiomas."""
    ruins = [f"{nome}:{linha}  falta {', '.join(f)}  {s!r}" for nome in SCRIPTS
             for linha, s, f in marcadores_sem_valor((PREVIEW / nome).read_text(encoding="utf-8"))]
    assert not ruins, "t() com marcador sem valor:\n  " + "\n  ".join(ruins)


def test_todo_texto_do_html_tem_traducao():
    en = dicionario()
    p = _Html()
    p.feed((PREVIEW / "celular.html").read_text(encoding="utf-8"))
    assert p.textos, "o leitor do HTML não achou nenhum texto"
    faltam = [f"celular.html:{linha}  {s!r}" for linha, s in p.textos if s not in en and s not in HTML_IGUAIS]
    assert not faltam, "texto do HTML sem inglês no i18n-en.js:\n  " + "\n  ".join(faltam)


HELPERS = PREVIEW.parents[1] / "helpers"
AVISO = re.compile(r'idm\.mensagem\(\s*"((?:\\.|[^"\\])*)"')


def avisos_dos_scripts() -> list[tuple[str, str]]:
    """(arquivo, chave) de cada aviso que um script grava no state.json para a barra do editor."""
    return [(f.name, m.group(1)) for f in sorted(HELPERS.glob("*.py"))
            for m in AVISO.finditer(f.read_text(encoding="utf-8"))]


def test_todo_aviso_que_um_script_grava_tem_ingles_no_editor():
    """O editor mostra pela chave (avisoNoIdioma): sem ela no dicionário, a barra fica em português."""
    avisos = avisos_dos_scripts()
    assert {a for a, _ in avisos} >= {"montagem.py", "projetos.py"}  # o leitor acha os avisos
    en = dicionario()
    faltam = [f"{a}  {k!r}" for a, k in avisos if k not in en]
    assert not faltam, "aviso de script sem inglês no i18n-en.js:\n  " + "\n  ".join(faltam)


def test_o_dicionario_nao_guarda_texto_que_a_tela_nao_usa_mais():
    """Texto trocado no código deixa a chave antiga no dicionário, e ninguém percebe."""
    p = _Html()
    p.feed((PREVIEW / "celular.html").read_text(encoding="utf-8"))
    usados = ({s for nome in SCRIPTS for _, _, s in chamadas(nome)} | {s for _, s in p.textos}
              | {s for _, s in avisos_dos_scripts()})
    assert "Desfazer" in usados  # o leitor acha os textos do HTML e dos scripts
    sobrando = [k for k in dicionario() if k not in usados]
    assert not sobrando, "chave do i18n-en.js que nenhum t() nem o HTML usa:\n  " + "\n  ".join(map(repr, sobrando))


def test_o_i18n_carrega_antes_dos_outros_scripts():
    html = (PREVIEW / "celular.html").read_text(encoding="utf-8")
    ordem = re.findall(r'<script src="/assets/([\w.-]+)"', html)
    assert ordem[:2] == ["i18n-en.js", "i18n.js"], f"os scripts carregam nesta ordem: {ordem}"
