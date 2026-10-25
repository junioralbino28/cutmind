#!/usr/bin/env python3
"""Montagem na batida: um modelo de lugares contados em batidas, uma música e fotos ou clipes viram um
vídeo em que cada troca de imagem cai numa batida.

    uv run python helpers/montagem.py usar <modelo.json> --musica <arquivo> --midias <a> <b> … --edit <dir>
                                      [--modelo-batida pequeno|completo] [--so-dados] [--substituir]
    uv run python helpers/montagem.py conferir <edit> [--video <arquivo>] [--modelo-batida …]
    uv run python helpers/montagem.py aplicar <edit> [--lugar N [--midia <arquivo>] [--de <s>]] [--so-dados]
    uv run python helpers/montagem.py render <edit> [--modelo-batida …]
    uv run python helpers/montagem.py montar <edit> [--so-dados]
    uv run python helpers/montagem.py capturar <edit> --nome "Meu modelo" [--so-mostrar]

`usar` faz tudo, em ordem:
  1. a grade de batida da música (batida.py; do cache quando essa música já foi analisada). A música
     é copiada para <edit>/midia/ (de um vídeo de clipe, só o som) e a grade sai dessa cópia, a mesma
     que toca no vídeo final;
  2. cada lugar do modelo vira um trecho da música, da batida B0 + as batidas dos lugares anteriores
     até a seguinte. B0 é o primeiro tempo forte, ou a batida que põe o lugar `drop_na_vaga` no drop.
     Cada borda vai para o quadro mais perto da SUA batida (a 30 qps, no máximo 16,7 ms dela): o erro
     não se acumula de um lugar para o outro. Se a música acaba antes, os lugares que sobram saem;
  3. cada mídia vira um clipe padronizado em <edit>/montagem/ (1080×1920, 30 qps, com faixa de som,
     muda quando a mídia não tem som): a foto ganha um zoom leve (`movimento`: zoom-in, zoom-out ou
     parado); o clipe entra do começo, ou de `arquivo@segundos`, e o que é mais curto que o lugar
     fica mais lento, até 0,5×, e depois para no último quadro. Com mais lugares que mídias, as mídias
     se repetem em ordem;
  4. escreve edl.json (sem J-cut, que comeria quadros em cada emenda; um range por lugar, com
     `vaga`), camadas.json (a música numa faixa de áudio, o som dos clipes desligado e cada texto
     do modelo numa faixa de texto, com o `nome` dele) e state.json;
  5. renderiza, a menos que --so-dados: render.py → cut.mp4; sem nada por cima, mixar_final.py
     --imagem corte põe a música direto no corte; com texto, imagem, filtro ou transição, a imagem
     sai do Remotion (o modelo de Reels da Fase 2, montado em <edit>/remotion/ na primeira vez) e o
     mixar_final.py põe a música sobre ela. Por fim, o `conferir` no final.mp4; se a imagem que saiu
     do Remotion trocar fora do quadro planejado (com o computador ocupado ele pega um quadro
     vizinho), o render dele é refeito uma vez, um quadro por vez (conferir_o_render).

`conferir` acha no vídeo onde cada troca de imagem caiu (pela diferença entre quadros) e mostra,
troca a troca, a distância até a batida da música; e confere, pelas batidas que acha no som do
próprio vídeo, que a música não entrou deslocada. Sai 0 quando toda troca caiu no quadro planejado e
a no máximo 1 quadro da batida.

`aplicar` refaz só os lugares mudados (outra mídia, outro trecho do clipe), sem mexer nos outros, e
renderiza: os do Salvar do editor (`montagem` do preview_edits.json) ou o de `--lugar`. O `usar` guarda
de onde cada lugar saiu no bloco `montagem.lugares` do edl.json; é dali que o `aplicar` parte.

`render` refaz o vídeo como ele está (o que mudou foram as camadas, os textos ou os efeitos, que o
Salvar já gravou) e confere.

`montar` faz o `usar` que o editor pediu no Salvar (o Usar do painel Modelos de montagem:
`montagem.usar` = {modelo, musica, midias} no preview_edits.json); o modelo vem do `montagens.py`
e os arquivos, do midia/ do projeto. `capturar` guarda a montagem como ela está como modelo de
montagem (os lugares em batidas, os textos e as transições das trocas).

O modelo é um JSON:

    {"versao": 1, "id": "drop-rapido", "nome": "Drop rápido", "comeca": "forte", "drop_na_vaga": 5,
     "vagas": [{"batidas": 4, "repetir": 4}, {"batidas": 1, "repetir": 16}, {"batidas": 2, "repetir": 4}]}

`repetir` abre um lugar em vários iguais (o `drop_na_vaga` conta os lugares já abertos); `comeca` é
"forte" (a música entra no primeiro tempo forte) ou "batida" (na primeira batida). `textos`, opcional,
põe textos trocáveis: [{"nome": "Título", "texto": "SEU TÍTULO", "vaga": 1, "batidas": 4, "x": 540,
"y": 700, "estilo": {"fonte": "Anton", "cor": "#ffffff"}}] (sem `batidas`, o texto dura o lugar; o
estilo é o do painel de Texto, camadas.py). `transicoes`, opcional, põe uma transição da biblioteca
na troca que abre um lugar: [{"vaga": 3, "pacote": "t-zoom-central", "duracao": 0.4}] (centrada na
troca e encurtada para caber entre as trocas vizinhas; o `usar` grava no efeitos.json). Com `golpe` (o
padrão), a troca que cairia numa batida fraca vai para o golpe forte do contratempo vizinho, meia
batida antes ou depois, quando ele é 1,5× mais forte que a batida: é o bumbo sincopado, que a grade
sozinha deixa passar. `"golpe": false` corta só na grade.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import atualizar_template
import batida  # mesma pasta deste arquivo
import camadas as cam
import efeitos
import render
import tempo

AQUI = Path(__file__).resolve().parent
TEMPLATE = AQUI.parent / "assets" / "shortform"  # o modelo de Reels da Fase 2 (o Remotion)
FPS = 30
LARGURA, ALTURA = 1080, 1920
IMAGENS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEOS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}
MOVIMENTOS = ("zoom-in", "zoom-out", "parado")
ZOOM_POR_SEGUNDO = 0.04  # a foto aproxima 4% por segundo, até 10%: a mesma velocidade em lugar curto e longo
ZOOM_MAX = 0.10
VEL_MIN = 0.5  # o clipe curto desacelera até 0,5× e depois para no último quadro
PUXA = 1.5  # o golpe no contratempo leva a troca quando é 1,5× mais forte que a batida
MEIO_MIN = 0.4  # duas trocas nunca ficam a menos de 0,4 batida uma da outra
MAX_VAGAS = 400
MAX_TEXTOS = 20
FAIXA_TEXTO = "modelo-texto"  # as faixas dos textos do modelo: modelo-texto-1, -2… (o usar as refaz)
JANELA = 3  # quadros para cada lado do planejado em que o conferir procura a troca
FAIXA_MUSICA = "musica"
CODIFICA = ["-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]


class ErroMontagem(Exception):
    """Falha que a pessoa entende e consegue resolver (modelo, música, mídia)."""


# ---------- o modelo ----------

def _inteiro(v, nome: str, lo: int, hi: int) -> int:
    ok = (not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
          and float(v).is_integer() and lo <= v <= hi)
    if not ok:
        raise ErroMontagem(f"{nome}: um número inteiro de {lo} a {hi}")
    return int(v)


def carregar_modelo(fonte: Path | dict) -> dict:
    """O modelo conferido, com os lugares abertos (`repetir`) e numerados a partir de 1."""
    if isinstance(fonte, dict):
        m = fonte
    else:
        try:
            m = json.loads(Path(fonte).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ErroMontagem(f"modelo não encontrado: {fonte}") from None
        except json.JSONDecodeError as e:
            raise ErroMontagem(f"o modelo não é um JSON válido: {e}") from None
    if not isinstance(m, dict):
        raise ErroMontagem("o modelo precisa ser um objeto JSON")
    if m.get("versao", 1) != 1:
        raise ErroMontagem(f"versão de modelo desconhecida: {m.get('versao')!r}")
    comeca = m.get("comeca", "forte")
    if comeca not in ("forte", "batida"):
        raise ErroMontagem('"comeca" é "forte" ou "batida"')
    vagas_in = m.get("vagas")
    if not isinstance(vagas_in, list) or not vagas_in:
        raise ErroMontagem('o modelo precisa de "vagas": uma lista de lugares')
    vagas: list[dict] = []
    for i, v in enumerate(vagas_in, 1):
        if not isinstance(v, dict):
            raise ErroMontagem(f"lugar {i}: precisa ser um objeto")
        nb = _inteiro(v.get("batidas"), f"lugar {i}, batidas", 1, 64)
        rep = _inteiro(v.get("repetir", 1), f"lugar {i}, repetir", 1, MAX_VAGAS)
        mov = v.get("movimento")
        if mov is not None and mov not in MOVIMENTOS:
            raise ErroMontagem(f"lugar {i}: o movimento é {', '.join(MOVIMENTOS)}")
        if len(vagas) + rep > MAX_VAGAS:
            raise ErroMontagem(f"mais de {MAX_VAGAS} lugares")
        for _ in range(rep):
            vagas.append({"n": len(vagas) + 1, "batidas": nb, **({"movimento": mov} if mov else {})})
    drop = m.get("drop_na_vaga")
    if drop is not None:
        drop = _inteiro(drop, "drop_na_vaga", 1, len(vagas))
    golpe = m.get("golpe", True)
    if not isinstance(golpe, bool):
        raise ErroMontagem('"golpe" é true ou false')
    textos_in = m.get("textos") or []
    if not isinstance(textos_in, list) or len(textos_in) > MAX_TEXTOS:
        raise ErroMontagem(f'"textos": uma lista de até {MAX_TEXTOS}')
    textos = []
    for k, t in enumerate(textos_in, 1):
        if not isinstance(t, dict):
            raise ErroMontagem(f"texto {k}: precisa ser um objeto")
        vaga = _inteiro(t.get("vaga", 1), f"texto {k}, vaga", 1, len(vagas))
        nb = None if t.get("batidas") is None else _inteiro(t["batidas"], f"texto {k}, batidas", 1, 64 * MAX_VAGAS)
        item = {"id": "x", "nome": t.get("nome") or f"Texto {k}", "texto": t.get("texto"), "duracao": 1,
                "x": t.get("x", 540), "y": t.get("y", 960), "estilo": t.get("estilo")}
        try:  # as mesmas regras de um texto do editor (camadas.py)
            it = cam.normalize({"faixas": [{"id": "t", "tipo": "texto", "itens": [item]}]})["faixas"][0]["itens"][0]
        except cam.CamadasInvalidas as e:
            raise ErroMontagem(f"texto {k}: {e}") from None
        textos.append({"nome": it["nome"], "texto": it["texto"], "vaga": vaga, "batidas": nb,
                       "x": it["x"], "y": it["y"], "estilo": it["estilo"]})
    trans_in = m.get("transicoes") or []
    if not isinstance(trans_in, list) or len(trans_in) > MAX_VAGAS:
        raise ErroMontagem(f'"transicoes": uma lista de até {MAX_VAGAS}')
    if trans_in and len(vagas) < 2:
        raise ErroMontagem("transição precisa de uma troca: o modelo tem um lugar só")
    transicoes: dict[int, dict] = {}
    for k, t in enumerate(trans_in, 1):
        if not isinstance(t, dict):
            raise ErroMontagem(f"transição {k}: precisa ser um objeto")
        vaga = _inteiro(t.get("vaga"), f"transição {k}, vaga (a troca que abre o lugar)", 2, len(vagas))
        if vaga in transicoes:
            raise ErroMontagem(f"transição {k}: a troca do lugar {vaga} já tem transição")
        pacote = t.get("pacote")
        if not isinstance(pacote, str) or not efeitos._PACOTE.fullmatch(pacote):
            raise ErroMontagem(f"transição {k}: o pacote é o id de uma transição da biblioteca")
        dur = t.get("duracao", 0.5)
        if (isinstance(dur, bool) or not isinstance(dur, (int, float))
                or not efeitos.TRANSICAO_MIN <= dur <= efeitos.TRANSICAO_MAX):
            raise ErroMontagem(f"transição {k}: duração de {efeitos.TRANSICAO_MIN:g} a {efeitos.TRANSICAO_MAX:g} s")
        transicoes[vaga] = {"vaga": vaga, "pacote": pacote, "duracao": round(float(dur), 3)}
    ident = str(m.get("id") or "montagem")
    return {"versao": 1, "id": ident, "nome": str(m.get("nome") or ident), "comeca": comeca,
            "drop_na_vaga": drop, "golpe": golpe, "vagas": vagas, "textos": textos,
            "transicoes": [transicoes[v] for v in sorted(transicoes)]}


# ---------- os lugares no tempo ----------

def planejar(grade: dict, modelo: dict, fps: int = FPS) -> dict:
    """Cada lugar no tempo da música e no quadro do vídeo.

    Devolve {"inicio_musica", "lugares", "quadros", "avisos", "no_golpe"}. A música entra no vídeo a
    partir de `inicio_musica` (segundos do arquivo); cada lugar começa no `quadro` do vídeo, dura
    `quadros`, e `batida` é o instante exato, no relógio do vídeo, em que ele começa: a batida, ou o golpe
    forte a meia batida dela (`golpe`), se o modelo não desligou isso com "golpe": false."""
    b = np.asarray(grade.get("batidas") or [], dtype=float)
    if len(b) < 2:
        raise ErroMontagem("a música não tem batida que dê para seguir (silêncio ou ritmo solto demais)")
    vagas = modelo["vagas"]
    antes = np.concatenate([[0], np.cumsum([v["batidas"] for v in vagas])]).astype(int)
    avisos: list[str] = []
    if grade.get("confianca") == "baixa":
        avisos.append("a batida desta música é irregular (confiança baixa): confira os cortes de ouvido")
    i0 = None
    d = modelo.get("drop_na_vaga")
    if d is not None:
        if grade.get("drop") is None:
            avisos.append(f"a música não tem um drop claro: o lugar {d} não tem onde cair")
        else:
            no_drop = int(np.argmin(np.abs(b - float(grade["drop"]))))
            if no_drop >= antes[d - 1]:
                i0 = no_drop - int(antes[d - 1])
            else:
                avisos.append(f"antes do drop a música tem {no_drop} batidas e os lugares antes do {d} "
                              f"pedem {int(antes[d - 1])}: o lugar {d} não cai no drop")
    if i0 is None:
        fortes = grade.get("fortes") or []
        i0 = int(np.argmin(np.abs(b - float(fortes[0])))) if modelo["comeca"] == "forte" and fortes else 0
    t0 = round(float(b[i0]), 3)
    ac = grade.get("acentos") or []
    if len(ac) != 2 * len(b) - 1:  # grade antiga, sem a força dos golpes
        ac = []
    # cada troca: a batida, ou o golpe a meia batida dela; a primeira é o começo da música e não anda
    bordas: list[tuple[float, bool]] = [(float(b[i0]), False)]
    for k in range(1, len(vagas) + 1):
        z = i0 + int(antes[k])
        if z >= len(b):
            break
        t, golpe = _no_golpe(b, ac, z) if modelo.get("golpe", True) else (float(b[z]), False)
        if t - bordas[-1][0] < MEIO_MIN * float(np.median(np.diff(b))):  # perto demais da troca anterior
            t, golpe = float(b[z]), False
        bordas.append((t, golpe))
    lugares = []
    for k, v in enumerate(vagas[:len(bordas) - 1]):
        (ta, ga), (tz, _) = bordas[k], bordas[k + 1]
        q0, q1 = int(round((ta - t0) * fps)), int(round((tz - t0) * fps))
        if q1 <= q0:
            raise ErroMontagem(f"lugar {v['n']}: as batidas dele ficam a menos de um quadro uma da outra")
        lugares.append({**v, "quadro": q0, "quadros": q1 - q0, "batida": round(ta - t0, 4), "golpe": ga})
    if not lugares:
        raise ErroMontagem("a música acaba antes de o primeiro lugar terminar")
    if len(lugares) < len(vagas):
        avisos.append(f"a música acaba antes: {len(vagas) - len(lugares)} de {len(vagas)} lugares ficaram de fora")
    fim = lugares[-1]["quadro"] + lugares[-1]["quadros"]
    return {"inicio_musica": t0, "fps": fps, "lugares": lugares, "quadros": fim, "avisos": avisos,
            "no_golpe": sum(lg["golpe"] for lg in lugares)}


def janela_do_texto(plano: dict, grade: dict, vaga: int, batidas: int | None) -> tuple[int, int] | None:
    """(quadro inicial, quadros) de um texto do modelo: começa com o lugar `vaga` e dura `batidas`
    batidas (sem elas, o lugar). Quando as batidas fecham na troca de um lugar, termina nela, mesmo
    que a troca tenha ido para o golpe do contratempo; senão, na batida da grade. None quando a
    música acabou antes do lugar."""
    lug = plano["lugares"]
    if vaga > len(lug):
        return None
    q0 = lug[vaga - 1]["quadro"]
    if batidas is None:
        return q0, lug[vaga - 1]["quadros"]
    soma = 0
    for lg in lug[vaga - 1:]:
        soma += lg["batidas"]
        if soma == batidas:
            return q0, lg["quadro"] + lg["quadros"] - q0
        if soma > batidas:
            break
    b = np.asarray(grade.get("batidas") or [], dtype=float)
    t0 = plano["inicio_musica"]
    z = int(np.argmin(np.abs(b - t0))) + sum(lg["batidas"] for lg in lug[:vaga - 1]) + batidas
    fim = plano["quadros"] if z >= len(b) else min(plano["quadros"], int(round((b[z] - t0) * plano.get("fps", FPS))))
    return q0, max(1, fim - q0)


def transicoes_nos_lugares(plano: dict, transicoes: list[dict]) -> list[dict]:
    """As transições do modelo como itens do efeitos.json: cada uma centrada na troca que abre o lugar
    dela e cabendo entre as trocas vizinhas (o começo e o fim do vídeo contam), como as do modelo de
    estilo (transicoesNosCortes, no editor). Uma que não cabe em 0,1 s sai, e a de um lugar que a
    música não alcançou também."""
    lug = plano["lugares"]
    cortes = [lg["quadro"] / plano.get("fps", FPS) for lg in lug] + [plano["quadros"] / plano.get("fps", FPS)]
    out = []
    for t in transicoes:
        k = t["vaga"]
        if not 2 <= k <= len(lug):
            continue
        c = cortes[k - 1]
        d = min(t["duracao"], c - cortes[k - 2], cortes[k] - c)
        if d >= efeitos.TRANSICAO_MIN:
            out.append({"id": f"t{k}", "tipo": "transicao", "pacote": t["pacote"], "corte": round(c, 3),
                        "duracao": round(d, 3)})
    return out


def _no_golpe(b: np.ndarray, ac: list, z: int) -> tuple[float, bool]:
    """A troca da batida z: no golpe do contratempo vizinho (meia batida antes ou depois) quando ele é
    `PUXA` vezes mais forte que a batida. É o bumbo sincopado: numa música real, o golpe mais forte do
    compasso vinha meia batida depois do 3º tempo, o tempo mais fraco, e a troca na batida o deixava passar."""
    if not ac:
        return float(b[z]), False
    forca = ac[2 * z][1]
    vizinhos = [ac[j] for j in (2 * z - 1, 2 * z + 1) if 0 <= j < len(ac)]
    melhor = max(vizinhos, key=lambda c: c[1], default=None)
    if melhor is not None and melhor[1] > 0 and melhor[1] >= PUXA * forca:
        return float(melhor[0]), True
    return float(b[z]), False


def referencias(grade: dict) -> np.ndarray:
    """Onde uma troca pode cair: as batidas e os contratempos que puxariam uma troca (mais fortes que
    `PUXA` vezes a mais fraca das duas batidas vizinhas)."""
    b = [float(x) for x in grade.get("batidas") or []]
    ac = grade.get("acentos") or []
    refs = list(b)
    if len(ac) == 2 * len(b) - 1:
        for i in range(len(b) - 1):
            meio = ac[2 * i + 1]
            if meio[1] > 0 and meio[1] >= PUXA * min(ac[2 * i][1], ac[2 * i + 2][1]):
                refs.append(float(meio[0]))
    return np.asarray(sorted(refs), dtype=float)


# ---------- as mídias ----------

def _ffmpeg(args: list[str], o_que: str) -> None:
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", *args], capture_output=True)
    if r.returncode != 0:
        msg = (r.stderr or b"").decode("utf-8", "replace").strip()[-400:]
        raise ErroMontagem(f"o ffmpeg falhou em {o_que}: {msg}")


def sondar(arquivo: Path) -> dict:
    """Foto ou vídeo, se tem som, e a duração."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name:format=duration",
                        "-of", "json", str(arquivo)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        raise ErroMontagem(f"não consegui abrir {Path(arquivo).name}")
    d = json.loads(r.stdout or "{}")
    streams = d.get("streams") or []
    tipos = {s.get("codec_type") for s in streams}
    try:
        dur = float((d.get("format") or {}).get("duration") or 0)
    except ValueError:
        dur = 0.0
    som = next((s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), None)
    return {"foto": Path(arquivo).suffix.lower() in IMAGENS, "imagem": "video" in tipos,
            "som": som is not None, "codec_som": som, "duracao": dur}


