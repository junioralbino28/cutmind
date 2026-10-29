"""Cards girando em volta da pessoa (`cenas[]` tipo `orbita`), do Reels 1 (29/10/2026).

O editor já conhecia o nome; o template recusava. Agora a órbita é um efeito como os outros: o helper
faz o recorte da pessoa na janela e escolhe os cards (as imagens que a pessoa der, ou quadros do próprio
vídeo); o template desenha os de trás, a pessoa por cima no MESMO enquadre da imagem de baixo (o zoom da
tomada incluído) e os da frente. O título opcional nasce abaixo da zona segura.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import cenas  # noqa: E402
import cenas_edit_data as ce  # noqa: E402

TSX = RAIZ / "assets" / "shortform" / "src" / "cenas" / "orbita.tsx"
com_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")
PESSOA = {"x0": 300, "x1": 780, "topo": 420, "base": 1920, "cabecaX": 540, "presenca": 1.0}


def test_a_orbita_e_um_efeito_que_o_template_desenha():
    assert "orbita" in cenas.TIPOS
    index = (RAIZ / "assets" / "shortform" / "src" / "cenas" / "index.tsx").read_text(encoding="utf-8")
    assert "import {Orbita} from './orbita';" in index and re.search(r"^\s*orbita: Orbita,", index, re.M)


def test_validar_a_orbita():
    assert cenas.validar({"tipo": "orbita", "start": 1.0, "end": 4.0}) == []
    ok = {"tipo": "orbita", "start": 1.0, "end": 4.0, "titulo": ["ESSE", "É O KIT"], "voltas": 1.0,
          "cartoes": [{"src": "midia/a.png"}, {"src": "midia/b.png"}]}
    assert cenas.validar(ok) == []
    assert any("voltas" in e for e in cenas.validar({**ok, "voltas": 9}))
    assert any("titulo" in e for e in cenas.validar({**ok, "titulo": ["a", "b", "c"]}))
    assert any("cartoes" in e for e in cenas.validar({**ok, "cartoes": [{"arquivo": "x"}]}))


def test_o_titulo_nasce_abaixo_da_zona_segura_e_o_editor_desenha_igual():
    tsx = TSX.read_text(encoding="utf-8")
    assert "ORBITA_TITULO_TOPO = ZONA_SEGURA.topo + 30" in tsx
    js = (RAIZ / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
    m = re.search(r"orbita: \(c, t\) => \{ const h = 104 \* linhasDe\(t\.titulo\)\.length; return \{ x: 540, y: (\d+) \+ h / 2,", js)
    assert m and int(m.group(1)) == 240 + 30


def test_a_pessoa_por_cima_segue_o_enquadre_da_imagem():
    tsx = TSX.read_text(encoding="utf-8")
    assert "cameraAt(a + f, W, H, fps)" in tsx  # o mesmo enquadre/zoom do DynamicVideo
    assert tsx.index("desenha(false)") < tsx.index("staticFile(c.matte)") < tsx.index("desenha(true)")


@com_ffmpeg
def test_sem_cartoes_os_cards_sao_quadros_do_video(tmp_path):
    pub = tmp_path / "public"
    pasta = pub / "cenas"
    pasta.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=4",
                    "-pix_fmt", "yuv420p", str(pub / "cut.mp4")], check=True)
    usados: set[str] = set()
    out = ce._arquivos(tmp_path, pub, pasta, {"tipo": "orbita", "start": 0.5, "end": 3.5}, usados, [])
    cards = out["cartoes"]
    assert len(cards) == cenas.ORBITA_CARTOES and all((pub / c["src"]).is_file() for c in cards)
    # com cartões da pessoa, são eles (copiados para o public, com nome limpo)
    (tmp_path / "midia").mkdir()
    shutil.copy(pub / cards[0]["src"], tmp_path / "midia" / "Print do editor 1.jpg")
    out = ce._arquivos(tmp_path, pub, pasta, {"tipo": "orbita", "start": 0.5, "end": 3.5,
                                              "cartoes": [{"src": "midia/Print do editor 1.jpg"}]}, usados, [])
    assert len(out["cartoes"]) == 1 and " " not in out["cartoes"][0]["src"]
