"""Os efeitos de voz (item `voz` do efeitos.json): o trecho muda, a sincronia não.

Pedido no Reels 1 (29/10/2026): a voz de gás hélio na quebra de objeção. Lá, o deslocamento de tom do
ffmpeg adiantava o som 11 ms; aqui o deslocamento é medido em cada trecho e compensado. A prova é com
"sílabas" sintéticas em instantes conhecidos: fora do trecho, a voz sai igual amostra por amostra;
dentro, cada sílaba começa no mesmo lugar (até 10 ms).
"""
from __future__ import annotations

import json
import shutil
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import efeitos as ef  # noqa: E402
import efeitos_render  # noqa: E402
import voz_efeitos as vz  # noqa: E402

com_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="precisa do ffmpeg")
SR = vz.SR
SILABAS = [0.3 + 0.4 * i for i in range(14)]  # começos, em segundos


def _voz(dur: float = 6.0) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    y = np.zeros_like(t)
    for s in SILABAS:
        k = (t >= s) & (t < s + 0.14)
        tt = t[k] - s
        env = np.minimum(1, tt / 0.004) * np.exp(-tt * 9)
        y[k] += env * (np.sin(2 * np.pi * 220 * tt) + 0.5 * np.sin(2 * np.pi * 440 * tt) + 0.3 * np.sin(2 * np.pi * 660 * tt))
    y *= 0.3
    return np.stack([y, y], axis=1).astype(np.float32)


def _ataques(x: np.ndarray, de: float, ate: float) -> list[float]:
    m = np.abs(x).mean(axis=1)
    out = []
    for s in SILABAS:
        if not (de + 0.05 <= s <= ate - 0.2):
            continue
        a, b = int((s - 0.08) * SR), int((s + 0.08) * SR)
        trecho = m[a:b]
        out.append((a + int(np.argmax(trecho > 0.3 * trecho.max()))) / SR - s)
    return out


@com_ffmpeg
@pytest.mark.parametrize("efeito", sorted(vz.EFEITOS))
def test_fora_do_trecho_igual_e_dentro_na_mesma_hora(efeito):
    voz = _voz()
    out, feitos = vz.aplicar(voz, [{"inicio": 2.0, "duracao": 2.0, "efeito": efeito}])
    assert out.shape == voz.shape
    a, b = int(2.0 * SR), int(4.0 * SR)
    assert np.array_equal(out[:a], voz[:a])
    if efeito != "eco":  # o eco deixa a cauda passar do fim, de propósito
        assert np.array_equal(out[b:], voz[b:])
    assert not np.allclose(out[a + 2000:b - 2000], voz[a + 2000:b - 2000])  # mudou mesmo
    desvios = _ataques(out, 2.0, 4.0)
    assert desvios and max(abs(d) for d in desvios) <= 0.010, (efeito, [round(d * 1000, 1) for d in desvios], feitos)


@com_ffmpeg
@pytest.mark.parametrize("efeito", ["helio", "grave"])
def test_sem_rubberband_a_reserva_tambem_fica_na_hora(efeito, monkeypatch):
    monkeypatch.setattr(vz, "_RUBBERBAND", [False])
    assert vz.cadeia(efeito) == vz.RESERVA[efeito]
    out, _ = vz.aplicar(_voz(), [{"inicio": 2.0, "duracao": 2.0, "efeito": efeito}])
    desvios = _ataques(out, 2.0, 4.0)
    # o atempo oscila ~5 ms de sílaba para sílaba (medido: −9,8 a 6,6 ms no hélio); o rubberband, não
    assert desvios and max(abs(d) for d in desvios) <= 0.012, [round(d * 1000, 1) for d in desvios]


@com_ffmpeg
def test_o_helio_mede_e_compensa_o_adiantamento():
    voz = _voz()
    _, feitos = vz.aplicar(voz, [{"inicio": 2.0, "duracao": 2.0, "efeito": "helio"}])
    assert abs(feitos[0]["deslocamento_ms"]) <= vz.BUSCA * 1000


