#!/usr/bin/env python3
"""O Baixar do editor sem o agente: monta o vídeo final com o que a pessoa fez à mão.

Hoje o agente faz isto a cada Salvar (SKILL.md, "When the user saves timeline edits"); aqui é a
mesma sequência, só quando ela pede o vídeo:

  1. a voz melhorada de volta, quando o corte foi refeito depois dela (melhorar_voz.py aplicar);
  2. a montagem na batida refaz os lugares salvos e o vídeo (montagem.py) e para aí;
  3. sem nada para desenhar por cima, só o som: mixar_final.py com a imagem do próprio corte;
  4. o projeto do Remotion: o do agente quando a Fase 2 existe (a legenda, o gancho, os efeitos que
     ele pôs), com o public/cut.mp4 de agora (efeitos_render.py), as cenas e as camadas; sem a Fase 2,
     um projeto do kit só com as camadas e os efeitos, sem legenda, gancho nem zoom;
  5. o render, o som final (mixar_final.py) e a velocidade do vídeo final (velocidade_final.py).

Com a Fase 2 feita para um corte que mudou depois, ele para: a legenda e os efeitos estão no relógio
do corte antigo, e levar tudo para o novo é trabalho do agente (o Pronto).

    uv run python -X utf8 helpers/gerar.py <edit> [--andamento <arquivo>]
    uv run python -X utf8 helpers/gerar.py <edit> --falta     # só diz o que falta e o que o Baixar entrega
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import aquecer_navegador  # mesma pasta deste arquivo
import camadas as cam  # mesma pasta deste arquivo
import camadas_edit_data  # mesma pasta deste arquivo
import cenas_edit_data  # mesma pasta deste arquivo
import efeitos as ef  # mesma pasta deste arquivo
import efeitos_render  # mesma pasta deste arquivo
import melhorar_voz as mv  # mesma pasta deste arquivo
import montagem as mt  # mesma pasta deste arquivo
import pacotes as pk  # mesma pasta deste arquivo
import pendente as pend  # mesma pasta deste arquivo
import tempo  # mesma pasta deste arquivo
import trabalhos  # mesma pasta deste arquivo
import velocidade as vel  # mesma pasta deste arquivo

AQUI = Path(__file__).resolve().parent
FINAL, ENTREGA = "final.mp4", "final-entrega.mp4"
FOLGA_QUADROS = 1.5  # a Fase 2 é deste corte quando cada tomada bate com o segments.json até aqui
TIMEOUT_MS = 180000  # o <Video> do modelo estoura os 28 s padrão com a máquina ocupada (render 4K)
_PROGRESSO = re.compile(r"(Rendered|Encoded) (\d+)/(\d+)")


class ErroGerar(RuntimeError):
    """O vídeo final não saiu, por um motivo que a pessoa entende."""


def _sem_andamento(etapa: str, texto: str, fracao: float, **extra) -> None:
    pass


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _ler(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _video(edit: Path) -> Path:
    return Path(edit) / (_ler(Path(edit) / "state.json").get("video") or "cut.mp4")


def tem_estilo(edit: Path) -> bool:
    """A Fase 2 foi montada pelo agente (o Estilo escolhido): legenda, gancho, blocos."""
    st = _ler(Path(edit) / "state.json")
    return int(st.get("phase") or 1) >= 2 and bool(st.get("style"))


def eh_montagem(edit: Path) -> bool:
    return "montagem" in _ler(Path(edit) / "edl.json")


def precisa_remotion(edit: Path) -> bool:
    """Algo a desenhar por cima do corte: a Fase 2, texto ou imagem das camadas, filtro ou transição."""
    edit = Path(edit)
    c = cam.load(edit / "camadas.json")
    return tem_estilo(edit) or bool(cam.textos(c) or cam.aparecem(c) or ef.load(edit / "efeitos.json")["itens"])


def precisa_som(edit: Path) -> bool:
    """O som do vídeo final não é o do corte: áudio nas camadas, ou o som do vídeo desligado."""
    c = cam.load(Path(edit) / "camadas.json")
    return bool(cam.tocam(c)) or c["video"]["mudo"]


def _trechos(edit: Path) -> list:
    return vel.load(Path(edit) / "velocidade.json").get("trechos") or []


def _montagem_salva(edit: Path) -> dict:
    """Os lugares e o formato que o Salvar guardou para a montagem (pendente.json)."""
    m = pend.ler(edit).get("montagem")
    return {k: m[k] for k in ("lugares", "formato") if m.get(k)} if isinstance(m, dict) else {}


def _voz_pedida(edit: Path) -> dict | None:
    """A escolha do Melhorar voz salva no editor e ainda não aplicada: {voz, fundo} ou {desligar}."""
    v = pend.ler(edit).get("melhorar")
    return v if isinstance(v, dict) and v else None


def _voz_velha(edit: Path) -> bool:
    """A voz melhorada foi aplicada um dia e o cut.mp4 de agora (refeito depois) não a tem. Sem nunca
    ter aplicado, nem mede o som do corte."""
    e = mv.ler_estado(edit)
    if not e or not e.get("aplicado"):
        return False
    return bool(mv.situacao(edit).get("reaplicar"))


def o_que_falta(edit: Path) -> list[str]:
    """Os passos que o Baixar tem de rodar antes de entregar: voz, remotion, final, entrega ou montagem.
    Vazio = o que está no disco já é o vídeo de agora."""
    edit = Path(edit)
    final = edit / FINAL
    if eh_montagem(edit):
        salvo = _montagem_salva(edit)
        entradas = [edit / "edl.json", _video(edit), edit / "camadas.json", edit / "efeitos.json"]
        velho = not final.exists() or max(map(_mtime, entradas)) > _mtime(final)
        return ["montagem"] if salvo or velho else []
    falta = ["voz"] if _voz_pedida(edit) or _voz_velha(edit) else []
    if precisa_remotion(edit):
        pub = edit / "remotion" / "public"
        entradas = [_video(edit), edit / "camadas.json", edit / "efeitos.json",
                    pub / "edit-data.json", pub / "captions.json"]
        if not final.exists() or max(map(_mtime, entradas)) > _mtime(final) or falta:
            falta += ["remotion", "final"]
    elif precisa_som(edit):
        entradas = [_video(edit), edit / "camadas.json"]
        if not final.exists() or max(map(_mtime, entradas)) > _mtime(final) or falta:
            falta.append("final")
    else:
        return falta
    if _trechos(edit) and ("final" in falta or _mtime(edit / ENTREGA) < max(_mtime(edit / "velocidade.json"),
                                                                                _mtime(final))):
        falta.append("entrega")
    return falta


def entrega(edit: Path) -> str:
    """O arquivo que o Baixar entrega quando nada falta (caminho dentro do projeto)."""
    edit = Path(edit)
    if not (eh_montagem(edit) or precisa_remotion(edit) or precisa_som(edit)):
        return _ler(edit / "state.json").get("video") or "cut.mp4"
    if _trechos(edit) and (edit / ENTREGA).is_file():
        return ENTREGA
    return FINAL


def fase2_do_corte(edit: Path) -> bool:
    """O segments.json da Fase 2 descreve o corte de agora: uma entrada por tomada, cada uma com a
    duração da imagem dela no cut.mp4 (até 1,5 quadro de diferença)."""
    edit = Path(edit)
    segs = _ler(edit / "remotion" / "public" / "segments.json").get("segments")
    if not isinstance(segs, list):
        return False
    tomadas = tempo.tomadas_no_corte(_ler(edit / "edl.json"))
    fps = float(_ler(edit / "state.json").get("fps") or 30)
    if not tomadas or len(segs) != len(tomadas):
        return False
    try:
        return all(abs(float(s["dur"]) - t["dur"]) <= FOLGA_QUADROS / fps for s, t in zip(segs, tomadas))
    except (KeyError, TypeError, ValueError):
        return False


# ---------- os passos ----------

def _passo(args: list[str]) -> int:
    """Um helper do kit com o mesmo Python; a saída dele vai para o registro do trabalho."""
    return subprocess.run([sys.executable, "-X", "utf8", *map(str, args)]).returncode


def _sondar(video: Path) -> tuple[float, int, int, int]:
    """fps, largura, altura e quadros do vídeo."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=r_frame_rate,width,height,nb_frames", "-of", "json", str(video)],
                       capture_output=True, text=True)
    s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    num, _, den = str(s.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1)
    return round(fps, 3), int(s.get("width") or 0), int(s.get("height") or 0), int(s.get("nb_frames") or 0)


