"""As imagens das camadas viram inserts no edit-data.json, sem mexer nos inserts do agente."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from camadas_edit_data import aplicar  # noqa: E402


@pytest.fixture
def projeto(tmp_path):
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    (edit / "midia").mkdir()
    (edit / "midia" / "Print do repositório.png").write_bytes(b"png1")
    (edit / "midia" / "outro.jpg").write_bytes(b"jpg2")
    (edit / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    agente = {"src": "inserts/grafico.png", "start": 1.0, "end": 2.0}
    (public / "edit-data.json").write_text(json.dumps({"fps": 30, "inserts": [agente]}), encoding="utf-8")
    return edit, public, agente


def _camadas(edit, faixas):
    (edit / "camadas.json").write_text(json.dumps({"versao": 1, "video": {"mudo": False}, "faixas": faixas},
                                                  ensure_ascii=False), encoding="utf-8")


def _img(fid, arquivo, inicio, duracao, oculto=False):
    return {"id": fid, "tipo": "imagem", "oculto": oculto, "travado": False,
            "itens": [{"id": f"{fid}-1", "arquivo": arquivo, "inicio": inicio, "duracao": duracao}]}


def _inserts(public):
    return json.loads((public / "edit-data.json").read_text(encoding="utf-8"))["inserts"]


def test_imagem_visivel_vira_insert_e_a_escondida_fica_fora(projeto):
    edit, public, agente = projeto
    _camadas(edit, [_img("i1", "midia/Print do repositório.png", 5, 3),
                    _img("i2", "midia/outro.jpg", 9, 2, oculto=True)])
    r = aplicar(edit)
    assert r == {"inserts": 1, "faltando": []}
    ins = _inserts(public)
    assert ins[0] == agente  # o do agente fica, no mesmo lugar
    assert ins[1] == {"src": "midia/camada-i1-1.png", "start": 5.0, "end": 8.0, "camada": "i1-1"}
    assert (public / "midia" / "camada-i1-1.png").read_bytes() == b"png1"  # nome sem espaço nem acento
    assert not (public / "midia" / "camada-i2-1.jpg").exists()


def test_rodar_de_novo_nao_duplica_e_o_que_saiu_sai_do_video(projeto):
    edit, public, agente = projeto
    _camadas(edit, [_img("i1", "midia/Print do repositório.png", 5, 3), _img("i2", "midia/outro.jpg", 9, 2)])
    aplicar(edit)
    aplicar(edit)
    assert [i.get("camada") for i in _inserts(public)] == [None, "i1-1", "i2-1"]
    _camadas(edit, [_img("i2", "midia/outro.jpg", 9, 2)])  # a pessoa excluiu o print
    aplicar(edit)
    assert [i.get("camada") for i in _inserts(public)] == [None, "i2-1"]
    assert not (public / "midia" / "camada-i1-1.png").exists()  # a cópia antiga também sai


def test_arquivo_que_sumiu_e_avisado(projeto):
    edit, public, _ = projeto
    _camadas(edit, [_img("i1", "midia/nao-existe.png", 5, 3)])
    assert aplicar(edit) == {"inserts": 0, "faltando": ["midia/nao-existe.png"]}
    assert [i.get("camada") for i in _inserts(public)] == [None]
