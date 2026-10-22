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


def test_aviso_conta_o_volume_das_tomadas(tmp_path):
    aviso = _salvo(tmp_path, {"ranges": [{"source": "A", "beat": "HOOK", "volume": 0.5},
                                         {"source": "A", "beat": "CTA"},
                                         {"source": "B", "volume": 2}],
                              "changes": [], "removed": [], "ops": {"volume": 2}})
    assert "volume mudado em 2 take(s)" in aviso
    assert "take 1 (HOOK): 50%" in aviso and "take 3 (B): 200%" in aviso
    assert "take 2" not in aviso  # sem `volume`: 100%, nada a dizer


def test_aviso_conta_a_velocidade_das_tomadas(tmp_path):
    aviso = _salvo(tmp_path, {"ranges": [{"source": "A", "beat": "HOOK", "velocidade": 2},
                                         {"source": "B", "velocidade": 0.5}, {"source": "A"}],
                              "changes": [], "removed": [], "ops": {"velocidade": 2}})
    assert "velocidade mudada em 2 take(s)" in aviso
    assert "take 1 (HOOK): 2×" in aviso and "take 2 (B): 0.5×" in aviso and "take 3" not in aviso


def test_aviso_conta_a_curva_das_tomadas(tmp_path):
    curva = {"nome": "montagem", "pontos": [[0, 0.9], [0.1, 0.9], [0.5, 6.8], [0.65, 0.3], [0.8, 1], [1, 1]]}
    aviso = _salvo(tmp_path, {"ranges": [{"source": "A", "beat": "HOOK", "curva": curva}, {"source": "B"}],
                              "changes": [], "removed": [], "ops": {"curva": 1}})
    assert "curva de velocidade em 1 take(s)" in aviso
    assert "take 1 (HOOK): curva montagem, 6 pontos" in aviso and "take 2" not in aviso


def test_aviso_do_editor_de_pc_continua_igual(tmp_path):
    aviso = _salvo(tmp_path, {"ranges": [], "changes": [{}], "removed": [{}]})
    assert "1 take(s) reajustado(s), 1 take(s) removido(s)" in aviso
    assert "lista inteira" not in aviso


def test_aviso_conta_as_camadas(tmp_path):
    """Imagem e áudio postos no editor: o agente precisa saber o que entra no vídeo final,
    o que ficou de fora (silenciada) e quais helpers aplicam."""
    camadas = {"versao": 1, "video": {"mudo": True}, "faixas": [
        {"id": "i1", "tipo": "imagem", "oculto": False, "travado": False,
         "itens": [{"id": "i1-1", "arquivo": "midia/print.png", "inicio": 5, "duracao": 3}]},
        {"id": "a1", "tipo": "audio", "mudo": False, "travado": False,
         "itens": [{"id": "a1-1", "arquivo": "midia/Gravação.m4a", "inicio": 2, "duracao": 4,
                    "corte": 0, "volume": 1.5, "melhorar": True}]},
        {"id": "a2", "tipo": "audio", "mudo": True, "travado": False,
         "itens": [{"id": "a2-1", "arquivo": "midia/b.m4a", "inicio": 0, "duracao": 1,
                    "corte": 0, "volume": 1, "melhorar": False}]}]}
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "camadas": camadas}, ensure_ascii=False), encoding="utf-8")
    aviso = digest(p)
    assert "camadas: 1 imagem, 2 áudios" in aviso
    assert '"Gravação.m4a"' in aviso and "volume 150%" in aviso and "melhorar" in aviso
    assert "silenciada" in aviso
    assert "som do vídeo desligado" in aviso
    assert "camadas_edit_data.py" in aviso and "mixar_final.py" in aviso


def test_corte_e_camadas_no_mesmo_salvar_pede_remapear(tmp_path):
    """Os tempos das camadas são do corte que estava na tela: se o mesmo Salvar refaz o
    corte, o agente tem de levar as camadas para o corte novo antes de montar."""
    p = tmp_path / "preview_edits.json"
    camadas = {"video": {"mudo": False}, "faixas": []}
    p.write_text(json.dumps({"type": "timeline-edits", "camadas": camadas,
                             "edl": {"ranges": [], "changes": [{}], "removed": []}}), encoding="utf-8")
    assert "corte ANTIGO" in digest(p)
    p.write_text(json.dumps({"type": "timeline-edits", "camadas": camadas}), encoding="utf-8")
    assert "corte ANTIGO" not in digest(p)


def test_aviso_diz_que_e_trilha_da_biblioteca(tmp_path):
    p = tmp_path / "preview_edits.json"
    camadas = {"video": {"mudo": False}, "faixas": [{"id": "a1", "tipo": "audio", "mudo": False, "itens": [
        {"id": "a1-1", "arquivo": "midia/calma-01.m4a", "inicio": 0, "duracao": 30, "volume": 0.15,
         "trilha": "calma-01"}]}]}
    p.write_text(json.dumps({"type": "timeline-edits", "camadas": camadas}), encoding="utf-8")
    aviso = digest(p)
    assert 'trilha "calma-01" (biblioteca) de 0:00.00' in aviso and "volume 15%" in aviso


def test_aviso_conta_os_efeitos_e_diz_quem_aplica(tmp_path):
    p = tmp_path / "preview_edits.json"
    efeitos = {"versao": 1, "itens": [
        {"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 2, "duracao": 3.5, "intensidade": 0.8},
        {"id": "t1", "tipo": "transicao", "pacote": "zoom-central", "corte": 4.2, "duracao": 1.1}]}
    p.write_text(json.dumps({"type": "timeline-edits", "efeitos": efeitos}), encoding="utf-8")
    aviso = digest(p)
    assert "efeitos: 1 filtro, 1 transição" in aviso
    assert 'filtro "filme-pb" de 0:02.00 a 0:05.50, intensidade 80%' in aviso
    assert 'transição "zoom-central" no corte de 0:04.20 (1.1 s)' in aviso
    assert "efeitos_render.py" in aviso
    p.write_text(json.dumps({"type": "timeline-edits", "efeitos": efeitos,
                             "edl": {"ranges": [], "changes": [{}], "removed": []}}), encoding="utf-8")
    assert "corte ANTIGO" in digest(p)
    efeitos["itens"].append({"id": "a1", "tipo": "ajuste", "inicio": 2, "duracao": 3.5,
                             "ajustes": {"brilho": 20, "vinheta": -35}})
    p.write_text(json.dumps({"type": "timeline-edits", "efeitos": efeitos}), encoding="utf-8")
    aviso = digest(p)
    assert "efeitos: 1 filtro, 1 transição, 1 ajuste" in aviso
    assert "ajuste de 0:02.00 a 0:05.50: brilho +20, vinheta -35" in aviso


def test_aviso_de_camadas_vazias(tmp_path):
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "camadas": {"video": {"mudo": False}, "faixas": []}}), encoding="utf-8")
    assert "camadas: nenhuma" in digest(p)  # tirou tudo: o agente tira do vídeo final também


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
