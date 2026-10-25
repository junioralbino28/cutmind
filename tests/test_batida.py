"""A grade de batida: BPM, confiança, energia por compasso, drop, cache pelo conteúdo, cliques e o
download conferido. Os testes do modelo de verdade (cliques sintéticos a 90, 120 e 140 BPM, troca de
andamento, silêncio) só rodam quando o modelo pequeno já está baixado neste computador."""
import hashlib
import importlib.util
import io
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("batida", RAIZ / "helpers" / "batida.py")
b = importlib.util.module_from_spec(_spec)
sys.modules["batida"] = b
_spec.loader.exec_module(b)


def test_bpm_pela_mediana_mesmo_com_batida_perdida():
    batidas = [i * 0.5 for i in range(40)]
    del batidas[10]
    assert b.bpm(batidas) == 120.0
    assert b.bpm([1.0]) is None


def test_confianca():
    regular = [i * 0.5 for i in range(40)]
    rng = np.random.default_rng(1)
    torta = np.cumsum(rng.uniform(0.2, 0.9, 40))
    assert b.confianca(regular) == "alta"
    assert b.confianca(torta) == "baixa"
    assert b.confianca(regular[:5]) == "baixa"   # poucas batidas não dão para confiar


def test_compassos_tem_energia_relativa_ao_mais_forte():
    sr = 1000
    sinal = np.concatenate([np.full(4 * sr, 0.1), np.full(4 * sr, 1.0)]).astype(np.float32)
    itens = b.compassos(sinal, sr, [0.0, 2.0, 4.0, 6.0], 8.0)
    assert [i["inicio"] for i in itens] == [0.0, 2.0, 4.0, 6.0]
    assert [i["energia"] for i in itens] == [0.1, 0.1, 1.0, 1.0]


def test_drop_e_a_maior_subida_de_energia():
    itens = [{"inicio": 2.0 * k, "fim": 2.0 * k + 2, "energia": 0.2 if k < 8 else 0.9} for k in range(16)]
    assert b.achar_drop(itens) == 16.0
    plano = [{"inicio": 2.0 * k, "fim": 2.0 * k + 2, "energia": 0.8} for k in range(16)]
    assert b.achar_drop(plano) is None          # sem subida clara, sem drop
    baixinho = [{"inicio": 2.0 * k, "fim": 2.0 * k + 2, "energia": 0.1 if k < 8 else 0.4} for k in range(16)]
    assert b.achar_drop(baixinho) is None       # subiu, mas não "explodiu"


def _wav(caminho: Path, segundos: float, freq: float = 440.0) -> Path:
    sr = 22050
    t = np.arange(int(segundos * sr)) / sr
    b._grava_wav(caminho, 0.3 * np.sin(2 * np.pi * freq * t), sr)
    return caminho


def test_cache_e_pelo_conteudo_nao_pelo_nome(tmp_path, monkeypatch):
    chamadas = []

    def falso(sinal, sr, modelo=b.MODELO_PADRAO):
        chamadas.append(len(sinal))
        return np.array([0.5, 1.0, 1.5, 2.0]), np.array([0.5, 1.5])

    monkeypatch.setattr(b, "detectar", falso)
    edit = tmp_path / "edit"
    musica = _wav(tmp_path / "musica.wav", 3.0)
    grade, destino = b.analisar(musica, edit)
    assert len(chamadas) == 1
    assert destino.parent == edit / "batidas"
    assert grade["batidas"] == [0.5, 1.0, 1.5, 2.0] and grade["fortes"] == [0.5, 1.5]
    assert grade["bpm"] == 120.0 and grade["duracao"] == 3.0

    renomeada = musica.rename(tmp_path / "outro nome.wav")
    b.analisar(renomeada, edit)
    assert len(chamadas) == 1                   # mesmo conteúdo: veio do cache

    _wav(renomeada, 3.0, freq=880.0)
    b.analisar(renomeada, edit)
    assert len(chamadas) == 2                   # conteúdo novo: analisa de novo


def test_cliques_caem_nas_batidas_e_o_forte_e_mais_forte():
    sr = 44100
    faixa = b.cliques([0.5, 1.0], [0.5], 2.0, sr)
    assert len(faixa) == 2 * sr
    assert np.abs(faixa[: int(0.49 * sr)]).max() == 0
    forte = np.abs(faixa[int(0.5 * sr): int(0.53 * sr)]).max()
    fraco = np.abs(faixa[int(1.0 * sr): int(1.03 * sr)]).max()
    assert forte > fraco > 0


