"""O leitor de valores do ffprobe (edição real de 01/11): a vírgula que o ffprobe 8.1 põe no fim
da linha de `stream=` quando o vídeo traz dados extras (a gravação HLG do iPhone) zerava a contagem de
quadros e o atraso da imagem do corte, sem aviso."""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import gerar  # noqa: E402
import montagem  # noqa: E402
import sonda  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


def _ffprobe_com_virgula(monkeypatch, saida: str):
    def falso(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout=saida, stderr="")
    monkeypatch.setattr(sonda.subprocess, "run", falso)


def test_a_virgula_do_ffprobe_nao_zera_os_quadros(monkeypatch):
    _ffprobe_com_virgula(monkeypatch, "5568,\r\n")
    assert montagem._quadros(Path("cut.mp4")) == 5568


def test_a_virgula_do_ffprobe_nao_zera_o_atraso_da_imagem(monkeypatch):
    _ffprobe_com_virgula(monkeypatch, "0.021029,\r\n")
    assert gerar._atraso(Path("cut.mp4"), 30) == 1
    assert montagem.atraso_da_imagem(Path("cut.mp4")) == 1


def test_nenhum_leitor_de_stream_do_kit_le_csv_cru():
    """Leitor novo de `stream=` com `-of csv=p=0` e int()/float() direto volta a quebrar no vídeo do iPhone:
    use sonda.valor. Os de várias colunas (que dividem por vírgula) e os que já tiram a vírgula ficam."""
    ruins = []
    for p in sorted((RAIZ / "helpers").glob("*.py")):
        s = p.read_text(encoding="utf-8")
        for m in re.finditer(r'"stream=(\w+)"[^\n]*\n?[^\n]*"csv=p=0"', s):
            depois = s[m.end(): m.end() + 400]
            if 'split(",")' in depois or 'strip(",")' in depois or "bool(" in depois:
                continue
            ruins.append(f"{p.name}: stream={m.group(1)}")
    assert not ruins, ruins
