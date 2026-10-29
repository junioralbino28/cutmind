#!/usr/bin/env python3
"""O Salvar do editor que mexe nas tomadas, aplicado sem o agente: o edl.json novo pelas regras do
SKILL.md ("When the user saves timeline edits"), o render.py com as opções de antes, a conferência e as
camadas, efeitos e trechos de velocidade levados para o corte novo (remapear.py), e, com a Fase 2
feita, o edit-data.json, a legenda, a transcrição do corte e o segments.json junto.

    uv run python -X utf8 helpers/aplicar_corte.py <edit> --pedido <arquivo.json>
"""
from __future__ import annotations

import argparse
import json
import os
import string
import subprocess
import sys
import time
from pathlib import Path

import camadas as cam  # mesma pasta deste arquivo
import efeitos as ef  # mesma pasta deste arquivo
import gerar as gr  # mesma pasta deste arquivo
import remapear  # mesma pasta deste arquivo
import speech_regions as sr  # mesma pasta deste arquivo
import tempo  # mesma pasta deste arquivo
import trabalhos  # mesma pasta deste arquivo
import velocidade as vel  # mesma pasta deste arquivo
from render import JCUT_LEAD_FRAMES, JCUT_TAIL_TRIM_FRAMES, resolve_path  # mesma pasta deste arquivo

AQUI = Path(__file__).resolve().parent

FOLGA_FALA = 0.03     # a margem do SKILL ao cortar: 30 ms antes ou depois da fala não é "no meio"
# o editor manda as pontas arredondadas no milésimo, e o edl.json guarda pontas alinhadas ao quadro
# (80,2333…): até 2 ms de diferença é a mesma ponta, não uma ponta que a pessoa mexeu
FOLGA_IGUAL = 0.002
SILENCIO_MAX = 1.2    # o --min-silence do verify_cut: mais que isso numa emenda é ar morto
NOMES_ITEM = {"imagem": "A imagem", "texto": "O texto", "audio": "O áudio", "filtro": "O filtro",
              "ajuste": "O ajuste de cor", "transicao": "A transição", "velocidade": "O trecho de velocidade",
              # os blocos e efeitos da Fase 2 (remapear.fase2)
              "insert": "A imagem do vídeo final", "split": "A tela dividida", "splitvideo": "O vídeo da tela dividida",
              "word": "A palavra em destaque", "behind": "O destaque atrás da pessoa", "numero": "O número",
              "cena": "O efeito do vídeo final", "grafico": "O gráfico do vídeo final",
              "voz": "O efeito de voz"}

# o que vem da pessoa (a régua de volume, a velocidade, a curva, o lugar da montagem): o Salvar manda
# quando não é o padrão; sem ele, a tomada volta ao padrão, e não herda o do edl.json velho
DA_PESSOA = ("volume", "velocidade", "curva", "vaga", "enquadre")


def novo_edl(edl: dict, pedido: dict) -> tuple[dict, list[int | None]]:
    """O edl.json novo e, para cada tomada nova, o índice da tomada velha de onde ela veio. Do agente
    fica o que ele escreveu na tomada (`quote`, `reason`, `gain_db`, a cor); da pessoa, as pontas, a
    ordem e o que está em DA_PESSOA. O `jcut_timeline` sai: ele é do render velho."""
    velhas = edl.get("ranges") or []
    ranges, origem = [], []
    for p in pedido.get("ranges") or []:
        k = p.get("take")
        conhecida = isinstance(k, int) and 0 <= k < len(velhas)
        base = dict(velhas[k]) if conhecida else {}
        for c in DA_PESSOA:
            base.pop(c, None)
        base.update(source=p["source"], start=float(p["start"]), end=float(p["end"]))
        if p.get("beat") is not None:
            base["beat"] = p["beat"]
        for c in DA_PESSOA:
            if p.get(c) is not None:
                base[c] = p[c]
        if base.get("enquadre") is not None:  # o lugar e o tamanho da gravação: conferido como uma camada
            base["enquadre"] = cam.enquadre(base["enquadre"])
        ranges.append(base)
        origem.append(k if conhecida else None)
    ranges, origem = _juntar_divisoes(ranges, origem)
    novo = {k: v for k, v in edl.items() if k not in ("ranges", "jcut_timeline", "total_duration_s")}
    novo["ranges"] = ranges
    return novo, origem