def _clipes(edit: Path) -> list[Path]:
    """Os trechos de imagem do último render do corte, na ordem (seg_NN, com NN podendo passar de 99)."""
    pasta = edit / "clips_graded"
    fs = list(pasta.glob("seg_*_v.mp4")) or list(pasta.glob("seg_*.mp4"))
    return sorted(fs, key=lambda f: int(re.match(r"seg_(\d+)", f.name).group(1)))


def segmentos_do_corte(edit: Path, fps: float) -> tuple[list[dict], int]:
    """O segments.json pelos quadros de cada trecho gravado (references/shortform.md), nunca pela soma
    dos segundos do EDL. Confere o número de trechos e a soma contra o cut.mp4."""
    edit = Path(edit)
    clipes = _clipes(edit)
    n_tomadas = len(_ler(edit / "edl.json").get("ranges") or [])
    total = _sondar(_video(edit))[3]
    quadros = [mt._quadros(c) for c in clipes]
    if len(clipes) != n_tomadas or sum(quadros) != total or not total:
        raise ErroGerar("os trechos do corte não batem com o cut.mp4: salve as tomadas de novo para refazer o corte")
    segs, q0 = [], 0
    for q in quadros:
        segs.append({"start": round(q0 / fps, 4), "dur": round(q / fps, 4)})
        q0 += q
    return segs, total


