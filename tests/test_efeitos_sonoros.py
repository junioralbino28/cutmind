"""A biblioteca de efeitos sonoros do kit (assets/sfx/): sons sintetizados pelo próprio kit, sem licença
de ninguém, com o golpe no instante 0 (o whoosh, no `golpe` do catálogo), e o caminho até o vídeo
(o editor põe como camada de áudio; o agente, pelo `usar` ou pelo `mixar_final --sfx`).

Os virais (meme, marca, série) entram pela lista `virais.json`: o áudio não mora no repositório, desce
da Release do repositório de pacotes na primeira vez, conferido por sha256."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import efeitos_sonoros as es  # noqa: E402
import pacotes as pk  # noqa: E402

PREVIEW = RAIZ / "assets" / "preview"
com_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")


def _pcm(p: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "f32le", "-ac", "1", "-ar", str(es.SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def test_o_catalogo_e_os_arquivos_batem():
    cat = es.catalogo()
    assert [x["id"] for x in cat] == [s[0] for s in es.SONS]
    for x in cat:
        assert (es.PASTA / x["arquivo"]).is_file(), x
        assert x["nome"] and x["nome_en"] and x["uso"] and 0.1 <= x["volume"] <= 1.0
    assert sorted(p.name for p in es.PASTA.glob("*.mp3")) == sorted(x["arquivo"] for x in cat)


@com_ffmpeg
def test_o_golpe_esta_no_instante_do_catalogo_e_o_pico_tem_folga():
    for x in es.catalogo():
        y = _pcm(es.PASTA / x["arquivo"])
        assert abs(len(y) / es.SR - x["duracao"]) < 0.01, x["id"]  # o atraso do MP3 não empurra o som
        env = np.abs(y)
        assert np.max(env) <= 10 ** (-1 / 20), x["id"]
        ataque = int(np.argmax(env > 0.25 * np.max(env))) / es.SR
        if x["golpe"]:
            assert abs(int(np.argmax(env)) / es.SR - x["golpe"]) < 0.03, x["id"]
        else:
            assert ataque < 0.01, (x["id"], ataque)  # posto num segundo, cai NAQUELE segundo


@com_ffmpeg
def test_gerar_de_novo_da_o_mesmo_arquivo(tmp_path):
    es.gerar(tmp_path)
    for x in es.catalogo():
        assert (tmp_path / x["arquivo"]).read_bytes() == (es.PASTA / x["arquivo"]).read_bytes(), x["id"]
    assert json.loads((tmp_path / es.CATALOGO).read_text(encoding="utf-8")) == es.catalogo()


def test_usar_copia_para_a_pasta_das_camadas(tmp_path):
    p = es.usar(tmp_path, "ding")
    assert p == tmp_path / "midia" / "sfx-ding.mp3" and p.read_bytes() == (es.PASTA / "ding.mp3").read_bytes()
    with pytest.raises(KeyError):
        es.usar(tmp_path, "foguete")


def test_o_editor_tem_a_folha_de_efeitos_sonoros():
    js = (PREVIEW / "celular.js").read_text(encoding="utf-8")
    html = (PREVIEW / "celular.html").read_text(encoding="utf-8")
    assert "tool(ctx, 'sfx', t('Efeitos sonoros')" in js and "case 'sfx':" in js
    assert 'id="sfxSheet"' in html and "/api/sfx/usar" in js
    assert "t('Virais')" in js and "s.viral" in js  # os virais num grupo à parte, com o aviso de anúncio
    en = (PREVIEW / "i18n-en.js").read_text(encoding="utf-8")
    assert '"Efeitos sonoros"' in en and '"Virais"' in en


def test_o_servidor_lista_e_entrega_os_efeitos(tmp_path):
    srv = (RAIZ / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    assert '"/api/sfx"' in srv and '"/api/sfx/usar"' in srv and '"/gen/sfx"' in srv
    assert "es.todos()" in srv and "es.arquivo(" in srv  # os virais também, baixados na hora


def test_o_audio_dos_virais_nao_mora_no_kit():
    """O som de meme, marca e série fica numa Release do repositório de pacotes (apagar é um comando,
    sem reescrever histórico); o kit leva só a lista, com tamanho e sha256 de cada um."""
    assert sorted(p.name for p in es.PASTA.glob("*.mp3")) == sorted(x["arquivo"] for x in es.catalogo())
    cat = pk.ler_catalogo(es.PASTA / es.VIRAIS)
    assert cat["base"].startswith("https://github.com/") and cat["repo"]
    assert all(p["tipo"] == "som" for p in cat["pacotes"])
    guia = (RAIZ / "references" / "efeitos-sonoros.md").read_text(encoding="utf-8")
    assert "paid ad" in guia.lower() and "mixar_final" in guia and "virais.json" in guia


def test_os_virais_tem_o_que_o_editor_precisa():
    vs = es.virais()
    assert len(vs) >= 10
    ids_kit = {x["id"] for x in es.catalogo()}
    for x in vs:
        assert x["id"].startswith("v-") and x["id"] not in ids_kit, x["id"]
        assert x["nome"] and x["nome_en"] and x["uso"] and x["viral"] is True
        assert 0.05 <= x["volume"] <= 1.0 and 0 <= x["golpe"] < 0.3 and x["duracao"] > x["golpe"], x["id"]
    assert [x["id"] for x in es.todos()] == [x["id"] for x in es.catalogo()] + [x["id"] for x in vs]


def _virais_de_mentira(tmp_path: Path, conteudo: bytes) -> Path:
    pasta = tmp_path / "sfx"
    pasta.mkdir()
    shutil.copy(es.PASTA / es.CATALOGO, pasta / es.CATALOGO)
    item = {"id": "v-teste", "tipo": "som", "nome": "Teste", "nome_en": "Test", "uso": "teste", "viral": True,
            "duracao": 0.5, "golpe": 0.01, "volume": 0.3, "release": "sons-1", "arquivo": "v-teste.mp3",
            "tamanho": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}
    cat = {"versao": 1, "repo": "dono/pacotes", "base": "https://example.invalid/download", "gerado": "x",
           "pacotes": [item]}
    (pasta / es.VIRAIS).write_text(json.dumps(cat), encoding="utf-8")
    return pasta


def test_usar_um_viral_baixa_uma_vez_confere_e_copia(tmp_path, monkeypatch):
    som = b"ID3 som de mentira" * 40
    pasta = _virais_de_mentira(tmp_path, som)
    monkeypatch.setenv("CUTMIND_PACOTES_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("CUTMIND_PACOTES_BASE", raising=False)
    pedidos = []

    def baixar(url, destino, limite):
        pedidos.append(url)
        Path(destino).write_bytes(som)

    monkeypatch.setattr(pk, "_http_baixar", baixar)
    p = es.usar(tmp_path / "edit", "v-teste", pasta)
    assert p == tmp_path / "edit" / "midia" / "sfx-v-teste.mp3" and p.read_bytes() == som
    assert pedidos == ["https://example.invalid/download/sons-1/v-teste.mp3"]
    assert (tmp_path / "cache" / "sons" / "som" / "v-teste.mp3").is_file()  # fora do cache da biblioteca
    es.usar(tmp_path / "edit2", "v-teste", pasta)
    assert len(pedidos) == 1  # a 2ª vez sai do cache


def test_viral_que_chega_diferente_nao_entra(tmp_path, monkeypatch):
    pasta = _virais_de_mentira(tmp_path, b"o som certo" * 30)
    monkeypatch.setenv("CUTMIND_PACOTES_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(pk, "_http_baixar", lambda url, destino, limite: Path(destino).write_bytes(b"x" * 330))
    with pytest.raises(pk.PacoteCorrompido):
        es.usar(tmp_path / "edit", "v-teste", pasta)
    assert not (tmp_path / "edit" / "midia" / "sfx-v-teste.mp3").exists()
    with pytest.raises(KeyError):
        es.arquivo("v-nao-existe", pasta)