def so_enquadre(edl: dict, novo: dict) -> bool:
    """O Salvar só mudou o enquadre das tomadas (o lugar e o tamanho da gravação na tela): as tomadas são as
    mesmas, nas mesmas pontas (até FOLGA_IGUAL), e o resto delas igual. Aí o corte não precisa ser refeito: o
    enquadre é desenhado depois, no vídeo final."""
    velhas, novas = edl.get("ranges") or [], novo.get("ranges") or []
    if len(velhas) != len(novas):
        return False
    for a, b in zip(velhas, novas):
        if abs(float(a["start"]) - float(b["start"])) > FOLGA_IGUAL or abs(float(a["end"]) - float(b["end"])) > FOLGA_IGUAL:
            return False
        fora = ("start", "end", "enquadre")
        if {k: v for k, v in a.items() if k not in fora} != {k: v for k, v in b.items() if k not in fora}:
            return False
    return True


def _juntar_divisoes(ranges: list[dict], origem: list[int | None]) -> tuple[list[dict], list[int | None]]:
    """Duas metades encostadas da mesma tomada, com o mesmo volume e a mesma velocidade, são uma divisão
    que a pessoa deixou como estava: juntas de novo, ou o J-cut dobraria o som na emenda. Tomadas de
    origens diferentes não juntam, mesmo encostadas: o agente pode tê-las separado de propósito (o zoom
    é um por tomada)."""
    out_r: list[dict] = []
    out_o: list[int | None] = []
    for r, o in zip(ranges, origem):
        if out_r and o is not None and out_o[-1] == o:
            a = out_r[-1]
            if a["source"] == r["source"] and abs(a["end"] - r["start"]) < FOLGA_IGUAL and \
                    all(a.get(c) == r.get(c) for c in DA_PESSOA):
                a["end"] = r["end"]
                continue
        out_r.append(dict(r))
        out_o.append(o)
    return out_r, out_o


# ---- a conferência antes de aplicar ----------------------------------------------------------
# O editor pergunta antes de aplicar o que fica desalinhado (pedido dele em 27/10: "pode ser
# proposital"). A conta é aproximada, sem render: as regiões de fala da gravação (speech_regions.py)
# e o corte novo sem J-cut. Cada aviso volta como dados (o editor monta a frase no idioma da tela) e
# com um `texto` em português para o agente e para o terminal.

def _fala_em(regioes: list, t: float) -> bool:
    return any(a + FOLGA_FALA < t < b - FOLGA_FALA for a, b in regioes)


def _palavra_em(palavras: list, t: float) -> str | None:
    for w in palavras:
        if w.get("type", "word") == "word" and float(w["start"]) < t < float(w["end"]):
            return str(w.get("text", "")).strip().strip(string.punctuation + "«»“”…") or None
    return None


def _silencio_no_fim(regioes: list, r: dict) -> float:
    a, b = float(r["start"]), float(r["end"])
    fins = [min(fim, b) for ini, fim in regioes if ini < b and fim > a]
    return b - max(fins) if fins else b - a


def _silencio_no_comeco(regioes: list, r: dict) -> float:
    a, b = float(r["start"]), float(r["end"])
    inicios = [max(ini, a) for ini, fim in regioes if ini < b and fim > a]
    return min(inicios) - a if inicios else b - a


def _desconto_jcut(edl: dict) -> float:
    """O que o J-cut já tira de cada emenda: a voz da tomada seguinte entra antes e a ponta muda
    da anterior é aparada."""
    if edl.get("jcut", True) in (False, "off", "none") or (edl.get("render") or {}).get("no_jcut"):
        return 0.0
    return (JCUT_LEAD_FRAMES + JCUT_TAIL_TRIM_FRAMES) / 30.0


