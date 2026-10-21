#!/usr/bin/env python3
"""O vídeo final com os filtros, as transições e os ajustes do editor (efeitos.json).

Desenha cada quadro das janelas com o MESMO motor da prévia (assets/efeitos/motor.js),
pela composição EfeitosBase do projeto Remotion, e grava um cut.mp4 novo em
<remotion>/public/ com essas janelas trocadas. O resto do vídeo passa por uma regravação
de qualidade alta (crf 8: PSNR medido de 54 dB contra o corte, ~0,5 nível de cor),
porque regravar sem perda custa ~1 GB a cada 90 s. O som vai copiado.

Rodar depois de copiar o cut.mp4 para o public do Remotion e antes do render final, e
de novo sempre que o efeitos.json mudar (references/shortform.md, "Efeitos"):

    uv run python helpers/efeitos_render.py <edit> [--remotion <edit>/remotion]

Pelo número do quadro, com as contas da prévia (efeitos.py, celular.js): o quadro n está
no efeito se início − 1 ms ≤ n/fps < fim − 1 ms (a folga cobre o arredondamento de 3 casas
dos tempos gravados, que punha o 1º quadro da tomada seguinte dentro do filtro);
na transição, k = ⌊corte·fps + 0,5⌋ é o
1º quadro depois do corte; antes dele o lado A é o quadro n e o B é o k; dali em diante o
A é o k−1 e o B é o n; tempo_ms = (n/fps − (corte − duração/2))·1000. Primeiro a
transição, depois o filtro por cima e o ajuste por último.

Em blocos de até 90 quadros: as entradas de um bloco saem do cut.mp4 em PNG, o Remotion
desenha, o resultado entra no vídeo novo e os PNGs são apagados. Um filtro numa tomada
de um minuto não enche o disco.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

import efeitos as ef  # mesma pasta deste arquivo
import pacotes as pk  # mesma pasta deste arquivo

KIT = Path(__file__).resolve().parent.parent
MOTOR = KIT / "assets" / "efeitos"
NODE = Path(__file__).resolve().with_suffix(".mjs")
BLOCO = 90
CRF = 8
MATRIZ = {"bt709": (0.2126, 0.0722), "bt601": (0.299, 0.114)}


# ---- as contas (as mesmas da prévia) ----
FOLGA = 1e-3  # os tempos são gravados com 3 casas (até 0,5 ms fora do corte); um quadro tem ~33 ms


def quadros(ini: float, fim: float, fps: float, total: int) -> list[int]:
    a = max(0, math.floor((ini - FOLGA) * fps) - 1)
    b = min(total, math.ceil(fim * fps) + 1)
    return [n for n in range(a, b) if ini - FOLGA <= n / fps < fim - FOLGA]


def receitas(efeitos: dict, fps: float, total: int) -> list[dict]:
    """Uma receita por quadro tocado:
    {n, tr?: {pacote, tempo_ms, a, b}, fi?: {pacote, intensidade}, aj?: {ajustes}}."""
    por_n: dict[int, dict] = {}
    for it in efeitos["itens"]:
        ini, fim = ef.janela(it)
        for n in quadros(ini, fim, fps, total):
            r = por_n.setdefault(n, {"n": n})
            if it["tipo"] == "transicao":
                k = math.floor(it["corte"] * fps + 0.5)
                a, b = (n, k) if n < k else (k - 1, n)
                r["tr"] = {"pacote": it["pacote"], "tempo_ms": (n / fps - ini) * 1000,
                           "a": max(0, a), "b": min(total - 1, b)}
            elif it["tipo"] == "ajuste":
                r["aj"] = {"ajustes": it["ajustes"]}
            else:
                r["fi"] = {"pacote": it["pacote"], "intensidade": it.get("intensidade")}
    return [por_n[n] for n in sorted(por_n)]


def blocos(rs: list[dict], tamanho: int = BLOCO) -> list[list[dict]]:
    """Blocos de até `tamanho` quadros; um bloco nunca termina no meio de uma transição
    (os quadros parados dela ficam no mesmo bloco que os quadros que os usam)."""
    out, cur = [], []
    for i, r in enumerate(rs):
        cur.append(r)
        prox = rs[i + 1] if i + 1 < len(rs) else None
        meio_da_transicao = "tr" in r and prox is not None and "tr" in prox and prox["n"] == r["n"] + 1
        if len(cur) >= tamanho and not meio_da_transicao:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def rgb_para_yuv420(rgb: np.ndarray, matriz: str, faixa: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """RGB 8 bits → Y, U, V (4:2:0, média 2×2), na matriz e na faixa do cut.mp4."""
    kr, kb = MATRIZ[matriz]
    x = rgb.astype(np.float64) / 255.0
    yl = kr * x[..., 0] + (1 - kr - kb) * x[..., 1] + kb * x[..., 2]
    pb = (x[..., 2] - yl) / (2 * (1 - kb))
    pr = (x[..., 0] - yl) / (2 * (1 - kr))
    if faixa == "tv":
        y, u, v = 16 + 219 * yl, 128 + 224 * pb, 128 + 224 * pr
    else:
        y, u, v = 255 * yl, 128 + 255 * pb, 128 + 255 * pr
    h, w = y.shape
    sub = lambda c: c.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))  # noqa: E731
    para8 = lambda c: np.clip(np.floor(c + 0.5), 0, 255).astype(np.uint8)  # noqa: E731
    return para8(y), para8(sub(u)), para8(sub(v))


# ---- o vídeo ----
def sondar(video: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_read_packets,color_space,color_range,"
                          "color_primaries,color_transfer", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    espaco = s.get("color_space") or "bt709"
    return {"largura": int(s["width"]), "altura": int(s["height"]), "fps": Fraction(s["r_frame_rate"]),
            "total": int(s["nb_read_packets"]),
            "matriz": "bt601" if espaco in ("smpte170m", "bt470bg") else "bt709",
            "faixa": "pc" if s.get("color_range") == "pc" else "tv",
            "tags": {"colorspace": espaco, "color_primaries": s.get("color_primaries") or "bt709",
                     "color_trc": s.get("color_transfer") or "bt709",
                     "color_range": "pc" if s.get("color_range") == "pc" else "tv"}}


def _fps_da_previa(edit: Path, fps_video: Fraction) -> float:
    """A prévia conta com o fps do state.json (S.fps): o mesmo número aqui, para os quadros baterem."""
    try:
        fps = float(json.loads((edit / "state.json").read_text(encoding="utf-8")).get("fps") or 0)
    except (OSError, json.JSONDecodeError):
        fps = 0.0
    if not fps:
        return float(fps_video)
    if abs(fps - float(fps_video)) > 0.01:
        print(f"aviso: state.json diz {fps} qps e o cut.mp4 tem {float(fps_video):.3f}", file=sys.stderr)
    return fps


class Leitor:
    """Lê o cut.mp4 quadro a quadro por um cano do ffmpeg, no formato pedido."""

    def __init__(self, video: Path, info: dict, rgb: bool):
        w, h = info["largura"], info["altura"]
        self.tam = w * h * 3 if rgb else w * h * 3 // 2
        filtro = (f"scale=in_color_matrix={info['matriz']}:in_range={info['faixa']}:out_range=pc:"
                  "flags=accurate_rnd+full_chroma_int,format=rgb24") if rgb else "format=yuv420p"
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:v:0", "-vf", filtro,
                                   "-fps_mode", "passthrough", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        self.n = 0  # o número do próximo quadro

    def ler(self) -> bytes | None:
        b = self.p.stdout.read(self.tam)
        if len(b) < self.tam:
            return None
        self.n += 1
        return b

    def fechar(self) -> None:
        self.p.stdout.close()
        self.p.kill()  # parou antes do fim (erro ou leitor adiantado): o ffmpeg não fica esperando
        self.p.wait()


def _node(*args: str, projeto: Path) -> None:
    r = subprocess.run(["node", str(NODE), *args], cwd=projeto, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"o Remotion não desenhou: {(r.stderr or r.stdout).strip()[-800:]}")


def montar_public(pasta: Path, ids: set[str], pac: pk.Pacotes) -> None:
    """public/efeitos/ do empacotamento: o motor, o Three.js e os pacotes abertos."""
    destino = pasta / "efeitos"
    shutil.copytree(MOTOR, destino)
    for pid in sorted(ids):
        shutil.copytree(pac.aberto(pid), destino / "pacotes" / pid, ignore=shutil.ignore_patterns(".*"))
    (destino / "quadros").mkdir()


def aplicar(edit: Path, remotion: Path, pac: pk.Pacotes | None = None, bloco: int = BLOCO) -> dict:
    corte = edit / "cut.mp4"
    efeitos = ef.load(edit / "efeitos.json")
    saida = remotion / "public" / "cut.mp4"
    saida.parent.mkdir(parents=True, exist_ok=True)
    tmp_saida = saida.with_name(f".cut.{os.getpid()}.mp4")
    if not efeitos["itens"]:
        shutil.copyfile(corte, tmp_saida)
        tmp_saida.replace(saida)  # troca o arquivo: nunca grava através de um link
        return {"quadros": 0, "efeitos": 0}

    info = sondar(corte)
    fps = _fps_da_previa(edit, info["fps"])
    rs = receitas(efeitos, fps, info["total"])
    pac = pac or pk.Pacotes.do_ambiente()
    ids = {r[k]["pacote"] for r in rs for k in ("tr", "fi") if k in r}
    w, h = info["largura"], info["altura"]

    with tempfile.TemporaryDirectory(prefix="cutmind-efeitos-") as t:
        tmp = Path(t)
        montar_public(tmp / "public", ids, pac)
        bundle = tmp / "bundle"
        _node("bundle", str(remotion), str(tmp / "public"), str(bundle), projeto=remotion)
        quadros_dir = bundle / "public" / "efeitos" / "quadros"
        if not quadros_dir.is_dir():
            raise RuntimeError(f"o empacotamento não trouxe o public/efeitos ({quadros_dir})")
        props = tmp / "props.json"
        props.write_text(json.dumps({"largura": w, "altura": h, "receitas": rs}), encoding="utf-8")
        indice = {r["n"]: i for i, r in enumerate(rs)}  # n → quadro da composição

        bs = blocos(rs, bloco)
        entradas = [sorted({r["n"] for r in b} | {r["tr"][x] for r in b if "tr" in r for x in ("a", "b")})
                    for b in bs]
        ultimo_uso = {}
        for i, e in enumerate(entradas):
            for n in e:
                ultimo_uso[n] = i
        todas = set(ultimo_uso)

        rgb = Leitor(corte, info, rgb=True)
        yuv = Leitor(corte, info, rgb=False)
        tg = info["tags"]
        # os quadros do cano não têm etiqueta de cor: sem o setparams, o ffmpeg os "converte"
        # para o bt709 da saída e o vídeo inteiro escurece ~3 níveis (medido)
        etiqueta = (f"setparams=colorspace={tg['colorspace']}:color_primaries={tg['color_primaries']}:"
                    f"color_trc={tg['color_trc']}:range={tg['color_range']}")
        cod = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}",
             "-framerate", str(info["fps"]), "-i", "-", "-i", str(corte), "-map", "0:v", "-map", "1:a?",
             "-vf", etiqueta,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF), "-pix_fmt", "yuv420p",
             *[x for k, v in info["tags"].items() for x in (f"-{k}", v)],
             "-c:a", "copy", "-movflags", "+faststart", str(tmp_saida)], stdin=subprocess.PIPE)
        try:
            for i, b in enumerate(bs):
                # as entradas do bloco: o leitor RGB guarda, ao passar, todo quadro que algum bloco usa
                while rgb.n <= entradas[i][-1]:
                    n = rgb.n
                    q = rgb.ler()
                    if q is None:
                        raise RuntimeError(f"o cut.mp4 acabou no quadro {n}")
                    if n in todas:
                        Image.frombuffer("RGB", (w, h), q, "raw", "RGB", 0, 1).save(
                            quadros_dir / f"{n}.png", compress_level=1)
                fora = tmp / f"saida-{i}"
                _node("render", str(remotion), str(bundle), str(props), str(indice[b[0]["n"]]),
                      str(indice[b[-1]["n"]]), str(fora), projeto=remotion)
                prontos = {int("".join(c for c in f.stem if c.isdigit())): f for f in fora.glob("*.png")}
                # o vídeo novo anda até o fim do bloco: quadro desenhado no lugar, o resto como veio
                for r in b:
                    while yuv.n < r["n"]:
                        cod.stdin.write(yuv.ler())
                    yuv.ler()
                    arq = prontos.get(indice[r["n"]])
                    if arq is None:
                        raise RuntimeError(f"o quadro {r['n']} não saiu do Remotion")
                    with Image.open(arq) as im:
                        rgb_out = np.asarray(im.convert("RGB"))
                    y, u, v = rgb_para_yuv420(rgb_out, info["matriz"], info["faixa"])
                    cod.stdin.write(y.tobytes() + u.tobytes() + v.tobytes())
                shutil.rmtree(fora)
                for n in entradas[i]:
                    if ultimo_uso[n] == i:
                        (quadros_dir / f"{n}.png").unlink(missing_ok=True)
            while (q := yuv.ler()) is not None:
                cod.stdin.write(q)
        finally:
            cod.stdin.close()
            cod.wait()
            rgb.fechar()
            yuv.fechar()
        if cod.returncode != 0:
            raise RuntimeError("o ffmpeg não gravou o cut.mp4 novo")
    tmp_saida.replace(saida)
    return {"quadros": len(rs), "efeitos": len(efeitos["itens"]), "blocos": len(bs)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--remotion", type=Path, help="o projeto Remotion (padrão: <edit>/remotion)")
    ap.add_argument("--bloco", type=int, default=BLOCO, help=argparse.SUPPRESS)
    a = ap.parse_args()
    edit = a.edit.resolve()
    remotion = (a.remotion or edit / "remotion").resolve()
    if not (remotion / "src" / "index.ts").is_file():
        print(f"não achei o projeto Remotion em {remotion}", file=sys.stderr)
        return 1
    try:
        r = aplicar(edit, remotion, bloco=a.bloco)
    except (RuntimeError, pk.PacoteErro, ef.EfeitosInvalidos) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    if not r["efeitos"]:
        print("nenhum efeito: o cut.mp4 foi para o public como está")
    else:
        print(f"{r['efeitos']} efeito(s), {r['quadros']} quadro(s) desenhado(s) em {r['blocos']} bloco(s) "
              f"→ {remotion / 'public' / 'cut.mp4'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
