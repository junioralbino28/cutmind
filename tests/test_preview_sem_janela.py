"""No Windows, o servidor de prévia não pode abrir janela de terminal.

O servidor chama ffprobe/ffmpeg o tempo todo. Se ele nascer SEM console
(DETACHED_PROCESS), cada chamada ganha um console novo e o Windows abre uma
janela de terminal a cada poucos segundos. CREATE_NO_WINDOW sozinho dá ao
servidor um console escondido, que os filhos herdam. A documentação da
Microsoft diz que CREATE_NO_WINDOW é IGNORADO quando vem com DETACHED_PROCESS.
"""
import re
from pathlib import Path

FONTE = (Path(__file__).resolve().parents[1] / "helpers" / "start_preview.py").read_text(encoding="utf-8")


def _flags_do_windows() -> str:
    # a atribuição com flags do subprocess (a outra é `creationflags = 0`); comentários ficam de fora
    m = re.search(r"^\s+creationflags = (subprocess\.[^\n#]+)", FONTE, re.M)
    assert m, "não achei a linha de creationflags do Windows em start_preview.py"
    return m.group(1)


def test_servidor_nasce_com_console_escondido():
    flags = _flags_do_windows()
    assert "CREATE_NO_WINDOW" in flags


def test_servidor_nao_nasce_sem_console():
    assert "DETACHED_PROCESS" not in _flags_do_windows()
