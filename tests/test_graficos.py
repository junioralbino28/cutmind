"""Os gráficos animados como dado (`graficos[]` do edit-data.json): o template desenha, o helper confere,
o re-corte e o Salvar do editor levam os instantes de cada um junto com a janela.

Vieram do Reels 1 (29/10/2026), onde moravam no CustomGraphics.tsx do projeto: no kit viraram tipos do
template, com as cores do Estilo e os lugares padrão dentro da zona segura.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import editdata_aplicar as ea  # noqa: E402
import graficos  # noqa: E402
import remapear  # noqa: E402

SRC = RAIZ / "assets" / "shortform" / "src"
TSX = SRC / "graficos" / "index.tsx"
PREVIEW = RAIZ / "assets" / "preview"

EXEMPLOS = {
    "palavras": {"tipo": "palavras", "start": 0.2, "end": 2.0, "itens": [
        {"t": "UM", "at": 0.2}, {"t": "DOIS", "at": 0.8, "ate": 1.2, "selecao": {"at": 1.0, "palavra": "DOIS"}},
        {"t": "Claude", "at": 1.4, "pilula": True}]},
    "botoes": {"tipo": "botoes", "start": 3.0, "end": 5.0, "itens": [{"t": "Cortar", "icone": "corte", "at": 3.0}, {"t": "Legendas", "icone": "cc", "at": 4.0}]},
    "celular": {"tipo": "celular", "start": 5.0, "end": 6.0, "src": "telas/tela.png"},
    "objecao": {"tipo": "objecao", "start": 6.0, "end": 7.5, "usuario": "@alguem", "texto": "Mas é caro?"},
    "grande": {"tipo": "grande", "start": 7.5, "end": 9.0, "t": "GRÁTIS", "at": 7.6, "riscoAt": 8.4},
    "lista": {"tipo": "lista", "start": 9.0, "end": 11.0, "titulo": "OS OUTROS", "itens": [{"t": "Caro", "at": 9.3}, {"t": "Lento", "at": 9.9}]},
    "selo": {"tipo": "selo", "start": 11.0, "end": 12.0, "src": "brand/logo.png"},
    "ajuste": {"tipo": "ajuste", "start": 12.0, "end": 13.5},
    "progresso": {"tipo": "progresso", "start": 13.5, "end": 15.0, "titulo": "Aprendendo", "fimAt": 14.6, "fim": "Pronto"},
    "comenta": {"tipo": "comenta", "start": 15.0, "end": 18.0, "texto": "QUERO", "digitaAt": 15.4, "digitaFimAt": 16.0,
                "dmAt": 16.6, "dm": "te mando no direct", "seta": {"x": 820, "y": 1380}},
}


def test_o_template_e_o_helper_conhecem_os_mesmos_tipos():
    tsx = TSX.read_text(encoding="utf-8")
    bloco = re.search(r"export const TIPOS[^=]*= \{([^}]*)\}", tsx).group(1)
    assert set(re.findall(r"(\w+):", bloco)) == set(graficos.TIPOS) == set(EXEMPLOS)


def test_o_template_monta_os_graficos_entre_os_efeitos_e_os_textos():
    main = (SRC / "Main.tsx").read_text(encoding="utf-8")
    assert "import {Graficos} from './graficos'" in main
    corpo = main[main.index("export const Main"):]
    assert corpo.index("<Cenas />") < corpo.index("<Graficos />") < corpo.index("<CamadasTexto />")


def test_cores_vem_do_estilo_e_lugares_da_zona_segura():
    tsx = TSX.read_text(encoding="utf-8") + (SRC / "graficos" / "comum.tsx").read_text(encoding="utf-8")
    assert "LARANJA" not in tsx and "#F87000" not in tsx.upper()  # a cor é a do Estilo (hook.accent)
    assert "hook?.accent" in tsx
    padroes = re.findall(r"g\.y \?\? ([^,;)}]+)", tsx)
    assert padroes and all(p.strip().startswith("TOPO +") for p in padroes), padroes
    # os cartões terminam antes da coluna de botões do Reels (x 930)
    for left, w in re.findall(r"left: (\d+), top: g\.y \?\? TOPO \+ \d+, width: (\d+)", tsx):
        assert int(left) + int(w) <= 930, (left, w)


def test_os_exemplos_passam_e_os_erros_dizem_o_campo(tmp_path):
    for g in EXEMPLOS.values():
        assert graficos.validar(g) == [], g
    assert any("texto" in e for e in graficos.validar({"tipo": "objecao", "start": 1, "end": 2, "usuario": "x"}))
    assert any("tipo" in e for e in graficos.validar({"tipo": "foguete", "start": 1, "end": 2}))
    assert any("end" in e for e in graficos.validar({"tipo": "ajuste", "start": 3, "end": 2}))
    fora = {**EXEMPLOS["grande"], "riscoAt": 12.0}
    assert any("riscoAt" in e for e in graficos.validar(fora))
    assert any("icone" in e for e in graficos.validar({"tipo": "botoes", "start": 0, "end": 1, "itens": [{"t": "x", "at": 0, "icone": "foguete"}]}))


def test_o_helper_confere_as_imagens_do_projeto(tmp_path):
    pub = tmp_path / "remotion" / "public"
    (pub / "telas").mkdir(parents=True)
    (pub / "telas" / "tela.png").write_bytes(b"x")
    ed = {"graficos": [EXEMPLOS["celular"], EXEMPLOS["selo"]]}
    (pub / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    erros = graficos.conferir(pub / "edit-data.json")
    assert len(erros) == 1 and "brand/logo.png" in erros[0]


def _levar_somando(d):
    def levar(t):
        return t + d
    levar.perto = levar
    levar.janela = lambda a, b: (a + d, b + d)
    return levar


def test_o_re_corte_leva_a_janela_e_todos_os_instantes():
    ed = {"graficos": [json.loads(json.dumps(g)) for g in EXEMPLOS.values()]}
    novo, fora = remapear.fase2(ed, _levar_somando(1.0), 60.0, [0], 1)
    assert fora == []
    for velho, g in zip(ed["graficos"], novo["graficos"]):
        assert g["start"] == velho["start"] + 1 and g["end"] == velho["end"] + 1
    p = novo["graficos"][0]
    assert [i["at"] for i in p["itens"]] == [1.2, 1.8, 2.4]
    assert p["itens"][1]["ate"] == 2.2 and p["itens"][1]["selecao"]["at"] == 2.0  # o aninhado anda junto
    c = novo["graficos"][-1]
    assert (c["digitaAt"], c["digitaFimAt"], c["dmAt"]) == (16.4, 17.0, 17.6)
    assert c["seta"] == {"x": 820, "y": 1380}  # lugar não é tempo
    assert novo["graficos"][4]["riscoAt"] == 9.4 and novo["graficos"][8]["fimAt"] == 15.6


def test_o_grafico_que_cai_fora_do_corte_vira_aviso():
    def levar(t):
        return None
    levar.perto = levar
    levar.janela = lambda a, b: None
    novo, fora = remapear.fase2({"graficos": [EXEMPLOS["lista"]]}, levar, 60.0, [0], 1)
    assert novo["graficos"] == [] and fora and fora[0]["item"] == "grafico"


def test_mover_o_bloco_no_editor_leva_os_instantes_e_aparar_os_prende_na_janela():
    ed = {"graficos": [json.loads(json.dumps(EXEMPLOS["comenta"])), json.loads(json.dumps(EXEMPLOS["lista"]))]}
    ea.aplicar(ed, {"graficos": [{"ref": 0, "start": 20.0, "end": 23.0}, {"ref": 1, "start": 9.5, "end": 10.5}]})
    c, li = ed["graficos"]
    assert (c["start"], c["end"], c["digitaAt"], c["digitaFimAt"], c["dmAt"]) == (20.0, 23.0, 20.4, 21.0, 21.6)
    assert (li["start"], li["end"]) == (9.5, 10.5)
    assert [i["at"] for i in li["itens"]] == [9.5, 9.9]  # aparado: o que ficou antes do começo entra no começo


def test_o_editor_mostra_os_graficos_como_blocos_da_fase_2():
    js = (PREVIEW / "celular.js").read_text(encoding="utf-8")
    assert "(d.graficos || []).forEach" in js
    assert "graficos: de('grafico')" in js
    assert re.search(r"const isText = \(c\) => [^;]*'grafico'", js)
    en = (PREVIEW / "i18n-en.js").read_text(encoding="utf-8")
    assert '"O gráfico do vídeo final"' in en
    for nome in graficos.TIPOS:
        assert f"{nome}: t('" in js, nome  # o nome de cada tipo no bloco


@pytest.mark.parametrize("arquivo", ["helpers/preview_server.py", "helpers/watch_edits.py"])
def test_o_servidor_e_o_vigia_sabem_que_graficos_e_bloco_da_fase_2(arquivo):
    assert '"graficos"' in (RAIZ / arquivo).read_text(encoding="utf-8")