def _onde_ficou(levar, t: float, total_velho: float) -> float:
    """O instante do corte novo mais perto de onde estava um item que saiu: o primeiro que ficou
    depois dele, ou o último antes."""
    passo = 0.05
    x = t
    while x <= total_velho:
        v = levar(x)
        if v is not None:
            return round(v, 3)
        x += passo
    x = t
    while x >= 0:
        v = levar(x)
        if v is not None:
            return round(v, 3)
        x -= passo
    return 0.0


def _texto(a: dict) -> str:
    if a["tipo"] == "ponta_na_fala":
        verbo = "começa" if a["ponta"] == "começo" else "termina"
        onde = f"no meio da palavra «{a['palavra']}»" if a.get("palavra") else "no meio da fala"
        return f"A tomada {a['tomada']} {verbo} {onde}."
    if a["tipo"] == "silencio_longo":
        return f"Entre as tomadas {a['tomadas'][0]} e {a['tomadas'][1]} ficam {a['segundos']:.1f} s sem fala."
    nome = f" «{a['nome']}»" if a.get("nome") else ""
    return f"{NOMES_ITEM.get(a['item'], a['item'])}{nome} estava num trecho que saiu do corte e vai sair do vídeo."


def conferir(edl: dict, pedido: dict, regioes: dict, palavras: dict, camadas: dict | None = None,
             efeitos: dict | None = None, velocidade: dict | None = None, fase2: dict | None = None) -> list[dict]:
    """O que o Salvar deixaria desalinhado: ponta nova no meio da fala, emenda com silêncio longo e
    item (camada, efeito, trecho de velocidade, bloco ou efeito da Fase 2 no `fase2`, o edit-data.json)
    que cairia fora do corte. `regioes` e `palavras` vêm por fonte (speech_regions.py e a transcrição de
    cada gravação). Vazio = pode aplicar sem perguntar."""
    novo, origem = novo_edl(edl, pedido)
    velhas = edl.get("ranges") or []
    rs = novo["ranges"]
    spans = tempo.tomadas_no_corte({"ranges": rs})
    avisos: list[dict] = []
    # montagem na batida (fotos e clipes sobre a música) e gravação sem fala: nada de fala para cortar
    # no meio nem de silêncio para medir; só o que sai do vídeo
    com_fala = "montagem" not in edl

    for j, (r, k) in enumerate(zip(rs, origem)):
        if not com_fala:
            break
        v = velhas[k] if k is not None else None
        fala = regioes.get(r["source"]) or []
        for ponta, chave, em in (("começo", "start", spans[j]["out"]),
                                 ("fim", "end", spans[j]["out"] + spans[j]["dur"])):
            t = float(r[chave])
            if v is not None and abs(float(v[chave]) - t) < FOLGA_IGUAL:
                continue  # a ponta é a que o agente escolheu
            if _fala_em(fala, t):
                avisos.append({"tipo": "ponta_na_fala", "em": round(max(0.0, em - (0.04 if ponta == "fim" else 0)), 3),
                               "tomada": j + 1, "ponta": ponta, "palavra": _palavra_em(palavras.get(r["source"]) or [], t)})

    desconto = _desconto_jcut(novo)
    for j in range(len(rs) - 1 if com_fala else 0):
        a, b, ka, kb = rs[j], rs[j + 1], origem[j], origem[j + 1]
        if not regioes.get(a["source"]) or not regioes.get(b["source"]):
            continue  # uma das gravações não tem fala nenhuma: o silêncio dela não é defeito
        seguidas = ka is not None and kb == ka + 1
        if seguidas and abs(float(velhas[ka]["end"]) - float(a["end"])) < FOLGA_IGUAL and \
                abs(float(velhas[kb]["start"]) - float(b["start"])) < FOLGA_IGUAL:
            continue  # a emenda que já existia
        mudo = _silencio_no_fim(regioes.get(a["source"]) or [], a) + \
            _silencio_no_comeco(regioes.get(b["source"]) or [], b) - desconto
        antes = (_silencio_no_fim(regioes.get(a["source"]) or [], velhas[ka]) +
                 _silencio_no_comeco(regioes.get(b["source"]) or [], velhas[kb]) - desconto) if seguidas else 0.0
        if mudo > SILENCIO_MAX and mudo > antes + 0.1:
            avisos.append({"tipo": "silencio_longo", "em": round(spans[j + 1]["out"], 3), "segundos": round(mudo, 1),
                           "tomadas": [j + 1, j + 2]})

    if camadas or efeitos or velocidade or fase2:
        levar = remapear.mapa(edl, {"ranges": rs}, origem)
        total = sum(s["dur"] for s in spans)
        total_velho = float(edl.get("total_duration_s") or sum(s["dur"] for s in tempo.tomadas_no_corte(edl)))
        fora: list[dict] = []
        if camadas:
            fora += remapear.camadas(camadas, levar, total)[1]
        if efeitos:
            fora += remapear.efeitos(efeitos, levar, [s["out"] for s in spans[1:]], total)[1]
        if velocidade:
            fora += remapear.velocidade(velocidade, levar, total)[1]
        if fase2:
            fora += remapear.fase2(fase2, levar, total, origem, len(velhas))[1]
        for f in fora:
            avisos.append({"tipo": "item_sai", "em": _onde_ficou(levar, f["inicio"], total_velho),
                           "item": f["item"], "nome": f["nome"]})

    for a in avisos:
        a["texto"] = _texto(a)
    return sorted(avisos, key=lambda a: a["em"])