def _quadros(arquivo: Path) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames",
                        "-of", "csv=p=0", str(arquivo)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def _cor(arquivo: Path) -> str:
    """O mesmo cuidado de cor do render.py: HDR e gama larga viram Rec.709 antes de escalar."""
    if render.is_hdr_source(arquivo):
        return render.TONEMAP_CHAIN + ","
    largo = render.wide_gamut_chain(arquivo)
    return largo + "," if largo else ""


def _encher(w: int, h: int) -> str:
    """Escala para cobrir w×h e corta o meio: a mídia em pé ou deitada enche a tela em pé. A conversão
    para YUV Rec.709 é feita pela própria escala (o `format` logo depois a obriga a isso)."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2:flags=lanczos"
            f":out_color_matrix=bt709:out_range=tv,format=yuv420p,crop={w}:{h},setsar=1")


def padronizar(midia: Path, destino: Path, quadros: int, movimento: str | None = None, de: float = 0.0) -> dict:
    """A mídia como clipe de 1080×1920 a 30 qps, com faixa de som, e o trecho dele que enche o lugar.

    Devolve {"foto", "quadros_no_arquivo", "velocidade", "fim", "congela"}: o lugar toca o arquivo
    de 0 a `fim` a `velocidade`, e isso dura exatamente `quadros` no vídeo."""
    midia, destino = Path(midia), Path(destino)
    info = sondar(midia)
    if not info["imagem"]:
        raise ErroMontagem(f"{midia.name} não é foto nem vídeo")
    destino.parent.mkdir(parents=True, exist_ok=True)
    precisa = quadros / FPS
    mudo = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    if info["foto"]:
        extra = min(ZOOM_MAX, ZOOM_POR_SEGUNDO * precisa)
        passo = f"{extra:.5f}*on/{max(1, quadros - 1)}"
        z = {"zoom-in": f"1+{passo}", "zoom-out": f"{1 + extra:.5f}-{passo}", "parado": "1"}[movimento or "zoom-in"]
        # a foto é escalada ao DOBRO antes do zoompan, que posiciona o recorte em pixel inteiro: no
        # tamanho final o zoom andaria aos trancos
        vf = (f"{_cor(midia)}{_encher(2 * LARGURA, 2 * ALTURA)},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={quadros}"
              f":s={LARGURA}x{ALTURA}:fps={FPS}")
        _ffmpeg(["-i", str(midia), *mudo, "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "1:a",
                 "-frames:v", str(quadros), "-t", f"{precisa:.6f}", *CODIFICA, str(destino)], midia.name)
        return {"foto": True, "quadros_no_arquivo": _quadros(destino), "velocidade": 1.0,
                "fim": round(precisa, 6), "congela": False}

    disponivel = max(0.0, info["duracao"] - de)
    entrada = ["-ss", f"{de:.6f}", "-i", str(midia)]
    if info["som"]:
        mapa_som = ["-map", "0:a:0"]
    else:
        entrada += mudo
        mapa_som = ["-map", "1:a"]
    vf = f"{_cor(midia)}fps={FPS},{_encher(LARGURA, ALTURA)}"
    base = [*entrada, "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", *mapa_som]
    if disponivel >= precisa + 0.5 / FPS:
        _ffmpeg([*base, "-frames:v", str(quadros), "-t", f"{precisa:.6f}", *CODIFICA, str(destino)], midia.name)
    else:
        _ffmpeg([*base, "-t", f"{disponivel:.6f}", *CODIFICA, str(destino)], midia.name)
    f = _quadros(destino)
    if f >= quadros:
        return {"foto": False, "quadros_no_arquivo": f, "velocidade": 1.0, "fim": round(precisa, 6), "congela": False}
    if f == 0:
        raise ErroMontagem(f"{midia.name} não tem imagem a partir de {de:g} s")
    if 2 * f >= quadros:  # dá para esticar sem passar de 0,5×
        v = round(f / quadros, 6)
        return {"foto": False, "quadros_no_arquivo": f, "velocidade": v,
                "fim": round(quadros * v / FPS, 6), "congela": False}
    # nem a 0,5× ele enche o lugar: o último quadro se repete até cobrir a metade do lugar, e a 0,5×
    # o clipe toca inteiro e fica parado no fim
    alvo = math.ceil(quadros * VEL_MIN)
    tmp = destino.with_name(destino.stem + "_curto.mp4")
    destino.replace(tmp)
    try:
        _ffmpeg(["-i", str(tmp), "-filter_complex", f"[0:v]tpad=stop_mode=clone:stop={alvo - f}[v];[0:a]apad[a]",
                 "-map", "[v]", "-map", "[a]", "-frames:v", str(alvo), "-t", f"{alvo / FPS:.6f}", *CODIFICA,
                 str(destino)], midia.name)
    finally:
        tmp.unlink(missing_ok=True)
    return {"foto": False, "quadros_no_arquivo": _quadros(destino), "velocidade": VEL_MIN,
            "fim": round(quadros * VEL_MIN / FPS, 6), "congela": True}


def _slug(texto: str, limite: int = 32) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:limite].strip("-") or "midia"


def listar_midias(entradas: list[str]) -> list[tuple[Path, float]]:
    """Os arquivos e de onde cada um entra. Uma pasta vale as fotos e os vídeos dela, em ordem de nome;
    `arquivo@12.5` faz o clipe entrar dos 12,5 s."""
    saida: list[tuple[Path, float]] = []
    for e in entradas:
        caminho, de = str(e), 0.0
        m = re.fullmatch(r"(.+)@(\d+(?:[.,]\d+)?)", caminho)
        if m and not Path(caminho).exists():
            caminho, de = m.group(1), float(m.group(2).replace(",", "."))
        p = Path(caminho)
        if p.is_dir():
            achados = sorted((x for x in p.iterdir() if x.is_file() and x.suffix.lower() in IMAGENS | VIDEOS),
                             key=lambda x: x.name.lower())
            if not achados:
                raise ErroMontagem(f"a pasta {p} não tem foto nem vídeo")
            saida += [(x, 0.0) for x in achados]
        elif p.is_file():
            saida.append((p, de))
        else:
            raise ErroMontagem(f"mídia não encontrada: {caminho}")
    if not saida:
        raise ErroMontagem("nenhuma mídia para a montagem")
    return saida


def copiar_musica(musica: Path, edit: Path) -> Path:
    """A música em <edit>/midia/, onde as camadas a acham. De um vídeo (o clipe da música) vai só o som.
    Um arquivo de mesmo nome e conteúdo diferente não é sobrescrito: a cópia ganha um número."""
    musica = Path(musica)
    if not musica.is_file():
        raise ErroMontagem(f"música não encontrada: {musica}")
    pasta = edit / cam.MIDIA_DIR
    pasta.mkdir(parents=True, exist_ok=True)
    ext = musica.suffix.lower()
    so_som = ext not in cam.AUDIO_EXTS
    ext_final = ".m4a" if so_som else ext
    nome = _slug(musica.stem)
    candidato = musica
    if so_som:
        info = sondar(musica)
        if not info["som"]:
            raise ErroMontagem(f"{musica.name} não tem som")
        candidato = pasta / f".{nome}.extraindo.m4a"
        som = ["-c:a", "copy"] if info["codec_som"] == "aac" else ["-c:a", "aac", "-b:a", "256k"]
        _ffmpeg(["-i", str(musica), "-map", "0:a:0", "-vn", *som, "-movflags", "+faststart", str(candidato)],
                musica.name)
    sha = batida.sha256_arquivo(candidato)
    for i in range(1, 100):
        destino = pasta / f"{nome}{'' if i == 1 else f'-{i}'}{ext_final}"
        if not destino.exists():
            break
        if batida.sha256_arquivo(destino) == sha:  # a mesma música de antes: usa a cópia que já está lá
            if so_som:
                candidato.unlink()
            return destino
    else:
        raise ErroMontagem(f"cópias demais de {musica.name} em {pasta}")
    if so_som:
        candidato.replace(destino)
    else:
        shutil.copy2(musica, destino)
    return destino


# ---------- o projeto ----------

def _chave_midia(edit: Path, arq: Path) -> str:
    """Como o lugar guarda a mídia: `midia/<nome>` quando ela é do projeto (o editor a acha assim na
    lista do Trocar), senão o caminho inteiro."""
    p = Path(arq).resolve()
    return f"{cam.MIDIA_DIR}/{p.name}" if p.parent == (edit / cam.MIDIA_DIR).resolve() else str(p)


def _grava_json(caminho: Path, dados: dict) -> None:
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_bytes((json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    tmp.replace(caminho)


def usar(modelo_arq: Path | dict, musica: Path, midias: list[str], edit: Path,
         modelo_batida: str = batida.MODELO_PADRAO, so_dados: bool = False, substituir: bool = False,
         jobs: int = 0) -> dict:
    """Monta o projeto (e, sem `so_dados`, o vídeo). Devolve o resumo."""
    edit = Path(edit).resolve()
    modelo = carregar_modelo(modelo_arq)
    lista = listar_midias(midias)
    edl_p = edit / "edl.json"
    if edl_p.exists() and not substituir:
        try:
            atual = json.loads(edl_p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            atual = {}
        if "montagem" not in atual:
            raise ErroMontagem(f"{edl_p} é de outra edição, não de uma montagem: use outra pasta, ou "
                               "--substituir para trocar a edição dela por esta montagem")
    edit.mkdir(parents=True, exist_ok=True)
    arq_musica = copiar_musica(musica, edit)
    grade, caminho_grade = batida.analisar(arq_musica, edit, modelo_batida)
    plano = planejar(grade, modelo)
    # os textos do modelo, cada um numa faixa de texto própria, no tempo do lugar dele
    faixas_texto = []
    for k, t in enumerate(modelo["textos"], 1):
        jan = janela_do_texto(plano, grade, t["vaga"], t["batidas"])
        if jan is None:
            plano["avisos"].append(f'o texto "{t["nome"]}" ficou de fora: a música acaba antes do lugar {t["vaga"]}')
            continue
        fid = f"{FAIXA_TEXTO}-{k}"
        faixas_texto.append({"id": fid, "tipo": "texto", "oculto": False, "travado": False, "itens": [
            {"id": f"{fid}-1", "nome": t["nome"], "texto": t["texto"], "inicio": round(jan[0] / FPS, 4),
             "duracao": round(jan[1] / FPS, 4), "x": t["x"], "y": t["y"], "estilo": t["estilo"]}]})

    pasta = edit / "montagem"
    if pasta.is_dir():  # clipes de uma montagem anterior: os nomes mudam com as mídias
        for velho in pasta.glob("v*.mp4"):
            velho.unlink()
    largura = 3 if len(plano["lugares"]) > 99 else 2
    tarefas = []
    for k, lugar in enumerate(plano["lugares"]):
        arq, de = lista[k % len(lista)]
        nome = f"v{lugar['n']:0{largura}d}_{_slug(arq.stem, 24)}"
        tarefas.append((lugar, arq, de, nome, pasta / f"{nome}.mp4"))

    def faz(t):
        lugar, arq, de, nome, destino = t
        return padronizar(arq, destino, lugar["quadros"], lugar.get("movimento"), de)

    if jobs <= 0:
        jobs = max(1, min(4, (os.cpu_count() or 4) // 3))
    print(f"padronizando {len(tarefas)} lugar(es) em {pasta}  ({jobs} em paralelo)", flush=True)
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        feitos = list(ex.map(faz, tarefas))

    sources, ranges, duracoes, lentos, lugares = {}, [], {}, [], []
    for (lugar, arq, de, nome, destino), p in zip(tarefas, feitos):
        sources[nome] = destino.as_posix()
        duracoes[nome] = round(p["quadros_no_arquivo"] / FPS, 3)
        r = {"source": nome, "start": 0.0, "end": p["fim"], "beat": f"lugar {lugar['n']}", "vaga": lugar["n"]}
        if p["velocidade"] != 1.0:
            r["velocidade"] = p["velocidade"]
            lentos.append(f"lugar {lugar['n']} ({arq.name}): {p['velocidade']:.2f}×"
                          + (" e para no último quadro" if p["congela"] else ""))
        ranges.append(r)
        # de onde o lugar saiu: é o que deixa refazer um lugar sem refazer os outros (aplicar)
        lugares.append({"vaga": lugar["n"], "midia": _chave_midia(edit, arq), "de": de, "batidas": lugar["batidas"],
                        **({"movimento": lugar["movimento"]} if lugar.get("movimento") else {})})
        print(f"  lugar {lugar['n']:>3}: {arq.name} → {lugar['quadros']} quadros"
              + (f", {p['velocidade']:.2f}×" if p["velocidade"] != 1.0 else ""), flush=True)

    vd = round(plano["quadros"] / FPS, 3)
    rel_musica = arq_musica.relative_to(edit).as_posix()
    edl = {"version": 1, "sources": sources, "grade": "", "jcut": False, "ranges": ranges,
           "montagem": {"modelo": modelo["id"], "nome": modelo["nome"], "musica": rel_musica,
                        "inicio_musica": plano["inicio_musica"], "bpm": grade.get("bpm"),
                        "confianca": grade.get("confianca"),
                        "batidas": caminho_grade.relative_to(edit).as_posix(), "comeca": modelo["comeca"],
                        "drop_na_vaga": modelo["drop_na_vaga"], "golpe": modelo["golpe"],
                        "avisos": plano["avisos"], "lugares": lugares,
                        # todas as mídias dadas (inclusive as que sobraram): as opções do Trocar no editor
                        "midias": list(dict.fromkeys(_chave_midia(edit, p) for p, _ in lista))}}
    _grava_json(edl_p, edl)

    cam_p = edit / "camadas.json"
    camadas = cam.load(cam_p)
    camadas["faixas"] = [f for f in camadas["faixas"]
                         if f["id"] != FAIXA_MUSICA and not f["id"].startswith(FAIXA_TEXTO)]
    camadas["faixas"].insert(0, {"id": FAIXA_MUSICA, "tipo": "audio", "mudo": False, "travado": False,
                                 "itens": [{"id": f"{FAIXA_MUSICA}-1", "arquivo": rel_musica, "inicio": 0.0,
                                            "corte": plano["inicio_musica"], "duracao": vd, "volume": 1.0,
                                            "melhorar": False}]})
    camadas["faixas"] += faixas_texto  # por cima de tudo, como os textos que a pessoa põe no editor
    camadas["video"]["mudo"] = True  # só a música toca; o som dos clipes se religa no editor
    cam.save(cam_p, camadas)

    # a montagem é nova: os efeitos de antes eram de outros lugares; ficam as transições do modelo
    ef_p = edit / "efeitos.json"
    transicoes = transicoes_nos_lugares(plano, modelo["transicoes"])
    if transicoes or ef_p.exists():
        efeitos.save(ef_p, {"versao": 1, "itens": transicoes})

    st_p = edit / "state.json"
    try:  # o nome que a pessoa deu ao projeto (Nova montagem) fica
        nome_projeto = json.loads(st_p.read_text(encoding="utf-8")).get("project")
    except (OSError, ValueError, AttributeError):
        nome_projeto = None
    _grava_json(st_p, {
        "project": nome_projeto or f"{modelo['nome']} (montagem)", "phase": 1, "video": "cut.mp4", "edl": "edl.json",
        "finalVideo": "final.mp4", "fps": FPS, "sourceDurations": duracoes,
        "message": f"Montagem na batida: {len(ranges)} lugares, {vd:.1f} s, {grade.get('bpm')} BPM"})

    resumo = {"edit": str(edit), "lugares": len(ranges), "duracao": vd, "bpm": grade.get("bpm"),
              "confianca": grade.get("confianca"), "inicio_musica": plano["inicio_musica"],
              "drop": grade.get("drop"), "drop_na_vaga": modelo["drop_na_vaga"], "lentos": lentos,
              "no_golpe": plano["no_golpe"], "avisos": plano["avisos"],
              "textos": [f["itens"][0]["nome"] for f in faixas_texto],
              "sobraram_midias": max(0, len(lista) - len(ranges))}
    if not so_dados:
        renderizar(edit)
    return resumo


def _passo(args: list[str]) -> None:
    """Um helper do kit com o mesmo Python; a saída dele passa direto."""
    r = subprocess.run([sys.executable, "-X", "utf8", *args])
    if r.returncode != 0:
        raise ErroMontagem(f"{Path(args[0]).name} falhou (código {r.returncode})")


def tem_visual(edit: Path) -> bool:
    """A montagem leva alguma coisa por cima da imagem: texto ou imagem nas camadas (de faixa que não
    está escondida), filtro, transição ou ajuste. Aí o vídeo passa pelo Remotion."""
    c = cam.load(Path(edit) / "camadas.json")
    return bool(cam.textos(c) or cam.aparecem(c) or efeitos.load(Path(edit) / "efeitos.json")["itens"])


def imagem_do_zero(video: Path) -> None:
    """Deixa no arquivo só a imagem, começando no zero. O cut.mp4 da montagem (emenda sem J-cut) tem
    o vídeo começando 0,021 s depois, empurrado pelo atraso do AAC; o Remotion desenha o quadro que
    está em ou antes de cada instante, e cada quadro do render mostrava o quadro ANTERIOR do corte
    (medido em 25/10: as 33 trocas 1 quadro atrasadas, o som certo). Sem recodificar: os dois relógios
    (PTS e DTS) andam o mesmo tanto. Num ffmpeg sem o filtro `setts` (antes do 4.4), regravado."""
    video = Path(video)
    tmp = video.with_name(video.stem + ".zero.mp4")
    try:
        _ffmpeg(["-i", str(video), "-map", "0:v:0", "-an", "-c", "copy",
                 "-bsf:v", "setts=pts=PTS-STARTPTS:dts=DTS-STARTPTS", str(tmp)], "a imagem para o Remotion")
    except ErroMontagem:
        _ffmpeg(["-i", str(video), "-map", "0:v:0", "-an", "-vf", "setpts=PTS-STARTPTS", "-c:v", "libx264",
                 "-preset", "fast", "-crf", "12", "-pix_fmt", "yuv420p", "-colorspace", "bt709",
                 "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", str(tmp)],
                "a imagem para o Remotion")
    tmp.replace(video)


def atraso_da_imagem(video: Path) -> int:
    """Quadros que a imagem do Remotion fica atrás do vídeo: o começo do vídeo arredondado PARA CIMA
    (references/shortform.md, segments.json). 0 depois do imagem_do_zero."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=start_time",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        inicio = float(r.stdout.strip() or 0)
    except ValueError:
        inicio = 0.0
    return max(0, math.ceil(inicio * FPS - 1e-3))


