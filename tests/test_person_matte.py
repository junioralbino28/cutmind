"""O recorte da pessoa (person_matte.py): o motor pelo ONNX Runtime, o modelo baixado e conferido, e
a cor da borda. Sem o modelo de verdade: a sessão do ONNX e o download são de mentira."""
from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import person_matte as pm  # noqa: E402


def test_compor_original_guarda_a_cor_e_misturada_tira_o_fundo_da_borda():
    verde = np.zeros((1, 3, 3), np.uint8)
    verde[..., 1] = 255  # a cor original: o fundo antigo verde vazando na borda
    pele = np.full((1, 3, 3), [200 / 255, 150 / 255, 130 / 255], np.float32)  # a cor da pessoa que o RVM devolve
    a = np.array([[1.0, 0.5, 0.0]], np.float32)
    orig = pm.compor(verde, a, pele, "original")
    assert orig[0, :, :3].tolist() == [[0, 255, 0]] * 3 and orig[0, :, 3].tolist() == [255, 127, 0]
    mist = pm.compor(verde, a, pele, "misturada")
    assert mist[0, 0, :3].tolist() == [0, 255, 0]  # dentro da pessoa, a cor de verdade
    assert mist[0, 1, :3].tolist() == [100, 203, 65]  # na borda, meio a meio
    assert mist[0, 2, :3].tolist() == [200, 150, 130]  # no fundo, só a cor da pessoa
    assert mist[0, :, 3].tolist() == orig[0, :, 3].tolist()  # o alfa é o mesmo


def test_motor_onnx_passa_o_estado_de_um_quadro_ao_seguinte(monkeypatch):
    import onnxruntime as ort
    entradas = []

    class Sessao:
        def __init__(self, caminho, providers):
            assert providers == ["CPUExecutionProvider"]

        def run(self, saidas, feed):
            entradas.append(feed)
            k = len(entradas)
            h, w = feed["src"].shape[2:]
            fgr = np.full((1, 3, h, w), 0.5, np.float32)
            pha = np.full((1, 1, h, w), 0.25 * k, np.float32)
            return [fgr, pha] + [np.full((1, 2, 2, 2), 10 * k + i, np.float32) for i in range(4)]

    monkeypatch.setattr(pm, "modelo_onnx", lambda: Path("rvm.onnx"))
    monkeypatch.setattr(ort, "InferenceSession", Sessao)
    motor = pm.MotorOnnx(0.25)
    rgb = np.full((4, 6, 3), 255, np.uint8)
    a1, f1 = motor(rgb)
    a2, _ = motor(rgb)
    assert a1.shape == (4, 6) and f1.shape == (4, 6, 3) and a1[0, 0] == 0.25 and a2[0, 0] == 0.5
    primeiro, segundo = entradas
    assert primeiro["src"].shape == (1, 3, 4, 6) and primeiro["src"].max() == 1.0
    assert all(primeiro[f"r{i}i"].shape == (1, 1, 1, 1) and not primeiro[f"r{i}i"].any() for i in range(1, 5))
    assert [segundo[f"r{i}i"][0, 0, 0, 0] for i in range(1, 5)] == [10, 11, 12, 13]  # o estado do 1º quadro
    assert segundo["downsample_ratio"].tolist() == [0.25]


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.mark.parametrize("certo", [True, False])
def test_modelo_onnx_so_fica_se_o_sha256_bate(tmp_path, monkeypatch, certo):
    dados = b"pesos de mentira"
    monkeypatch.setenv("CUTMIND_RECORTE_DIR", str(tmp_path))
    monkeypatch.setattr(pm, "RVM_ONNX", {"arquivo": "rvm.onnx", "tamanho": len(dados), "url": "https://exemplo/rvm.onnx",
                                         "sha256": hashlib.sha256(dados if certo else b"outro").hexdigest()})
    monkeypatch.setattr(pm.urllib.request, "urlopen", lambda req, timeout: _Resposta(dados))
    if certo:
        assert pm.modelo_onnx().read_bytes() == dados
        monkeypatch.setattr(pm.urllib.request, "urlopen", lambda req, timeout: pytest.fail("baixou de novo"))
        assert pm.modelo_onnx() == tmp_path / "rvm.onnx"  # já no cache: não baixa de novo
    else:
        with pytest.raises(SystemExit):
            pm.modelo_onnx()
        assert list(tmp_path.iterdir()) == []  # nem o arquivo nem o pedaço ficam