def test_o_efeitos_json_aceita_voz_e_recusa_o_que_nao_existe():
    ok = ef.normalize({"itens": [{"id": "v1", "tipo": "voz", "inicio": 1, "duracao": 2, "efeito": "helio"},
                                 {"id": "f1", "tipo": "filtro", "pacote": "filme-pb", "inicio": 1, "duracao": 2}]})
    assert ok["itens"][0] == {"id": "v1", "tipo": "voz", "inicio": 1.0, "duracao": 2.0, "efeito": "helio"}
    with pytest.raises(ef.EfeitosInvalidos):
        ef.normalize({"itens": [{"id": "v1", "tipo": "voz", "inicio": 1, "duracao": 2, "efeito": "foguete"}]})
    with pytest.raises(ef.EfeitosInvalidos):
        ef.normalize({"itens": [{"id": "v1", "tipo": "voz", "inicio": 1, "duracao": 2, "efeito": "eco"},
                                {"id": "v2", "tipo": "voz", "inicio": 2, "duracao": 2, "efeito": "robo"}]})
    assert set(ef.EFEITOS_VOZ) == set(vz.EFEITOS)


def test_o_desenho_dos_quadros_ignora_a_voz():
    rs = efeitos_render.receitas({"itens": [{"id": "v1", "tipo": "voz", "inicio": 0, "duracao": 1, "efeito": "eco"}]}, 30, 60)
    assert rs == []


def _projeto(tmp_path: Path, voz: np.ndarray, itens: list[dict]) -> Path:
    edit = tmp_path / "edit"
    edit.mkdir()
    with wave.open(str(edit / "cut.wav"), "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((voz * 32767).astype("<i2").tobytes())
    (edit / "state.json").write_text(json.dumps({"video": "cut.wav"}), encoding="utf-8")
    ef.save(edit / "efeitos.json", {"itens": itens})
    return edit


@com_ffmpeg
def test_preparar_guarda_e_so_refaz_quando_muda(tmp_path):
    edit = _projeto(tmp_path, _voz(), [{"id": "v1", "tipo": "voz", "inicio": 2.0, "duracao": 1.5, "efeito": "radio"}])
    p = vz.preparar(edit)
    assert p and p.is_file() and p.parent.name == vz.PASTA
    assert vz.preparar(edit) == p  # a mesma assinatura: não refaz
    ef.save(edit / "efeitos.json", {"itens": [{"id": "v1", "tipo": "voz", "inicio": 2.0, "duracao": 1.5, "efeito": "grave"}]})
    q = vz.preparar(edit)
    assert q != p and q.is_file() and not p.exists()
    ef.save(edit / "efeitos.json", {"itens": []})
    assert vz.preparar(edit) is None


@com_ffmpeg
def test_o_mix_final_usa_a_voz_com_efeito(tmp_path):
    import mixar_final as mf
    edit = _projeto(tmp_path, _voz(), [{"id": "v1", "tipo": "voz", "inicio": 2.0, "duracao": 1.5, "efeito": "eco"}])
    cmd, resumo = mf.montar(edit, edit / "cut.wav", edit / "final.mp4", 6.0, imagem="corte")
    entradas = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-i"]
    assert any(vz.PASTA in e and e.endswith(".wav") for e in entradas)
    assert resumo["voz"] == "corte com efeito de voz"


def test_o_editor_tem_a_folha_de_voz_e_o_servidor_a_previa():
    js = (RAIZ / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
    html = (RAIZ / "assets" / "preview" / "celular.html").read_text(encoding="utf-8")
    assert "tool(ctx, 'voz', t('Voz')" in js and "case 'voz':" in js and 'id="vfxSheet"' in html
    assert "if (it.tipo === 'voz' || !fxDentro(it, t)) continue;" in js  # a prévia dos quadros não desenha som
    for nome in vz.EFEITOS:
        assert f"{nome}: [t('" in js or f"  {nome}: [t('" in js, nome
    srv = (RAIZ / "helpers" / "preview_server.py").read_text(encoding="utf-8")
    assert '"/gen/voz-previa"' in srv
