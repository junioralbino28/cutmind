"""O editor é um script só (celular.js): duas `function` com o mesmo nome não dão erro
nenhum, a de baixo apenas substitui a de cima, inclusive para quem chama lá do alto. Foi
assim que o Aplicar dos modelos de estilo caiu no aplicaModelo dos modelos de texto
("m.linhas is not iterable") em 23/10."""
import re
from collections import Counter
from pathlib import Path

EDITOR = Path(__file__).resolve().parents[1] / "assets" / "preview" / "celular.js"
TOPO = re.compile(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.M)


def test_detector_acha_as_funcoes_do_topo():
    nomes = TOPO.findall(EDITOR.read_text(encoding="utf-8"))
    # caso positivo: se a regex parar de casar, o teste de baixo passaria vazio
    assert {"salvar", "poll", "aplicaModeloDeEstilo", "abreProjetos"} <= set(nomes)
    assert len(nomes) > 300


def test_nenhuma_funcao_do_topo_declarada_duas_vezes():
    nomes = TOPO.findall(EDITOR.read_text(encoding="utf-8"))
    repetidas = sorted(n for n, k in Counter(nomes).items() if k > 1)
    assert not repetidas, f"declaradas mais de uma vez em celular.js (a de baixo vence): {repetidas}"
