"""Melhorar voz: as faixas do regulador (Voz limpa → estúdio, Fundo) e o som aplicado no cut.mp4.

Os modelos de verdade (DeepFilterNet e Sidon, ~1 GB) não rodam aqui: o `preparar` recebe uma
voz limpa e um estúdio de mentira, determinísticos, e o teste confere o que é do kit: o
alinhamento, a mistura espectral, os volumes, a assinatura do corte e a troca do som.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
import melhorar_voz as mv  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
SR = mv.SR
ATRASO_ESTUDIO = 144  # 3 ms: o Sidon de verdade saiu 2 a 3 ms fora da voz limpa (23/10)


def _fala(seg: float, semente: int, chiado: float = 0.01) -> np.ndarray:
    """Algo com cara de fala: harmônicos de uma voz que sobe e desce, em sílabas, com chiado."""
    rng = np.random.default_rng(semente)
    t = np.arange(int(seg * SR)) / SR
    fase = 2 * np.pi * np.cumsum(140 + 30 * np.sin(2 * np.pi * 0.7 * t + semente)) / SR
    voz = sum(np.sin(k * fase) / k for k in range(1, 12))
    silabas = np.convolve((np.sin(2 * np.pi * 3.1 * t) > -0.2).astype(float), np.ones(480) / 480, mode="same")
    return 0.12 * voz * silabas + chiado * rng.standard_normal(len(t))


def _gravar_corte(pasta: Path, audio: np.ndarray) -> Path:
    """Um cut.mp4 como o do render: H.264 + AAC 192k, 48 kHz, estéreo."""
    pasta.mkdir(parents=True, exist_ok=True)
    p = pasta / "cut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc=size=64x112:rate=30:duration={len(audio) / SR}",
                    "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ac", "2",
                    "-shortest", str(p)], input=audio.astype(np.float32).tobytes(), check=True)
    return p


def _limpar(x: np.ndarray) -> np.ndarray:
    """A voz limpa de mentira: média móvel centrada (tira o chiado agudo, sem atraso)."""
    return np.convolve(x, np.ones(9) / 9, mode="same")


class _Estudio:
    """O estúdio de mentira, no formato do Sidon: uma linha de características a cada 20 ms (as
    amostras de 16 kHz daquele trecho) e a voz em 48 kHz por repetição, com outro timbre, `atraso`
    amostras atrasada e 20 ms mais curta. Não depende de onde o pedaço começa: em pedaços ou
    inteiro, sai a mesma coisa."""

    quadro = 960

    def __init__(self, atraso: int = ATRASO_ESTUDIO, timbre: bool = True):
        self.atraso, self.timbre = atraso, timbre

    def caracteristicas(self, x16: np.ndarray) -> np.ndarray:
        n = len(x16) // 320
        return x16[:n * 320].reshape(n, 320)

    def gerar(self, f: np.ndarray) -> np.ndarray:
        y = np.repeat(f.ravel(), 3)
        if self.timbre:
            y = np.convolve(y, [0.6, 0.4], mode="same")
        return np.concatenate([np.zeros(self.atraso), y])[:len(y) - 960]


_estudio = _Estudio()


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTMIND_VOZ_DIR", str(tmp_path / "modelos-voz"))
    edit = tmp_path / "Vídeo de teste" / "edit"
    _gravar_corte(edit, _fala(3.0, 1))
    (edit / "state.json").write_text(json.dumps({"project": "teste", "video": "cut.mp4"}), encoding="utf-8")
    return edit


def _preparar(edit: Path) -> dict:
    return mv.preparar(edit, eco=False, limpar=_limpar, estudio=_estudio)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    return float(np.corrcoef(a[:n], b[:n])[0, 1])


def _hash(arq: Path, fluxo: str) -> str:
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq), "-map", f"0:{fluxo}:0", "-c", "copy",
                           "-f", "hash", "-hash", "sha256", "-"], capture_output=True, check=True).stdout.decode()


def test_preparar_grava_as_faixas_e_voz_zero_mais_fundo_e_o_original(projeto):
    e = _preparar(projeto)
    pasta = projeto / mv.PASTA
    assert all((pasta / a).is_file() for a in mv.ARQUIVOS)
    assert e["fonte"]["hash"] == mv.hash_audio(projeto / "cut.mp4")
    orig = mv.ler_audio(projeto / "cut.mp4")
    limpa, fundo = np.load(pasta / "limpa.npy"), np.load(pasta / "fundo.npy")
    assert np.abs(limpa + fundo - orig).max() < 1e-6  # o fundo é exatamente o que a limpa tirou
    p = {k: mv.ler_audio(pasta / "previa" / f"{k}.flac") for k in ("voz-000", "voz-050", "voz-100", "fundo", "original")}
    assert _corr(p["voz-000"], limpa) > 0.999  # o degrau 0 é a voz limpa
    soma = p["voz-000"] + p["fundo"]
    assert _corr(soma, p["original"]) > 0.999  # Voz 0% + Fundo 100% = o original
    assert np.sqrt(np.mean(soma ** 2)) / np.sqrt(np.mean(p["original"] ** 2)) == pytest.approx(1, abs=0.01)
    niveis = [mv.lufs(p[k]) for k in ("voz-000", "voz-050", "voz-100")]
    assert max(niveis) - min(niveis) < 0.5  # arrastar a Voz não muda o volume
    assert max(float(np.abs(x).max()) for x in p.values()) <= mv.TETO + 1e-3
    s = mv.situacao(projeto)
    assert s["preparo"] == "pronto" and s["escolha"] == mv.PADRAO and s["aplicado"] is None and not s["reaplicar"]
    assert all((projeto / rel).is_file() for rel in s["previa"].values())
    assert mv.andamento(projeto)["etapa"] == "pronto"
    assert _preparar(projeto) == e  # o mesmo corte: nada a refazer


def test_ler_audio_mono_e_estereo_sem_mudar_o_volume(tmp_path):
    # o ffmpeg abre um arquivo mono em estéreo a −3 dB por canal: a voz limpa do DeepFilterNet
    # (mono) chegava 3 dB abaixo do original (estéreo) e 29% da voz sobrava no fundo
    a, b = 0.5 * np.sin(np.arange(SR) / 7), 0.3 * np.cos(np.arange(SR) / 11)
    for nome, canais, dados in (("mono.wav", 1, a), ("estereo.wav", 2, np.stack([a, b], 1).ravel())):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(canais), "-i", "-",
                        "-c:a", "pcm_f32le", str(tmp_path / nome)], input=dados.astype(np.float32).tobytes(), check=True)
    assert np.abs(mv.ler_audio(tmp_path / "mono.wav") - a).max() < 1e-6
    assert np.abs(mv.ler_audio(tmp_path / "estereo.wav") - (a + b) / 2).max() < 1e-6


FALSO_DF = """
import subprocess, sys
from pathlib import Path
a = sys.argv[1:]
assert "-D" in a and a[a.index("-a") + 1] == "100", a
saida, ent = Path(a[a.index("-o") + 1]), Path(a[-1])
saida.mkdir(parents=True, exist_ok=True)
pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ent), "-f", "f32le", "-"], capture_output=True, check=True).stdout
# como o DeepFilterNet 0.5.6: mono, 16 bits e 30 ms mais curto que a entrada
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", "48000", "-ac", "1", "-i", "-",
                "-c:a", "pcm_s16le", str(saida / ent.name)], input=pcm[:len(pcm) - 1440 * 4], check=True)
