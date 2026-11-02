"""O Whisper em int8 que o kit baixa (modelo_whisper.py): confere o sha256, retoma o download que caiu e, se
der errado, deixa a transcrição seguir com o modelo de sempre. A rede é de mentira."""
import hashlib
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import modelo_whisper as mw  # noqa: E402

CONTEUDO = {"model.bin": b"pesos" * 1000, "config.json": b'{"a": 1}'}


@pytest.fixture
def rede(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTMIND_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(mw, "ARQUIVOS", {n: (len(c), hashlib.sha256(c).hexdigest()) for n, c in CONTEUDO.items()})
    monkeypatch.setattr(mw, "ja_tem_o_de_sempre", lambda: False)  # o PC do teste pode ter o float16 no cache
    pedidos = []
    servir = dict(CONTEUDO)

    class Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        nome = req.full_url.rsplit("/", 1)[1]
        faixa = req.headers.get("Range")
        pedidos.append((nome, faixa))
        dados = servir[nome]
        if faixa:
            r = Resp(dados[int(faixa.split("=")[1].rstrip("-")):])
            r.status = 206
            return r
        return Resp(dados)
    monkeypatch.setattr(mw.urllib.request, "urlopen", urlopen)
    return pedidos, servir


def test_baixa_confere_e_nao_baixa_de_novo(rede):
    pedidos, _ = rede
    p = mw.para_o_processador(lambda m: None)
    assert p and mw.pronto() and (Path(p) / "model.bin").read_bytes() == CONTEUDO["model.bin"]
    assert len(pedidos) == 2
    mw.para_o_processador(lambda m: None)
    assert len(pedidos) == 2  # pronto: nada de rede


def test_quem_ja_tem_o_de_sempre_nao_baixa_de_novo(rede, monkeypatch):
    pedidos, _ = rede
    monkeypatch.setattr(mw, "ja_tem_o_de_sempre", lambda: True)
    assert mw.para_o_processador(lambda m: None) is None and not pedidos


def test_o_menor_ja_baixado_vale_mesmo_com_o_de_sempre_no_cache(rede, monkeypatch):
    p = mw.para_o_processador(lambda m: None)
    monkeypatch.setattr(mw, "ja_tem_o_de_sempre", lambda: True)
    assert mw.para_o_processador(lambda m: None) == p


def test_download_que_caiu_continua_de_onde_parou(rede):
    pedidos, _ = rede
    destino = mw.pasta()
    destino.mkdir(parents=True)
    (destino / "model.bin.part").write_bytes(CONTEUDO["model.bin"][:1234])
    assert mw.para_o_processador(lambda m: None)
    assert ("model.bin", "bytes=1234-") in pedidos


def test_arquivo_errado_nao_fica_e_a_transcricao_segue_com_o_de_sempre(rede):
    _, servir = rede
    servir["model.bin"] = b"x" * len(CONTEUDO["model.bin"])  # o mesmo tamanho, outro conteúdo
    avisos = []
    assert mw.para_o_processador(avisos.append) is None
    assert not mw.pronto() and not (mw.pasta() / "model.bin").exists() and "indisponível" in avisos[-1]


def test_o_transcribe_so_usa_o_int8_no_processador():
    s = (Path(__file__).resolve().parents[1] / "helpers" / "transcribe.py").read_text(encoding="utf-8")
    assert 'if model_name == WHISPERX_MODEL and compute_type == "int8":' in s
    assert "modelo_whisper.para_o_processador(" in s
