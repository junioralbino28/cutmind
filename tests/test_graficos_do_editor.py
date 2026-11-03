"""Os gráficos animados criados e mudados no editor, do Salvar ao edit-data.json, sem o agente.

O editor manda `nova` + `item` (um gráfico do painel), ou `ref` + `item` (o texto mudado, o desligar). O item tem
de passar na conferência do graficos.py, porque o Baixar desenha com ele como chegou; e os instantes de dentro
andam com o bloco, como num gráfico do agente.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import editdata_aplicar as eda  # noqa: E402
import graficos as gf  # noqa: E402
from remapear import INSTANTE  # noqa: E402

JS = (Path(__file__).resolve().parents[1] / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")


def um_de_cada(a=10.0, b=14.0):
    return [
        {"tipo": "palavras", "start": a, "end": b, "itens": [{"t": "Foco", "at": a}, {"t": "Ritmo", "at": a + 1}]},
        {"tipo": "botoes", "start": a, "end": b, "itens": [{"t": "Cortar", "at": a + 0.2}]},
        {"tipo": "grande", "start": a, "end": b, "t": "66%", "at": a, "sub": "quase tudo", "riscoAt": b - 0.7},
        {"tipo": "objecao", "start": a, "end": b, "usuario": "@quem_assiste", "texto": "Mas isso funciona?", "quando": "agora"},
        {"tipo": "lista", "start": a, "end": b, "titulo": "NÃO FAÇA", "itens": [{"t": "Sem roteiro", "at": a + 0.5}]},
        {"tipo": "comenta", "start": a, "end": b, "texto": "QUERO", "digitaAt": a + 0.4, "digitaFimAt": a + 1.2,
         "dmAt": a + 1.7, "dm": "te mando no direct", "seta": {"x": 820, "y": 1380}, "placeholder": "Adicione", "publicar": "Publicar"},
        {"tipo": "progresso", "start": a, "end": b, "titulo": "Aprendendo", "fimAt": b - 0.8, "fim": "Pronto!"},
        {"tipo": "ajuste", "start": a, "end": b, "titulo": "linha do tempo"},
        {"tipo": "selo", "start": a, "end": b, "src": "midia/logo.png"},
        {"tipo": "celular", "start": a, "end": b, "src": "midia/tela.png"},
        {"tipo": "pula", "start": a, "end": b, "itens": [{"t": "pula", "at": a + 0.1}, {"t": "aqui", "at": a + 0.5}]},
        {"tipo": "partes", "start": a, "end": b, "tamanho": 110, "itens": [{"t": "IMPOSSÍVEL?", "at": a + 0.1}, {"t": "NÃO É.", "at": a + 1.0}]},
        {"tipo": "danca", "start": a, "end": b, "t": "TIPOGRAFIA", "sub": "animada", "at": a},
        {"tipo": "glitch", "start": a, "end": b, "t": "GLITCH", "at": a},
        {"tipo": "marca", "start": a, "end": b, "texto": "A frase mais importante", "frase": "mais importante", "marcaAt": a + 0.5, "marcaFimAt": a + 1.2},
        {"tipo": "contador", "start": a, "end": b, "valor": 1500.5, "casas": 1, "prefixo": "R$", "sufixo": "%", "rotulo": "AO MÊS", "fimAt": b - 0.8},
        {"tipo": "nome", "start": a, "end": b, "nome": "Quem Fala", "cargo": "Criador"},
        {"tipo": "chat", "start": a, "end": b, "itens": [{"t": "oi", "at": a + 0.1}, {"t": "oi!", "at": a + 1.0}]},
        {"tipo": "maquina", "start": a, "end": b, "texto": "digitando", "digitaAt": a + 0.2, "digitaFimAt": a + 1.0},
        {"tipo": "prompt", "start": a, "end": b, "titulo": "Claude", "texto": "faz isso", "digitaAt": a + 0.2, "digitaFimAt": a + 1.0},
        {"tipo": "emoji", "start": a, "end": b, "itens": [{"t": "🔥", "at": a + 0.2}]},
        {"tipo": "polaroide", "start": a, "end": b, "src": "midia/tela.png", "legenda": "Nova York", "alfinete": "#c8102e"},
        {"tipo": "flash", "start": a, "end": b},
        {"tipo": "cta", "start": a, "end": b, "frase": "Fale com a gente", "botao": "Link na bio", "src": "midia/logo.png"},
    ]


def test_o_painel_tem_todos_os_tipos_do_modelo():
    m = re.search(r"const GF_TIPOS = \[([^\]]*)\]", JS)
    assert m, "GF_TIPOS sumiu do celular.js"
    assert set(re.findall(r"'(\w+)'", m.group(1))) == set(gf.TIPOS) == set(gf.CAMPOS)


def test_o_cartao_nao_leva_a_classe_do_proprio_desenho():
    """Com `gf-<tipo>` no botão, o cartão do Selo e o da Palavra grande pegavam o estilo do desenho de dentro: o
    Selo saía do lugar, por cima do Celular, e o clique nele escolhia o outro (teste no navegador de 02/11)."""
    assert "gf-${tipo}" not in JS
    assert "el('button', 'mod-card gf-card', grade)" in JS


def test_o_ajuste_da_letra_parte_do_tamanho_do_template():
    """O template não quebra a linha da Palavra grande nem de Palavras: o painel reduz a letra de quem digita
    texto longo, a partir do mesmo tamanho de sempre do template."""
    src = (Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "graficos" / "index.tsx").read_text(encoding="utf-8")
    grande = re.search(r"const Grande: .*?const tam = g\.tamanho \?\? (\d+);", src, re.S)
    palavras = re.search(r"const Palavras: .*?const tam = g\.tamanho \?\? (\d+);", src, re.S)
    assert grande and f"gfTamanho(g, [v('t'), v('troca')], {grande.group(1)})" in JS
    assert palavras and f"gfTamanho(g, ls, {palavras.group(1)})" in JS
    texto = (Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "graficos" / "texto.tsx").read_text(encoding="utf-8")
    danca = re.search(r"const Danca: .*?const tam = g\.tamanho \?\? (\d+);", texto, re.S)
    glitch = re.search(r"const Glitch: .*?const tam = g\.tamanho \?\? (\d+);", texto, re.S)
    partes = re.search(r"const Partes: .*?const tam = g\.tamanho \?\? (\d+);", texto, re.S)
    contador = re.search(r"const Contador: .*?const tam = g\.tamanho \?\? (\d+);", texto, re.S)
    assert danca and glitch and f"tipo === 'danca' ? {danca.group(1)} : {glitch.group(1)}" in JS
    assert partes and f"gfTamanho(g, ls, {partes.group(1)})" in JS
    assert contador and f"`], {contador.group(1)})" in JS


def test_os_instantes_do_editor_sao_os_mesmos_do_recorte():
    """O editor move os instantes quando a pessoa edita o texto de um gráfico já movido: a mesma regra do
    remapear.py e do editdata_aplicar.py, ou um instante fica para trás."""
    m = re.search(r"const GF_INSTANTE = /(.+)/;", JS)
    assert m and m.group(1).replace("\\", "") == INSTANTE.pattern.replace("\\", "")


def test_cada_tipo_novo_chega_ao_edit_data_e_passa_na_conferencia():
    pedidos = [{"nova": True, "start": g["start"], "end": g["end"], "item": g} for g in um_de_cada()]
    d = {}
    _, avisos = eda.aplicar(d, {"graficos": pedidos})
    assert not avisos and [g["tipo"] for g in d["graficos"]] == [g["tipo"] for g in um_de_cada()]
    for g in d["graficos"]:
        assert gf.validar(g) == [], (g["tipo"], gf.validar(g))


def test_o_novo_movido_antes_de_salvar_leva_os_instantes_junto():
    g = um_de_cada()[6]  # progresso, com fimAt
    d = {"graficos": [{"tipo": "ajuste", "start": 1.0, "end": 2.0}]}
    eda.aplicar(d, {"graficos": [{"ref": 0, "start": 1.0, "end": 2.0}, {"nova": True, "start": 20.0, "end": 24.0, "item": g}]})
    novo = d["graficos"][1]
    assert (novo["start"], novo["end"], novo["fimAt"]) == (20.0, 24.0, 23.2)
    assert d["graficos"][0]["tipo"] == "ajuste"  # os `ref` dos que já existiam não mudam


def test_texto_mudado_troca_o_item_e_mantem_o_resto():
    velho = {"tipo": "palavras", "start": 5.0, "end": 8.0, "cor": "#fff",
             "itens": [{"t": "Antes", "at": 5.5, "selecao": {"at": 6.0, "palavra": "Antes"}}]}
    d = {"graficos": [velho]}
    item = json.loads(json.dumps(velho))
    item["itens"][0]["t"] = "Depois"
    eda.aplicar(d, {"graficos": [{"ref": 0, "start": 5.0, "end": 8.0, "item": item}]})
    assert d["graficos"][0]["itens"][0] == {"t": "Depois", "at": 5.5, "selecao": {"at": 6.0, "palavra": "Antes"}}
    assert d["graficos"][0]["cor"] == "#fff"


def test_desligar_vai_no_item_e_o_template_nao_desenha():
    d = {"graficos": [{"tipo": "ajuste", "start": 1.0, "end": 3.0}]}
    eda.aplicar(d, {"graficos": [{"ref": 0, "start": 1.0, "end": 3.0, "item": {"tipo": "ajuste", "start": 1.0, "end": 3.0, "desligada": True}}]})
    assert d["graficos"][0]["desligada"] is True
    src = (Path(__file__).resolve().parents[1] / "assets" / "shortform" / "src" / "graficos" / "index.tsx").read_text(encoding="utf-8")
    assert "!g.desligada" in src


def test_mover_sem_mudar_o_item_continua_como_antes():
    d = {"graficos": [{"tipo": "grande", "start": 1.0, "end": 3.0, "t": "X", "at": 1.5}]}
    eda.aplicar(d, {"graficos": [{"ref": 0, "start": 2.0, "end": 4.0}]})
    assert (d["graficos"][0]["start"], d["graficos"][0]["at"]) == (2.0, 2.5)


@pytest.fixture
def projeto(tmp_path):
    raiz = tmp_path / "edit"
    public = raiz / "remotion" / "public"
    (raiz / "midia").mkdir(parents=True)
    public.mkdir(parents=True)
    (raiz / "midia" / "logo.png").write_bytes(b"png")
    (raiz / "midia" / "tela.png").write_bytes(b"png")
    (raiz / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    (public / "edit-data.json").write_text("{}", encoding="utf-8")
    (tmp_path / "segredo.png").write_bytes(b"png")
    return raiz, public


def _pede(g, **kw):
    return [{"nova": True, "start": g["start"], "end": g["end"], "item": g, **kw}]


def test_a_conferencia_aceita_todos_os_tipos_do_painel(projeto):
    raiz, public = projeto
    for g in um_de_cada():
        gf.conferir_do_editor(raiz, public, _pede(g))


@pytest.mark.parametrize("mexe, frase", [
    (lambda g: g.update(tipo="inventado"), "não existe"),
    (lambda g: g.update(texto=""), "falta"),
    (lambda g: g.update(digitaAt=99.0), "fora da janela"),
    (lambda g: g.update(chave_estranha=1), "não leva"),
    (lambda g: g.update(texto="x" * 201), "até 200"),
])
def test_a_conferencia_recusa_o_que_o_baixar_nao_desenharia(projeto, mexe, frase):
    raiz, public = projeto
    g = next(x for x in um_de_cada() if x["tipo"] == "comenta")
    mexe(g)
    with pytest.raises(gf.GraficosInvalidos, match=frase):
        gf.conferir_do_editor(raiz, public, _pede(g))


@pytest.mark.parametrize("src", ["../../segredo.png", "midia/../../segredo.png", "midia/nao-existe.png", "C:/Windows/win.ini"])
def test_a_imagem_tem_de_ser_do_projeto(projeto, src):
    raiz, public = projeto
    g = {"tipo": "selo", "start": 1.0, "end": 3.0, "src": src}
    with pytest.raises(gf.GraficosInvalidos, match="não está no projeto"):
        gf.conferir_do_editor(raiz, public, _pede(g))


def test_a_pasta_irma_de_mesmo_prefixo_nao_passa(projeto):
    raiz, public = projeto
    irma = raiz / "midia-segredo"
    irma.mkdir()
    (irma / "x.png").write_bytes(b"png")
    assert not gf.imagem_do_projeto(raiz, public, "midia/../midia-segredo/x.png")


def test_o_mover_e_aparar_de_sempre_passa_sem_conferir_item(projeto):
    raiz, public = projeto
    gf.conferir_do_editor(raiz, public, [{"ref": 0, "start": 1.0, "end": 2.0}])


def test_o_novo_sem_item_para(projeto):
    raiz, public = projeto
    with pytest.raises(gf.GraficosInvalidos, match="precisa do `item`"):
        gf.conferir_do_editor(raiz, public, [{"nova": True, "start": 1.0, "end": 2.0}])


def test_o_item_do_agente_com_campo_proprio_continua_editavel(projeto):
    """A trava dos campos é para o que o painel cria; o item do agente pode ter um campo que o painel não conhece."""
    raiz, public = projeto
    g = {"tipo": "grande", "start": 1.0, "end": 3.0, "t": "X", "campo_do_agente": 1}
    gf.conferir_do_editor(raiz, public, [{"ref": 0, "start": 1.0, "end": 3.0, "item": g}])


def test_gravar_leva_a_imagem_da_midia_para_o_public(projeto):
    raiz, public = projeto
    g = {"tipo": "selo", "start": 1.0, "end": 3.0, "src": "midia/logo.png"}
    eda.gravar(raiz, {"graficos": _pede(g)})
    assert (public / "midia" / "logo.png").read_bytes() == b"png"
    assert gf.conferir(public / "edit-data.json") == []
