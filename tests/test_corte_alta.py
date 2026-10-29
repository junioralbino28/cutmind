"""O corte em alta resolução para o zoom do vídeo final ficar nítido (corte_alta.py).

No Reels 1 (29/10/2026) a gravação era 4K e o enquadre da cintura para cima ampliava 1,7×: sobre o
cut.mp4 de 1080 a imagem amolecia, sobre um corte em 4K ficou nítida. O kit faz esse corte sozinho
quando serve, com os mesmos quadros do cut.mp4, sem trocar o corte normal nem o "como antes".
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import corte_alta as ca  # noqa: E402
import render  # noqa: E402

com_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")


def _projeto(tmp_path: Path, largura_enquadre: float | None, w: int = 2160, h: int = 3840) -> Path:
    fonte = tmp_path / "grav.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=30:duration=2.6",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2.6", "-c:v", "libx264", "-preset", "ultrafast",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(fonte)], check=True)
    edit = tmp_path / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    faixa = {"source": "A", "start": 0.2, "end": 2.3}
    if largura_enquadre:
        faixa["enquadre"] = {"x": 540, "y": 960, "largura": largura_enquadre}
    (edit / "edl.json").write_text(json.dumps({"version": 1, "sources": {"A": str(fonte)}, "ranges": [faixa]}), encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({"video": "cut.mp4", "editData": "remotion/public/edit-data.json", "fps": 30}),
                                     encoding="utf-8")
    (edit / "remotion" / "public" / "edit-data.json").write_text(json.dumps({"camera": {"enabled": False}}), encoding="utf-8")
    subprocess.run([sys.executable, "-X", "utf8", str(RAIZ / "helpers" / "render.py"), str(edit / "edl.json"), "-o", str(edit / "cut.mp4"),
                    "--no-subtitles", "--no-loudnorm"], check=True, capture_output=True)
    return edit


def test_o_zoom_vem_do_enquadre_e_da_camera(tmp_path):
    edit = tmp_path
    (edit / "edl.json").write_text(json.dumps({"ranges": [{"enquadre": {"largura": 1836}}, {}]}), encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({"editData": "ed.json"}), encoding="utf-8")
    (edit / "ed.json").write_text(json.dumps({"camera": {"enabled": True, "zooms": [1.1, 1.2], "pushIn": 0.05}}), encoding="utf-8")
    assert ca.zoom_maximo(edit) == pytest.approx(1.7)
    (edit / "edl.json").write_text(json.dumps({"ranges": [{}]}), encoding="utf-8")
    assert ca.zoom_maximo(edit) == pytest.approx(1.25)
    assert ca.precisa(edit) is False  # 1,25× não precisa (e nem chega a procurar o corte)


def test_a_opcao_do_render_nao_vira_opcao_salva():
    assert "lado_maior" not in render.OPCOES  # o "como antes" do editor nunca refaz o corte normal em 4K
    assert render.LADO_MAIOR == 1920


def test_o_template_e_o_gerar_usam_o_corte_alto():
    main = (RAIZ / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    assert "src = D.corteAlta ? 'cut-alta.mp4' : 'cut.mp4'" in main
    gerar = (RAIZ / "helpers" / "gerar.py").read_text(encoding="utf-8")
    assert gerar.count("corte_alta.aplicar(") == 2  # com e sem a Fase 2


@com_ffmpeg
def test_gravacao_4k_com_zoom_ganha_o_corte_alto_com_os_mesmos_quadros(tmp_path):
    edit = _projeto(tmp_path, 1836)
    assert ca.precisa(edit)
    r = ca.aplicar(edit)
    assert r["feito"] and (r["largura"], r["altura"]) == (2160, 3840)
    assert r["quadros"] == ca._sondar(edit / "cut.mp4")["quadros"] and r["psnr_min"] >= ca.PSNR_MINIMO
    assert (edit / "remotion" / "public" / ca.ARQUIVO).is_file()
    assert json.loads((edit / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8"))["corteAlta"] is True
    assert not (edit / ".alta").exists()  # a pasta de trabalho some
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    assert "lado_maior" not in json.dumps(edl.get("render") or {})
    # sem o zoom, o corte alto sai e a marca volta
    edl["ranges"][0].pop("enquadre")
    (edit / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    r = ca.aplicar(edit)
    assert not r["feito"] and not (edit / ca.ARQUIVO).exists() and not (edit / "remotion" / "public" / ca.ARQUIVO).exists()
    assert json.loads((edit / "remotion" / "public" / "edit-data.json").read_text(encoding="utf-8"))["corteAlta"] is False


@com_ffmpeg
def test_gravacao_1080_nao_ganha_corte_alto(tmp_path):
    edit = _projeto(tmp_path, 1836, 1080, 1920)
    assert ca.precisa(edit) is False
