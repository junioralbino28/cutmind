"""A transcrição que fica sem memória desce de lote em vez de cair, e pede menos memória desde o início.

Medido em 03/11/2026 nos vídeos de teste: mesmas palavras e tempos com os lotes 8, 4, 2 e 1. As quedas eram
`mkl_malloc: failed to allocate memory`, num PC com pouca memória virtual livre. Aqui o WhisperX é falso.
"""
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("transcribe_memoria", RAIZ / "helpers" / "transcribe.py")
t = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(t)

MKL = "mkl_malloc: failed to allocate memory"


@pytest.fixture
def wx(monkeypatch):
    """Um WhisperX de mentira: `erros` diz em que lotes a 1ª passada cai, `erro_alinhar` faz o alinhador cair."""
    visto = {"lotes": [], "erros": {}, "erro_alinhar": None, "erro_carregar": None, "vivos_ao_alinhar": None, "pack": None}
    m = types.ModuleType("whisperx")
    m.load_audio = lambda caminho: [0.0] * 16000

    class Modelo:
        def transcribe(self, audio, batch_size, language):
            visto["lotes"].append(batch_size)
            if batch_size in visto["erros"]:
                raise visto["erros"][batch_size]
            return {"segments": [{"text": "oi", "start": 0.0, "end": 1.0}], "language": "pt"}

        def __del__(self):
            visto["apagou"] = True

    def load_model(*a, **k):
        visto["pack"] = os.environ.get("CT2_PACKED_GEMM")
        if visto["erro_carregar"]:
            raise visto["erro_carregar"]
        return Modelo()

    def load_align_model(language_code, device):
        visto["vivos_ao_alinhar"] = visto.get("apagou", False)
        if visto["erro_alinhar"]:
            raise visto["erro_alinhar"]
        return object(), {}

    m.load_model = load_model
    m.load_align_model = load_align_model
    m.align = lambda segs, *a, **k: {"segments": [{"text": "oi", "words": [{"word": "oi", "start": 0.1, "end": 0.4}]}]}
    monkeypatch.setitem(sys.modules, "whisperx", m)
    monkeypatch.setitem(sys.modules, "modelo_whisper", types.SimpleNamespace(para_o_processador=lambda aviso: None))
    monkeypatch.setattr(t, "_whisperx_device", lambda: ("cpu", "int8"))
    monkeypatch.setenv("CT2_PACKED_GEMM", "x")
    monkeypatch.delenv("CT2_PACKED_GEMM")
    return visto


def test_sem_falta_de_memoria_usa_so_o_lote_4_no_processador(wx):
    r = t.call_whisperx(Path("x.wav"), language="pt")
    assert wx["lotes"] == [4] and r["text"] == "oi" and r["_aligned"] is True


def test_na_placa_continua_o_lote_de_sempre(wx, monkeypatch):
    monkeypatch.setattr(t, "_whisperx_device", lambda: ("cuda", "float16"))
    t.call_whisperx(Path("x.wav"), language="pt")
    assert wx["lotes"] == [8]


@pytest.mark.parametrize("erro", [RuntimeError(MKL), MemoryError(), RuntimeError("[enforce fail] DefaultCPUAllocator: not enough memory"), RuntimeError("CUDA out of memory")])
def test_falta_de_memoria_desce_de_lote_e_a_transcricao_sai(wx, erro):
    wx["erros"] = {4: erro}
    r = t.call_whisperx(Path("x.wav"), language="pt")
    assert wx["lotes"] == [4, 2] and r["text"] == "oi"


def test_cai_em_todos_os_lotes_e_a_mensagem_diz_o_que_fazer(wx):
    wx["erros"] = {4: RuntimeError(MKL), 2: RuntimeError(MKL), 1: RuntimeError(MKL)}
    with pytest.raises(RuntimeError, match="out of memory.*Close the heavy programs"):
        t.call_whisperx(Path("x.wav"), language="pt")
    assert wx["lotes"] == [4, 2, 1]


def test_outro_erro_nao_vira_falta_de_memoria(wx):
    wx["erros"] = {4: RuntimeError("arquivo corrompido")}
    with pytest.raises(RuntimeError, match="corrompido"):
        t.call_whisperx(Path("x.wav"), language="pt")
    assert wx["lotes"] == [4]


def test_faltar_memoria_ao_abrir_o_modelo_diz_o_que_fazer(wx):
    wx["erro_carregar"] = OSError("[WinError 1455] The paging file is too small for this operation to complete")
    with pytest.raises(RuntimeError, match="Close the heavy programs"):
        t.call_whisperx(Path("x.wav"), language="pt")


def test_faltar_memoria_no_alinhador_nao_vira_tempo_grosseiro_em_silencio(wx):
    wx["erro_alinhar"] = RuntimeError("[enforce fail] DefaultCPUAllocator: not enough memory")
    with pytest.raises(RuntimeError, match="Close the heavy programs"):
        t.call_whisperx(Path("x.wav"), language="pt")


def test_alinhador_sem_modelo_da_lingua_continua_saindo_sem_alinhar(wx):
    wx["erro_alinhar"] = ValueError("no default align-model for language xx")
    r = t.call_whisperx(Path("x.wav"), language="pt")
    assert r["_aligned"] is False


def test_o_whisper_sai_da_memoria_antes_do_alinhador(wx):
    t.call_whisperx(Path("x.wav"), language="pt")
    assert wx["vivos_ao_alinhar"] is True  # o __del__ do modelo já rodou quando o alinhador carrega


def test_os_pesos_nao_sao_empacotados_e_quem_roda_pode_mudar(wx, monkeypatch):
    t.call_whisperx(Path("x.wav"), language="pt")
    assert wx["pack"] == "0"
    monkeypatch.setenv("CT2_PACKED_GEMM", "1")
    t.call_whisperx(Path("x.wav"), language="pt")
    assert wx["pack"] == "1"


def test_a_chave_ainda_existe_no_ctranslate2():
    """Com outro nome, o kit voltaria a reservar 6,6 GB para um modelo de 1,45 GB, sem aviso. O CTranslate2 lê a chave
    no próprio binário: ela tem de aparecer nele."""
    spec = importlib.util.find_spec("ctranslate2")
    pasta = Path(spec.origin).parent
    binarios = [*pasta.glob("*.dll"), *pasta.glob("*.so*"), *pasta.glob("*.dylib"), *pasta.parent.glob("ctranslate2.libs/*")]
    assert any(b"CT2_PACKED_GEMM" in p.read_bytes() for p in binarios if p.is_file())