# ---- aplicar ------------------------------------------------------------------------------------

class PrecisaConfirmar(Exception):
    """O Salvar deixa algo desalinhado e a pessoa ainda não disse que mantém."""

    def __init__(self, avisos: list[dict]):
        super().__init__(f"{len(avisos)} aviso(s) antes de aplicar")
        self.avisos = avisos


class ErroCorte(Exception):
    pass


def _grava_json(p: Path, dados) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8"))
    for _ in range(40):  # outro processo lendo o arquivo nesse instante (Windows): tenta de novo
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)
    raise ErroCorte(f"não consegui gravar {p.name}: o arquivo está aberto em outro programa")


def regioes_da_fonte(edit: Path, fonte: Path) -> list[tuple[float, float]]:
    """As regiões de fala da gravação (speech_regions.py), guardadas por tamanho e data do arquivo: a 1ª
    vez leva alguns segundos; depois, nada."""
    cache = Path(edit) / ".cutmind" / f"regioes-{fonte.stem}.json"
    st = fonte.stat()
    chave = [st.st_size, round(st.st_mtime, 3)]
    try:
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("chave") == chave:
            return [(float(a), float(b)) for a, b in d["regioes"]]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    reg = sr.speech_regions(fonte, "-33dB", 0.10)
    cache.parent.mkdir(parents=True, exist_ok=True)
    _grava_json(cache, {"chave": chave, "regioes": [[round(a, 3), round(b, 3)] for a, b in reg]})
    return reg


def palavras_da_fonte(edit: Path, chave: str, fonte: Path) -> list[dict]:
    for nome in (fonte.stem, chave):
        try:
            return json.loads((Path(edit) / "transcripts" / f"{nome}.json").read_text(encoding="utf-8")).get("words") or []
        except (OSError, ValueError, AttributeError):
            continue
    return []


def conferir_projeto(edit: Path, pedido: dict) -> list[dict]:
    """A conferência com o que o projeto tem: a fala de cada gravação, a transcrição e as camadas,
    efeitos e trechos de velocidade gravados."""
    edit = Path(edit).resolve()
    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    regioes, palavras = {}, {}
    for chave, caminho in (edl.get("sources") or {}).items():
        fonte = resolve_path(str(caminho), edit)
        if fonte.exists():
            regioes[chave] = regioes_da_fonte(edit, fonte)
            palavras[chave] = palavras_da_fonte(edit, chave, fonte)
    c = cam.load(edit / "camadas.json")
    e = ef.load(edit / "efeitos.json")
    v = vel.load(edit / "velocidade.json")
    return conferir(edl, pedido, regioes, palavras, camadas=c if any(f["itens"] for f in c["faixas"]) else None,
                    efeitos=e if e["itens"] else None, velocidade=v if v.get("trechos") else None,
                    fase2=_ler(_edit_data(edit)) if _fase2_valida(edit) else None)