def _template_do_kit(edit: Path) -> None:
    """O código do Remotion da montagem acompanha o kit (atualizar_template.py): o projeto é do
    montagem.py, e o que o kit ganha depois só aparece no render com o código novo."""
    try:
        pl = atualizar_template.aplicar(edit)
    except atualizar_template.ErroTemplate as e:
        raise ErroMontagem(f"o código do Remotion da montagem: {e}") from None
    n = len(pl["novos"]) + len(pl["trocados"])
    if n:
        print(f"o código do Remotion da montagem veio do kit de agora ({n} arquivo(s))", flush=True)


def preparar_remotion(edit: Path) -> Path:
    """O projeto do Remotion da montagem (o modelo de Reels da Fase 2) pronto para o cut.mp4 de agora:
    os arquivos de public/ que o modelo pede, um edit-data.json sem legenda, sem gancho e sem zoom (o
    `editData` do state.json passa a apontar para ele) e as camadas por cima (camadas_edit_data.py).
    Na primeira vez, copia o modelo e roda o npm install. Devolve a pasta do projeto."""
    edit = Path(edit).resolve()
    rem = edit / "remotion"
    pub = rem / "public"
    if not (rem / "package.json").is_file():
        print(f"montando o projeto do Remotion em {rem}", flush=True)
        shutil.copytree(TEMPLATE, rem, dirs_exist_ok=True)
    else:
        _template_do_kit(edit)
    if not (rem / "node_modules" / "@remotion" / "cli").is_dir():
        npm = shutil.which("npm")
        if not npm:
            raise ErroMontagem("o que vai por cima da montagem (texto, imagem, filtro) é desenhado pelo Remotion, "
                               "que precisa do Node.js: instale o Node 18 ou mais novo")
        print("instalando as dependências do Remotion (só na primeira vez; leva alguns minutos)", flush=True)
        if subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=rem).returncode != 0:
            raise ErroMontagem("o npm install do projeto do Remotion falhou (a saída dele está acima)")
    shutil.copyfile(edit / "cut.mp4", pub / "cut.mp4")
    if efeitos.load(edit / "efeitos.json")["itens"]:  # filtro, transição, ajuste: um public/cut.mp4 com eles
        _passo([str(AQUI / "efeitos_render.py"), str(edit), "--remotion", str(rem)])
    imagem_do_zero(pub / "cut.mp4")
    lag = atraso_da_imagem(pub / "cut.mp4")
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    inicios, total = quadros_dos_lugares(edl)
    _grava_json(pub / "segments.json", {"segments": [  # cada lugar é um trecho
        {"start": round(q / FPS, 4), "dur": round(((inicios + [total])[k + 1] - q) / FPS, 4)}
        for k, q in enumerate(inicios)], "videoLag": lag})
    _grava_json(pub / "track.json", {"fps": FPS, "width": LARGURA, "height": ALTURA, "count": total,
                                     "points": [[0.5, 0.4]] * total, "neutral": True})
    _grava_json(pub / "captions.json", [])
    ed_p = pub / "edit-data.json"
    try:
        ed = json.loads(ed_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ed = json.loads((TEMPLATE / "public" / "edit-data.json").read_text(encoding="utf-8"))
    ed.pop("_readme", None)
    ed.update({"fps": FPS, "width": LARGURA, "height": ALTURA, "durationSec": round(total / FPS, 4),
               "videoLag": lag, "inserts": [i for i in ed.get("inserts") or [] if "camada" in i],
               "behind": [b for b in ed.get("behind") or [] if "camada" in b]})
    for chave in ("hook", "captions", "camera", "soundtrack"):  # a montagem não tem fala, gancho nem zoom
        ed[chave] = {**(ed.get(chave) or {}), "enabled": False}
    _grava_json(ed_p, ed)
    st_p = edit / "state.json"
    st = json.loads(st_p.read_text(encoding="utf-8"))
    if st.get("editData") != "remotion/public/edit-data.json":
        st["editData"] = "remotion/public/edit-data.json"
        _grava_json(st_p, st)
    _passo([str(AQUI / "camadas_edit_data.py"), str(edit), "--edit-data", str(ed_p)])
    return rem


def renderizar(edit: Path, concorrencia: int | None = None, so_remotion: bool = False) -> None:
    """O caminho de sempre: render.py faz o cut.mp4 (a imagem). Sem nada por cima, o mixar_final.py põe
    a música direto nele; com texto, imagem, filtro ou transição, a imagem sai do Remotion (o modelo
    de Reels da Fase 2, preparar_remotion) e o mixar_final.py põe a música sobre ela. `so_remotion`
    refaz só a parte do Remotion (o cut.mp4 fica); `concorrencia`, quantos quadros ele desenha juntos."""
    edit = Path(edit).resolve()
    if not so_remotion:
        _passo([str(AQUI / "render.py"), str(edit / "edl.json"), "-o", str(edit / "cut.mp4"), "--no-subtitles"])
    if not tem_visual(edit):
        _passo([str(AQUI / "mixar_final.py"), str(edit), "--render", str(edit / "cut.mp4"), "--imagem", "corte"])
        return
    rem = preparar_remotion(edit)
    cli = rem / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    cmd = ["node", str(cli), "render", "Reels", "out/render.mp4"] + ([f"--concurrency={concorrencia}"] if concorrencia else [])
    if subprocess.run(cmd, cwd=rem).returncode != 0:
        raise ErroMontagem("o render do Remotion falhou (a saída dele está acima)")
    _passo([str(AQUI / "mixar_final.py"), str(edit), "--render", str(rem / "out" / "render.mp4")])


def conferir_o_render(edit: Path, modelo_batida: str = batida.MODELO_PADRAO) -> bool:
    """O conferir depois de um render. Se a IMAGEM saiu fora do quadro planejado num vídeo que passou
    pelo Remotion, refaz só o render dele uma vez, um quadro por vez, e confere de novo: com o
    computador ocupado (disco ou memória), o OffthreadVideo serve o quadro mais perto que tiver no
    cache, e a troca aparece até 3 quadros antes (medido em 25/10: 6 de 33 trocas no quadro com o disco
    ocupado; o mesmo render, com a máquina parada, 33 de 33)."""
    rel = conferir(edit, modelo_batida=modelo_batida)
    if rel["ok"] or not rel.get("fora_do_quadro") or not tem_visual(edit):
        return rel["ok"]
    print()
    print(f"a imagem saiu fora do quadro planejado em {rel['fora_do_quadro']} troca(s): o Remotion pegou um quadro "
          "vizinho do vídeo, o que acontece com o computador ocupado. Refazendo o render uma vez, um quadro por vez.",
          flush=True)
    renderizar(edit, concorrencia=1, so_remotion=True)
    return conferir(edit, modelo_batida=modelo_batida)["ok"]


def mudancas_salvas(edit: Path) -> list[dict]:
    """O que o Salvar do editor pediu para a montagem (`montagem.lugares` do preview_edits.json)."""
    try:
        pe = json.loads((Path(edit) / "preview_edits.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(((pe.get("montagem") or {}).get("lugares")) or [])


def aplicar(edit: Path, mudancas: list[dict] | None = None, so_dados: bool = False) -> dict:
    """Refaz só os lugares mudados (outra mídia, outro trecho do clipe) e, sem `so_dados`, o vídeo.

    `mudancas` = [{vaga, midia?, de?}]; sem elas, as do Salvar do editor (preview_edits.json). A mídia é
    um caminho de arquivo ou `midia/<nome>` do projeto. `de` é de onde o clipe entra, em segundos: sem ele,
    uma mídia nova entra do começo e a mesma mídia fica no trecho de antes. A duração do lugar, a regra do
    clipe curto e o movimento da foto são os do lugar. O que já foi pedido de volume da tomada fica."""
    edit = Path(edit).resolve()
    edl_p = edit / "edl.json"
    edl = json.loads(edl_p.read_text(encoding="utf-8"))
    mont = edl.get("montagem") or {}
    if not mont.get("lugares"):
        raise ErroMontagem("este edl.json não é de uma montagem do montagem.py (falta a lista de lugares)")
    if mudancas is None:
        mudancas = mudancas_salvas(edit)
    if not mudancas:
        raise ErroMontagem("nenhum lugar para refazer")
    por_vaga = {lg["vaga"]: lg for lg in mont["lugares"]}
    ranges = edl["ranges"]
    idx = {r.get("vaga"): i for i, r in enumerate(ranges)}
    largura = 3 if len(ranges) > 99 else 2
    pasta = edit / "montagem"
    t0 = time.perf_counter()
    pedidos = []  # tudo conferido antes do primeiro clipe: um pedido errado não deixa nada pela metade
    for m in mudancas:
        n = m.get("vaga")
        if isinstance(n, bool) or n not in por_vaga or n not in idx:
            raise ErroMontagem(f"o lugar {n} não existe nesta montagem")
        if any(p[0] == n for p in pedidos):
            raise ErroMontagem(f"o lugar {n} foi pedido duas vezes")
        lg = por_vaga[n]
        midia = Path(m.get("midia") or lg["midia"])
        if not midia.is_absolute():
            midia = (edit / midia).resolve()
        if not midia.is_file():
            raise ErroMontagem(f"lugar {n}: mídia não encontrada: {midia}")
        de = float(m["de"]) if m.get("de") is not None else (0.0 if m.get("midia") else float(lg.get("de") or 0.0))
        if not math.isfinite(de) or de < 0:
            raise ErroMontagem(f"lugar {n}: o trecho começa em {de}?")
        pedidos.append((n, midia, de))
    # os clipes novos nascem ao lado (.novo.mp4); se um falhar, os outros somem e o projeto fica como estava
    prontos = []
    try:
        for n, midia, de in pedidos:
            quadros = int(round(tempo.dur_no_corte(ranges[idx[n]]) * FPS))
            nome = f"v{n:0{largura}d}_{_slug(midia.stem, 24)}"
            novo = pasta / f"{nome}.novo.mp4"
            prontos.append((n, midia, de, quadros, nome, novo, None))
            p = padronizar(midia, novo, quadros, por_vaga[n].get("movimento"), de)
            prontos[-1] = (n, midia, de, quadros, nome, novo, p)
    except BaseException:
        for *_, novo, _p in prontos:
            novo.unlink(missing_ok=True)
        raise
    feitos = []
    for n, midia, de, quadros, nome, novo, p in prontos:
        lg, r = por_vaga[n], ranges[idx[n]]
        velho = edl["sources"].get(r["source"])
        if velho and Path(velho).parent == pasta and r["source"] != nome:
            Path(velho).unlink(missing_ok=True)
        novo.replace(pasta / f"{nome}.mp4")
        edl["sources"].pop(r["source"], None)
        edl["sources"][nome] = (pasta / f"{nome}.mp4").as_posix()
        r.update({"source": nome, "start": 0.0, "end": p["fim"]})
        r.pop("velocidade", None)
        if p["velocidade"] != 1.0:
            r["velocidade"] = p["velocidade"]
        lg.update({"midia": _chave_midia(edit, midia), "de": de})
        feitos.append({"vaga": n, "midia": midia.name, "de": de, "velocidade": p["velocidade"],
                       "congela": p["congela"], "quadros_no_arquivo": p["quadros_no_arquivo"]})
        print(f"  lugar {n:>3}: {midia.name}" + (f" a partir de {de:g} s" if de else "") + f" → {quadros} quadros"
              + (f", {p['velocidade']:.2f}×" if p["velocidade"] != 1.0 else ""), flush=True)
    _grava_json(edl_p, edl)
    st_p = edit / "state.json"
    try:
        st = json.loads(st_p.read_text(encoding="utf-8"))
        st["sourceDurations"] = {k: v for k, v in (st.get("sourceDurations") or {}).items() if k in edl["sources"]}
        for f in feitos:
            nome = ranges[idx[f["vaga"]]]["source"]
            st["sourceDurations"][nome] = round(f["quadros_no_arquivo"] / FPS, 3)
        _grava_json(st_p, st)
    except (OSError, json.JSONDecodeError):
        pass
    resumo = {"lugares": feitos, "padronizar_s": round(time.perf_counter() - t0, 1)}
    if not so_dados:
        renderizar(edit)
    resumo["total_s"] = round(time.perf_counter() - t0, 1)
    return resumo


# ---------- a conferência ----------

def _passo_da_batida(edit: Path, mont: dict) -> float:
    """O tempo de uma batida da música da montagem: a mediana da grade (sem ela, pelo BPM)."""
    try:
        b = np.asarray(json.loads((edit / mont["batidas"]).read_text(encoding="utf-8"))["batidas"], dtype=float)
        if len(b) > 1:
            return float(np.median(np.diff(b)))
    except (KeyError, OSError, ValueError, TypeError):
        pass
    bpm = mont.get("bpm")
    return 60.0 / float(bpm) if isinstance(bpm, (int, float)) and not isinstance(bpm, bool) and bpm > 0 else 0.5


def capturar(edit: Path, nome: str) -> dict:
    """O modelo da montagem como ela está (o "Salvar como modelo de montagem"), para montagens.salvar:
    os lugares em batidas; os textos das camadas (com o nome deles; o texto solto vira "Texto N") nas
    batidas da janela deles; as transições que caem numa troca. O texto que começa no meio de um lugar
    passa a começar com ele, porque o modelo só começa texto numa troca. O que não coube vai em
    `avisos`."""
    edit = Path(edit).resolve()
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    mont = edl.get("montagem") or {}
    por_vaga = {lg.get("vaga"): lg for lg in mont.get("lugares") or [] if isinstance(lg, dict)}
    if not por_vaga:
        raise ErroMontagem("este edl.json não é de uma montagem do montagem.py")
    inicios, total = quadros_dos_lugares(edl)
    limites = inicios + [total]
    passo = _passo_da_batida(edit, mont)
    vagas, batidas, avisos = [], [], []
    for i, r in enumerate(edl["ranges"]):
        lg = por_vaga.get(r.get("vaga")) or {}
        nb = lg.get("batidas")
        if isinstance(nb, bool) or not isinstance(nb, int) or nb < 1:  # montagem de antes das batidas guardadas
            nb = max(1, round((limites[i + 1] - limites[i]) / FPS / passo))
        batidas.append(nb)
        vagas.append({"batidas": nb, **({"movimento": lg["movimento"]} if lg.get("movimento") else {})})

    meio = 0.5 / FPS

    def lugar_em(t: float) -> int:  # o índice do lugar em que o instante t cai
        k = 0
        while k + 1 < len(inicios) and inicios[k + 1] / FPS <= t + meio:
            k += 1
        return k

    textos = []
    for f in cam.load(edit / "camadas.json")["faixas"]:
        if f.get("tipo") != "texto" or f.get("oculto"):
            continue
        for it in f["itens"]:
            if len(textos) >= MAX_TEXTOS:
                avisos.append(f"mais de {MAX_TEXTOS} textos: os seguintes ficaram de fora")
                break
            s = float(it["inicio"])
            e = s + float(it["duracao"])
            v, w = lugar_em(s), lugar_em(e - 2 * meio)
            if abs(s - limites[v] / FPS) <= meio and abs(e - limites[w + 1] / FPS) <= meio:
                nb = None if v == w else sum(batidas[v:w + 1])  # sem batidas, o texto dura o lugar
            else:
                nb = max(1, round((e - s) / passo))
            textos.append({"nome": it.get("nome") or f"Texto {len(textos) + 1}", "texto": it["texto"],
                           "vaga": v + 1, "batidas": nb, "x": it["x"], "y": it["y"], "estilo": it.get("estilo")})
        else:
            continue
        break

    transicoes, outros = [], 0
    for it in efeitos.load(edit / "efeitos.json")["itens"]:
        if it["tipo"] != "transicao":
            outros += 1
            continue
        q = int(round(it["corte"] * FPS))
        if q in inicios[1:]:
            transicoes.append({"vaga": inicios.index(q) + 1, "pacote": it["pacote"],
                               "duracao": max(efeitos.TRANSICAO_MIN, round(float(it["duracao"]), 3))})
        else:
            avisos.append(f"a transição em {it['corte']:.2f} s não cai numa troca de lugar e ficou de fora")
    if outros:
        avisos.append(f"{outros} filtro(s) ou ajuste(s) não entram no modelo de montagem (só as transições)")
    drop = mont.get("drop_na_vaga")
    return {"versao": 1, "nome": nome, "comeca": mont.get("comeca", "forte"),
            "drop_na_vaga": drop if isinstance(drop, int) and 1 <= drop <= len(vagas) else None,
            "golpe": mont.get("golpe", True) is not False, "vagas": vagas, "textos": textos,
            "transicoes": transicoes, "avisos": avisos}


def pedido_de_montar(edit: Path) -> dict | None:
    """O "Usar" do painel Modelos de montagem, gravado pelo Salvar do editor: {modelo, musica, midias}."""
    try:
        pe = json.loads((Path(edit) / "preview_edits.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    p = (pe.get("montagem") or {}).get("usar") if isinstance(pe, dict) else None
    return p if isinstance(p, dict) else None


def montar(edit: Path, modelo_batida: str = batida.MODELO_PADRAO, so_dados: bool = False) -> dict:
    """Faz o que o editor pediu no Salvar: a montagem com o modelo, a música e as fotos e clipes
    escolhidos. A música é um arquivo do midia/ do projeto; as fotos e clipes, do midia/ ou da
    montagem aberta (o servidor conferiu; aqui confere de novo)."""
    import montagens  # aqui dentro: o montagens.py importa este arquivo

    edit = Path(edit).resolve()
    p = pedido_de_montar(edit)
    if not p:
        raise ErroMontagem("o Salvar do editor não pediu montagem (preview_edits.json sem montagem.usar)")
    modelo = montagens.obter(p.get("modelo"))
    if not modelo:
        raise ErroMontagem(f'o modelo de montagem "{p.get("modelo")}" não existe mais')
    pasta = (edit / cam.MIDIA_DIR).resolve()
    try:
        atual = json.loads((edit / "edl.json").read_text(encoding="utf-8")).get("montagem") or {}
    except (OSError, ValueError, AttributeError):
        atual = {}
    usadas = [*(atual.get("midias") or []), *(lg.get("midia") for lg in atual.get("lugares") or [] if isinstance(lg, dict))]
    originais = {str(Path(x)) for x in usadas if isinstance(x, str) and Path(x).is_absolute()}

    def do_projeto(rel: object, da_montagem: bool = False) -> Path:
        if da_montagem and isinstance(rel, str) and str(Path(rel)) in originais and Path(rel).is_file():
            return Path(rel)
        q = (edit / str(rel)).resolve()
        if not isinstance(rel, str) or q.parent != pasta or not q.is_file():
            raise ErroMontagem(f"arquivo fora do midia/ do projeto: {rel}")
        return q

    musica = do_projeto(p.get("musica"))
    midias = [str(do_projeto(x, da_montagem=True)) for x in p.get("midias") or []]
    if not midias:
        raise ErroMontagem("o pedido não tem foto nem clipe")
    return usar(modelo, musica, midias, edit, modelo_batida, so_dados)


def quadros_dos_lugares(edl: dict, fps: int = FPS) -> tuple[list[int], int]:
    """O quadro do vídeo em que cada lugar começa, e o total."""
    inicios, pos = [], 0
    for r in edl["ranges"]:
        inicios.append(pos)
        pos += int(round(tempo.dur_no_corte(r) * fps))
    return inicios, pos


def diferencas(video: Path) -> np.ndarray:
    """A diferença média entre cada quadro e o seguinte (cinza, 72×128): `d[i]` é a troca do quadro i
    para o i + 1. `passthrough` entrega os quadros como estão, sem repetir nem descartar nenhum."""
    w, h = 72, 128
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-map", "0:v:0",
                        "-fps_mode", "passthrough", "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    if r.returncode != 0:
        msg = (r.stderr or b"").decode("utf-8", "replace").strip()[-300:]
        raise ErroMontagem(f"não consegui ler os quadros de {Path(video).name}: {msg}")
    q = np.frombuffer(r.stdout, np.uint8)
    q = q[: len(q) // (w * h) * (w * h)].reshape(-1, h, w).astype(np.int16)
    return np.abs(np.diff(q, axis=0)).mean(axis=(1, 2))


def achar_troca(d: np.ndarray, quadro: int, janela: int = JANELA) -> int:
    """O quadro em que a imagem nova aparece, perto do `quadro` planejado: o maior salto na janela."""
    lo, hi = max(0, quadro - 1 - janela), min(len(d), quadro + janela)
    return lo + int(np.argmax(d[lo:hi])) + 1


def conferir(edit: Path, video: Path | None = None, modelo_batida: str = batida.MODELO_PADRAO,
             mostrar: bool = True) -> dict:
    """Três medidas, que juntas dizem se a troca cai na batida que se ouve no vídeo:

    - a imagem: o quadro em que cada troca aparece no vídeo × o planejado pelo edl.json;
    - a troca × a batida mais perto da grade da música (a da música inteira, com o contexto que o
      detector precisa: rodando só no trecho do vídeo, ele perde uma batida aqui e ali);
    - o som: as batidas que o detector acha no som do PRÓPRIO vídeo × a grade. A mediana diz se a
      música entrou deslocada; o erro de cada troca já desconta esse deslocamento.

    A troca com transição (efeitos.json) é gradual e não tem um quadro de troca para achar: nela vale
    o corte, que é o centro da transição."""
    edit = Path(edit).resolve()
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    mont = edl.get("montagem")
    if not mont:
        raise ErroMontagem("este edl.json não é de uma montagem")
    video = Path(video) if video else edit / "final.mp4"
    if not video.is_file():
        raise ErroMontagem(f"vídeo não encontrado: {video}")
    try:
        grade = json.loads((edit / mont["batidas"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, json.JSONDecodeError):
        raise ErroMontagem("a grade de batida da música não está no projeto: rode o `usar` de novo") from None
    inicios, total = quadros_dos_lugares(edl)
    t0 = float(mont["inicio_musica"])

    def no_video(x: np.ndarray) -> np.ndarray:
        return x[(x > -0.5) & (x < total / FPS + 0.5)]

    da_musica = no_video(np.asarray(grade["batidas"], dtype=float) - t0)
    golpes = no_video(referencias(grade) - t0)  # as batidas e os contratempos fortes
    if not len(da_musica):
        raise ErroMontagem("a grade da música não tem batida dentro do vídeo")
    d = diferencas(video)
    no_som, _ = batida.detectar(batida.ler_audio(video), batida.SR, modelo_batida)
    um_quadro = 1000.0 / FPS
    # o corte de cada transição, gravado com 3 casas, cai a menos de meio quadro da junção
    com_transicao = {int(round(it["corte"] * FPS)): it["pacote"]
                     for it in efeitos.load(edit / "efeitos.json")["itens"] if it["tipo"] == "transicao"}

    def perto(lista: np.ndarray, t: float) -> float | None:
        return float(lista[int(np.argmin(np.abs(lista - t)))]) if len(lista) else None

    # o som deslocado: cada batida achada no som do vídeo × a da grade mais perto dela
    desvios = [(t - perto(da_musica, t)) * 1000 for t in no_som]
    desvio = round(float(np.median(desvios)), 1) if desvios else None
    trocas = []
    for k in range(1, len(inicios)):
        transicao = com_transicao.get(inicios[k])
        visto = inicios[k] if transicao else achar_troca(d, inicios[k])
        t = visto / FPS
        bm = perto(golpes, t)
        no_golpe = bool(np.min(np.abs(da_musica - bm)) > 1e-6)  # caiu no contratempo, não numa batida
        bs = perto(no_som, t)
        trocas.append({"lugar": edl["ranges"][k].get("vaga", k + 1), "quadro": inicios[k], "visto": visto,
                       "troca": round(t, 4), "batida_da_musica": round(bm, 3), "no_golpe": no_golpe,
                       "transicao": transicao,
                       "erro_ms": round((t - bm) * 1000 - (desvio or 0.0), 1),
                       "batida_no_som": None if bs is None or abs(bs - t) * 1000 > 2 * um_quadro else round(bs, 3)})
    erros = [abs(x["erro_ms"]) for x in trocas]
    fora_do_quadro = [x for x in trocas if x["visto"] != x["quadro"]]
    ok = (bool(trocas) and not fora_do_quadro and max(erros) <= um_quadro + 0.05
          and desvio is not None and abs(desvio) <= um_quadro)
    rel = {"video": video.name, "trocas": trocas, "quadros": total, "pior_ms": max(erros) if erros else None,
           "ate_um_quadro": sum(e <= um_quadro + 0.05 for e in erros), "fora_do_quadro": len(fora_do_quadro),
           "som_vs_plano_ms": desvio, "batidas_no_som": len(no_som),
           "trocas_no_golpe": sum(x["no_golpe"] for x in trocas),
           "com_transicao": sum(bool(x["transicao"]) for x in trocas),
           # o detector de batida não marca contratempo: só a troca numa batida conta aqui
           "trocas_sem_batida_no_som": sum(x["batida_no_som"] is None and not x["no_golpe"] for x in trocas),
           "ok": ok}
    pasta = edit / "verify"
    pasta.mkdir(exist_ok=True)
    _grava_json(pasta / "montagem_conferir.json", rel)
    if mostrar:
        print(relatorio(rel))
    return rel


def relatorio(rel: dict) -> str:
    trocas = rel["trocas"]
    linhas = [f"conferir {rel['video']}: {len(trocas)} trocas de imagem"]
    mostrar = trocas if len(trocas) <= 30 else sorted(trocas, key=lambda x: -abs(x["erro_ms"] or 0))[:10]
    if len(trocas) > 30:
        linhas.append("  (as 10 piores)")
    linhas.append("  lugar  quadro planejado  quadro visto  troca (s)  batida da música (s)  erro    no som do vídeo")
    for x in mostrar:
        no_som = "—" if x["batida_no_som"] is None else f"{x['batida_no_som']:.3f}"
        onde = "golpe" if x.get("no_golpe") else ""
        visto = "transição" if x.get("transicao") else x["visto"]
        linhas.append(f"  {x['lugar']:>5}  {x['quadro']:>16}  {visto:>12}  {x['troca']:>9.3f}  "
                      f"{x['batida_da_musica']:>14.3f} {onde:>5}  {x['erro_ms']:+4.0f} ms  {no_som:>15}")
    if rel["pior_ms"] is not None:
        linhas.append(f"  pior erro: {rel['pior_ms']:.0f} ms; {rel['ate_um_quadro']} de {len(trocas)} trocas a no "
                      f"máximo 1 quadro ({1000 / FPS:.0f} ms) da batida")
    if rel.get("trocas_no_golpe"):
        linhas.append(f"  {rel['trocas_no_golpe']} troca(s) no golpe forte do contratempo (marcadas \"golpe\")")
    secas = len(trocas) - rel.get("com_transicao", 0)
    imagem = f"  imagem: {secas - rel['fora_do_quadro']} de {secas} trocas no quadro planejado"
    if rel.get("com_transicao"):
        imagem += f"; {rel['com_transicao']} com transição (gradual: vale o corte, no centro dela)"
    linhas.append(imagem)
    if rel["som_vs_plano_ms"] is None:
        linhas.append("  som: o detector não achou batida no som do vídeo")
    else:
        linhas.append(f"  som: {rel['batidas_no_som']} batidas achadas no som do vídeo, a {rel['som_vs_plano_ms']:+.0f} ms "
                      f"da grade da música (mediana); {rel['trocas_sem_batida_no_som']} troca(s) sem batida achada "
                      "perto, no trecho")
    linhas.append("  OK" if rel["ok"] else "  REPROVADO: veja as trocas acima")
    return "\n".join(linhas)


def _resumo_usar(r: dict) -> str:
    linhas = [f"montagem: {r['lugares']} lugares, {r['duracao']:.2f} s, {r['bpm']} BPM (confiança {r['confianca']}), "
              f"a música entra aos {r['inicio_musica']:.3f} s"]
    if r["drop_na_vaga"] and r["drop"] is not None:
        linhas.append(f"  drop da música aos {r['drop']:.2f} s, no lugar {r['drop_na_vaga']}")
    if r["no_golpe"]:
        linhas.append(f"  {r['no_golpe']} troca(s) no golpe forte do contratempo, meia batida antes ou depois da batida")
    for x in r["lentos"]:
        linhas.append(f"  mais lento: {x}")
    if r["sobraram_midias"]:
        linhas.append(f"  {r['sobraram_midias']} mídia(s) ficaram de fora (mais mídias que lugares)")
    for a in r["avisos"]:
        linhas.append(f"  aviso: {a}")
    linhas.append(f"  projeto: {r['edit']}")
    return "\n".join(linhas)


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="montagem", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("usar", help="monta o projeto e o vídeo")
    u.add_argument("modelo", type=Path, help="o JSON do modelo, ou o id de um modelo guardado (montagens.py listar)")
    u.add_argument("--musica", type=Path, required=True)
    u.add_argument("--midias", nargs="+", required=True, help="arquivos ou pastas; arquivo@segundos para o ponto de entrada")
    u.add_argument("--edit", type=Path, required=True)
    u.add_argument("--modelo-batida", choices=sorted(batida.MODELOS), default=batida.MODELO_PADRAO)
    u.add_argument("--so-dados", action="store_true", help="escreve o projeto sem renderizar")
    u.add_argument("--substituir", action="store_true", help="troca uma edição que não é montagem")
    c = sub.add_parser("conferir", help="mede onde cada troca caiu e a batida mais perto")
    c.add_argument("edit", type=Path)
    c.add_argument("--video", type=Path, default=None)
    c.add_argument("--modelo-batida", choices=sorted(batida.MODELOS), default=batida.MODELO_PADRAO)
    p = sub.add_parser("aplicar", help="refaz só os lugares mudados: os do Salvar do editor, ou o de --lugar")
    p.add_argument("edit", type=Path)
    p.add_argument("--lugar", type=int, default=None, help="o número do lugar (sem ele: o preview_edits.json)")
    p.add_argument("--midia", default=None, help="a mídia nova do lugar (arquivo ou midia/<nome>)")
    p.add_argument("--de", type=float, default=None, help="de onde o clipe entra, em segundos")
    p.add_argument("--so-dados", action="store_true", help="refaz os lugares sem renderizar")
    p.add_argument("--modelo-batida", choices=sorted(batida.MODELOS), default=batida.MODELO_PADRAO)
    rd = sub.add_parser("render", help="refaz o vídeo como está (camadas, textos ou efeitos mudaram) e confere")
    rd.add_argument("edit", type=Path)
    rd.add_argument("--modelo-batida", choices=sorted(batida.MODELOS), default=batida.MODELO_PADRAO)
    mo = sub.add_parser("montar", help="monta pelo Salvar do editor (o Usar do painel Modelos de montagem)")
    mo.add_argument("edit", type=Path)
    mo.add_argument("--so-dados", action="store_true", help="escreve o projeto sem renderizar")
    mo.add_argument("--modelo-batida", choices=sorted(batida.MODELOS), default=batida.MODELO_PADRAO)
    ca = sub.add_parser("capturar", help="guarda a montagem como modelo de montagem (montagens.py)")
    ca.add_argument("edit", type=Path)
    ca.add_argument("--nome", required=True)
    ca.add_argument("--so-mostrar", action="store_true", help="mostra o modelo sem guardar")
    a = ap.parse_args()
    try:
        if a.cmd == "usar":
            modelo = a.modelo
            if not modelo.is_file():  # o id de um modelo guardado (montagens.py), além de um arquivo
                import montagens  # aqui dentro: o montagens.py importa este arquivo
                modelo = montagens.obter(str(a.modelo)) or a.modelo
            r = usar(modelo, a.musica, a.midias, a.edit, a.modelo_batida, a.so_dados, a.substituir)
            print(_resumo_usar(r))
            if a.so_dados:
                return 0
            return 0 if conferir_o_render(a.edit, a.modelo_batida) else 1
        if a.cmd == "aplicar":
            mudancas = None
            if a.lugar is not None:
                mudancas = [{"vaga": a.lugar, **({"midia": a.midia} if a.midia else {}),
                             **({"de": a.de} if a.de is not None else {})}]
            r = aplicar(a.edit, mudancas, a.so_dados)
            print(f"aplicar: {len(r['lugares'])} lugar(es) refeito(s); padronizar {r['padronizar_s']} s"
                  + (f", com o render {r['total_s']} s" if not a.so_dados else ""))
            if a.so_dados:
                return 0
            return 0 if conferir_o_render(a.edit, a.modelo_batida) else 1
        if a.cmd == "render":
            if "montagem" not in json.loads((Path(a.edit) / "edl.json").read_text(encoding="utf-8")):
                raise ErroMontagem("este edl.json não é de uma montagem do montagem.py")
            renderizar(a.edit)
            return 0 if conferir_o_render(a.edit, a.modelo_batida) else 1
        if a.cmd == "montar":
            r = montar(a.edit, a.modelo_batida, a.so_dados)
            print(_resumo_usar(r))
            if a.so_dados:
                return 0
            return 0 if conferir_o_render(a.edit, a.modelo_batida) else 1
        if a.cmd == "capturar":
            import montagens  # aqui dentro: o montagens.py importa este arquivo
            m = capturar(a.edit, a.nome)
            avisos = m.pop("avisos")
            try:
                if a.so_mostrar:
                    print(json.dumps(montagens.normalize(m), ensure_ascii=False, indent=2))
                else:
                    m = montagens.salvar(m)
                    print(f"salvo: {m['id']}  {m['nome']}  ({montagens.pasta() / (m['id'] + '.json')})")
            except montagens.MontagemInvalida as e:
                print(f"montagem: o modelo não foi guardado: {e}", file=sys.stderr)
                return 2
            for x in avisos:
                print(f"  aviso: {x}")
            return 0
        return 0 if conferir(a.edit, a.video, a.modelo_batida)["ok"] else 1
    except (ErroMontagem, batida.ErroBatida, cam.CamadasInvalidas, efeitos.EfeitosInvalidos) as e:
        print(f"montagem: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
