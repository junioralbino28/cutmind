"""O aviso que o agente recebe quando o editor salva ajustes do corte."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from watch_edits import digest  # noqa: E402


def _salvo(tmp_path, edl):
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "edl": edl}), encoding="utf-8")
    return digest(p)


def test_aviso_conta_divisao_copia_e_ordem(tmp_path):
    aviso = _salvo(tmp_path, {"ranges": [], "changes": [{}], "removed": [],
                              "ops": {"divisoes": 1, "copias": 2, "ordemMudou": True}})
    assert "1 divisão(ões)" in aviso
    assert "2 take(s) duplicado(s)" in aviso
    assert "ordem dos takes mudou" in aviso
    assert "lista inteira" in aviso  # o agente monta o edl.json pela lista, não por changes/removed


def test_aviso_do_editor_de_pc_continua_igual(tmp_path):
    aviso = _salvo(tmp_path, {"ranges": [], "changes": [{}], "removed": [{}]})
    assert "1 take(s) reajustado(s), 1 take(s) removido(s)" in aviso
    assert "lista inteira" not in aviso


def test_aviso_de_estilo_conta_as_frases_posicionadas(tmp_path):
    from watch_edits import style_digest
    p = tmp_path / "preview_style.json"
    base = {"type": "style-setup", "captions": "karaoke", "captionsName": "Karaokê"}
    p.write_text(json.dumps({**base, "captionPositions": {"all": {"x": 0.5, "y": 0.3},
                                                            "phrases": [{"source": "A", "at": 1.0, "x": 0.5, "y": 0.2}]}}),
                 encoding="utf-8")
    aviso = style_digest(p)
    assert "todas as frases num lugar escolhido" in aviso and "1 frase(s) com lugar próprio" in aviso
    assert "caption_positions.py" in aviso
    p.write_text(json.dumps({**base, "captionPositions": {"all": None, "phrases": []}}), encoding="utf-8")
    assert "posição da legenda" not in style_digest(p)  # nada arrastado: nada a dizer
