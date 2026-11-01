"""Os efeitos de cena escolhidos no editor (Efeitos → Cenas), do Salvar ao edit-data.json, sem o agente.

O editor manda cada um como `nova`, com os textos soltos em `textos` e as listas (manchetes, valores) em
`campos`; o editdata_aplicar.py acrescenta em `cenas[]`, e o item tem de passar na conferência do
cenas.py, porque o Baixar desenha com ele como chegou. Os textos que a pessoa não mexeu vêm com
`textoAuto`, para o agente melhorar no "Pronto, Claude segue"."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import cenas  # noqa: E402
import editdata_aplicar as eda  # noqa: E402

JS = (Path(__file__).resolve().parents[1] / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")


def nova(tipo, textos=None, campos=None, a=10.0, b=13.0):
    return {"nova": True, "tipo": tipo, "start": a, "end": b, "desligada": False, "texto": None,
            "textos": textos or {}, "estilo": None, "campos": campos or {}}


def test_cada_tipo_do_painel_chega_ao_edit_data_e_passa_na_conferencia():
    pedidos = [
        nova("vidro", {"palavra": "FOCO"}, {"textoAuto": True}),
        nova("capa", {"nome": "MENTORA", "selo": "ESPECIAL"}),
        nova("mural", {}, {"manchetes": [{"kicker": "", "t": "A notícia do dia", "at": 10.25},
                                         {"kicker": "", "t": "O mercado mudou", "at": 11.4}],
                           "circulo": 0, "circuloAt": 12.1}),
        nova("parede", {"pequeno": "CONTEÚDO", "gigante": "TODO DIA"}),
        nova("grafico", {"etiqueta": "66%"}, {"valores": [0.28, 0.46, 0.64, 0.85]}),
        nova("chroma", {"titulo": "Seu editor agora", "frase": "Você fala, ele corta.", "botao": "Começar"}),
        nova("orbita", {"titulo": "Tudo num lugar só"}),
    ]
    d = {"cenas": []}
    depois, avisos = eda.aplicar(d, {"cenas": pedidos})
    assert not avisos and "cenas" in depois and len(d["cenas"]) == 7
    for c in d["cenas"]:
        assert cenas.validar(c) == [], (c["tipo"], cenas.validar(c))
    vidro, mural, grafico = d["cenas"][0], d["cenas"][2], d["cenas"][4]
    assert vidro == {"tipo": "vidro", "start": 10.0, "end": 13.0, "palavra": "FOCO", "textoAuto": True}
    assert [m["t"] for m in mural["manchetes"]] == ["A notícia do dia", "O mercado mudou"]
    assert grafico["valores"] == [0.28, 0.46, 0.64, 0.85] and grafico["etiqueta"] == "66%"


def test_texto_escrito_depois_do_salvar_tira_a_marca_do_agente():
    """Depois do Salvar o efeito novo é um item como os outros (`ref`); se a pessoa troca o texto no
    painel de Texto, o texto é dela e o agente não pode mais reescrever. Mudar só o lugar não tira."""
    d = {"cenas": [{"tipo": "vidro", "start": 10.0, "end": 13.0, "palavra": "FOCO", "textoAuto": True}]}
    eda.aplicar(d, {"cenas": [{"ref": 0, "desligada": False, "texto": {"x": 540, "y": 600}, "textos": {"palavra": "FOCO"}}]})
    assert d["cenas"][0]["textoAuto"] is True
    eda.aplicar(d, {"cenas": [{"ref": 0, "desligada": False, "texto": None, "textos": {"palavra": "PRESSA"}}]})
    assert d["cenas"][0]["palavra"] == "PRESSA" and "textoAuto" not in d["cenas"][0]


def test_o_painel_conhece_os_tipos_que_o_modelo_desenha():
    """Cada cartão do painel é um tipo do cenas.py (sem o Fundo, que tem painel próprio); um tipo novo
    no modelo sem cartão, ou um cartão sem tipo no modelo, quebra aqui."""
    m = re.search(r"const CENAS_NOVAS = \[([^\]]*)\]", JS)
    assert m, "CENAS_NOVAS sumiu do celular.js"
    no_painel = re.findall(r"'(\w+)'", m.group(1))
    assert sorted(no_painel) == sorted(t for t in cenas.TIPOS if t != "fundo")
    for tipo in no_painel:  # campos e dica de cada um
        assert re.search(rf"\b{tipo}: \[", JS.split("const CN_CAMPOS")[1].split("};")[0]), tipo
        assert re.search(rf"\b{tipo}: t\(", JS.split("const CENA_DICA")[1].split("};")[0]), tipo


def test_nenhuma_funcao_do_editor_declarada_duas_vezes():
    """No JavaScript a segunda declaração de uma função substitui a primeira sem erro nenhum. O painel
    Cenas nasceu com um `renderCenas()` e apagou o que desenha a faixa de efeitos: os blocos sumiram."""
    nomes = re.findall(r"^(?:async )?function (\w+)\(", JS, re.M)
    repetidas = sorted({n for n in nomes if nomes.count(n) > 1})
    assert not repetidas, f"declaradas mais de uma vez no celular.js: {repetidas}"


def test_campos_de_qualquer_efeito_novo_vao_no_salvar():
    """O `cenaValor` guardava só os campos do Fundo: as manchetes e os valores de um efeito novo se
    perderiam no Salvar e no desfazer."""
    corpo = JS.split("function cenaValor(v)")[1].split("\n}\n")[0]
    assert "JSON.parse(JSON.stringify(v.campos))" in corpo
