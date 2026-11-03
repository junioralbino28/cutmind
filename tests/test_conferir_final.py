"""A conferência do vídeo final: sinais montados à mão onde dá, e um vídeo de verdade onde o defeito só aparece no arquivo."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import conferir_final as cf  # noqa: E402


def fala(seg=20.0, semente=1):
    """Uma "voz" de mentira: rajadas de ruído de duração variada, com silêncio entre elas."""
    r = np.random.default_rng(semente)
    x = np.zeros(int(seg * cf.TAXA), dtype=np.float32)
    t = 0.0
    while t < seg:
        d = r.uniform(0.1, 0.5)
        a = int(t * cf.TAXA)
        b = min(len(x), int((t + d) * cf.TAXA))
        x[a:b] = r.normal(0, 0.2, b - a)
        t += d + r.uniform(0.05, 0.4)
    return x


def atrasa(x, s):
    n = int(s * cf.TAXA)
    return np.concatenate([np.zeros(n, dtype=np.float32), x])[: len(x)]


def test_som_no_lugar_passa():
    x = fala()
    r = cf.conferir_sincronia(x, x, 0.0)
    assert r["medidas"] and not r["problemas"]


def test_o_atraso_certo_da_imagem_passa():
    x = fala()
    r = cf.conferir_sincronia(atrasa(x, 0.033), x, 0.033)
    assert not r["problemas"], r


def test_som_fora_da_imagem_e_acusado():
    x = fala()
    r = cf.conferir_sincronia(atrasa(x, 0.135), x, 0.0)
    assert any("fora da imagem" in p for p in r["problemas"]), r


def test_som_que_escorrega_e_acusado():
    """26 emendas a 30 ms: começa no lugar e termina atrasado; a média esconderia."""
    x = fala(40.0)
    corte = len(x) // 2
    y = np.concatenate([x[:corte], np.zeros(int(0.1 * cf.TAXA), dtype=np.float32), x[corte:]])[: len(x)]
    r = cf.conferir_sincronia(y, x, 0.0)
    assert any("escorrega" in p for p in r["problemas"]), r


def test_a_maior_diferenca_so_conta_quando_se_destaca():
    assert cf.pico_da_troca(np.array([1, 1, 1, 1, 30, 1, 1, 1, 1.0])) == 4
    assert cf.pico_da_troca(np.array([1, 1.2, 1.1, 1, 1.3, 1, 1.1, 1, 1.2])) is None  # mesma imagem
    assert cf.pico_da_troca(np.array([9, 10, 11, 12, 13, 12, 11, 10, 9.0])) is None  # transição


def video_com_trocas(p: Path, trocas_q: list[int], total: int, fps=30):
    """Um vídeo de cores chapadas que troca nos quadros pedidos, de verdade, pelo ffmpeg."""
    w, h = cf.QW, cf.QH
    r = np.random.default_rng(3)
    cor = r.integers(0, 255, 3)
    bruto = bytearray()
    for q in range(total):
        if q in trocas_q:
            cor = r.integers(0, 255, 3)
        bruto += np.tile(cor.astype(np.uint8), (h, w, 1)).tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
                    "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-qp", "10", "-pix_fmt", "yuv420p", str(p)], input=bytes(bruto), check=True)


def test_acha_a_troca_no_quadro_exato_num_arquivo_de_verdade(tmp_path):
    """O índice só dá certo com o leitor de quadros pelo tempo: -frames:v depois de -ss repete o 1º quadro."""
    v = tmp_path / "v.mp4"
    video_com_trocas(v, [60, 150, 240], 300)
    r = cf.conferir_trocas(v, [0.0, 2.0, 5.0, 8.0], 30.0, 0)
    assert r["exatas"] == 3 and not r["fora"] and not r["problemas"], r


def test_acusa_a_troca_um_quadro_fora(tmp_path):
    v = tmp_path / "v.mp4"
    video_com_trocas(v, [61, 150], 240)
    r = cf.conferir_trocas(v, [0.0, 2.0, 5.0], 30.0, 0)
    assert r["fora"] == [(2.0, 1)] and r["exatas"] == 1 and len(r["problemas"]) == 1, r


def test_o_atraso_da_imagem_conta_na_troca(tmp_path):
    v = tmp_path / "v.mp4"
    video_com_trocas(v, [61], 120)
    assert cf.conferir_trocas(v, [0.0, 2.0], 30.0, 1)["exatas"] == 1


def projeto(tmp_path, voz, som, volume):
    edit = tmp_path
    (edit / "midia").mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "f32le", "-ar", str(cf.TAXA), "-ac", "1", "-i", "-", str(edit / "midia" / "s.wav")],
                   input=som.astype(np.float32).tobytes(), check=True)
    faixa = {"id": "f1", "tipo": "audio", "oculto": False, "itens": [{"id": "a1", "arquivo": "midia/s.wav", "inicio": 2.0, "duracao": 0.3, "corte": 0.0, "volume": volume}]}
    (edit / "camadas.json").write_text(json.dumps({"versao": 1, "video": {"mudo": False}, "faixas": [faixa]}), encoding="utf-8")
    return edit


def sinais():
    voz = np.zeros(cf.TAXA * 5, dtype=np.float32)
    voz[int(1.9 * cf.TAXA):int(2.2 * cf.TAXA)] = 0.3
    som = np.zeros(int(0.3 * cf.TAXA), dtype=np.float32)
    som[10] = 0.5  # o estalo fica no pico, a cauda não conta
    return voz, som


def test_som_que_some_debaixo_da_voz_e_acusado(tmp_path):
    voz, som = sinais()
    r = cf.conferir_sons(projeto(tmp_path, voz, som, 0.05), voz)
    assert any("abaixo da voz" in p for p in r["problemas"]), r


def test_som_no_nivel_passa(tmp_path):
    voz, som = sinais()
    r = cf.conferir_sons(projeto(tmp_path, voz, som, 0.4), voz)
    assert r["sons"] and not r["problemas"], r


def test_som_por_cima_da_fala_e_acusado(tmp_path):
    voz, som = sinais()
    r = cf.conferir_sons(projeto(tmp_path, voz, som, 2.0), voz * 0.1)
    assert any("acima da voz" in p for p in r["problemas"]), r