def test_baixar_recusa_arquivo_diferente_e_aceita_o_certo(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTMIND_BATIDA_DIR", str(tmp_path))
    certo = b"pesos de mentira" * 100
    monkeypatch.setitem(b.MODELOS, "teste", {"nome": "teste", "arquivo": "teste.ckpt", "tamanho": len(certo),
                                             "sha256": hashlib.sha256(certo).hexdigest()})
    entrega = {"dados": b"x" * len(certo)}

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(b.urllib.request, "urlopen", lambda req, timeout: Resposta(entrega["dados"]))
    with pytest.raises(b.ErroBatida):
        b.baixar("teste")
    assert not list(tmp_path.glob("*"))         # nem o arquivo nem o .part ficam
    entrega["dados"] = certo
    assert b.baixar("teste").read_bytes() == certo


# ---- com o modelo de verdade ----

MODELO_BAIXADO = (b.pasta() / b.MODELOS["pequeno"]["arquivo"]).is_file()
precisa_modelo = pytest.mark.skipif(not MODELO_BAIXADO, reason="modelo pequeno do Beat This! não baixado")


def _bateria(sr: int, bpm: float, segundos: float) -> np.ndarray:
    """Uma batida de rock: bumbo no 1 e no 3, caixa no 2 e no 4, chimbal em colcheias, baixo na
    tônica e um acorde que muda a cada compasso. Bumbo em toda batida com chimbal no contratempo
    confundia o modelo (contava o dobro ou o triplo): o que ele reconhece é música, não metrônomo."""
    rng = np.random.default_rng(3)
    s = np.zeros(int(segundos * sr), np.float32)
    p = 60.0 / bpm

    def env(n, k):
        return np.exp(-np.arange(n) / sr * k)

    t = np.arange(int(0.15 * sr)) / sr
    bumbo = np.sin(2 * np.pi * (50 + 60 * np.exp(-t * 40)) * t) * env(len(t), 25)
    ns = int(0.18 * sr)
    caixa = (rng.normal(0, 0.5, ns) + np.sin(2 * np.pi * 190 * np.arange(ns) / sr)) * env(ns, 22)
    nh = int(0.04 * sr)
    chimbal = np.diff(rng.normal(0, 0.3, nh + 1)) * env(nh, 90)

    def poe(x, at, ganho=1.0):
        fim = min(len(s), at + len(x))
        if at < fim:
            s[at:fim] += ganho * x[: fim - at]

    k = 0
    while k * p < segundos - 0.3:
        i = int(k * p * sr)
        poe(bumbo if k % 2 == 0 else caixa, i, 1.0 if k % 2 == 0 else 0.6)
        poe(chimbal, i, 0.35)
        poe(chimbal, int((k + 0.5) * p * sr), 0.25)
        f = (110.0, 146.8, 130.8, 98.0)[(k // 4) % 4]
        nd = int(p * sr * 0.9)
        poe(0.25 * np.sin(2 * np.pi * f * np.arange(nd) / sr) * env(nd, 3), i)
        if k % 4 == 0:
            ta = np.arange(int(4 * p * sr)) / sr
            pad = sum(np.sin(2 * np.pi * f * m * ta) for m in (2, 2.52, 3))
            poe(0.06 * pad * env(len(ta), 0.8), i)
        k += 1
    return s / max(1e-6, float(np.abs(s).max())) * 0.8


@precisa_modelo
@pytest.mark.parametrize("andamento", [90, 120, 140])
def test_acha_as_batidas_de_uma_bateria(andamento):
    sinal = _bateria(b.SR, andamento, 20.0)
    batidas, fortes = b.detectar(sinal, b.SR, "pequeno")
    esperado = np.arange(0, 19.7, 60.0 / andamento)
    meio = esperado[(esperado > 1.0) & (esperado < 18.5)]
    perto = [np.min(np.abs(batidas - e)) <= 0.03 for e in meio]
    assert sum(perto) / len(perto) >= 0.95
    assert abs(b.bpm(batidas) - andamento) <= 0.5
    assert set(np.round(fortes, 3)) <= set(np.round(batidas, 3))   # o tempo forte é uma das batidas


@precisa_modelo
def test_acompanha_a_troca_de_andamento():
    """30 s em cada andamento, como numa música. Medido em 24/10/2026: com só 10 s em cada um, o
    pequeno acerta 62% das batidas e o completo 88%; troca curta e brusca confunde, e é a prova de
    ouvido que pega."""
    sinal = np.concatenate([_bateria(b.SR, 100, 30.0), _bateria(b.SR, 130, 30.0)])
    batidas, _ = b.detectar(sinal, b.SR, "pequeno")
    assert abs(b.bpm(batidas[batidas < 28.0]) - 100) <= 1
    assert abs(b.bpm(batidas[batidas > 32.0]) - 130) <= 1


@precisa_modelo
def test_silencio_nao_quebra():
    batidas, fortes = b.detectar(np.zeros(5 * b.SR, dtype=np.float32), b.SR, "pequeno")
    assert len(batidas) <= 2 and len(fortes) <= 2
