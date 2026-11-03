"""O som na entrada dos textos e das fotos: camadas de verdade, no volume medido contra a voz do trecho."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import camadas as cam  # noqa: E402
import efeitos_sonoros as es  # noqa: E402
import sons_entrada as se  # noqa: E402


def test_so_entra_texto_em_destaque_e_foto_e_grafico_ligado():
    camadas = {"faixas": [
        {"id": "t1", "tipo": "texto", "itens": [
            {"id": "a", "inicio": 1.0, "estilo": {"tamanho": 1.5}}, {"id": "b", "inicio": 3.0, "estilo": {"tamanho": 0.6}}, {"id": "c", "inicio": 5.0}]},
        {"id": "t2", "tipo": "texto", "oculto": True, "itens": [{"id": "d", "inicio": 6.0}]},
        {"id": "i1", "tipo": "imagem", "itens": [{"id": "e", "inicio": 7.0, "arquivo": "midia/foto.jpg"}, {"id": "f", "inicio": 8.0, "arquivo": "midia/clipe.mp4"}]},
        {"id": "a1", "tipo": "audio", "itens": [{"id": "g", "inicio": 9.0, "arquivo": "midia/voz.m4a"}]},
    ]}
    ed = {"graficos": [
        {"tipo": "grande", "start": 10.0, "end": 12.0, "at": 10.5, "t": "X"},
        {"tipo": "maquina", "start": 13.0, "end": 14.0},  # tem o som de tecla
        {"tipo": "palavras", "start": 15.0, "end": 17.0, "itens": [{"t": "a", "at": 15.2}, {"t": "b", "at": 16.0}]},
        {"tipo": "contador", "start": 18.0, "end": 19.0, "desligada": True},
        {"tipo": "pula", "start": 20.0, "end": 22.0, "itens": [{"t": "a", "at": 20.1}, {"t": "b", "at": 20.4}]},  # um som só
    ]}
    assert se.entradas(camadas, ed) == [(1.0, "texto"), (5.0, "texto"), (7.0, "foto"), (10.5, "texto"), (15.2, "texto"), (16.0, "texto"), (20.0, "texto")]


def test_dois_colados_viram_um():
    camadas = {"faixas": [{"id": "t", "tipo": "texto", "itens": [{"inicio": 2.0}, {"inicio": 2.1}, {"inicio": 2.3}]}]}
    assert [t for t, _ in se.entradas(camadas, {})] == [2.0, 2.3]


def test_todo_tipo_de_grafico_tem_um_destino():
    """Tipo novo em graficos.py sem decidir aqui entraria mudo sem ninguém notar."""
    import graficos
    sem_som = {"comenta", "maquina", "prompt"}  # digitam: têm som de tecla ou o agente põe
    assert set(graficos.TIPOS) == se._NO_AT | se._NO_START | se._POR_ITEM | sem_som


def test_o_volume_acompanha_a_voz_do_trecho():
    voz = np.zeros(se.SR * 4, dtype=np.float32)
    voz[se.SR * 1:se.SR * 1 + 2000] = 0.5  # fala forte em 1 s
    voz[se.SR * 3:se.SR * 3 + 2000] = 0.2  # fala baixa em 3 s
    forte = se.volume_contra_a_voz(voz, 1.0, 0.0, 0.3)
    fraca = se.volume_contra_a_voz(voz, 3.0, 0.0, 0.3)
    assert forte == pytest.approx(0.5 * 10 ** (-se.MARGEM_DB / 20), abs=0.01)  # o pico do som MARGEM_DB abaixo do da voz
    assert fraca == pytest.approx(0.2 * 10 ** (-se.MARGEM_DB / 20), abs=0.01)
    assert se.volume_contra_a_voz(voz, 2.0, 0.0, 0.3) == 0.3  # sem fala por perto: o do catálogo


@pytest.fixture
def projeto(tmp_path):
    edit = tmp_path / "edit"
    pub = edit / "remotion" / "public"
    pub.mkdir(parents=True)
    # 4 s com fala (ruído alto) só entre 0,5 e 3,5 s
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=4:c=pink:a=0.5:r=48000", "-af", "volume='if(between(t,0.5,3.5),1,0)':eval=frame", str(edit / "cut.mp4")], check=True)
    (edit / "state.json").write_text(json.dumps({"video": "cut.mp4", "editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps({"graficos": [{"tipo": "grande", "start": 1.0, "end": 2.0, "t": "X", "at": 1.0}]}), encoding="utf-8")
    cam.save(edit / "camadas.json", cam.normalize({"versao": 1, "video": {"mudo": False}, "faixas": [
        {"id": "i1", "tipo": "imagem", "itens": [{"id": "e", "arquivo": "midia/f.jpg", "inicio": 2.0, "duracao": 1.0}]},
        {"id": "a1", "tipo": "audio", "itens": [{"id": "a", "arquivo": "midia/v.m4a", "inicio": 0.0, "corte": 0.0, "duracao": 1.0, "volume": 0.3, "melhorar": False}]},
    ]}))
    (edit / "midia").mkdir()
    return edit


def _sons(monkeypatch):
    """Sons do kit no lugar do viral e do gravado: o teste não baixa nada."""
    real = es.usar

    def usar(edit, sid, pasta=es.PASTA):
        return real(edit, {"v-whoosh": "whoosh", "g-camera": "clique"}.get(sid, sid), pasta)

    monkeypatch.setattr(es, "usar", usar)
    monkeypatch.setattr(se, "_do_catalogo", lambda sid: next(s for s in es.catalogo() if s["id"] == {"v-whoosh": "whoosh", "g-camera": "clique"}.get(sid, sid)))


def test_aplicar_cria_a_faixa_editavel_e_refazer_nao_duplica(projeto, monkeypatch):
    _sons(monkeypatch)
    r = se.aplicar(projeto)
    assert r == {"sons": 2, "textos": 1, "fotos": 1}
    c = cam.load(projeto / "camadas.json")  # passa na validação do editor
    f = next(x for x in c["faixas"] if x["id"] == se.FAIXA)
    assert f["tipo"] == "audio" and len(f["itens"]) == 2
    texto, foto = f["itens"]
    assert texto["inicio"] == pytest.approx(1.0 - 0.25, abs=0.001)  # o golpe do whoosh cai na entrada
    assert foto["inicio"] == 2.0 and foto["arquivo"] == "midia/sfx-clique.mp3"
    assert (projeto / "midia" / "sfx-whoosh.mp3").is_file()
    assert any(x["id"] == "a1" for x in c["faixas"])  # o áudio da pessoa fica
    se.aplicar(projeto)
    assert sum(x["id"] == se.FAIXA for x in cam.load(projeto / "camadas.json")["faixas"]) == 1


def test_remover_tira_so_a_faixa_de_sons(projeto, monkeypatch):
    _sons(monkeypatch)
    se.aplicar(projeto)
    se.remover(projeto)
    ids = [x["id"] for x in cam.load(projeto / "camadas.json")["faixas"]]
    assert se.FAIXA not in ids and "a1" in ids


def test_som_que_nao_existe_para_com_a_lista(projeto):
    with pytest.raises(se.SonsInvalidos, match="não existe"):
        se.aplicar(projeto, som_texto="foguete")


def test_o_viral_que_nao_desce_cai_na_reserva(projeto, monkeypatch):
    real = es.usar

    def usar(edit, sid, pasta=es.PASTA):
        if sid in ("v-whoosh", "g-camera"):
            raise es.pk.PacoteErro("sem internet")
        return real(edit, sid, pasta)

    monkeypatch.setattr(es, "usar", usar)
    monkeypatch.setattr(se, "RESERVA_TEXTO", "whoosh")
    r = se.aplicar(projeto)
    assert r["sons"] == 2
    assert any(i["arquivo"] == "midia/sfx-whoosh.mp3" for f in cam.load(projeto / "camadas.json")["faixas"] if f["id"] == se.FAIXA for i in f["itens"])
