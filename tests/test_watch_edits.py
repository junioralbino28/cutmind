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


def test_aviso_da_montagem_manda_rodar_o_aplicar(tmp_path):
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "montagem": {"lugares": [
        {"vaga": 3, "midia": "midia/foto nova.jpg"}, {"vaga": 5, "de": 12.4}, {"vaga": 7, "midia": "C:/x/clipe.mp4", "de": 2}]}}),
        encoding="utf-8")
    aviso = digest(p)
    assert "montagem: 3 lugares mudados" in aviso and "montagem.py aplicar <edit>" in aviso
    assert "lugar 3: troca para foto nova.jpg" in aviso and "lugar 5: trecho a partir de 12.4 s" in aviso
    assert "lugar 7: troca para clipe.mp4; trecho a partir de 2 s" in aviso
    assert "volume das tomadas" not in aviso  # sem tomada mudada no mesmo Salvar


def test_usar_um_modelo_manda_rodar_o_montar(tmp_path):
    p = tmp_path / "preview_edits.json"
    midias = [f"midia/f{i:02d}.jpg" for i in range(14)]
    p.write_text(json.dumps({"type": "timeline-edits", "montagem": {"usar": {
        "modelo": "drop-cedo", "musica": "midia/funk.mp3", "midias": midias}}}), encoding="utf-8")
    aviso = digest(p)
    assert "MONTAGEM NOVA com o modelo drop-cedo" in aviso and "rode montagem.py montar <edit>" in aviso
    assert "música: funk.mp3" in aviso and "14 fotos e clipes, na ordem: f00.jpg, f01.jpg" in aviso
    assert aviso.count(".jpg") == 12 and "…" in aviso  # os primeiros 12; o resto o agente lê no arquivo
    assert "montagem.py aplicar" not in aviso


