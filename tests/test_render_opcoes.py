"""O render.py lembra com que opções rodou, para o editor refazer o corte do mesmo jeito sem o agente."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import render  # noqa: E402


def _args(**kw) -> argparse.Namespace:
    base = {"keep_resolution": False, "voice_master": False, "no_jcut": False, "jcut_lead": None,
            "jcut_tail_trim": None, "no_loudnorm": False}
    base.update(kw)
    return argparse.Namespace(**base)


def _video(caminho: Path, w: int, h: int) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=30",
                    "-t", "0.5", "-pix_fmt", "yuv420p", str(caminho)], check=True)
    return caminho


def test_guarda_so_o_que_foi_pedido():
    assert render.opcoes_da_linha(_args(keep_resolution=True, jcut_lead=3)) == {"keep_resolution": True, "jcut_lead": 3}
    assert render.opcoes_da_linha(_args()) == {}


def test_como_antes_usa_o_que_o_edl_guardou(tmp_path):
    edl = {"render": {"no_jcut": True, "jcut_lead": 2, "coisa_estranha": 1}}
    assert render.opcoes_como_antes(edl, tmp_path / "nao-existe.mp4") == {"no_jcut": True, "jcut_lead": 2}


def test_projeto_de_antes_adivinha_pelo_formato_do_corte(tmp_path):
    deitado = _video(tmp_path / "deitado.mp4", 320, 180)
    em_pe = _video(tmp_path / "em-pe.mp4", 180, 320)
    assert render.opcoes_como_antes({}, deitado) == {"keep_resolution": True}
    assert render.opcoes_como_antes({}, em_pe) == {}
    assert render.opcoes_como_antes({}, tmp_path / "nao-existe.mp4") == {}


def test_aplicar_como_antes_preenche_os_args(tmp_path):
    a = _args()
    render.aplicar_como_antes(a, {"render": {"keep_resolution": True, "no_loudnorm": True}}, tmp_path / "x.mp4")
    assert a.keep_resolution is True and a.no_loudnorm is True and a.no_jcut is False


def test_main_grava_as_opcoes_no_edl(tmp_path, monkeypatch):
    """Só a gravação: o render de verdade é trocado por um que para logo depois dela."""
    fonte = _video(tmp_path / "a.mp4", 180, 320)
    edl_p = tmp_path / "edl.json"
    edl_p.write_bytes(json.dumps({"version": 1, "sources": {"a": str(fonte)},
                                  "ranges": [{"source": "a", "start": 0.0, "end": 0.4}]}).encode("utf-8"))

    class Parou(Exception):
        pass

    def para(*a, **k):
        raise Parou()
    monkeypatch.setattr(render, "jcut_settings", para)
    monkeypatch.setattr(sys, "argv", ["render.py", str(edl_p), "-o", str(tmp_path / "cut.mp4"), "--no-subtitles",
                                      "--keep-resolution"])
    try:
        render.main()
    except Parou:
        pass
    assert json.loads(edl_p.read_text(encoding="utf-8"))["render"] == {"keep_resolution": True}
