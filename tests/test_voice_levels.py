"""O voice_levels mede só as tomadas cortadas do vídeo que recebeu.

Numa lista de cortes com dois vídeos, ele media TODAS as tomadas no áudio do vídeo
passado: a tomada do outro vídeo saía com um nível (e um gain_db sugerido) de um
trecho que não é ela.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import voice_levels as vl  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")


def _fala(dest: Path) -> Path:
    # 1 s de tom, 1 s de quase silêncio, alternando: dá ao detector um chão e uma fala
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=6",
                    "-af", "volume='if(mod(floor(t),2),0.003,1)':eval=frame", str(dest)], check=True)
    return dest


def _edl(tmp_path: Path) -> tuple[Path, Path, Path]:
    pasta = tmp_path / "pasta com espaço"
    (pasta / "edit").mkdir(parents=True)
    a, b = _fala(pasta / "a.wav"), _fala(pasta / "b.wav")
    edl = pasta / "edit" / "edl.json"
    edl.write_text(json.dumps({
        "sources": {"a": str(a), "b": "../b.wav"},
        "ranges": [{"source": "a", "start": 0.0, "end": 1.0, "quote": "ação"},
                   {"source": "b", "start": 2.0, "end": 3.0},
                   {"source": "a", "start": 4.0, "end": 5.0}],
    }, ensure_ascii=False), encoding="utf-8")
    return a, b, edl


def test_mede_so_as_tomadas_do_video(tmp_path):
    a, b, edl = _edl(tmp_path)
    ra = vl.analyze(a, None, vl.DEFAULT_DROP_DB, edl)
    assert [r["index"] for r in ra["edl_ranges"]] == [0, 2]
    assert ra["edl_other_source"] == 1
    # o caminho relativo da fonte vale a partir da pasta da lista de cortes
    rb = vl.analyze(b, None, vl.DEFAULT_DROP_DB, edl)
    assert [r["index"] for r in rb["edl_ranges"]] == [1]


def test_lista_sem_fonte_vale_para_o_video(tmp_path):
    a, _, edl = _edl(tmp_path)
    d = json.loads(edl.read_text(encoding="utf-8"))
    for r in d["ranges"]:
        del r["source"]
    edl.write_text(json.dumps(d), encoding="utf-8")
    assert [r["index"] for r in vl.analyze(a, None, vl.DEFAULT_DROP_DB, edl)["edl_ranges"]] == [0, 1, 2]
