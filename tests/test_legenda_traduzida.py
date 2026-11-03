"""A legenda em outro idioma: o agente traduz por frase, o helper reparte cada frase no tempo da original."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import legenda_traduzida as lt  # noqa: E402

SCRIPT = RAIZ / "helpers" / "legenda_traduzida.py"


def w(texto, a, b):
    return {"text": texto, "startMs": a, "endMs": b, "timestampMs": (a + b) // 2, "confidence": None}


FALA = [w("Oi", 0, 200), w("gente.", 250, 500), w("Isso", 600, 800), w("funciona", 850, 1200), w("mesmo", 1250, 1500),
        w("agora", 2600, 3000)]


@pytest.fixture
def edit(tmp_path):
    pub = tmp_path / "remotion" / "public"
    pub.mkdir(parents=True)
    (pub / "captions.json").write_text(json.dumps(FALA), encoding="utf-8")
    (pub / "edit-data.json").write_text(json.dumps({"captions": {"style": "karaoke", "enabled": True}}), encoding="utf-8")
    (tmp_path / "state.json").write_text(json.dumps({"editData": "remotion/public/edit-data.json", "captions": "remotion/public/captions.json"}), encoding="utf-8")
    return tmp_path


def _roda(*args):
    return subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")


def test_as_frases_quebram_na_pontuacao_e_na_pausa():
    fs = lt.frases_de(FALA)
    assert [[x["text"] for x in f] for f in fs] == [["Oi", "gente."], ["Isso", "funciona", "mesmo"], ["agora"]]


def test_frase_longa_demais_quebra_mesmo_sem_pausa():
    longa = [w(f"p{i}", i * 100, i * 100 + 90) for i in range(30)]
    assert all(len(f) <= lt.MAX_PALAVRAS for f in lt.frases_de(longa))


def test_a_traducao_ocupa_o_tempo_da_frase_original_sem_buraco_nem_atropelo():
    novas = lt.repartir(FALA[2:5], "This really works")
    assert [n["text"] for n in novas] == ["This", "really", "works"]
    assert novas[0]["startMs"] == 600 and novas[-1]["endMs"] == 1500
    for x, y in zip(novas, novas[1:]):
        assert x["endMs"] == y["startMs"] and x["endMs"] > x["startMs"]
    # a palavra maior fica mais tempo
    assert (novas[1]["endMs"] - novas[1]["startMs"]) > (novas[0]["endMs"] - novas[0]["startMs"])


def test_uma_traducao_para_cada_frase():
    with pytest.raises(lt.LegendaInvalida, match="3 frases e vieram 2"):
        lt.aplicar(FALA, ["Hi guys.", "This works"])
    with pytest.raises(lt.LegendaInvalida, match="vazia"):
        lt.aplicar(FALA, ["Hi guys.", "  ", "now"])


def test_aplicar_guarda_o_original_e_voltar_o_devolve(edit):
    pub = edit / "remotion" / "public"
    tr = edit / "tr.json"
    tr.write_text(json.dumps(["Hi guys.", "This really works", "now"]), encoding="utf-8")
    r = _roda("aplicar", edit, tr, "--idioma", "en")
    assert r.returncode == 0, r.stderr
    novas = json.loads((pub / "captions.json").read_text(encoding="utf-8"))
    assert [n["text"] for n in novas] == ["Hi", "guys.", "This", "really", "works", "now"]
    assert json.loads((pub / "captions.original.json").read_text(encoding="utf-8")) == FALA
    assert json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))["captions"]["idioma"] == "en"
    # trocar de idioma parte do original, não da tradução
    r = _roda("frases", edit)
    assert json.loads(r.stdout.splitlines()[1])["texto"] == "Isso funciona mesmo"
    tr.write_text(json.dumps(["Hola gente.", "Esto funciona de verdad", "ahora"]), encoding="utf-8")
    assert _roda("aplicar", edit, tr, "--idioma", "es").returncode == 0
    assert json.loads((pub / "captions.original.json").read_text(encoding="utf-8")) == FALA
    assert _roda("voltar", edit).returncode == 0
    assert json.loads((pub / "captions.json").read_text(encoding="utf-8")) == FALA
    assert not (pub / "captions.original.json").exists()
    assert "idioma" not in json.loads((pub / "edit-data.json").read_text(encoding="utf-8"))["captions"]


def test_contagem_errada_para_sem_gravar_nada(edit):
    pub = edit / "remotion" / "public"
    tr = edit / "tr.json"
    tr.write_text(json.dumps(["so uma"]), encoding="utf-8")
    r = _roda("aplicar", edit, tr, "--idioma", "en")
    assert r.returncode == 1 and "3 frases" in r.stderr
    assert json.loads((pub / "captions.json").read_text(encoding="utf-8")) == FALA
    assert not (pub / "captions.original.json").exists()
