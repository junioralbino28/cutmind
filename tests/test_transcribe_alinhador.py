"""O alinhador não baixa o mesmo modelo duas vezes.

O alinhador de português só tem `pytorch_model.bin` na versão principal do Hugging Face.
Sem a chave DISABLE_SAFETENSORS_CONVERSION, o transformers baixa em segundo plano um
`model.safetensors` de 1,2 GB que nunca usa. Aqui o WhisperX é falso: o teste confere que a
chave já está ligada quando o alinhador carrega e que o nome dela ainda existe no
transformers instalado.
"""
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("transcribe_alinhador",
                                               RAIZ / "helpers" / "transcribe.py")
t = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t)

CHAVE = "DISABLE_SAFETENSORS_CONVERSION"


@pytest.fixture
def whisperx_falso(monkeypatch):
    """Um WhisperX de mentira que anota o valor da chave na hora de carregar o alinhador."""
    visto = {}
    wx = types.ModuleType("whisperx")
    wx.load_audio = lambda caminho: [0.0] * 16000

    class Modelo:
        def transcribe(self, audio, batch_size, language):
            return {"segments": [], "language": "pt"}

    def load_align_model(language_code, device):
        visto["chave"] = os.environ.get(CHAVE)
        return object(), {}

    wx.load_model = lambda *a, **k: Modelo()
    wx.load_align_model = load_align_model
    wx.align = lambda *a, **k: {"segments": []}
    monkeypatch.setitem(sys.modules, "whisperx", wx)
    monkeypatch.setattr(t, "_whisperx_device", lambda: ("cpu", "int8"))
    # setenv antes do delenv: assim o monkeypatch devolve a variável ao estado de antes,
    # inclusive o valor que o próprio call_whisperx gravar
    monkeypatch.setenv(CHAVE, "x")
    monkeypatch.delenv(CHAVE)
    return visto


def test_alinhador_carrega_com_a_chave_ligada(whisperx_falso):
    t.call_whisperx(Path("x.wav"), language="pt")
    assert whisperx_falso["chave"] == "true"   # o transformers só aceita exatamente "true"


def test_escolha_de_quem_roda_e_respeitada(whisperx_falso, monkeypatch):
    monkeypatch.setenv(CHAVE, "false")
    t.call_whisperx(Path("x.wav"), language="pt")
    assert whisperx_falso["chave"] == "false"


def test_a_chave_ainda_existe_no_transformers():
    """Se uma versão nova do transformers trocar o nome, o kit volta a baixar 1,2 GB sem aviso."""
    spec = importlib.util.find_spec("transformers")
    fonte = (Path(spec.origin).parent / "modeling_utils.py").read_text(encoding="utf-8")
    assert f'os.getenv("{CHAVE}", None) != "true"' in fonte
