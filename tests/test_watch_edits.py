"""O aviso que o agente recebe quando o editor salva ajustes do corte."""
from __future__ import annotations

import json
import sys
import time
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


def test_aviso_separa_o_pedido_escrito_das_marcacoes(tmp_path):
    """A caixa "O que você quer mudar?" manda um pedido sem trecho (`geral`): a agulha só situa."""
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "notes": [
        {"start": 12.5, "end": 12.5, "phase": 2, "text": "troca a música do final", "geral": True},
        {"start": 3, "end": 5, "phase": 1, "text": "tira essa pausa"},
    ]}), encoding="utf-8")
    aviso = digest(p)
    assert "1 pedido escrito, 1 marcação(ões)" in aviso
    assert "PEDIDO (agulha em 0:12.50, fase 2) troca a música do final" in aviso
    assert "[0:03.00 → 0:05.00] (fase 1) tira essa pausa" in aviso
    assert "0:12.50 → 0:12.50" not in aviso  # o pedido não vira um trecho de duração zero


def test_uma_vez_sai_no_primeiro_aviso(tmp_path):
    """`--uma-vez` roda como tarefa em segundo plano (sem o prazo do Monitor): o que já estava
    pendente sai na hora, e sem nada pendente ele espera o próximo Salvar e termina com o aviso."""
    import subprocess
    vigia = Path(__file__).resolve().parents[1] / "helpers" / "watch_edits.py"
    nota = {"type": "timeline-edits", "notes": [{"start": 1, "end": 1, "text": "pedido", "geral": True}]}
    pend = tmp_path / "pendente"
    pend.mkdir()
    (pend / "preview_edits.json").write_text(json.dumps(nota), encoding="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", str(vigia), str(pend), "--uma-vez"],
                       capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert r.returncode == 0 and "1 pedido escrito" in r.stdout

    vazio = tmp_path / "vazio"
    vazio.mkdir()
    p = subprocess.Popen([sys.executable, "-X", "utf8", str(vigia), str(vazio), "--uma-vez"],
                         stdout=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        time.sleep(1.0)
        assert p.poll() is None  # sem nada pendente, fica esperando
        (vazio / "preview_edits.json").write_text(json.dumps(nota), encoding="utf-8")
        out, _ = p.communicate(timeout=20)
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode == 0 and "PEDIDO (agulha em 0:01.00" in out


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


def test_aviso_conta_os_textos(tmp_path):
    camadas = {"versao": 1, "video": {"mudo": False}, "faixas": [
        {"id": "t1", "tipo": "texto", "oculto": False, "travado": False,
         "itens": [{"id": "t1-1", "texto": "Linha 1\nLinha 2", "inicio": 1, "duracao": 2, "x": 540, "y": 960,
                    "estilo": {}, "atras": True, "acompanhar": True, "curva": -30}]},
        {"id": "t2", "tipo": "texto", "oculto": True, "travado": False,
         "itens": [{"id": "t2-1", "texto": "fora", "inicio": 4, "duracao": 1, "x": 540, "y": 960,
                    "estilo": {}, "atras": False, "acompanhar": False, "curva": 0}]}]}
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "camadas": camadas}, ensure_ascii=False), encoding="utf-8")
    aviso = digest(p)
    assert "camadas: 2 textos" in aviso
    assert '"Linha 1 / Linha 2"' in aviso and "atrás da pessoa" in aviso and "acompanha a pessoa" in aviso
    assert "curva -30" in aviso and "escondido: fica fora" in aviso
    assert "textos[]" in aviso


def test_aviso_da_legenda(tmp_path):
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "editData": {"legenda": {
        "estilo": {"fonte": "Bebas Neue", "peso": 400, "cor": "#ffe500", "tamanho": 1.3}, "acompanhar": True}}}), encoding="utf-8")
    aviso = digest(p)
    assert "legenda mudada" in aviso and "fonte=Bebas Neue" in aviso and "ACOMPANHA" in aviso
    assert "captions" in aviso and "camadas_edit_data.py" in aviso


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


def test_aviso_dos_blocos_da_fase_2(tmp_path):
    """Só blocos da Fase 2 movidos (editor único, vista Final): o aviso diz isso ao agente."""
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "editData": {
        "inserts": [], "splitInserts": [{"ref": 0, "label": None, "start": 5.0, "end": 8.0}],
        "splitVideos": [], "hook": {"endSec": 3.25}, "behind": [], "wordAccents": []}}), encoding="utf-8")
    aviso = digest(p)
    assert "inserts/gancho movidos" in aviso


def test_aviso_dos_efeitos_e_do_zoom_da_fase_2(tmp_path):
    """Efeito desligado ou com bloco arrastado e zoom de tomada: o aviso diz o que gravar e onde."""
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "editData": {
        "cenas": [{"ref": 16, "tipo": "vidro", "start": 71.23, "end": 74.43, "desligada": False,
                   "texto": {"x": 540, "y": 420}, "textos": {"palavra": "GARGALO"},
                   "estilo": {"fonte": "Bebas Neue", "peso": 400, "tamanho": 1.2}},
                  {"ref": 3, "tipo": "mural", "start": 33.0, "end": 36.43, "desligada": True, "texto": None, "textos": {}}],
        "camera": {"zooms": [1.0, 1.2, 1.0], "mudou": [1]}}}), encoding="utf-8")
    aviso = digest(p)
    assert "2 efeitos mudados" in aviso and "zoom mudado em 1 tomada" in aviso
    assert "#16 vidro" in aviso and "bloco em x=540 y=420" in aviso and 'palavra="GARGALO"' in aviso
    assert "estilo fonte=Bebas Neue, peso=400, tamanho=1.2" in aviso
    assert "#3 mural" in aviso and "DESLIGAR" in aviso
    assert "tomada 2 → 120%" in aviso
    assert "inserts/gancho movidos" not in aviso  # só efeitos e zoom: nenhum bloco andou


def test_aviso_do_gancho_e_do_numero(tmp_path):
    """Gancho e número mudados no painel de Texto: o aviso diz onde gravar cada campo."""
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "editData": {"destaques": [
        {"alvo": "hook", "desligada": False, "texto": {"x": 540, "y": 520}, "textos": {"text": "Só 2% cortaram"},
         "estilo": {"fonte": "Anton", "peso": 400, "cor": "#ffe500"}},
        {"alvo": "numero", "ref": 0, "desligada": False, "texto": None,
         "textos": {"prefixo": "", "valor": "6", "sufixo": " MIL", "rotulo": "empresas"}, "estilo": {"tamanho": 0.8}}]}}),
        encoding="utf-8")
    aviso = digest(p)
    assert "2 textos de destaque mudados" in aviso
    assert "gancho: bloco em x=540 y=520" in aviso and 'text="Só 2% cortaram"' in aviso and "fonte=Anton" in aviso
    assert "número #0" in aviso and 'valor="6"' in aviso and "tamanho=0.8" in aviso
