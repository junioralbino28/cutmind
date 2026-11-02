"""Ouvir cada emenda (edição real de 01/11: só transcrever a emenda pronta achou a palavra cortada que as medidas
deixavam passar). A transcrição de verdade não roda aqui: as palavras são de mentira, nas posições do áudio
juntado (uma janela por emenda, separadas por silêncio)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import conferir_emendas as ce  # noqa: E402

PASSO = ce.ANTES + ce.DEPOIS + ce.VAO


def test_as_palavras_de_cada_lado_da_juncao():
    jan = [5.0, 12.4]
    w = lambda t, a: {"text": t, "start": a, "end": a + 0.2}  # noqa: E731
    palavras = [w("fim", 1.5), w("da", 1.8), w("frase", 1.95), w("começo", 2.1),          # 1ª janela: junção a 2,0 s
                w("outra", PASSO + 1.7), w("coisa", PASSO + 2.05)]                        # 2ª janela
    assert ce.lados(palavras, jan) == [{"em": 5.0, "antes": "fim da frase", "depois": "começo"},
                                       {"em": 12.4, "antes": "outra", "depois": "coisa"}]


def test_juncao_perto_do_comeco_do_video():
    """A 1ª emenda a 1,2 s: a janela começa no 0 e a junção fica a 1,2 s dentro dela, não a 2 s."""
    w = lambda t, a: {"text": t, "start": a, "end": a + 0.2}  # noqa: E731
    assert ce.lados([w("oi", 0.5), w("tudo", 1.4)], [1.2]) == [{"em": 1.2, "antes": "oi", "depois": "tudo"}]


def test_sem_os_trechos_do_render_as_juncoes_vem_do_edl(tmp_path):
    edl = {"sources": {"A": "a.mp4"}, "ranges": [{"source": "A", "start": 0.0, "end": 2.0},
                                                {"source": "A", "start": 5.0, "end": 8.3, "velocidade": 1.1},
                                                {"source": "A", "start": 9.0, "end": 10.0}]}
    (tmp_path / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    j = ce.juncoes(tmp_path)
    assert len(j) == 2 and abs(j[0] - 2.0) < 0.05 and abs(j[1] - (2.0 + 3.3 / 1.1)) < 0.05