"""


def test_voz_limpa_passa_por_arquivo_sem_perder_volume(projeto, tmp_path):
    falso = tmp_path / "df_falso.py"
    falso.write_text(FALSO_DF, encoding="utf-8")
    mv.preparar(projeto, eco=False, estudio=_estudio,
                limpar=lambda x: mv.limpar_deepfilter(x, [sys.executable, "-I", str(falso)]))
    pasta = projeto / mv.PASTA
    orig = mv.ler_audio(projeto / "cut.mp4")
    limpa, fundo = np.load(pasta / "limpa.npy"), np.load(pasta / "fundo.npy")
    # o falso devolve a própria entrada: a voz limpa é o original, até o fim (a folga cobre os 30 ms),
    # e o fundo é só o arredondamento de 16 bits
    assert np.abs(limpa - orig).max() < 1e-4
    assert 20 * np.log10(np.sqrt(np.mean(fundo ** 2)) / np.sqrt(np.mean(orig ** 2))) < -60


def test_estudio_sai_alinhado_com_a_voz_limpa(projeto):
    _preparar(projeto)
    pasta = projeto / mv.PASTA
    limpa, estudio = np.load(pasta / "limpa.npy"), np.load(pasta / "estudio.npy")
    cru = _estudio.gerar(_estudio.caracteristicas(mv.reamostrar(mv.ler_audio(projeto / "cut.mp4"), SR, mv.SR_SIDON)))
    assert mv.atraso(limpa, cru) == ATRASO_ESTUDIO  # o de mentira vem 3 ms atrasado…
    assert mv.atraso(limpa, estudio) == 0  # …e o preparo alinhou


def test_voz_limpa_atrasada_e_realinhada(projeto):
    def atrasada(x):
        return np.concatenate([np.zeros(7), _limpar(x)])[:len(x)]

    mv.preparar(projeto, eco=False, limpar=atrasada, estudio=_estudio)
    ref = _limpar(mv.ler_audio(projeto / "cut.mp4"))
    limpa = np.load(projeto / mv.PASTA / "limpa.npy")
    assert np.abs(limpa[:-7] - ref[:-7]).max() < 1e-6


def test_pedacos_do_mesmo_tamanho_sem_passar_do_bloco():
    # 82,6 s em blocos fixos de 30 s deixavam um último pedaço de 4,8 s, com pouco contexto
    for seg, bloco in ((82.6, 30.0), (89.9, 30.0), (43.0, 30.0), (60.0, 30.0), (29.0, 30.0), (95.0, 15.0)):
        x = _fala(seg, 3)
        cortes = mv.pedacos(x, bloco)
        k = -(-len(x) // int(bloco * SR))
        assert len(cortes) == k and cortes[0][0] == 0 and cortes[-1][1] == len(x)
        assert all(b - a <= bloco * SR and a % 3 == 0 for a, b in cortes)
        if k > 1:
            ideal = len(x) / k
            assert all(0.7 * ideal <= b - a <= 1.3 * ideal for a, b in cortes), (seg, bloco, cortes)


def test_pedacos_cortam_no_quieto_e_emendam_sem_marca():
    x = _fala(5.0, 2)
    cortes = mv.pedacos(x, bloco=1.5)
    assert len(cortes) >= 3 and cortes[0][0] == 0 and cortes[-1][1] == len(x)
    assert all(b - a <= 1.5 * SR and a % 3 == 0 for a, b in cortes)
    assert all(cortes[i][1] == cortes[i + 1][0] for i in range(len(cortes) - 1))
    rms = np.sqrt(np.mean(x ** 2))
    for a, _ in cortes[1:]:  # cada emenda cai entre sílabas
        assert np.sqrt(np.mean(x[a - SR // 40:a + SR // 40] ** 2)) < 0.3 * rms

    sem_atraso = _Estudio(atraso=0, timbre=False)
    um = mv.estudio_em_pedacos(x, x, sem_atraso, bloco=100, contexto=1.0)
    varios = mv.estudio_em_pedacos(x, x, sem_atraso, bloco=1.5, contexto=1.0)
    fim = len(x) - 2 * 960  # o falso sai 20 ms mais curto: o fim fica sem estúdio nos dois
    assert np.abs(um[:fim] - varios[:fim]).max() < 1e-9


@pytest.mark.parametrize("gb,pedaco", [(15.8, (30.0, 3.0)), (12.0, (30.0, 3.0)), (7.9, (15.0, 2.0)),
                                         (None, (15.0, 2.0))])
def test_pedaco_do_sidon_pela_memoria_do_computador(monkeypatch, gb, pedaco):
    # 30 s + 3 s: pico de 3,8 GB e o mais fiel à rodada única; 15 s + 2 s: 2,0 GB (medido em 23/10)
    monkeypatch.setattr(mv, "memoria_gb", lambda: gb)
    assert mv.pedaco_do_computador() == pedaco


def test_memoria_do_computador_e_lida():
    gb = mv.memoria_gb()
    assert gb is not None and 1 < gb < 4096


def test_caracteristicas_iguais_as_do_extrator_publicado():
    # o Sidon roda em pedaços com a normalização do vídeo inteiro; numa rodada só, as
    # características têm que ser exatamente as do extrator (com janela de enchimento ou sem)
    tf = pytest.importorskip("transformers")
    ex = tf.SeamlessM4TFeatureExtractor(feature_size=80, num_mel_bins=80, sampling_rate=16000, stride=2,
                                        padding_value=1.0, padding_side="right", return_attention_mask=True)
    for n in (48000, 48160):  # 298 janelas (par) e 299 (ímpar: o extrator completa com enchimento)
        x = (0.1 * np.random.default_rng(6).standard_normal(n)).astype(np.float32)
        ref = ex(x, sampling_rate=16000, return_tensors="np")["input_features"][0]
        assert np.abs(mv.caracteristicas(x) - ref).max() < 1e-4


def test_degraus_dividem_a_fase_e_misturar_dois_nao_dobra():
    # uma voz limpa não tem chiado: onde ela fica 45 dB abaixo do pico do quadro, o desenho usa a
    # fase do estúdio, e um chiado a −47 dB faria o degrau 0 diferir da entrada de propósito
    limpa = _fala(2.0, 3, chiado=0)
    estudio = np.convolve(_fala(2.0, 4), [0.2, 0.5, 0.3], mode="same")
    assert np.abs(mv.vozes(limpa, limpa, [0])[0] - limpa).max() < 1e-5  # ida e volta pela STFT
    v = dict(zip((0, 0.25, 0.5, 0.75), mv.vozes(limpa, estudio, [0, 0.25, 0.5, 0.75])))
    assert _corr(v[0], limpa) > 0.999
    # a prévia mistura dois degraus vizinhos; o aplicar faz a conta exata: as duas ficam perto
    assert _corr(0.5 * v[0.25] + 0.5 * v[0.75], v[0.5]) > 0.99


def test_aplicar_troca_o_som_e_mantem_a_imagem(projeto):
    _preparar(projeto)
    corte = projeto / "cut.mp4"
    img, fonte = _hash(corte, "v"), mv.hash_audio(corte)
    esperado = mv.mistura(projeto, 60, 30)
    e = mv.aplicar(projeto, 60, 30, eco=False)
    assert _hash(corte, "v") == img  # a imagem não foi recodificada
    assert e["aplicado"]["hash"] == mv.hash_audio(corte) != fonte
    assert e["escolha"] == {"voz": 60, "fundo": 30} == mv.situacao(projeto)["aplicado"]
    novo = mv.ler_audio(corte)
    assert len(novo) == len(mv.ler_audio(projeto / mv.PASTA / "original.m4a"))  # nem o fim encurta
    assert mv._atraso_fino(esperado, novo) == 0  # a boca bate: o som novo no mesmo tempo
    assert _corr(novo, esperado) > 0.99
    # loudnorm do kit: −14 LUFS no estéreo, que é −17 em cada canal (L = R)
    assert mv.lufs(novo) == pytest.approx(-17, abs=1)
    s = mv.situacao(projeto)
    assert s["preparo"] == "pronto" and not s["reaplicar"]


def test_restaurar_devolve_o_som_original_byte_a_byte(projeto):
    _preparar(projeto)
    corte = projeto / "cut.mp4"
    antes, fonte = mv.ler_audio(corte), mv.hash_audio(corte)
    mv.aplicar(projeto, 40, 0, eco=False)
    assert mv.restaurar(projeto)
    assert mv.hash_audio(corte) == fonte
    assert np.array_equal(mv.ler_audio(corte), antes)  # nem uma amostra de atraso
    assert mv.situacao(projeto)["aplicado"] is None
    assert not mv.restaurar(projeto)


def test_voz_zero_e_fundo_cem_e_o_original_exato(projeto):
    _preparar(projeto)
    fonte = mv.hash_audio(projeto / "cut.mp4")
    mv.aplicar(projeto, 80, 10, eco=False)
    e = mv.aplicar(projeto, 0, 100, eco=False)
    assert mv.hash_audio(projeto / "cut.mp4") == fonte
    assert e["aplicado"] is None and e["escolha"] == {"voz": 0, "fundo": 100}


def test_corte_novo_pede_preparo_novo_e_a_escolha_continua(projeto, monkeypatch):
    _preparar(projeto)
    mv.aplicar(projeto, 70, 10, eco=False)
    _gravar_corte(projeto, _fala(3.0, 9))  # o agente renderizou o corte de novo
    s = mv.situacao(projeto)
    assert s["preparo"] == "velho" and s["reaplicar"] and s["aplicado"] is None
    assert s["escolha"] == {"voz": 70, "fundo": 10}
    chamou = []
    real = mv.preparar

    def preparar(edit, **kw):
        chamou.append(edit)
        return real(edit, **kw, limpar=_limpar, estudio=_estudio)

    monkeypatch.setattr(mv, "preparar", preparar)
    e = mv.aplicar(projeto, eco=False)  # sem números: a última escolha
    assert chamou and (e["aplicado"]["voz"], e["aplicado"]["fundo"]) == (70, 10)
    s = mv.situacao(projeto)
    assert s["preparo"] == "pronto" and s["aplicado"] == {"voz": 70, "fundo": 10} and not s["reaplicar"]


def test_public_do_mesmo_corte_ganha_o_mesmo_som(projeto):
    pub = projeto / "remotion" / "public" / "cut.mp4"
    pub.parent.mkdir(parents=True)
    shutil.copyfile(projeto / "cut.mp4", pub)
    _preparar(projeto)
    img = _hash(pub, "v")
    mv.aplicar(projeto, 50, 20, eco=False)
    assert mv.hash_audio(pub) == mv.hash_audio(projeto / "cut.mp4") and _hash(pub, "v") == img
    mv.restaurar(projeto)
    assert mv.hash_audio(pub) == mv.hash_audio(projeto / "cut.mp4")


def test_public_de_outro_corte_fica_como_esta(projeto):
    pub = _gravar_corte(projeto / "remotion" / "public", _fala(3.0, 5))
    antes = mv.hash_audio(pub)
    _preparar(projeto)
    mv.aplicar(projeto, 50, 20, eco=False)
    assert mv.hash_audio(pub) == antes


def test_preparo_que_falha_fica_no_andamento(projeto):
    def quebra(x):
        raise mv.VozErro("o DeepFilterNet falhou: teste")

    with pytest.raises(mv.VozErro):
        mv.preparar(projeto, eco=False, limpar=quebra, estudio=_estudio)
    a = mv.andamento(projeto)
    assert a["etapa"] == "falhou" and "teste" in a["erro"] and not a["vivo"]
    s = mv.situacao(projeto)
    assert s["preparo"] == "nenhum" and s["andamento"]["erro"] == a["erro"]


def test_video_que_nao_serve_e_recusado_antes_de_baixar_os_modelos(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTMIND_VOZ_DIR", str(tmp_path / "voz"))
    edit = tmp_path / "edit"
    _gravar_corte(edit, _fala(0.3, 1))
    monkeypatch.setattr(mv, "baixar_modelos", lambda *a: pytest.fail("baixou 1 GB para um vídeo que não serve"))
    with pytest.raises(mv.VozErro, match="curto demais"):
        mv.preparar(edit, eco=False)
    assert mv.andamento(edit)["etapa"] == "falhou"


def test_video_fora_do_projeto_e_recusado(projeto):
    (projeto / "state.json").write_text(json.dumps({"video": "../../fora.mp4"}), encoding="utf-8")
    with pytest.raises(mv.VozErro, match="fora do projeto"):
        mv.video(projeto)


@pytest.mark.parametrize("so,maq,fim", [
    ("Windows", "AMD64", "x86_64-pc-windows-msvc.exe"), ("Windows", "ARM64", "x86_64-pc-windows-msvc.exe"),
    ("Darwin", "arm64", "aarch64-apple-darwin"), ("Darwin", "x86_64", "x86_64-apple-darwin"),
    ("Linux", "x86_64", "x86_64-unknown-linux-musl"), ("Linux", "aarch64", "aarch64-unknown-linux-gnu")])
def test_executavel_do_deepfilternet_por_sistema(monkeypatch, so, maq, fim):
    monkeypatch.setattr(mv.platform, "system", lambda: so)
    monkeypatch.setattr(mv.platform, "machine", lambda: maq)
    ms = mv.modelos()
    assert ms[0]["arquivo"].endswith(fim) and ms[0]["executavel"]
    assert [m["arquivo"] for m in ms[1:]] == ["sidon-predictor-fp32.onnx", "sidon-vocoder-fp32.onnx"]
    assert sum(m["tamanho"] for m in ms) < 1.1e9


def test_sistema_sem_executavel(monkeypatch):
    monkeypatch.setattr(mv.platform, "system", lambda: "FreeBSD")
    with pytest.raises(mv.VozErro, match="FreeBSD"):
        mv.modelos()


def test_modelos_presos_numa_versao(monkeypatch):
    # o sha256 confere um arquivo fixo: o endereço não pode seguir a última versão
    for so, maq in (("Windows", "AMD64"), ("Darwin", "arm64"), ("Linux", "x86_64")):
        monkeypatch.setattr(mv.platform, "system", lambda: so)
        monkeypatch.setattr(mv.platform, "machine", lambda: maq)
        for m in mv.modelos():
            assert re.search(r"/resolve/[0-9a-f]{40}/|/releases/download/v\d+\.\d+\.\d+/", m["url"]), m["url"]
            assert re.fullmatch(r"[0-9a-f]{64}", m["sha256"]) and m["tamanho"] > 1_000_000


class _Servidor:
    """Um servidor de modelos local que entende Range e sabe cair no meio."""

    def __init__(self, dados: bytes):
        self.dados, self.corte, self.pedidos = dados, None, []
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                rng = self.headers.get("Range")
                srv.pedidos.append(rng)
                ini = int(rng.split("=")[1].split("-")[0]) if rng else 0
                corpo = srv.dados[ini:]
                self.send_response(206 if rng else 200)
                self.send_header("Content-Length", str(len(corpo)))
                if rng:
                    self.send_header("Content-Range", f"bytes {ini}-{len(srv.dados) - 1}/{len(srv.dados)}")
                self.end_headers()
                self.wfile.write(corpo if srv.corte is None else corpo[:srv.corte])

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/modelo.onnx"


def test_baixar_continua_de_onde_parou_e_confere_o_sha(tmp_path):
    dados = np.random.default_rng(4).bytes(300_000)
    srv = _Servidor(dados)
    m = {"arquivo": "modelo.onnx", "url": srv.url, "tamanho": len(dados), "sha256": hashlib.sha256(dados).hexdigest()}
    destino, part = tmp_path / "modelo.onnx", tmp_path / "modelo.onnx.part"
    andou = []
    try:
        srv.corte = 100_000
        with pytest.raises(mv.VozErro, match="pela metade"):
            mv._baixar(m, destino, andou.append)
        assert part.stat().st_size == 100_000 and not destino.exists()
        srv.corte = None
        mv._baixar(m, destino, andou.append)
        assert srv.pedidos[-1] == "bytes=100000-"  # continuou, não recomeçou
        assert destino.read_bytes() == dados and not part.exists() and sum(andou) == len(dados)
        destino.unlink()
        with pytest.raises(mv.VozErro, match="diferente"):
            mv._baixar({**m, "sha256": "0" * 64}, destino, andou.append)
        assert not destino.exists() and not part.exists()  # o que chegou errado não fica
    finally:
        srv.httpd.shutdown()


def test_baixar_modelos_guarda_no_cache_e_avisa_o_andamento(tmp_path, monkeypatch):
    dados = np.random.default_rng(5).bytes(200_000)
    srv = _Servidor(dados)
    m = {"arquivo": "deep-filter-teste", "url": srv.url, "tamanho": len(dados),
         "sha256": hashlib.sha256(dados).hexdigest(), "executavel": True}
    monkeypatch.setenv("CUTMIND_VOZ_DIR", str(tmp_path / "voz"))
    monkeypatch.setattr(mv, "modelos", lambda: [m])
    visto = []
    try:
        pasta = mv.baixar_modelos(lambda feito, total: visto.append((feito, total)))
        assert (pasta / m["arquivo"]).read_bytes() == dados and visto[-1] == (len(dados), len(dados))
        if sys.platform != "win32":
            assert (pasta / m["arquivo"]).stat().st_mode & 0o100
        n = len(srv.pedidos)
        mv.baixar_modelos()  # já está: não pede de novo
        assert len(srv.pedidos) == n
    finally:
        srv.httpd.shutdown()


def test_linha_de_comando(projeto):
    cli = [sys.executable, "-X", "utf8", str(HELPERS / "melhorar_voz.py")]
    r = subprocess.run([*cli, "estado", str(projeto)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    s = json.loads(r.stdout)
    assert s["preparo"] == "nenhum" and s["escolha"] == mv.PADRAO and s["modelos"]["prontos"] is False
    r = subprocess.run([*cli, "aplicar", str(projeto), "--voz", "150"], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 1 and "0 a 100" in r.stderr