def test_camadas_de_uma_montagem_mandam_rodar_o_render_dela(tmp_path):
    p = tmp_path / "preview_edits.json"
    camadas = {"versao": 1, "video": {"mudo": True}, "faixas": [{"id": "modelo-texto-1", "tipo": "texto", "itens": [
        {"id": "modelo-texto-1-1", "nome": "Título", "texto": "NOVO", "inicio": 0, "duracao": 2}]}]}
    p.write_text(json.dumps({"type": "timeline-edits", "camadas": camadas}), encoding="utf-8")
    assert "montagem.py render" not in digest(p)  # projeto comum: o caminho de sempre
    (tmp_path / "edl.json").write_text(json.dumps({"ranges": [], "montagem": {"lugares": [{"vaga": 1}]}}), encoding="utf-8")
    assert "rode montagem.py render <edit>" in digest(p)
    p.write_text(json.dumps({"type": "timeline-edits", "camadas": camadas,
                             "montagem": {"lugares": [{"vaga": 1, "de": 2}]}}), encoding="utf-8")
    aviso = digest(p)
    assert "montagem.py aplicar <edit>" in aviso and "já leva estas camadas" in aviso and "montagem.py render" not in aviso


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
    pendente sai na hora, e sem nada pendente ele espera o próximo Pronto e termina com o aviso."""
    import subprocess
    vigia = Path(__file__).resolve().parents[1] / "helpers" / "watch_edits.py"
    nota = {"quando": "agora", "fase": 1, "pedidos": [{"start": 1, "end": 1, "text": "pedido", "geral": True}]}
    pend = tmp_path / "pendente"
    pend.mkdir()
    (pend / "pronto.json").write_text(json.dumps(nota), encoding="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", str(vigia), str(pend), "--uma-vez"],
                       capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert r.returncode == 0 and "PRONTO DO EDITOR" in r.stdout and "1 pedido." in r.stdout

    vazio = tmp_path / "vazio"
    vazio.mkdir()
    p = subprocess.Popen([sys.executable, "-X", "utf8", str(vigia), str(vazio), "--uma-vez"],
                         stdout=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        time.sleep(1.0)
        assert p.poll() is None  # sem nada pendente, fica esperando
        (vazio / "pronto.json").write_text(json.dumps(nota), encoding="utf-8")
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
    assert "legenda_tempos.py" not in aviso  # nada arrastado no tempo: nada a dizer


def test_aviso_dos_pedacos_da_legenda_levados_no_tempo(tmp_path):
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "editData": {"legenda": {
        "estilo": None, "acompanhar": False,
        "tempos": [{"palavra": 12, "palavras": 3, "deMs": 8540, "paraMs": 8040}]}}}), encoding="utf-8")
    aviso = digest(p)
    assert "1 pedaço levado" in aviso and "legenda_tempos.py" in aviso
    assert "palavras 12–14" in aviso and "-0.50 s" in aviso


def test_aviso_da_velocidade_do_video_final(tmp_path):
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "velocidade": {"versao": 1, "duracao": 82.567, "trechos": [
        {"inicio": 10.0, "fim": 25.0, "fator": 2.0}]}}), encoding="utf-8")
    aviso = digest(p)
    assert "velocidade: 1 trecho" in aviso and "velocidade_final.py" in aviso
    assert "0:10.00 a 0:25.00 a 2×" in aviso and "15.00 s viram 7.50 s" in aviso
    p.write_text(json.dumps({"type": "timeline-edits", "velocidade": {"versao": 1, "trechos": []}}), encoding="utf-8")
    assert "sem trechos" in digest(p)  # tirou a velocidade: o agente desfaz a entrega acelerada


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


def test_aviso_do_melhorar_voz_diz_o_comando(tmp_path):
    edit = tmp_path / "edit"
    edit.mkdir()
    p = edit / "preview_edits.json"
    p.write_text(json.dumps({"melhorar": {"voz": 70, "fundo": 10}}), encoding="utf-8")
    out = digest(p)
    assert "melhorar voz: Voz 70%, Fundo 10%" in out
    assert "melhorar_voz.py aplicar <edit> --voz 70 --fundo 10" in out
    p.write_text(json.dumps({"melhorar": {"desligar": True}}), encoding="utf-8")
    assert "melhorar_voz.py restaurar <edit>" in digest(p)


def test_corte_refeito_com_a_voz_aplicada_lembra_de_reaplicar(tmp_path):
    edit = tmp_path / "edit"
    (edit / ".melhorar").mkdir(parents=True)
    p = edit / "preview_edits.json"
    p.write_text(json.dumps({"edl": {"ranges": [{"source": "C0001", "start": 0, "end": 2}]}}), encoding="utf-8")
    assert "Melhorar voz" not in digest(p)  # sem voz aplicada, nada a lembrar
    (edit / ".melhorar" / "estado.json").write_text(json.dumps({"versao": 1, "aplicado": {"voz": 50, "fundo": 20,
                                                                                         "hash": "ab" * 32}}),
                                                     encoding="utf-8")
    assert "Melhorar voz está aplicado" in digest(p)


def test_aviso_junta_o_que_um_modelo_repete(tmp_path):
    # o modelo de estilo põe o mesmo filtro e ajuste em cada tomada e a mesma transição em cada corte
    p = tmp_path / "preview_edits.json"
    cortes = [0, 5.467, 13.567, 15.667, 19.7, 22.733]
    itens = []
    for i, (a, b) in enumerate(zip(cortes, cortes[1:])):
        jan = {"inicio": a, "duracao": round(b - a, 3)}
        itens += [{"id": f"f{i}", "tipo": "filtro", "pacote": "f-ambar", **jan, "intensidade": 0.7},
                  {"id": f"a{i}", "tipo": "ajuste", **jan, "ajustes": {"brilho": 12}}]
        if i:
            itens.append({"id": f"t{i}", "tipo": "transicao", "pacote": "t-abrir-2", "corte": a, "duracao": 0.6})
    itens.append({"id": "f9", "tipo": "filtro", "pacote": "f-ambar", "inicio": 30, "duracao": 2, "intensidade": 0.7})
    p.write_text(json.dumps({"type": "timeline-edits", "efeitos": {"versao": 1, "itens": itens}}), encoding="utf-8")
    aviso = digest(p)
    assert 'filtro "f-ambar" de 0:00.00 a 0:22.73, intensidade 70% (5 trechos seguidos)' in aviso
    assert 'filtro "f-ambar" de 0:30.00 a 0:32.00, intensidade 70%\n' in aviso  # com buraco antes: linha própria
    assert "ajuste de 0:00.00 a 0:22.73: brilho +12 (5 trechos seguidos)" in aviso
    assert 'transição "t-abrir-2" (0.6 s) em 4 cortes: 0:05.47, 0:13.57, 0:15.67, 0:19.70' in aviso
    assert aviso.count("· filtro") == 2 and aviso.count("· transição") == 1


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
    assert "cenas_edit_data.py" in aviso and "references/cenas.md" in aviso  # as posições dependem dos textos
    assert "render_janelas.py <edit> --janelas 71.23-74.43,33-36.43" in aviso  # só as janelas dos dois
    assert "tomada 2 → 120%" in aviso
    assert "inserts/gancho movidos" not in aviso  # só efeitos e zoom: nenhum bloco andou


def test_aviso_do_fundo_criado_no_editor(tmp_path):
    """O Fundo novo vem sem `ref`: o aviso manda acrescentar o item pronto; o desligado não entra e
    não pede janela; o Fundo do agente trocado diz os `campos`."""
    p = tmp_path / "preview_edits.json"
    p.write_text(json.dumps({"type": "timeline-edits", "editData": {"cenas": [
        {"ref": 1, "tipo": "fundo", "start": 2.0, "end": 5.0, "desligada": False, "texto": None, "textos": {},
         "estilo": None, "campos": {"fundo": "fundos/neon", "escurecer": 0.3, "desfoque": 6}},
        {"nova": True, "tipo": "fundo", "start": 9.5, "end": 12.25, "desligada": False, "texto": None, "textos": {},
         "estilo": None, "campos": {"fundo": "midia/Cenário 1.jpg", "escurecer": 0.25, "desfoque": 0}},
        {"nova": True, "tipo": "fundo", "start": 20.0, "end": 22.0, "desligada": True, "texto": None, "textos": {},
         "estilo": None, "campos": {"fundo": "fundos/lousa", "escurecer": 0.25, "desfoque": 0}}]}}), encoding="utf-8")
    aviso = digest(p)
    assert "3 efeitos mudados" in aviso
    assert "#1 fundo" in aviso and "fundo=fundos/neon, escurecer=0.3, desfoque=6" in aviso
    assert ('NOVO fundo [0:09.50 → 0:12.25]: acrescente em cenas[] {"tipo": "fundo", "start": 9.5, "end": 12.25, '
            '"fundo": "midia/Cenário 1.jpg", "escurecer": 0.25, "desfoque": 0}') in aviso
    assert "NOVO fundo [0:20.00 → 0:22.00]: desligado no editor, não acrescente" in aviso
    assert "render_janelas.py <edit> --janelas 2-5,9.5-12.25 " in aviso  # o desligado não pede janela


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


# ---- a tela Projetos: o vigia segue o projeto aberto no editor (~/.cutmind/aberto.json) ----
def _proj(base, nome, **extra):
    edit = base / nome / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": nome, "phase": 1, **extra}), encoding="utf-8")
    return edit


def _vigia(pasta, *flags):
    import subprocess
    vigia = Path(__file__).resolve().parents[1] / "helpers" / "watch_edits.py"
    return subprocess.Popen([sys.executable, "-X", "utf8", str(vigia), str(pasta), *flags],
                            stdout=subprocess.PIPE, text=True, encoding="utf-8")


def test_uma_vez_avisa_quando_o_editor_abre_outro_projeto(tmp_path):
    import projetos as pj
    a, b = _proj(tmp_path, "A"), _proj(tmp_path, "Novo", phase=0, novo=True)
    pj.marcar_aberto(a)
    p = _vigia(a, "--uma-vez")
    try:
        time.sleep(1.0)
        assert p.poll() is None
        pj.marcar_aberto(b)
        out, _ = p.communicate(timeout=20)
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode == 0
    assert f"O EDITOR ABRIU OUTRO PROJETO: Novo — {b.resolve()}" in out
    assert "projeto novo" in out and "Enviar" in out


def test_aberto_antigo_ao_ligar_nao_e_aviso(tmp_path):
    """aberto.json de outra sessão (editor fechado) não derruba o vigia que acabou de ligar."""
    import projetos as pj
    a, b = _proj(tmp_path, "A"), _proj(tmp_path, "B")
    pj.marcar_aberto(b)
    p = _vigia(a, "--uma-vez")
    try:
        time.sleep(2.5)
        assert p.poll() is None
        (a / "pronto.json").write_text(json.dumps({"quando": "agora", "fase": 1, "pedidos": [
            {"start": 1, "end": 1, "text": "pedido", "geral": True}]}), encoding="utf-8")
        out, _ = p.communicate(timeout=20)
    finally:
        if p.poll() is None:
            p.kill()
    assert "PRONTO DO EDITOR" in out and "OUTRO PROJETO" not in out


def test_sem_uma_vez_passa_a_vigiar_a_pasta_nova(tmp_path):
    import projetos as pj
    a, b = _proj(tmp_path, "A"), _proj(tmp_path, "B")
    pj.marcar_aberto(a)
    p = _vigia(a)
    try:
        time.sleep(1.0)
        pj.marcar_aberto(b)
        time.sleep(3.0)
        (b / "pronto.json").write_text(json.dumps({"quando": "agora", "fase": 1, "pedidos": [
            {"start": 2, "end": 2, "text": "no projeto B", "geral": True}]}), encoding="utf-8")
        time.sleep(3.0)
    finally:
        p.kill()
    out, _ = p.communicate(timeout=20)
    assert f"OUTRO PROJETO: B — {b.resolve()}" in out
    assert "no projeto B" in out


ESTILO = {"edit": "limpa", "headline": "misto", "captions": "serifada", "accent": "#ff5200",
          "elements": {"zoomAuto": True, "zoomCuts": True}, "captionPositions": {"all": None, "phrases": []}, "note": ""}


def _projeto_com_estilo(tmp_path, estilo_fino=None):
    (tmp_path / "remotion" / "public").mkdir(parents=True)
    (tmp_path / "state.json").write_text(json.dumps({"phase": 2, "style": ESTILO,
                                                     "editData": "remotion/public/edit-data.json"}), encoding="utf-8")
    cap = {"enabled": True, "style": "serifada", **({"estilo": estilo_fino} if estilo_fino else {})}
    (tmp_path / "remotion" / "public" / "edit-data.json").write_text(json.dumps({"captions": cap}), encoding="utf-8")
    return tmp_path / "preview_style.json"


def test_estilo_igual_ao_do_video_nao_manda_refazer(tmp_path):
    # o Aplicar sem mudar nada, ou um modelo igual ao vídeo: refazer a Fase 2 daria o mesmo vídeo
    from watch_edits import style_digest
    p = _projeto_com_estilo(tmp_path, {"fonte": "Anton"})
    salvo = {"type": "style-setup", "rerender": True, **ESTILO, "accent": "#FF5200"}
    p.write_text(json.dumps(salvo), encoding="utf-8")
    assert "SEM MUDANÇA" in style_digest(p) and "REFAÇA" not in style_digest(p)
    p.write_text(json.dumps({**salvo, "legenda": {"estilo": {"fonte": "Anton"}, "acompanhar": False}}), encoding="utf-8")
    assert "SEM MUDANÇA" in style_digest(p)  # a legenda fina é a que o edit-data já tem
    p.write_text(json.dumps({**salvo, "legenda": {"estilo": {"fonte": "Bebas Neue"}}}), encoding="utf-8")
    assert "REFAÇA a Fase 2" in style_digest(p)
    p.write_text(json.dumps({**salvo, "captions": "karaoke"}), encoding="utf-8")
    assert "REFAÇA a Fase 2" in style_digest(p)
    p.write_text(json.dumps({**salvo, "rerender": False}), encoding="utf-8")
    assert "monte a Fase 2" in style_digest(p)  # a 1ª escolha sempre monta


def test_aviso_do_modelo_diz_o_que_ele_leva(tmp_path):
    import modelos as md
    from watch_edits import style_digest
    p = tmp_path / "preview_style.json"

    def aviso(mid, nome):
        p.write_text(json.dumps({"type": "style-setup", "rerender": True, **ESTILO, "captions": "karaoke",
                                 "modelo": {"id": mid, "nome": nome}}), encoding="utf-8")
        return style_digest(p)

    md.salvar({"nome": "Só estilo", "estilo": {"captions": "karaoke"}})
    md.salvar({"nome": "Com filtro", "estilo": {}, "filtro": {"pacote": "f-ambar"}, "trilha": {"pacote": "lofi-01"}})
    assert "é só o Estilo" in aviso("so-estilo", "Só estilo")
    assert "filtro, trilha dele já estão no efeitos.json e no camadas.json" in aviso("com-filtro", "Com filtro")
    assert "se tiver, já estão no efeitos.json e no camadas.json" in aviso("apagado", "Apagado")  # modelo que já não existe


def test_aviso_de_estilo_conta_o_modelo_aplicado(tmp_path):
    from watch_edits import style_digest
    p = tmp_path / "preview_style.json"
    p.write_text(json.dumps({"type": "style-setup", "rerender": True, "edit": "limpa", "captions": "karaoke",
                             "headline": "realce", "modelo": {"id": "canal-de-receitas", "nome": "Canal de Receitas"},
                             "legenda": {"estilo": {"fonte": "Anton", "cor": "#ffffff"}, "acompanhar": True}}),
                 encoding="utf-8")
    aviso = style_digest(p)
    assert 'MODELO "Canal de Receitas" aplicado (modelos.py mostrar canal-de-receitas)' in aviso
    assert "legenda fina do modelo: fonte=Anton cor=#ffffff · acompanhar" in aviso
