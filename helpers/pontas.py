"""Pontas seguras: nenhuma ponta de tomada do edl.json fica no meio de um som.

Edição real de 01/11: a pessoa achou palavra cortada três vezes seguidas ("se resolver um erro pontual
isso pode acontecer de novo"). Duas causas:
- a régua fixa (-33 dB) erra num take com ruído de sala alto (piso -39,6 dB): o fim da palavra e a
  respiração ficam perto dela, e a ponta cai no meio do som. Aqui o "quieto" é medido POR GRAVAÇÃO:
  o piso de ruído dela (percentil 10 do nível em janelas de 10 ms) + MARGEM_DB;
- o alinhador estica palavra sobre pausa (uma palavra de 3,2 s escondia um tropeço), então o tempo da
  palavra não serve de ponta.

Uma ponta no meio de um som: ou o som começou há pouco (é a palavra SEGUINTE, que ficou de fora) ou vem
de antes (é a palavra que FICA). Não dá para ir sempre ao ponto mais baixo por perto: a oclusão de um
"c" ou de um "p" é um silêncio curto DENTRO da palavra ("A|cabei"). Vale o silêncio mais perto, e a ponta
fica DENTRO_S dentro dele, de modo que rodar de novo não muda nada.

Na fala corrida (sem silêncio perto) a ponta NÃO anda: vai para a lista "ouvir". Depois de ouvir, ponha
"inicio" e/ou "fim" em `pontas_ouvidas` da tomada no edl.json; essas pontas ficam como estão.

    uv run python -X utf8 helpers/pontas.py <edit> [--aplicar]

Sem --aplicar só mostra. Sai 0 sem nada para ouvir; 1 com pontas na lista "ouvir".
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 16000
FR = 160  # 10 ms por ponto
MARGEM_DB = 7.0
QUIETO_S = 0.06  # um silêncio, para a ponta, dura pelo menos isto
AVANCO_FIM_S = 0.35  # o fim anda até isto para a frente atrás do fim da palavra
RECUO_INICIO_S = 0.25  # o começo recua até isto atrás do começo da palavra
ATRAS_S = 0.12  # o silêncio do lado "errado" (antes do fim, depois do começo) vale só até aqui
DENTRO_S = 0.03  # a ponta fica isto dentro do silêncio
MINIMO_S = 0.3  # nenhuma tomada encolhe abaixo disto


def niveis(fonte: Path) -> np.ndarray:
    """O nível (dB) da gravação, um ponto a cada 10 ms."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(fonte), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.float32)
    n = len(a) // FR
    q = a[: n * FR].reshape(n, FR)
    return 20 * np.log10(np.sqrt((q ** 2).mean(axis=1)) + 1e-9)


def limiar(niv: np.ndarray) -> float:
    """O que é "quieto" nesta gravação: o piso de ruído dela + MARGEM_DB."""
    return float(np.percentile(niv, 10)) + MARGEM_DB


def _quieto(niv, lim, t0, t1) -> bool:
    a, b = max(0, int(round(t0 * 100))), min(len(niv), int(round(t1 * 100)))
    if a >= len(niv):  # depois do fim da gravação não há som (uma ponta pode passar dele)
        return True
    return b > a and bool((niv[a:b] < lim).all())


def _silencio(niv, lim, x, limite, para_tras) -> float | None:
    """Quanto andar (s) a partir de `x` até a borda do silêncio mais perto daquele lado (None: passou de `limite`)."""
    d = 0.0
    while d <= limite + 1e-9:
        if (_quieto(niv, lim, x - d - QUIETO_S, x - d) if para_tras else _quieto(niv, lim, x + d, x + d + QUIETO_S)):
            return d
        d += 0.01
    return None


def ajustar_fim(niv, lim, e: float, dur: float) -> tuple[float, str]:
    if _quieto(niv, lim, e - 0.02, e + 0.02):
        return e, "ok"
    atras = _silencio(niv, lim, e, ATRAS_S, True)
    frente = _silencio(niv, lim, e, AVANCO_FIM_S, False)
    if atras is not None and (frente is None or atras <= frente):
        return e - atras - DENTRO_S, "antes da palavra seguinte"
    if frente is not None:
        return min(e + frente + DENTRO_S, dur), "até o fim da palavra"
    return e, "ouvir"  # fala corrida: nenhuma conta decide


