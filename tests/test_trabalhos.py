"""Um trabalho por projeto em segundo plano, com andamento que o editor pergunta."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import trabalhos as tb  # noqa: E402


def _espera(edit, ate=10.0):
    fim = time.time() + ate
    while tb.vivo(edit) and time.time() < fim:
        time.sleep(0.05)


def test_um_por_projeto_e_o_andamento_do_fim(tmp_path):
    cmd = [sys.executable, "-c", "import time; time.sleep(0.4)"]
    assert tb.iniciar(tmp_path, "corte", cmd) is True
    assert tb.iniciar(tmp_path, "gerar", cmd) is False          # o 1º ainda vive
    assert tb.vivo(tmp_path) == "corte" and tb.andamento(tmp_path)["vivo"] is True
    _espera(tmp_path)
    a = tb.andamento(tmp_path)
    assert a["etapa"] == "pronto" and a["vivo"] is False
    assert tb.iniciar(tmp_path, "gerar", cmd) is True            # acabou: outro pode começar
    _espera(tmp_path)


def test_processo_que_falha_mostra_a_ultima_linha(tmp_path):
    cmd = [sys.executable, "-c", "import sys; print('passo 1'); print('o disco encheu'); sys.exit(1)"]
    tb.iniciar(tmp_path, "corte", cmd)
    _espera(tmp_path)
    a = tb.andamento(tmp_path)
    assert a["etapa"] == "falhou" and a["erro"] == "o disco encheu"


def test_o_processo_escreve_o_proprio_andamento(tmp_path):
    arq = tb.pasta(tmp_path) / "andamento.json"
    codigo = (f"import sys; sys.path.insert(0, {str(Path(tb.__file__).parent)!r}); import trabalhos as tb; "
              f"tb.escritor({str(arq)!r}, 'corte')('corte', 'Refazendo o corte', 0.5); "
              f"tb.escritor({str(arq)!r}, 'corte')('pronto', 'Corte refeito', 1.0, avisos=['x'])")
    tb.iniciar(tmp_path, "corte", [sys.executable, "-c", codigo])
    _espera(tmp_path)
    a = tb.andamento(tmp_path)
    assert (a["etapa"], a["texto"], a["avisos"], a["vivo"]) == ("pronto", "Corte refeito", ["x"], False)
