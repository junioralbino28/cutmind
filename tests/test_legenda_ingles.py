"""A legenda empilhada de um vídeo falado em inglês: o destaque cai em palavra de conteúdo, nunca em
"the" ou "of", e a lista certa sai do idioma que o WhisperX gravou na transcrição."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import caption_style as cs  # noqa: E402


def palavras(texto: str, passo: int = 420) -> list[dict]:
    """Uma palavra a cada `passo` ms, cada uma dita por 360 ms (longa o bastante para ficar sozinha)."""
    return [{"text": w, "startMs": i * passo, "endMs": i * passo + 360} for i, w in enumerate(texto.split())]


def test_o_idioma_vem_da_transcricao(tmp_path):
    en = tmp_path / "en.json"
    en.write_text(json.dumps({"language": "en", "words": []}), encoding="utf-8")
    pt = tmp_path / "pt.json"
    pt.write_text(json.dumps({"words": []}), encoding="utf-8")
    assert cs.idioma_da_transcricao(en) == "en"
    assert cs.idioma_da_transcricao(pt) == "pt"  # sem o campo: o que o kit sempre fez
    assert cs.idioma_da_transcricao(tmp_path / "nao-existe.json") == "pt"
    assert cs.listas("en-US") is cs.LISTAS["en"] and cs.listas("pt-BR") is cs.LISTAS["pt"]
    assert cs.listas("es") is cs.LISTAS["en"]  # fora do português, as listas do inglês


def test_em_ingles_o_destaque_vai_para_a_palavra_de_conteudo():
    cues = cs.build_cues(palavras("the free course"), "en")
    assert len(cues) == 1
    linhas = [" ".join(w["text"] for w in ln) for ln in cues[0]["lines"]]
    destaque = [linhas[i] for i, s in enumerate(cues[0]["lineStyles"]) if s == 2]
    assert destaque and "free" in destaque[0] and destaque[0] != "the"
    # com as listas do português, "free" não é palavra de destaque
    assert not any(cs.norm(w) in cs.LISTAS["pt"].emph for w in ("the", "free", "course"))


def test_em_ingles_palavra_de_ligacao_nao_fica_sozinha_na_tela():
    en, pt = cs.LISTAS["en"], cs.LISTAS["pt"]
    assert cs.is_degenerate({"text": "the", "startMs": 0, "endMs": 400}, en)
    assert not cs.is_degenerate({"text": "the", "startMs": 0, "endMs": 400}, pt)  # "the" não é português
    assert not cs.is_degenerate({"text": "free", "startMs": 0, "endMs": 400}, en)
    # "free" sozinha é um golpe e sai circulada; "Don’t" (apóstrofo curvo) conta como negação
    solo = cs.build_cues(palavras("free"), "en")
    assert solo[0]["preset"] == "SOLO_OUTLINE"
    assert cs.norm("Don’t") in en.neg


def test_a_previa_e_o_render_evitam_as_mesmas_palavras_no_fim_da_linha():
    """A prévia do editor (estilos.js) espelha o render (SimpleCaptions.tsx): mesma lista, nos dois idiomas."""
    import re
    raiz = Path(__file__).resolve().parents[1]
    render = re.search(r"const ORPHAN = (/\^\(.*?\)\$/i);", (raiz / "assets/shortform/src/SimpleCaptions.tsx").read_text(encoding="utf-8"))
    previa = re.search(r"const ORPHAN = (/\^\(.*?\)\$/i);", (raiz / "assets/preview/estilos.js").read_text(encoding="utf-8"))
    assert render and previa, "não achei a lista ORPHAN"
    assert render.group(1) == previa.group(1)
    palavras = set(render.group(1)[3:-4].split("|"))
    assert {"de", "que", "e"} <= palavras and {"the", "of", "and", "to"} <= palavras