def ajustar_inicio(niv, lim, s: float) -> tuple[float, str]:
    if _quieto(niv, lim, s - 0.02, s + 0.02):
        return s, "ok"
    frente = _silencio(niv, lim, s, ATRAS_S, False)
    atras = _silencio(niv, lim, s, RECUO_INICIO_S, True)
    if frente is not None and (atras is None or frente < atras):
        return s + frente + DENTRO_S, "depois do resto da palavra anterior"
    if atras is not None:
        return max(s - atras - DENTRO_S, 0.0), "antes do começo da palavra"
    return s, "ouvir"


def ajustar(edl: dict, base: Path, medir=niveis) -> list[dict]:
    """As pontas que mudam (e as que é preciso ouvir), uma entrada por ponta. Não mexe no edl."""
    cache: dict[str, tuple] = {}
    out = []
    for i, r in enumerate(edl.get("ranges") or []):
        src = r["source"]
        if src not in cache:
            caminho = Path(edl["sources"][src])
            niv = medir(caminho if caminho.is_absolute() else (base / caminho).resolve())
            cache[src] = (niv, limiar(niv), len(niv) / 100)
        niv, lim, dur = cache[src]
        s0, e0 = float(r["start"]), float(r["end"])
        ouvidas = r.get("pontas_ouvidas") or []
        s1, cs = (s0, "ok") if "inicio" in ouvidas else ajustar_inicio(niv, lim, s0)
        e1, ce = (e0, "ok") if "fim" in ouvidas else ajustar_fim(niv, lim, e0, dur)
        if e1 - s1 < MINIMO_S:  # nunca encolher uma tomada a nada
            s1, e1 = s0, e0
            cs, ce = ("ok" if cs != "ouvir" else cs), ("ok" if ce != "ouvir" else ce)
        for ponta, a, b, como in (("inicio", s0, s1, cs), ("fim", e0, e1, ce)):
            if como == "ouvir" or abs(b - a) >= 0.005:
                out.append({"tomada": i, "source": src, "ponta": ponta, "de": round(a, 3), "para": round(b, 3), "como": como})
    return out


def aplicar(edl: dict, mudancas: list[dict]) -> int:
    """Põe as pontas novas no edl (as de "ouvir" ficam). Devolve quantas mudaram."""
    n = 0
    for m in mudancas:
        if m["como"] == "ouvir":
            continue
        edl["ranges"][m["tomada"]]["start" if m["ponta"] == "inicio" else "end"] = m["para"]
        n += 1
    if n:
        edl.pop("jcut_timeline", None)  # a linha do tempo do J-cut era a do corte velho
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--aplicar", action="store_true")
    a = ap.parse_args()
    edl_p = a.edit / "edl.json"
    edl = json.loads(edl_p.read_text(encoding="utf-8"))
    mud = ajustar(edl, a.edit)
    for m in mud:
        print(f"[{m['tomada']:2d}] {m['source']} {m['ponta']:6} {m['de']:8.3f} -> {m['para']:8.3f} "
              f"({(m['para'] - m['de']) * 1000:+5.0f} ms, {m['como']})")
    ouvir = [m for m in mud if m["como"] == "ouvir"]
    if a.aplicar:
        n = aplicar(edl, mud)
        if n:
            edl_p.write_bytes((json.dumps(edl, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(f"{n} ponta(s) ajustada(s) em {len(edl.get('ranges') or [])} tomadas")
    else:
        print(f"{len(mud) - len(ouvir)} ponta(s) a ajustar (rode com --aplicar)")
    if ouvir:
        print(f"{len(ouvir)} ponta(s) na fala corrida, sem silêncio perto: OUÇA (conferir_emendas.py depois do render) "
              "e ponha \"inicio\"/\"fim\" em `pontas_ouvidas` da tomada")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
