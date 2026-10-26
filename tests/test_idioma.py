"""O idioma da tela e a tradução das mensagens que o servidor devolve para o editor."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import idioma  # noqa: E402


@pytest.fixture
def dicionario(tmp_path, monkeypatch):
    def usa(d: dict) -> None:
        p = tmp_path / "scripts-en.json"
        p.write_bytes(json.dumps(d, ensure_ascii=False).encode("utf-8"))
        monkeypatch.setattr(idioma, "DICIONARIO", p)
        idioma._dicionario.cache_clear()
        idioma._padroes.cache_clear()
    yield usa
    idioma._dicionario.cache_clear()
    idioma._padroes.cache_clear()


@pytest.mark.parametrize("valor, esperado", [
    ("pt", "pt"), ("pt-BR", "pt"), ("PT_pt", "pt"), ("en", "en"), ("en-US", "en"), ("es-ES", "en"),
    ("", None), (None, None), ("pt;q=1", None), ("../x", None),
])
def test_normalizar(valor, esperado):
    assert idioma.normalizar(valor) == esperado


def test_o_cabecalho_do_editor_vale_mais_que_o_navegador():
    assert idioma.do_pedido("en", "pt-BR,pt;q=0.9") == "en"
    assert idioma.do_pedido("pt", "en-US,en;q=0.9") == "pt"
    assert idioma.do_pedido(None, "en-US,en;q=0.9") == "en"
    assert idioma.do_pedido("lixo!", "pt-BR") == "pt"
    assert idioma.do_pedido(None, None) == "pt"


def test_traduz_a_frase_exata_e_deixa_o_resto_como_esta(dicionario):
    dicionario({"o projeto ainda não tem o corte": "the project has no cut yet"})
    assert idioma.traduzir("o projeto ainda não tem o corte", "en") == "the project has no cut yet"
    assert idioma.traduzir("o projeto ainda não tem o corte", "pt") == "o projeto ainda não tem o corte"
    assert idioma.traduzir("frase sem tradução", "en") == "frase sem tradução"


def test_a_frase_montada_acha_o_padrao_e_traduz_o_valor_de_dentro(dicionario):
    dicionario({"não encontrado: {rel}": "not found: {rel}",
                "montagem: {e}": "montage: {e}",
                "o modelo passa de {kb} KB": "the template is over {kb} KB",
                "{a} de {b}": "{a} of {b}"})
    assert idioma.traduzir("não encontrado: midia/praia.mp4", "en") == "not found: midia/praia.mp4"
    assert idioma.traduzir("montagem: o modelo passa de 20 KB", "en") == "montage: the template is over 20 KB"
    # o padrão de mais texto fixo ganha do mais genérico
    assert idioma.traduzir("o modelo passa de 3 de 4 KB", "en") == "the template is over 3 of 4 KB"


def test_dicionario_ausente_nao_quebra(dicionario, tmp_path, monkeypatch):
    monkeypatch.setattr(idioma, "DICIONARIO", tmp_path / "nao-existe.json")
    idioma._dicionario.cache_clear()
    idioma._padroes.cache_clear()
    assert idioma.traduzir("qualquer coisa", "en") == "qualquer coisa"


# ---- o dicionário dos scripts contra o código: o que o servidor pode mandar para a tela ----
HELPERS = Path(__file__).resolve().parents[1] / "helpers"
PORTUGUES = re.compile(r"[ãõçáéíóúâêô]|\b(não|sem|para|com|uma|um|do|da|de|em|no|na|ou|já|vídeo|mídia|modelo|"
                       r"lugar|projeto|pedido|pasta|arquivo|envio|tente|falhou|consegui|inválid[oa])\b", re.I)
# vai para o terminal quando o servidor sobe, para o agente: não passa pelo editor
FORA = ("sem permissão para escrever em {where}\n\nNo macOS",)


def _texto(no) -> str | None:
    """O texto de um literal ou f-string, com {marcador} no lugar de cada expressão."""
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.JoinedStr):
        out, n = [], 0
        for v in no.values:
            if isinstance(v, ast.Constant):
                out.append(v.value)
            else:
                e = v.value
                nome = e.id if isinstance(e, ast.Name) else e.attr if isinstance(e, ast.Attribute) else f"p{n}"
                n += 1
                out.append("{" + nome + "}")
        return "".join(out)
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
        a, b = _texto(no.left), _texto(no.right)
        return a + b if a is not None and b is not None else None
    return None


def mensagens(fonte_do_servidor: str, modulos: dict[str, str]) -> dict[str, str]:
    """{mensagem: onde} — os erros que o servidor devolve e as exceções dos módulos que ele importa."""
    achadas: dict[str, str] = {}
    for mod, fonte in {"preview_server": fonte_do_servidor, **modulos}.items():
        for no in ast.walk(ast.parse(fonte)):
            cands = []
            if isinstance(no, ast.Raise) and isinstance(no.exc, ast.Call) and no.exc.args:
                cands.append(no.exc.args[0])
            if mod == "preview_server" and isinstance(no, ast.Dict):
                cands += [v for k, v in zip(no.keys, no.values) if isinstance(k, ast.Constant) and k.value == "error"]
            if (mod == "preview_server" and isinstance(no, ast.Call) and len(no.args) >= 2
                    and getattr(no.func, "attr", "") in ("_deny", "_fail")):
                cands.append(no.args[1])
            for c in cands:
                s = _texto(c)
                if s and s != "{e}" and re.search(r"[a-zà-ÿ]{3}", s, re.I):
                    achadas.setdefault(s, f"{mod}:{no.lineno}")
    return achadas


def mensagens_do_kit() -> dict[str, str]:
    srv = (HELPERS / "preview_server.py").read_text(encoding="utf-8")
    nomes = re.findall(r"^import (\w+) as \w+  # mesma pasta", srv, re.M)
    return mensagens(srv, {n: (HELPERS / f"{n}.py").read_text(encoding="utf-8") for n in nomes})


def test_o_leitor_acha_as_mensagens_do_servidor_e_dos_modulos():
    falso = ("def f(self):\n    self._json({'error': f'não achei {nome}'}, 404)\n"
             "    self._fail(400, 'Arquivo vazio.')\n    raise ValueError('x' + 'y é ruim')\n")
    assert set(mensagens(falso, {"m": "raise Erro(f'lugar {i}: {e}')"})) == {
        "não achei {nome}", "Arquivo vazio.", "xy é ruim", "lugar {i}: {e}"}
    reais = mensagens_do_kit()
    assert "o projeto ainda não tem o corte" in reais and "montagem: {e}" in reais
    assert any(onde.startswith("montagem:") for onde in reais.values())  # entra nos módulos importados


def test_toda_mensagem_que_chega_a_tela_tem_ingles():
    en = idioma._dicionario.__wrapped__()
    faltam = [f"{onde}  {s!r}" for s, onde in mensagens_do_kit().items()
              if PORTUGUES.search(s) and s not in en and not s.startswith(FORA)]
    assert not faltam, "mensagem sem inglês em assets/i18n/scripts-en.json:\n  " + "\n  ".join(faltam)


def test_o_dicionario_dos_scripts_nao_guarda_mensagem_que_sumiu_do_codigo():
    reais = mensagens_do_kit()
    sobrando = [k for k in idioma._dicionario.__wrapped__() if k not in reais]
    assert not sobrando, "chave do scripts-en.json que o código não manda mais:\n  " + "\n  ".join(map(repr, sobrando))


def test_os_marcadores_batem_no_dicionario_dos_scripts():
    en = idioma._dicionario.__wrapped__()
    diferentes = [k for k, v in en.items() if sorted(idioma.MARCADOR.findall(k)) != sorted(idioma.MARCADOR.findall(v))]
    assert not diferentes, diferentes
