"""As contas do vídeo final com efeitos: as mesmas da prévia (celular.js), quadro a quadro."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import efeitos_render as er  # noqa: E402

EF = {"versao": 1, "itens": [
    {"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 0.0, "duracao": 1.0, "intensidade": 0.2},
    {"id": "t1", "tipo": "transicao", "pacote": "zoom-central", "corte": 2.0, "duracao": 0.2}]}


def test_quadros_da_janela_pelo_numero():
    # 30 qps: [0, 1) é 0..29; o quadro 30 (1,0 s) já está fora
    assert er.quadros(0.0, 1.0, 30, 100) == list(range(0, 30))
    assert er.quadros(1.9, 2.1, 30, 100) == [57, 58, 59, 60, 61, 62]
    assert er.quadros(3.0, 9.0, 30, 100) == list(range(90, 100))  # corta no fim do vídeo


def test_filtro_da_tomada_nao_pega_o_primeiro_quadro_da_seguinte():
    """O corte é 60,666666 s (quadro 1820); gravado com 3 casas, o fim vira 60,667."""
    assert er.quadros(0.0, 60.667, 30, 3000)[-1] == 1819
    assert er.quadros(60.667, 61.0, 30, 3000)[0] == 1820  # e a tomada seguinte começa nele


def test_receita_da_transicao_troca_de_lado_no_corte():
    rs = {r["n"]: r for r in er.receitas(EF, 30, 100)}
    k = 60  # 1º quadro depois do corte de 2,0 s
    antes, depois = rs[59]["tr"], rs[60]["tr"]
    assert (antes["a"], antes["b"]) == (59, k)        # A anda, B parado no 1º quadro depois do corte
    assert (depois["a"], depois["b"]) == (k - 1, 60)  # A parado no último quadro antes, B anda
    assert antes["tempo_ms"] == pytest.approx((59 / 30 - 1.9) * 1000)
    assert antes["duracao_ms"] == depois["duracao_ms"] == pytest.approx(200)  # o motor encaixa a animação nela
    assert "fi" not in rs[59]


def test_template_antigo_com_transicao_para_antes_de_desenhar(tmp_path):
    """O EfeitosBase.tsx de um kit anterior não leva a duração da transição ao motor: o vídeo sairia
    diferente da prévia. Para antes de qualquer desenho e manda atualizar o template."""
    edit = tmp_path / "edit"
    rem = edit / "remotion"
    (rem / "src").mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30:duration=3",
                    "-pix_fmt", "yuv420p", str(edit / "cut.mp4")], check=True)
    (edit / "efeitos.json").write_text(json.dumps(EF), encoding="utf-8")
    kit = Path(er.__file__).resolve().parents[1] / "assets"
    for trilha in ("shortform", "longform"):  # o detector: o template do kit passa
        assert "duracao_ms: r.tr.duracao_ms" in (kit / trilha / "src" / "EfeitosBase.tsx").read_text(encoding="utf-8")
    (rem / "src" / "EfeitosBase.tsx").write_text("m.desenhar({a, b, tempo_ms: r.tr.tempo_ms});", encoding="utf-8")
    with pytest.raises(RuntimeError, match="atualizar_template"):
        er.aplicar(edit, rem)
    assert not (rem / "public" / "cut.mp4").exists()


def test_receita_do_filtro_e_ordem():
    rs = er.receitas(EF, 30, 100)
    assert [r["n"] for r in rs] == list(range(0, 30)) + [57, 58, 59, 60, 61, 62]
    assert rs[0]["fi"] == {"pacote": "filme-pb", "intensidade": 0.2} and "tr" not in rs[0]


def test_receita_do_ajuste_vai_junto_com_o_filtro_e_sem_pacote():
    ef = {"versao": 1, "itens": [
        EF["itens"][0], {"id": "a1", "tipo": "ajuste", "inicio": 0.5, "duracao": 1.0, "ajustes": {"brilho": 30}}]}
    rs = {r["n"]: r for r in er.receitas(ef, 30, 100)}
    assert rs[20]["fi"]["pacote"] == "filme-pb" and rs[20]["aj"] == {"ajustes": {"brilho": 30}}
    assert "aj" not in rs[14] and "fi" not in rs[40] and rs[40]["aj"]["ajustes"] == {"brilho": 30}


def test_corte_com_carimbo_um_pouco_antes_cai_no_quadro_certo():
    """O corte vem de video_start_in_output (60.666666): k é 1820, não 1819."""
    ef = {"versao": 1, "itens": [{"id": "t1", "tipo": "transicao", "pacote": "x", "corte": 60.667, "duracao": 1.1}]}
    rs = {r["n"]: r for r in er.receitas(ef, 30, 3000)}
    assert rs[1819]["tr"]["b"] == 1820 and rs[1820]["tr"]["a"] == 1819


def test_blocos_nao_partem_uma_transicao():
    rs = er.receitas(EF, 30, 100)
    bs = er.blocos(rs, 4)
    assert sum(len(b) for b in bs) == len(rs)
    for b in bs[:-1]:
        assert "tr" not in b[-1] or b[-1]["n"] == 62  # um bloco só termina dentro da transição no fim dela
    trans = [b for b in bs if any("tr" in r for r in b)]
    assert len(trans) == 1 and [r["n"] for r in trans[0] if "tr" in r] == [57, 58, 59, 60, 61, 62]


def test_rgb_para_yuv_bt709_faixa_limitada():
    rgb = np.zeros((2, 2, 3), np.uint8)
    rgb[...] = (255, 255, 255)
    y, u, v = er.rgb_para_yuv420(rgb, "bt709", "tv")
    assert y.tolist() == [[235, 235], [235, 235]] and u.tolist() == [[128]] and v.tolist() == [[128]]
    rgb[...] = (0, 0, 0)
    y, u, v = er.rgb_para_yuv420(rgb, "bt709", "tv")
    assert y.max() == 16 and u[0, 0] == 128
    rgb[...] = (255, 0, 0)  # vermelho puro em bt709: Y = 16 + 219·0,2126 ≈ 63, Cr = 240
    y, u, v = er.rgb_para_yuv420(rgb, "bt709", "tv")
    assert y[0, 0] == 63 and v[0, 0] == 240
