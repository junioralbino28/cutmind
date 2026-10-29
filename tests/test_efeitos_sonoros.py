"""A biblioteca de efeitos sonoros do kit (assets/sfx/): sons sintetizados pelo próprio kit, sem licença
de ninguém, com o golpe no instante 0 (o whoosh, no `golpe` do catálogo), e o caminho até o vídeo
(o editor põe como camada de áudio; o agente, pelo `usar` ou pelo `mixar_final --sfx`)."""
from __future__ import annotations

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
    en = (PREVIEW / "i18n-en.js").read_text(encoding="utf-8")
    assert '"Efeitos sonoros"' in en


def test_o_servidor_lista_e_entrega_os_efeitos(tmp_path):
    srv = (RAIZ / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    assert '"/api/sfx"' in srv and '"/api/sfx/usar"' in srv and '"/gen/sfx"' in srv


def test_nenhum_som_de_marca_no_kit():
    """Os virais de marca e de série ficam fora do kit público: só o guia diz onde achar."""
    nomes = " ".join(p.name.lower() for p in es.PASTA.iterdir())
    for marca in ("taco", "discord", "dexter", "iphone", "netflix", "windows"):
        assert marca not in nomes
    guia = (RAIZ / "references" / "efeitos-sonoros.md").read_text(encoding="utf-8")
    assert "paid ad" in guia.lower() and "mixar_final" in guia
