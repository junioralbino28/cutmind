"""O vigia acorda o agente só no Pronto (pronto.json), na escolha do Estilo e no vídeo enviado. O Salvar
não chega mais à conversa: o editor aplica sozinho (plano do ajuste sem IA, Etapa 4)."""
import json
import subprocess
import sys
import time
from pathlib import Path

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import watch_edits as we  # noqa: E402

PRONTO = {"quando": "2026-10-27 00:41:00", "fase": 1,
          "pedidos": [{"start": 12.4, "end": 15.1, "phase": 1, "text": "tira o trecho em que eu leio o roteiro"},
                      {"start": 3.0, "end": 3.0, "phase": 1, "geral": True, "text": "aumenta o texto do começo"}],
          "feitos": [{"quando": "2026-10-27 00:30:00", "oque": "corte: 1 tomada(s) aparada(s)"},
                     {"quando": "2026-10-27 00:35:00", "oque": "vídeo final: 1 imagem(s)"},
                     {"quando": "2026-10-27 00:36:00", "oque": "efeitos: 1 filtro"}]}


def _grava(p: Path, d: dict) -> Path:
    p.write_bytes(json.dumps(d, ensure_ascii=False).encode("utf-8"))
    return p


def test_pronto_lista_o_feito_e_os_pedidos(tmp_path):
    txt = we.pronto_digest(_grava(tmp_path / "pronto.json", PRONTO))
    linhas = txt.splitlines()
    assert linhas[0].startswith("PRONTO DO EDITOR (2026-10-27 00:41:00)") and "fase 1" in linhas[0] and "2 pedidos" in linhas[0]
    assert "NÃO refaça" in txt and "corte: 1 tomada(s) aparada(s); vídeo final: 1 imagem(s); efeitos: 1 filtro" in txt
    assert "1. [0:12.40 → 0:15.10] (fase 1) tira o trecho em que eu leio o roteiro" in txt
    assert "2. PEDIDO (agulha em 0:03.00, fase 1) aumenta o texto do começo" in txt
    assert '"agente": {"trabalhando": true' in txt and "apague pronto.json e ajustes_feitos.json" in txt


def test_pronto_sem_pedido_na_fase_1_aprova_o_corte(tmp_path):
    txt = we.pronto_digest(_grava(tmp_path / "pronto.json", {**PRONTO, "pedidos": []}))
    assert "0 pedidos" in txt and "corte está aprovado" in txt and "awaitingStyle" in txt


def test_pronto_com_ajustes_de_antes_da_versao_nova(tmp_path):
    _grava(tmp_path / "preview_edits.json", {"savedAt": "ontem", "notes": [{"start": 1, "end": 2, "text": "velho"}]})
    txt = we.pronto_digest(_grava(tmp_path / "pronto.json", {**PRONTO, "legado": True}))
    assert "preview_edits.json" in txt and "AJUSTES DO PREVIEW" in txt and "velho" in txt


def test_o_salvar_nao_acorda_mais_e_o_pronto_sim(tmp_path):
    edit = tmp_path / "edit"
    edit.mkdir()
    _grava(edit / "preview_edits.json", {"savedAt": "agora", "notes": []})  # de antes: não é aviso
    p = subprocess.Popen([sys.executable, "-X", "utf8", str(HELPERS / "watch_edits.py"), str(edit), "--uma-vez"],
                         stdout=subprocess.PIPE, text=True, encoding="utf-8",
                         env={**__import__("os").environ, "CUTMIND_HOME": str(tmp_path / "home")})
    try:
        time.sleep(1.5)
        assert p.poll() is None  # o preview_edits.json não acordou ninguém
        _grava(edit / "pronto.json", PRONTO)
        out, _ = p.communicate(timeout=15)
    finally:
        if p.poll() is None:
            p.kill()
    assert out.startswith("PRONTO DO EDITOR") and p.returncode == 0


def test_estilo_e_video_enviado_continuam_acordando(tmp_path):
    vigiados = {f.name for f in we.vigiar(tmp_path)}
    assert vigiados == {"pronto.json", "preview_style.json", "preview_upload.json"}