def preparar_remotion_fala(edit: Path) -> Path:
    """O projeto do Remotion de um vídeo falado sem a Fase 2: o do kit, com o cut.mp4 de agora (e os
    filtros e transições desenhados nele) e só as camadas por cima."""
    edit = Path(edit).resolve()
    rem = mt.projeto_remotion(edit)
    efeitos_render.aplicar(edit, rem)
    fps, largura, altura, _ = _sondar(rem / "public" / "cut.mp4")
    segs, total = segmentos_do_corte(edit, fps)
    lag = _atraso(rem / "public" / "cut.mp4", fps)
    ed_p = mt.dados_sem_fase2(edit, rem, fps, largura, altura, segs, lag, total)
    ed = _ler(ed_p)
    ed["_gerar"] = "editor"  # feito pelo Baixar, não pelo agente: a Fase 2 pode montar por cima
    mt._grava_json(ed_p, ed)
    return rem


def _atraso(video: Path, fps: float) -> int:
    """Quadros que a imagem do Remotion fica atrás do vídeo: o começo dele arredondado para cima."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=start_time",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        inicio = float(r.stdout.strip() or 0)
    except ValueError:
        inicio = 0.0
    return max(0, math.ceil(inicio * fps - 1e-3))


def preparar_remotion_fase2(edit: Path) -> Path:
    """O projeto do agente como ele está, com o cut.mp4 de agora e o que a pessoa mexeu por cima."""
    edit = Path(edit).resolve()
    rem = edit / "remotion"
    pub = rem / "public"
    # o public/cut.mp4 só é refeito quando o corte ou os efeitos mudaram: desenhar os filtros leva minutos
    if _mtime(pub / "cut.mp4") < max(_mtime(_video(edit)), _mtime(edit / "efeitos.json")):
        efeitos_render.aplicar(edit, rem)
    r = cenas_edit_data.aplicar(edit)
    if r["template"]:
        raise ErroGerar("o projeto do vídeo final é de um kit anterior e não desenha os efeitos de agora: aperte "
                        "Pronto para o Claude atualizar")
    if r["erros"]:
        raise ErroGerar("um efeito do vídeo final ficou inválido: aperte Pronto para o Claude corrigir")
    camadas_edit_data.aplicar(edit)
    return rem


def renderizar(rem: Path, andamento, de: float, ate: float) -> Path:
    """O render do Remotion, com o andamento pelas linhas "Rendered N/M" e "Encoded N/M" da saída."""
    cli = rem / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    saida = rem / "out" / "render.mp4"
    cmd = ["node", str(cli), "render", "Reels", "out/render.mp4", f"--timeout={TIMEOUT_MS}"]
    p = subprocess.Popen(cmd, cwd=rem, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    resto = b""
    while True:
        bloco = p.stdout.read1(4096) if hasattr(p.stdout, "read1") else p.stdout.read(4096)
        if not bloco:
            break
        sys.stdout.buffer.write(bloco)
        sys.stdout.flush()
        linhas = re.split(rb"[\r\n]", resto + bloco)
        resto = linhas.pop()
        for ln in linhas:
            m = _PROGRESSO.search(ln.decode("utf-8", "replace"))
            if m:
                feito, total = int(m.group(2)), max(1, int(m.group(3)))
                # desenhar os quadros é quase tudo; juntar no mp4 ("Encoded") é o último pedaço
                parte = 0.85 * feito / total if m.group(1) == "Rendered" else 0.85 + 0.15 * feito / total
                andamento("desenhando", "Desenhando o vídeo", de + (ate - de) * parte, quadro=feito, quadros=total)
    if p.wait() != 0 or not saida.is_file():
        raise ErroGerar("o render do Remotion falhou (a saída dele está no registro do trabalho)")
    return saida


def _gravar_state(edit: Path, **campos) -> None:
    p = Path(edit) / "state.json"
    st = _ler(p)
    if all(st.get(k) == v for k, v in campos.items()):
        return
    st.update(campos)
    mt._grava_json(p, st)


def gerar(edit: Path, andamento=_sem_andamento) -> dict:
    """Roda o que o_que_falta() pede e devolve {"falta": [...], "entrega": <arquivo>}."""
    edit = Path(edit).resolve()
    falta = o_que_falta(edit)
    if not falta:
        andamento("pronto", "Vídeo pronto", 1.0, entrega=entrega(edit))
        return {"falta": [], "entrega": entrega(edit)}
    if "remotion" in falta and tem_estilo(edit) and not fase2_do_corte(edit):
        raise ErroGerar("o corte mudou depois da legenda e dos efeitos do vídeo final: aperte Pronto para o "
                        "Claude refazer essa parte")
    try:
        if "montagem" in falta:
            andamento("montagem", "Montando o vídeo", 0.05)
            salvo = _montagem_salva(edit)
            if salvo:
                mt.aplicar(edit, list(salvo.get("lugares") or []), formato=salvo.get("formato"))
                pend.tirar(edit, "montagem", "lugares", "formato")  # entrou: sai do que o editor guardou
            else:
                mt.renderizar(edit)
            andamento("conferindo", "Conferindo as trocas na batida", 0.9)
            mt.conferir_o_render(edit)
        if "voz" in falta:
            andamento("voz", "Pondo a voz melhorada de volta", 0.05)
            pedida = _voz_pedida(edit)
            if pedida and pedida.get("desligar"):
                cmd = [AQUI / "melhorar_voz.py", "restaurar", edit]
            elif pedida:
                cmd = [AQUI / "melhorar_voz.py", "aplicar", edit, "--voz", pedida["voz"], "--fundo", pedida["fundo"]]
            else:  # o corte foi refeito depois: a última escolha
                cmd = [AQUI / "melhorar_voz.py", "aplicar", edit]
            if _passo(cmd) != 0:
                raise ErroGerar("a voz melhorada não voltou ao corte (a saída está no registro do trabalho)")
            pend.tirar(edit, "melhorar")
        if "remotion" in falta:
            v = aquecer_navegador.macos_antigo()
            if v:
                raise ErroGerar(f"o vídeo final passa pelo Remotion, que precisa do macOS 13 ou mais novo, e este "
                                f"Mac está no {v}")
            andamento("preparando", "Preparando o vídeo", 0.15)
            rem = preparar_remotion_fase2(edit) if tem_estilo(edit) else preparar_remotion_fala(edit)
            render = renderizar(rem, andamento, 0.25, 0.85)
        elif "final" in falta:
            render = _video(edit)
        if "final" in falta:
            andamento("som", "Montando o som", 0.88)
            imagem = [] if "remotion" in falta else ["--imagem", "corte"]
            if _passo([AQUI / "mixar_final.py", edit, "--render", render, *imagem]) != 0:
                raise ErroGerar("o som do vídeo final não foi montado (a saída está no registro do trabalho)")
            _gravar_state(edit, finalVideo=FINAL)
        if "entrega" in falta:
            andamento("velocidade", "Aplicando a velocidade", 0.95)
            cod = _passo([AQUI / "velocidade_final.py", edit])
            if cod == 2:
                raise ErroGerar("a velocidade foi marcada num vídeo final de outra duração: marque os trechos de "
                                "novo na vista Final")
            if cod != 0:
                raise ErroGerar("a velocidade não foi aplicada (a saída está no registro do trabalho)")
    except (mt.ErroMontagem, RuntimeError, pk.PacoteErro, ef.EfeitosInvalidos, cam.CamadasInvalidas) as e:
        if isinstance(e, ErroGerar):
            raise
        raise ErroGerar(str(e)) from e
    andamento("pronto", "Vídeo pronto", 1.0, entrega=entrega(edit))
    return {"falta": falta, "entrega": entrega(edit)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--andamento", type=Path, help="arquivo de andamento que o editor lê")
    ap.add_argument("--falta", action="store_true", help="só diz o que falta e o que o Baixar entrega")
    a = ap.parse_args()
    edit = a.edit.resolve()
    if a.falta:
        print(json.dumps({"falta": o_que_falta(edit), "entrega": entrega(edit)}, ensure_ascii=False))
        return 0
    escrever = trabalhos.escritor(a.andamento, "gerar") if a.andamento else _sem_andamento
    try:
        r = gerar(edit, escrever)
    except ErroGerar as e:
        escrever("falhou", str(e), 1.0, erro=str(e))
        print(str(e), file=sys.stderr)
        return 1
    print(("nada a refazer" if not r["falta"] else "feito: " + ", ".join(r["falta"])) + f" · entrega {r['entrega']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