def _ler(p: Path) -> dict:
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _edit_data(edit: Path) -> Path:
    return Path(edit) / (_ler(Path(edit) / "state.json").get("editData") or "remotion/public/edit-data.json")


def _fase2_valida(edit: Path) -> bool:
    """A Fase 2 do agente existe e está no relógio do corte de agora (o segments.json bate): só aí
    ela vai junto para o corte novo. Fora do relógio, quem refaz é o agente (gerar.py avisa)."""
    return gr.tem_estilo(edit) and _edit_data(edit).is_file() and gr.fase2_do_corte(edit)


def _tolerante(levar, aprox=None):
    """A conta exata (com o J-cut) às vezes acha fora um item que a aproximada, a da pergunta (`aprox`),
    deixava dentro: a voz da tomada entra uns quadros antes da imagem. Nesse caso o item fica no instante
    mais perto, em vez de sumir sem a pessoa ter visto. O que a pergunta já disse que sai, sai."""
    def f(t: float):
        v = levar(t)
        if v is not None or (aprox is not None and aprox(t) is None):
            return v
        for d in (0.05, -0.05, 0.1, -0.1, 0.15, -0.15, 0.2, -0.2, 0.25, -0.25):
            v = levar(t + d)
            if v is not None:
                return v
        return None
    if hasattr(levar, "janela"):  # o que ficou de uma janela (remapear.mapa), pela mesma regra
        def janela(ini: float, fim: float):
            r = levar.janela(ini, fim)
            if r is not None or aprox is None:
                return r
            return aprox.janela(ini, fim)
        f.janela = janela
    if hasattr(levar, "perto"):
        f.perto = levar.perto
    return f


def resumo_corte(pedido: dict) -> str:
    ops = pedido.get("ops") or {}
    n = len(pedido.get("changes") or [])
    rm_ = len(pedido.get("removed") or [])
    partes = [x for x in (
        n and f"{n} tomada(s) aparada(s)", rm_ and f"{rm_} removida(s)",
        ops.get("divisoes") and f"{ops['divisoes']} divisão(ões)", ops.get("copias") and f"{ops['copias']} duplicada(s)",
        ops.get("ordemMudou") and "ordem mudou", ops.get("volume") and f"volume em {ops['volume']}",
        ops.get("velocidade") and f"velocidade em {ops['velocidade']}", ops.get("curva") and f"curva em {ops['curva']}") if x]
    return "corte: " + (", ".join(partes) or "ajustado")


def anotar_feito(edit: Path, linha: str) -> None:
    """O que a pessoa fez à mão e o editor já aplicou, para o agente saber no Pronto sem reler nada."""
    p = Path(edit) / "ajustes_feitos.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    feitos = d.get("feitos") if isinstance(d.get("feitos"), list) else []
    feitos.append({"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "oque": linha})
    _grava_json(p, {"feitos": feitos})


def _sem_andamento(etapa: str, texto: str, fracao: float, **extra) -> None:
    pass


def _levar_fase2(edit: Path, levar, origem: list[int | None], n_velhas: int, transcricao_ok: bool) -> list[dict]:
    """A Fase 2 do agente no corte novo, sem ele: o edit-data.json (blocos, efeitos, gancho, zoom de
    cada tomada) com a duração do cut.mp4 novo, a legenda (captions.json) e a transcrição do corte com
    as mesmas palavras nos lugares novos, as pilhas da legenda empilhada de novo, o segments.json pelos
    quadros e o track.json neutro com o número de quadros novo. O rastreio do rosto e os recortes da
    pessoa que mudaram de começo o Baixar refaz (gerar.py)."""
    st = _ler(edit / "state.json")
    ed_p = _edit_data(edit)
    pub = ed_p.parent
    fps, _, _, quadros = gr._sondar(edit / "cut.mp4")
    total = quadros / fps
    novo, fora = remapear.fase2(_ler(ed_p), levar, total, origem, n_velhas)
    novo["durationSec"] = round(total, 4)
    segs, _ = gr.segmentos_do_corte(edit, fps)
    lag = gr._atraso(edit / "cut.mp4", fps)
    if novo.get("videoLag") is not None:
        novo["videoLag"] = lag
    _grava_json(pub / "segments.json", {"segments": segs, "videoLag": lag})
    _grava_json(ed_p, novo)
    caps_p = edit / (st.get("captions") or "remotion/public/captions.json")
    if caps_p.is_file():
        caps = json.loads(caps_p.read_text(encoding="utf-8"))
        if isinstance(caps, list):
            _grava_json(caps_p, remapear.legenda(caps, levar)[0])
    cues = pub / "caption-cues.json"
    tr_p = edit / "transcripts" / "cut.json"
    if transcricao_ok and cues.is_file() and cues.stat().st_size > 2:
        subprocess.run([sys.executable, "-X", "utf8", str(AQUI / "caption_style.py"), "--transcript", str(tr_p),
                        "-o", str(cues)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    track = _ler(pub / "track.json")
    if track.get("neutral") and track.get("points"):
        _grava_json(pub / "track.json", {**track, "count": quadros, "points": [track["points"][0]] * quadros})
    return fora


def aplicar(edit: Path, pedido: dict, confirmado: bool = False, andamento=_sem_andamento) -> dict:
    """O Salvar das tomadas: confere (sem `confirmado`, o que fica desalinhado vira PrecisaConfirmar e
    nada muda), grava o edl.json, refaz o cut.mp4 com as opções de antes e leva camadas, efeitos e trechos
    de velocidade para o corte novo. O render falhou: o edl.json de antes volta."""
    edit = Path(edit).resolve()
    edl_p = edit / "edl.json"
    edl_velho = json.loads(edl_p.read_text(encoding="utf-8"))
    fase2 = _fase2_valida(edit)  # antes do edl.json novo: a conta é contra o corte de agora
    # a transcrição do corte vale quando é deste cut.mp4 (feita ou levada depois dele); a de um corte
    # mais velho sai, para o transcribe.py não devolver do cache as palavras de outro corte
    tr_p = edit / "transcripts" / "cut.json"
    transcricao_ok = tr_p.is_file() and tr_p.stat().st_mtime >= gr._mtime(edit / "cut.mp4")
    try:
        novo, origem = novo_edl(edl_velho, pedido)
    except cam.CamadasInvalidas as e:
        raise ErroCorte(f"o enquadre de uma tomada ficou inválido: {e}") from None
    if so_enquadre(edl_velho, novo):  # só o lugar e o tamanho da gravação: grava, sem refazer o corte
        for r, n in zip(edl_velho.get("ranges") or [], novo["ranges"]):
            if n.get("enquadre"):
                r["enquadre"] = n["enquadre"]
            else:
                r.pop("enquadre", None)
        _grava_json(edl_p, edl_velho)
        anotar_feito(edit, f"enquadre da gravação em {sum(1 for r in novo['ranges'] if r.get('enquadre'))} tomada(s)")
        res = {"rede": [], "fora": [], "voz": None}
        andamento("pronto", "Corte guardado", 1.0, **res)
        return res
    if not confirmado:
        andamento("conferindo", "Conferindo o corte", 0.02)
        avisos = conferir_projeto(edit, pedido)
        if avisos:
            raise PrecisaConfirmar(avisos)
    _grava_json(edl_p, novo)
    andamento("corte", "Refazendo o corte", 0.1)
    r = subprocess.run([sys.executable, "-X", "utf8", str(AQUI / "render.py"), str(edl_p), "-o", str(edit / "cut.mp4"),
                        "--no-subtitles", "--como-antes"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        _grava_json(edl_p, edl_velho)
        ultima = next((x for x in reversed((r.stderr + r.stdout).splitlines()) if x.strip()), "")
        raise ErroCorte(f"o corte não foi refeito; o de antes continua. {ultima.strip()}")
    andamento("conferencia", "Conferindo o vídeo novo", 0.8)
    v = subprocess.run([sys.executable, "-X", "utf8", str(AQUI / "verify_cut.py"), str(edl_p), str(edit / "cut.mp4")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    rede = [x.strip() for x in v.stdout.splitlines() if "CHECK-" in x or "LOW-LEVEL" in x]
    edl_novo = json.loads(edl_p.read_text(encoding="utf-8"))
    spans = tempo.tomadas_no_corte(edl_novo)
    total = float(edl_novo.get("total_duration_s") or sum(s["dur"] for s in spans))
    levar = _tolerante(remapear.mapa(edl_velho, edl_novo, origem), remapear.mapa(edl_velho, {"ranges": novo["ranges"]}, origem))
    fora: list[dict] = []
    if (edit / "camadas.json").exists():
        c, f = remapear.camadas(cam.load(edit / "camadas.json"), levar, total)
        cam.save(edit / "camadas.json", c)
        fora += f
    if (edit / "efeitos.json").exists():
        e, f = remapear.efeitos(ef.load(edit / "efeitos.json"), levar, [s["out"] for s in spans[1:]], total)
        ef.save(edit / "efeitos.json", e)
        fora += f
    if (edit / "velocidade.json").exists() and vel.load(edit / "velocidade.json").get("trechos"):
        vv, f = remapear.velocidade(vel.load(edit / "velocidade.json"), levar, total)
        vel.save(edit / "velocidade.json", vv)
        fora += f
    if transcricao_ok:
        _grava_json(tr_p, remapear.transcricao(json.loads(tr_p.read_text(encoding="utf-8")), levar))
    elif tr_p.is_file():
        tr_p.unlink()
    if fase2:
        andamento("fase2", "Levando a legenda e os efeitos do vídeo final", 0.9)
        try:
            fora += _levar_fase2(edit, levar, origem, len(edl_velho.get("ranges") or []), transcricao_ok)
        except gr.ErroGerar:  # os trechos não batem: o Baixar avisa e o Pronto leva para o agente
            pass
    voz = None
    try:  # a voz melhorada não vem junto num corte refeito: o Baixar a refaz (leva minutos)
        import melhorar_voz as mv  # mesma pasta deste arquivo
        if mv.situacao(edit).get("reaplicar"):
            voz = "velha"
    except Exception:  # noqa: BLE001 (sem a voz instalada, nada a refazer)
        pass
    linha = resumo_corte(pedido)
    if fora:
        linha += "; saíram do vídeo: " + ", ".join(f'{x["item"]} {x["nome"]}'.strip() for x in fora)
    anotar_feito(edit, linha)
    res = {"rede": rede, "fora": fora, "voz": voz}
    andamento("pronto", "Corte refeito", 1.0, **res)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--pedido", type=Path, required=True, help="o `edl` do Salvar do editor, em JSON")
    ap.add_argument("--confirmado", action="store_true", help="a pessoa já disse que mantém o que a conferência achou")
    ap.add_argument("--andamento", type=Path, help="arquivo de andamento que o editor lê")
    a = ap.parse_args()
    pedido = json.loads(a.pedido.read_text(encoding="utf-8"))
    escrever = trabalhos.escritor(a.andamento, "corte") if a.andamento else _sem_andamento
    try:
        res = aplicar(a.edit, pedido, a.confirmado, escrever)
    except PrecisaConfirmar as e:
        escrever("confirmar", "Antes de aplicar", 0.0, avisos=e.avisos)
        for x in e.avisos:
            print(f"  ? {x['texto']}")
        print("nada aplicado: rode de novo com --confirmado para manter assim")
        return 3
    except ErroCorte as e:
        escrever("falhou", str(e), 1.0, erro=str(e))
        print(str(e), file=sys.stderr)
        return 1
    for x in res["rede"]:
        print(f"  verify_cut: {x}")
    for x in res["fora"]:
        print(f"  saiu do vídeo: {x['item']} {x['nome']}".rstrip())
    print("corte refeito" + (" (a voz melhorada volta no Baixar)" if res["voz"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
