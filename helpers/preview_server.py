"""CutMind preview server — serves the standard editing interface + session media.

The interface app (assets/preview/) is IMMUTABLE and lives in the skill repo;
per-session it is fed by data only:
  - <edit>/state.json          written by the skill (phase, files, message)
  - <edit>/edl.json            the cut (segments shown/trimmed on the timeline)
  - <edit>/cut.mp4             current render (played + scrubbed)
  - the Salvar is applied HERE, without the agent: takes → aplicar_corte.py (a job),
    layers/effects/speed → their files, Phase 2 data → edit-data.json
    (editdata_aplicar.py); markers and requests → <edit>/pedidos.json; montage and
    Melhorar voz → <edit>/.cutmind/pendente.json, for the Baixar (gerar.py)
  - <edit>/pronto.json         WRITTEN BY THE UI when the user presses Pronto: the
                               requests plus what the editor already applied; the
                               watcher (watch_edits.py) wakes the agent once.
                               A preview_edits.json is from an older editor.
  - <edit>/preview_style.json  WRITTEN BY THE UI at the Fase 1 → Fase 2 gate:
                               editing style, caption style, edit elements.

Routes:
  /, /celular           the editor (assets/preview/celular.html): one page for the
                        computer and the phone, laid out by the screen width
  /c?t=<código>         entrada do celular pelo link/QR: grava o código num
                        cookie e manda para /celular
  /assets/<file>        app files (css/js/logo)
  /efeitos/<file>       o motor de efeitos (assets/efeitos/motor.js + Three.js):
                        o mesmo arquivo da prévia e do vídeo final
  /media/<path>         files under --root (the edit dir) — Range supported
  /gen/waveform.json    min/max audio peaks of cut.mp4 (auto-(re)generated)
  /gen/thumbs/<n>.jpg   timeline filmstrip thumbs (auto-generated, 1 per 2s)
  /gen/frame?src=&t=    um quadro do vídeo de ORIGEM (edl.json "sources") no
                        tempo t — a prévia da alça ao aparar
  /gen/frases?estilo=stacked
                        as frases da legenda Empilhado, pelo próprio diretor
                        (caption_style.py) sobre transcripts/cut.json — o modo
                        "Posição das frases" mostra as mesmas frases do render
  /gen/recorte?t=       a pessoa no quadro t do corte, recortada (PNG com alfa,
                        540x960): os cartões da ferramenta Fundo
  /api/state    GET     state.json + mtimes (UI polls this to hot-reload)
  /api/celular  GET     só no computador: links + QR code para abrir no celular
  /api/midia    GET     imagens e áudios do projeto (<edit>/midia/)
  /api/save     POST    applied by the server (see above), or
                        <edit>/preview_style.json when body.type=="style-setup";
                        com `camadas`, grava também <edit>/camadas.json (camadas.py);
                        com `efeitos`, <edit>/efeitos.json (efeitos.py); com
                        `velocidade`, <edit>/velocidade.json (velocidade.py); com
                        `melhorar`, a Voz e o Fundo escolhidos (o Baixar aplica);
                        os efeitos (`editData.cenas`) conferidos: o editor só cria
                        o Fundo (conferir_cenas)
  /api/upload   POST    ?name=<arquivo>, corpo = o arquivo. Vídeo → pasta dos
                        vídeos (pai do <edit>) + aviso em <edit>/preview_upload.json;
                        imagem e áudio → <edit>/midia/ (camadas do projeto);
                        com &para=montagem, a foto ou o vídeo de um lugar → midia/, sem aviso
  /api/pacotes  GET     ?tipo=trilha: a biblioteca do kit (pacotes.py), com o que já
                        está baixado neste computador e os favoritos
  /gen/pacote-previa?id=  a prévia de um pacote (baixa na primeira vez)
  /gen/pacote/<id>/<arq>  um arquivo de filtro/transição, da pasta aberta no
                        cache (baixa e abre o zip na primeira vez)
  /api/pacotes/usar      POST {id}: baixa o pacote e copia para <edit>/midia/
  /api/pacotes/favorito  POST {id, on}: favorito fica no cache, mesmo cheio
  /api/sfx      GET     os efeitos sonoros do kit (efeitos_sonoros.py, assets/sfx/catalogo.json)
  /gen/sfx?id=          o arquivo de um efeito sonoro, para ouvir
  /api/sfx/usar POST {id}: copia o efeito para <edit>/midia/sfx-<id>.mp3 (vira camada de áudio)
  /gen/voz-previa?efeito=&inicio=&duracao=  o trecho do corte com um efeito de voz, para ouvir antes
                        de usar (voz_efeitos.py; guardado em <edit>/.voz/)
  /api/melhorar          GET  Melhorar voz (melhorar_voz.py): se o preparo vale para o corte
                         de agora, a escolha, o que está aplicado, o que foi salvo e ainda
                         não aplicado (`pendente`) e as faixas da prévia (servidas em /media/)
  /api/melhorar/andamento GET  só o andamento do preparo (leve: o editor pergunta a cada segundo)
  /api/melhorar/preparar POST  começa o preparo num processo à parte (~1 s por s de áudio,
                         até ~4 GB de memória; na 1ª vez baixa os modelos)
  /api/batida?arquivo=midia/x.mp3  GET  a grade de batida de uma música do projeto (batida.py),
                         para as marcas e o ímã da linha do tempo: `pronta` com as batidas, ou
                         `calculando` (a análise roda num processo à parte; na 1ª vez baixa o modelo)
  /api/montagem/midias   GET  numa montagem na batida (montagem.py): o que o Trocar oferece para um
                         lugar (as mídias da montagem e as fotos e vídeos de midia/), com tipo e duração;
                         na Nova montagem ainda sem edl.json, só as de midia/ (o painel Modelos de montagem)
  /gen/montagem-quadro?midia=&t=&h=  um quadro de uma dessas mídias (Trocar e a tira do Trecho)
  /gen/montagem-video?midia=          o clipe original de um lugar, para o Trecho tocar a janela
  /api/montagens         GET  os modelos de montagem (montagens.py: os da pessoa e os do kit), com o
                         resumo do cartão (o ritmo em batidas, os textos, o drop)
  /api/montagens         POST {nome}: guarda a montagem aberta como modelo (montagem.py capturar)
  /api/montagens/apagar  POST {id}: apaga um modelo da pessoa
  /api/mural             GET  (?antes=) uma página dos modelos do mural da comunidade (mural.py, no
                         endereço de CUTMIND_MURAL); `mural` no /api/montagens diz se ele está ligado
  /api/mural/pegar       POST {codigo}: traz um modelo do mural para os da pessoa
  /api/mural/compartilhar?id=  GET  redireciona para a página de publicar do mural com o modelo
  /api/save com `montagem.usar` = {modelo, musica, midias}: o Usar do painel (a montagem inteira);
                         conferido em conferir_usar, e o agente roda montagem.py montar. Até ele
                         montar, /api/state traz o pedido em `montagemNova`
  /api/projetos/novo     POST {nome, tipo?}: com tipo "montagem", o projeto nasce como montagem

Quem entra: por padrão o servidor ouve só em 127.0.0.1 e atende só este
computador (e o celular ligado por `adb reverse`, que chega como 127.0.0.1).
Com --host 0.0.0.0 ele abre para a rede, e todo pedido que não venha do
próprio computador precisa do código (cookie gravado pela entrada /c). Em
qualquer caso o cabeçalho Host tem de ser IP, localhost ou um nome liberado
com --allow-host: é o que barra um site de fora usando DNS rebinding.

Usage:
    uv run helpers/preview_server.py --root <videos_dir>/edit [--port 4820]
        [--host 0.0.0.0] [--allow-host .ts.net] [--max-upload-gb 8]
"""
from __future__ import annotations

import argparse
import array
import hmac
import io
import ipaddress
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


def _texto_do_erro(erro: BaseException | None) -> str:
    partes = []
    while erro is not None and len(partes) < 5:
        partes.append(str(erro))
        erro = erro.__cause__ or erro.__context__
    return " ".join(partes)


def _importar_dlls() -> None:
    import numpy  # noqa: F401  (as únicas bibliotecas do .venv com DLL que o servidor carrega: medido)
    import PIL.Image  # noqa: F401


def esperar_dlls(importar=_importar_dlls, prazo: float = 20.0, pausa: float = 0.5) -> int:
    """Logo depois de instalar ou atualizar, o antivírus ainda examina as DLLs novas e o Windows recusa
    carregá-las ("o arquivo já está sendo usado por outro processo"); passa em segundos. Tenta de novo a cada
    0,5 s por até 20 s, só nesse erro (o mesmo conserto do Papory 0.1.9). Devolve quantas vezes esperou."""
    inicio, esperas = time.monotonic(), 0
    while True:
        try:
            importar()
            return esperas
        except ImportError as e:
            if "DLL load failed" not in _texto_do_erro(e) or time.monotonic() - inicio > prazo:
                raise
            esperas += 1
            time.sleep(pausa)


ESPERAS_DLL = esperar_dlls()

import atualizar as atu  # mesma pasta deste arquivo
import tunel as tn  # mesma pasta deste arquivo
import camadas as cam  # mesma pasta deste arquivo
import cenas as cn  # mesma pasta deste arquivo
import efeitos as ef  # mesma pasta deste arquivo
import velocidade as vel  # mesma pasta deste arquivo
import pacotes as pk  # mesma pasta deste arquivo
import projetos as pj  # mesma pasta deste arquivo
import modelos as md  # mesma pasta deste arquivo
import melhorar_voz as mv  # mesma pasta deste arquivo
import batida as bt  # mesma pasta deste arquivo
import montagem as mt  # mesma pasta deste arquivo
import idioma as idm  # mesma pasta deste arquivo
import montagens as mg  # mesma pasta deste arquivo
import mural as mu  # mesma pasta deste arquivo
import aplicar_corte as ac  # mesma pasta deste arquivo
import trabalhos as tb  # mesma pasta deste arquivo
import gerar as gr  # mesma pasta deste arquivo
import editdata_aplicar as eda  # mesma pasta deste arquivo
import efeitos_sonoros as es  # mesma pasta deste arquivo
import voz_efeitos as vze  # mesma pasta deste arquivo
import pendente as pend  # mesma pasta deste arquivo

APP_DIR = Path(__file__).resolve().parent.parent / "assets" / "preview"
EFEITOS_DIR = APP_DIR.parent / "efeitos"
PEAKS_PER_SEC = 40
THUMB_EVERY_S = 2.0
THUMB_HEIGHT = 90

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".weba": "audio/webm",
    ".srt": "text/plain; charset=utf-8",
    ".frag": "text/plain; charset=utf-8",
    ".vert": "text/plain; charset=utf-8",
}

# ---- acesso pela rede (celular) ----
LOCAL_CLIENTS = {"127.0.0.1", "::1"}
TOKEN_COOKIE = "cutmind_t"
TOKEN_MAX_AGE = 30 * 24 * 3600  # 30 dias: o atalho na tela inicial continua entrando
MAX_JSON_BYTES = 2_000_000
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp", ".mts", ".m2ts"}
# imagem e áudio são camadas do projeto: vão para <edit>/midia/, não para a pasta dos vídeos
UPLOAD_EXTS = VIDEO_EXTS | cam.IMAGE_EXTS | cam.AUDIO_EXTS
DISK_MARGIN = 512 * 1024 * 1024  # nunca encher o disco: sobra meio GB
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                    *(f"LPT{i}" for i in range(1, 10))}

_thumb_lock = threading.Lock()
_thumb_state: dict[str, float] = {}  # video path -> mtime generated
_upload_lock = threading.Lock()
# os envios em pedaços abertos: id → {part, final, total, recebido, ...}; largado há mais de 1 h é apagado
_ENVIOS: dict[str, dict] = {}
PEDACO_MAX = 32 * 1024 * 1024
ENVIO_LARGADO_S = 3600


def _limpar_envios_largados(agora: float | None = None, pastas: tuple[Path, ...] = ()) -> None:
    """Apaga o envio parado há mais de 1 h: o da memória e, nas `pastas`, o .parte que ficou no disco de um
    servidor que fechou no meio (a lista de envios só vive na memória)."""
    agora = time.time() if agora is None else agora
    with _upload_lock:
        velhos = [k for k, e in _ENVIOS.items() if agora - e["quando"] > ENVIO_LARGADO_S and not e["trava"].locked()]
        for k in velhos:
            _ENVIOS.pop(k)["part"].unlink(missing_ok=True)
        abertos = {e["part"] for e in _ENVIOS.values()}
        for pasta in pastas:
            try:
                partes = list(Path(pasta).glob(".*.parte"))
            except OSError:
                continue
            for parte in partes:
                try:
                    if parte not in abertos and agora - parte.stat().st_mtime > ENVIO_LARGADO_S:
                        parte.unlink()
                except OSError:
                    pass


_codigos_tunel: dict[Path, tuple[int, str]] = {}


def _codigo_do_tunel(arq: Path | None) -> str | None:
    """O código da porta do túnel, lido do arquivo do tunel.py (um túnel novo ganha código novo, e o
    servidor acompanha sem reiniciar). Guardado pela data do arquivo: o celular pergunta a cada segundo."""
    if arq is None:
        return None
    try:
        quando = arq.stat().st_mtime_ns
        guardado = _codigos_tunel.get(arq)
        if guardado and guardado[0] == quando:
            return guardado[1]
        codigo = arq.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if len(codigo) < 20:
        return None
    _codigos_tunel[arq] = (quando, codigo)
    return codigo
_frame_slots = threading.BoundedSemaphore(2)  # ffmpeg de quadro avulso ao mesmo tempo
_quadros_guardados: dict[tuple, bytes] = {}  # miniaturas da montagem já tiradas (o mais velho sai primeiro)
_quadros_lock = threading.Lock()
QUADROS_GUARDADOS = 400  # ~15 KB cada
_troca_lock = threading.Lock()  # abrir outro projeto troca a pasta do servidor inteiro
_recorte_lock = threading.Lock()  # um recorte da pessoa por vez: o modelo usa todos os núcleos
RECORTE_CACHE = 30  # recortes guardados em .preview_cache/recorte (um por quadro pedido)
_voz_lock = threading.Lock()
_voz_jobs: dict[str, subprocess.Popen] = {}  # pasta edit → o processo do preparo da voz
_batida_lock = threading.Lock()
_batida_jobs: dict[str, subprocess.Popen] = {}  # música → o processo que analisa a batida dela
_sha_musicas: dict[tuple[str, int, int], str] = {}


TRABALHO_RECENTE_S = 60  # o fim de um trabalho aparece no editor por um minuto; depois, sai


def trabalho_recente(edit: Path) -> dict | None:
    """O trabalho do editor que roda agora, ou o que terminou há pouco (o editor mostra o fim dele: o
    "corte refeito", ou o erro). O editor não recarrega o corte enquanto um roda: o edl.json novo chega
    antes do cut.mp4 novo."""
    a = tb.andamento(edit)
    if not a:
        return None
    if a.get("vivo"):
        return a
    try:
        idade = time.time() - (tb.pasta(edit) / "andamento.json").stat().st_mtime
    except OSError:
        return None
    return a if idade < TRABALHO_RECENTE_S else None


AGENTE_PARADO_S = 30 * 60  # "trabalhando" há mais que isso: o agente caiu, a trava não vale


def agente_trabalhando(root: Path) -> bool:
    """O agente gravou `"agente": {"trabalhando": true, "desde": <segundos>}` no state.json (agente.py) ao
    começar a mexer no projeto, a pedido de um Pronto ou da conversa, e tira ao terminar. Enquanto isso, o
    corte e o Baixar esperam: os dois mexeriam nos mesmos arquivos que ele."""
    try:
        st = json.loads((Path(root) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    a = st.get("agente") if isinstance(st, dict) else None
    if not isinstance(a, dict) or not a.get("trabalhando"):
        return False
    try:
        return time.time() - float(a.get("desde") or 0) < AGENTE_PARADO_S
    except (TypeError, ValueError):
        return False


def comando_montar(edit: Path) -> list[str]:
    """A montagem nova pedida no editor (o Usar do painel Modelos de montagem), num processo à parte.
    Os testes trocam por um falso."""
    return [sys.executable, "-X", "utf8", str(Path(__file__).resolve().parent / "montagem.py"), "montar", str(edit)]


def comando_gerar(edit: Path, andamento: Path) -> list[str]:
    """O Baixar com algo por refazer monta o vídeo final num processo à parte (gerar.py), sem o agente.
    Os testes trocam por um falso."""
    return [sys.executable, "-X", "utf8", str(Path(__file__).resolve().parent / "gerar.py"), str(edit),
            "--andamento", str(andamento)]


SKILL = Path(__file__).resolve().parents[1]
# o que a procura achou (a linha à parte de vigiar_atualizacao) e o clique que espera um trabalho acabar
ATUALIZACAO: dict = {"resultado": None, "pedido": False}


def copia_de_desenvolvimento() -> bool:
    """Rodando de um clone git: quem desenvolve atualiza com git, não pela barra."""
    return (SKILL / ".git").exists()


def comando_atualizar(andamento: Path, servidor: Path) -> list[str]:
    """A atualização num processo à parte e solto (atualizar.py), porque ela pode precisar fechar este
    servidor e ligá-lo de novo. Os testes trocam por um falso."""
    return [sys.executable, "-X", "utf8", str(Path(__file__).resolve().parent / "atualizar.py"), "aplicar",
            "--andamento", str(andamento), "--servidor", str(servidor)]


def lancar_solto(cmd: list[str], log: Path) -> subprocess.Popen:
    """Como o start_preview.py: sem janela no Windows e fora do grupo deste processo, para sobreviver a ele."""
    log.parent.mkdir(parents=True, exist_ok=True)
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    with log.open("ab") as saida:
        return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT, close_fds=True,
                                cwd=str(Path(__file__).resolve().parent), creationflags=flags,
                                start_new_session=os.name != "nt")


def linha_de_comando(root: Path) -> dict:
    """Como religar este servidor depois de atualizar: os mesmos argumentos, com o projeto aberto AGORA (a
    tela Projetos troca o --root com o servidor ligado)."""
    argv = list(sys.argv)
    if "--root" in argv:
        argv[argv.index("--root") + 1] = str(root)
    else:
        argv += ["--root", str(root)]
    return {"argv": argv, "python": sys.executable, "pid": os.getpid(), "script": str(Path(__file__).resolve())}


def comecar_atualizacao(srv, root: Path, r: dict) -> None:
    """Lança o atualizador solto; com reinício, este servidor desliga 1 s depois (o atualizador espera ele
    sair, instala e liga de novo)."""
    pasta = atu.casa() / "atualizacao"
    servidor = pasta / "servidor.json"
    atu._gravar_json(servidor, linha_de_comando(root))
    (pasta / "andamento.json").unlink(missing_ok=True)
    lancar_solto(comando_atualizar(pasta / "andamento.json", servidor), pasta / "atualizar.log")
    ATUALIZACAO["pedido"] = False
    if r.get("reiniciar"):
        threading.Timer(1.0, srv.shutdown).start()


def _esperando(root: Path) -> str | None:
    if tb.vivo(root):
        return "trabalho"
    return "agente" if agente_trabalhando(root) else None


def sistema() -> str:
    """Só o nome e a versão do sistema, para o formulário de erro do GitHub: nunca nome de máquina ou de pessoa."""
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]}".strip()
    if os.name == "nt":
        return "Windows 11" if sys.getwindowsversion().build >= 22000 else f"Windows {platform.release()}"
    return platform.system()


def resultado_atual() -> dict | None:
    """O que a procura achou, conferido contra a versão instalada AGORA: depois de uma atualização sem
    reinício o servidor é o mesmo, e a versão que ele oferecia já está aqui."""
    r = ATUALIZACAO["resultado"]
    if r and r.get("nova"):
        local = (atu.vs.ler(SKILL) or {}).get("versao")
        if local and atu.vs.numero(local) >= atu.vs.numero(r.get("versao")):
            return {**r, "nova": False, "atual": local}
    return r


def vigiar_atualizacao(srv, handler, pausa: float = 2.0) -> None:
    """A procura da versão nova numa linha à parte (a página nunca espera a rede): ao subir e a cada 6 h,
    como o Papory; e o clique que esperava um trabalho acabar começa quando o projeto libera. Sai quando o
    servidor fecha."""
    proxima = 0.0
    while srv.socket.fileno() >= 0:
        if time.time() >= proxima:
            try:
                ATUALIZACAO["resultado"] = atu.procurar()
            except Exception as e:  # noqa: BLE001 (a procura nunca derruba o editor)
                print(f"atualização: não deu para procurar ({e})", file=sys.stderr, flush=True)
            proxima = time.time() + atu.CACHE_S
        r = resultado_atual() or {}
        if ATUALIZACAO["pedido"] and r.get("nova") and _esperando(handler.root) is None:
            comecar_atualizacao(srv, handler.root, r)
        time.sleep(pausa)


def comando_corte(edit: Path, pedido: Path, andamento: Path) -> list[str]:
    """O Salvar que mexe nas tomadas refaz o corte num processo à parte (aplicar_corte.py), sem o agente.
    A conferência já foi feita aqui (e a pessoa respondeu), por isso o --confirmado. Os testes trocam
    por um falso."""
    return [sys.executable, "-X", "utf8", str(Path(__file__).resolve().parent / "aplicar_corte.py"), str(edit),
            "--pedido", str(pedido), "--confirmado", "--andamento", str(andamento)]


def comando_preparo(edit: Path) -> list[str]:
    """O preparo da voz roda num processo à parte: é pesado (~1 s por s de áudio e até ~4 GB de
    memória) e a memória volta quando ele termina. Os testes trocam por um falso."""
    return [sys.executable, "-X", "utf8", str(Path(__file__).resolve().parent / "melhorar_voz.py"),
            "preparar", str(edit)]


def iniciar_preparo(edit: Path) -> bool:
    """False quando já tem um preparo rodando para esta pasta (deste servidor ou do agente)."""
    edit = edit.resolve()
    with _voz_lock:
        p = _voz_jobs.get(str(edit))
        if p is not None and p.poll() is None:
            return False
        a = mv.andamento(edit)
        if a and a["vivo"]:
            return False
        pasta = edit / mv.PASTA
        pasta.mkdir(exist_ok=True)
        (pasta / "andamento.json").unlink(missing_ok=True)  # o "pronto" de antes não vale para este
        with open(pasta / "preparo.log", "ab") as log:
            _voz_jobs[str(edit)] = subprocess.Popen(
                comando_preparo(edit), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True


def andamento_preparo(edit: Path) -> dict | None:
    """O andamento do preparo, também nos dois instantes que o arquivo não mostra: o processo
    acabou de nascer (ainda não escreveu nada) e o processo morreu sem escrever o fim."""
    edit = edit.resolve()
    p = _voz_jobs.get(str(edit))
    a = mv.andamento(edit)
    if p is None:
        return a
    if p.poll() is None:
        return a or {"etapa": "comecando", "n": 0, "de": 0, "texto": "Começando o preparo", "fracao": 0.0,
                     "vivo": True}
    if a is None or a.get("etapa") not in ("pronto", "falhou"):
        try:
            linhas = (edit / mv.PASTA / "preparo.log").read_text(encoding="utf-8", errors="replace").splitlines()
            ultima = next((x.strip() for x in reversed(linhas) if x.strip()), "")
        except OSError:
            ultima = ""
        erro = ultima.removeprefix("erro: ") if ultima.startswith("erro: ") else (
            "o preparo parou sem terminar" + (f" ({ultima[:200]})" if ultima else ""))
        return {"etapa": "falhou", "n": 0, "de": 0, "texto": "O preparo parou", "fracao": 0.0, "erro": erro,
                "vivo": False}
    return a


def comando_batida(arquivo: Path, edit: Path) -> list[str]:
    """A grade de batida roda num processo à parte: o detector carrega o torch (~0,5 GB) só enquanto
    analisa, e o servidor continua leve. Os testes trocam por um falso."""
    return [sys.executable, "-X", "utf8", str(Path(__file__).resolve().parent / "batida.py"),
            "analisar", str(arquivo), "--edit", str(edit)]


def _sha_da_musica(arquivo: Path) -> str:
    """O sha256 do arquivo, lembrado pelo tamanho e pela data: o editor pergunta a cada 2 s enquanto
    a análise roda, e reler 8 MB a cada pergunta seria à toa."""
    st = arquivo.stat()
    chave = (str(arquivo), st.st_size, st.st_mtime_ns)
    if chave not in _sha_musicas:
        _sha_musicas[chave] = bt.sha256_arquivo(arquivo)
    return _sha_musicas[chave]


def grade_da_musica(arquivo: Path, edit: Path) -> dict:
    """A grade de batida de uma música do projeto, para as marcas e o ímã da linha do tempo.

    `pronta` quando ela (pelo conteúdo) já foi analisada; senão a análise começa num processo à parte
    (`calculando`), uma por vez no servidor (`na fila` para as outras), e `falhou`, com a última linha
    do registro, quando o processo terminou sem deixar a grade."""
    arquivo, edit = arquivo.resolve(), edit.resolve()
    sha = _sha_da_musica(arquivo)
    try:
        g = json.loads(bt.caminho_grade(sha, bt.MODELO_PADRAO, edit).read_text(encoding="utf-8"))
        if g.get("versao") == bt.VERSAO and g.get("sha256") == sha:
            return {"estado": "pronta", **{k: g.get(k) for k in ("bpm", "confianca", "duracao", "batidas", "fortes")}}
    except (OSError, ValueError):
        pass
    registro = edit / "batidas" / "analise.log"
    with _batida_lock:
        p = _batida_jobs.get(str(arquivo))
        if p is not None and p.poll() is None:
            return {"estado": "calculando"}
        if p is not None:  # terminou e não deixou a grade
            del _batida_jobs[str(arquivo)]
            try:
                linhas = registro.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                linhas = []
            ultima = next((x.strip() for x in reversed(linhas) if x.strip()), "")
            return {"estado": "falhou", "erro": ultima.removeprefix("batida: ") or "a análise parou sem terminar"}
        if any(q.poll() is None for q in _batida_jobs.values()):
            return {"estado": "na fila"}  # duas análises juntas dobrariam a memória
        registro.parent.mkdir(parents=True, exist_ok=True)
        with open(registro, "ab") as log:
            _batida_jobs[str(arquivo)] = subprocess.Popen(
                comando_batida(arquivo, edit), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return {"estado": "calculando"}


# blocos da Fase 2 que o editor manda INTEIROS (todos os de cada tipo) quando algum anda
BLOCOS_F2 = ("inserts", "splitInserts", "splitVideos", "hook", "behind", "wordAccents", "numeros", "graficos")


def recorte_disponivel() -> bool:
    """O recorte da prévia roda pelo onnxruntime, da instalação base do kit."""
    import importlib.util
    return importlib.util.find_spec("onnxruntime") is not None


def recorte_png(video: Path, t: float, destino: Path) -> None:
    """A pessoa do quadro do corte em `t`, recortada como no vídeo final (person_matte.py, borda na
    cor dela), em PNG 540x960 com alfa. Roda os 8 quadros até `t`: o modelo é recorrente e só acerta
    a borda depois de alguns quadros."""
    import cv2
    from PIL import Image

    import person_matte as pm  # mesma pasta deste arquivo
    cap = cv2.VideoCapture(str(video))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        q = int(round(t * fps))
        ini = max(0, q - 7)
        motor = pm.MotorOnnx(pm.auto_downsample_ratio(h, w))
        ultimo = None
        for rgb in pm.ler_janela(cap, ini, q - ini + 1):
            ultimo = (rgb, *motor(rgb))
    finally:
        cap.release()
    if ultimo is None:
        raise ValueError("sem quadro nesse tempo")
    Image.fromarray(pm.compor(*ultimo, cor="misturada"), "RGBA").resize((540, 960), Image.LANCZOS).save(destino)


class CenasInvalidas(ValueError):
    pass


def conferir_cenas(root: Path, itens: list) -> list:
    """Os efeitos que o editor manda no Salvar. Ele só CRIA o Fundo (`nova: true`) e, num Fundo, muda
    os `campos` (`fundo`, `escurecer`, `desfoque`); o resto (ligar, texto, lugar, estilo) é por `ref`.
    O fundo vem dos prontos do kit ou da mídia do projeto, que precisa existir."""
    if not isinstance(itens, list):
        raise CenasInvalidas("cenas: uma lista")
    for i, c in enumerate(itens):
        if not isinstance(c, dict):
            raise CenasInvalidas(f"cenas[{i}]: um objeto")
        if c.get("nova") and c.get("tipo") != "fundo":
            raise CenasInvalidas(f"cenas[{i}]: o editor só cria o efeito Fundo (veio `{c.get('tipo')}`)")
        if not c.get("nova") and not isinstance(c.get("ref"), int):
            raise CenasInvalidas(f"cenas[{i}]: falta o `ref` do efeito")
        campos = c.get("campos")
        if campos is None:
            continue
        if c.get("tipo") != "fundo" or not isinstance(campos, dict):
            raise CenasInvalidas(f"cenas[{i}]: `campos` só num Fundo")
        item = {"tipo": "fundo", "start": c.get("start"), "end": c.get("end"),
                **{k: campos[k] for k in ("fundo", "escurecer", "desfoque") if k in campos}}
        erros = cn.validar(item)
        if erros:
            raise CenasInvalidas(f"cenas[{i}]: {'; '.join(erros)}")
        if cn.midia(item["fundo"]):
            p = (root / item["fundo"]).resolve()
            if not p.is_relative_to(root.resolve()) or not p.is_file():
                raise CenasInvalidas(f"cenas[{i}]: a imagem do fundo não está no projeto ({item['fundo']})")
    return itens


class MontagemInvalida(ValueError):
    pass


def conferir_montagem(root: Path, pasta_videos: Path, pedido: object) -> dict:
    """O que o editor pede para uma montagem (montagem.py): os lugares, [{vaga, midia?, de?, enquadre?}], e o
    `formato` do vídeo (um de montagem.FORMATOS). Só lugares que existem; a mídia é uma foto ou vídeo
    de midia/, um original da própria montagem ou um vídeo enviado para a pasta dos vídeos; `de` é um
    tempo de verdade. O lugar que não muda nada sai; o formato vai como veio (um Salvar de volta ao
    formato de agora desfaz o pedido de outro, ainda não feito: juntar_salvamentos)."""
    try:
        edl = json.loads((root / "edl.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise MontagemInvalida("o projeto não tem edl.json") from None
    mont = edl.get("montagem") if isinstance(edl, dict) else None
    lugares = (mont or {}).get("lugares") or []
    vagas = {lg.get("vaga") for lg in lugares if isinstance(lg, dict)}
    if not vagas:
        raise MontagemInvalida("este projeto não é uma montagem")
    originais = {str(Path(x)) for x in originais_da_montagem(mont)}
    if not isinstance(pedido, dict) or not isinstance(pedido.get("lugares", []), list) or len(pedido.get("lugares", [])) > 400:
        raise MontagemInvalida("lugares: uma lista")
    saida = []
    for it in pedido.get("lugares", []):
        v = it.get("vaga") if isinstance(it, dict) else None
        if isinstance(v, bool) or v not in vagas:
            raise MontagemInvalida(f"lugar desconhecido: {v!r}")
        x = {"vaga": int(v)}
        if it.get("midia") is not None:
            x["midia"] = _midia_da_montagem(root, pasta_videos, originais, it["midia"])
        de = it.get("de")
        if de is not None:
            if isinstance(de, bool) or not isinstance(de, (int, float)) or not 0 <= de <= cam.MAX_T:
                raise MontagemInvalida(f"lugar {v}: o trecho começa em {de!r}?")
            x["de"] = round(float(de), 3)
        if "enquadre" in it:  # o enquadramento à mão; null volta ao automático
            try:
                x["enquadre"] = mt.conferir_enquadre(it["enquadre"])
            except mt.ErroMontagem as e:
                raise MontagemInvalida(f"lugar {v}: {e}") from None
        if len(x) > 1:
            saida.append(x)
    out = {"lugares": saida}
    formato = pedido.get("formato")
    if formato is not None:
        if not isinstance(formato, str) or formato not in mt.FORMATOS:
            raise MontagemInvalida(f"formato: {', '.join(mt.FORMATOS)}")
        out["formato"] = formato
    return out


def sem_formato_novo(root: Path, body: dict) -> None:
    """Tira do Salvar o formato que é o da montagem de agora (nada a refazer), e a montagem que ficou
    sem lugar e sem formato."""
    m = body["montagem"]
    if "formato" not in m or "usar" in m:
        return
    if m["formato"] == ((montagem_do_projeto(root) or {}).get("formato") or mt.FORMATO_PADRAO):
        del m["formato"]
        if not m.get("lugares"):
            del body["montagem"]


def conferir_usar(root: Path, pedido: object) -> dict:
    """O Usar do painel Modelos de montagem: {modelo, musica, midias, formato?}. O modelo existe
    (montagens.py), a música é um áudio de midia/ e as mídias são fotos e vídeos de midia/ ou da
    montagem aberta (as mesmas que o Trocar oferece), de 1 a 400, na ordem em que a pessoa tocou; o
    formato, sem ele o do modelo, é um de montagem.FORMATOS. Um projeto que já é um corte de fala não
    vira montagem por aqui."""
    if not isinstance(pedido, dict):
        raise MontagemInvalida("usar: um objeto")
    modelo = mg.obter(pedido.get("modelo"))
    if not modelo:
        raise MontagemInvalida(f"o modelo de montagem {pedido.get('modelo')!r} não existe")
    musica = _do_midia(root, pedido.get("musica"), cam.AUDIO_EXTS, "a música")
    midias = pedido.get("midias")
    if not isinstance(midias, list) or not 1 <= len(midias) <= mt.MAX_VAGAS:
        raise MontagemInvalida(f"as fotos e clipes: uma lista de 1 a {mt.MAX_VAGAS}")
    mont = montagem_do_projeto(root)
    originais = {str(Path(x)) for x in originais_da_montagem(mont)} if mont else set()
    lista = [_midia_da_montagem(root, None, originais, x) for x in midias]
    try:
        edl = json.loads((root / "edl.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        edl = None
    if isinstance(edl, dict) and edl.get("ranges") and not edl.get("montagem"):
        raise MontagemInvalida("este projeto é um corte de vídeo, não uma montagem: comece uma Nova montagem")
    out = {"modelo": modelo["id"], "musica": musica, "midias": lista}
    formato = pedido.get("formato")
    if formato is not None:
        if not isinstance(formato, str) or formato not in mt.FORMATOS:
            raise MontagemInvalida(f"formato: {', '.join(mt.FORMATOS)}")
        out["formato"] = formato
    return out


def _do_midia(root: Path, valor: object, exts: set[str], nome: str) -> str:
    if not isinstance(valor, str) or not valor.startswith(cam.MIDIA_DIR + "/") or len(valor) > 1024:
        raise MontagemInvalida(f"{nome}: um arquivo de midia/")
    p = (root / valor).resolve()
    if p.parent != (root / cam.MIDIA_DIR).resolve() or p.suffix.lower() not in exts or not p.is_file():
        raise MontagemInvalida(f"{nome}: {valor} não está em midia/")
    return f"{cam.MIDIA_DIR}/{p.name}"


def _midia_da_montagem(root: Path, pasta_videos: Path | None, originais: set[str], valor: object) -> str:
    if not isinstance(valor, str) or not valor or len(valor) > 1024:
        raise MontagemInvalida("mídia inválida")
    ext = Path(valor).suffix.lower()
    if valor.startswith(cam.MIDIA_DIR + "/"):
        p = (root / valor).resolve()
        if p.parent != (root / cam.MIDIA_DIR).resolve() or ext not in cam.IMAGE_EXTS | VIDEO_EXTS or not p.is_file():
            raise MontagemInvalida(f"mídia de midia/ inválida: {valor}")
        return f"{cam.MIDIA_DIR}/{p.name}"
    p = Path(valor)
    if str(p) in originais and p.is_file():
        return str(p)
    if (pasta_videos is not None and p.is_absolute() and ext in VIDEO_EXTS and p.is_file()
            and p.resolve().parent == pasta_videos.resolve()):
        return str(p.resolve())  # um vídeo enviado pelo editor (vai para a pasta dos vídeos)
    raise MontagemInvalida(f"essa mídia não é do projeto: {p.name}")


def montagem_do_projeto(root: Path) -> dict | None:
    """O bloco `montagem` do edl.json, quando o projeto é uma montagem na batida (montagem.py)."""
    try:
        edl = json.loads((root / "edl.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    mont = edl.get("montagem") if isinstance(edl, dict) else None
    return mont if isinstance(mont, dict) and mont.get("lugares") else None


def montagem_nova(root: Path) -> bool:
    """Um projeto que ainda vai virar montagem: criado pela Nova montagem e sem edl.json."""
    try:
        st = json.loads((root / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(st, dict) and st.get("montagem") is True and not (root / "edl.json").exists()


def originais_da_montagem(mont: dict) -> list[str]:
    """As mídias que a montagem recebeu (`midias`) e a de cada lugar, sem repetir, na ordem."""
    lugares = [lg for lg in mont.get("lugares") or [] if isinstance(lg, dict)]
    return list(dict.fromkeys([*(x for x in mont.get("midias") or [] if isinstance(x, str)),
                               *(lg["midia"] for lg in lugares if isinstance(lg.get("midia"), str))]))


_duracoes: dict[tuple[str, int, int], float] = {}  # (arquivo, tamanho, data) → duração: o ffprobe roda uma vez


def _duracao(p: Path) -> float:
    st = p.stat()
    chave = (str(p), st.st_size, st.st_mtime_ns)
    if chave not in _duracoes:
        _duracoes[chave] = round(probe_duration(p), 3)
    return _duracoes[chave]


def opcoes_da_montagem(root: Path) -> list[dict]:
    """O que o Trocar oferece para um lugar: as mídias da montagem e as fotos e vídeos de midia/ (o
    que o editor envia para um lugar cai ali), cada uma com o tipo e a duração."""
    mont = montagem_do_projeto(root)
    if mont is None and not montagem_nova(root):
        raise MontagemInvalida("este projeto não é uma montagem")
    chaves = originais_da_montagem(mont) if mont else []  # na montagem nova, só o que chegou em midia/
    pasta = root / cam.MIDIA_DIR
    if pasta.is_dir():
        chaves += [f"{cam.MIDIA_DIR}/{f.name}" for f in sorted(pasta.iterdir(), key=lambda x: x.stat().st_mtime)
                   if f.is_file() and not f.name.startswith(".")]
    itens = []
    for chave in dict.fromkeys(chaves):
        p = root / chave if chave.startswith(cam.MIDIA_DIR + "/") else Path(chave)
        ext = p.suffix.lower()
        tipo = "video" if ext in VIDEO_EXTS else "foto" if ext in cam.IMAGE_EXTS else None
        if tipo and p.is_file():  # a música e o que sumiu do disco ficam de fora
            itens.append({"midia": chave, "nome": p.name, "tipo": tipo,
                          "duracao": _duracao(p) if tipo == "video" else 0.0})
    return itens


def arquivo_da_montagem(root: Path, valor: object) -> Path:
    """Um arquivo da montagem que o editor pode ver (quadro, o vídeo do Trecho): um original dela ou
    uma foto ou vídeo de midia/. Nunca um caminho qualquer vindo do pedido."""
    mont = montagem_do_projeto(root)
    if mont is None and not montagem_nova(root):
        raise MontagemInvalida("este projeto não é uma montagem")
    chave = _midia_da_montagem(root, None, {str(Path(x)) for x in originais_da_montagem(mont or {})}, valor)
    return root / chave if chave.startswith(cam.MIDIA_DIR + "/") else Path(chave)


def juntar_salvamentos(velho: dict, novo: dict) -> dict:
    """Two saves before the agent applies the first: the second ADDS to the first.

    Each save carries only what changed since the previous one (the editor resets its
    reference on Save), so writing it over a pending preview_edits.json lost the first
    one. Notes add up; effects merge by `ref` and the hook/number texts by `alvo` + `ref`
    (newest wins); the zoom list is always the whole list, and its `mudou` adds up;
    whole-state keys (`edl.ranges`, the Phase 2 blocks of a kind, camadas, efeitos,
    velocidade, the captions' `legenda`) are replaced by the newest.
    """
    out = {**velho, **{k: v for k, v in novo.items() if k not in ("notes", "editData")}}
    notas = (velho.get("notes") or []) + (novo.get("notes") or [])
    if notas:
        out["notes"] = notas
    ev, en = velho.get("editData") or {}, novo.get("editData") or {}
    if ev or en:
        ed = {**ev, **{k: v for k, v in en.items() if k not in ("cenas", "camera", "destaques")}}
        if ev.get("cenas") or en.get("cenas"):
            # os do agente pelo `ref`; os novos (Fundo criado no editor) pela janela da tomada
            chave = lambda c: (0, c["ref"], 0.0) if not c.get("nova") else (1, 0, float(c.get("start") or 0))  # noqa: E731
            por_ref = {chave(c): c for c in ev.get("cenas") or []}
            por_ref.update({chave(c): c for c in en.get("cenas") or []})
            ed["cenas"] = [por_ref[k] for k in sorted(por_ref)]
        if ev.get("destaques") or en.get("destaques"):  # o gancho e cada número, como os efeitos
            chave = lambda c: (c.get("alvo"), c.get("ref"))  # noqa: E731
            por_alvo = {chave(c): c for c in ev.get("destaques") or []}
            por_alvo.update({chave(c): c for c in en.get("destaques") or []})
            ed["destaques"] = list(por_alvo.values())
        if en.get("camera"):
            cam_novo = dict(en["camera"])
            cam_novo["mudou"] = sorted(set((ev.get("camera") or {}).get("mudou") or []) | set(cam_novo.get("mudou") or []))
            ed["camera"] = cam_novo
        out["editData"] = ed
    m_velho, m_novo = velho.get("montagem") or {}, novo.get("montagem") or {}
    if m_novo.get("usar") or m_velho.get("usar"):
        # uma montagem nova (Usar um modelo) refaz tudo: os lugares da montagem de antes não valem mais
        out["montagem"] = {"usar": m_novo.get("usar") or m_velho["usar"]}
    elif m_velho or m_novo:
        # os lugares da montagem somam pelo número; uma mídia nova sem `de` entra do começo, e sem
        # `enquadre`, no automático
        por_vaga = {x["vaga"]: dict(x) for x in m_velho.get("lugares") or []}
        if m_novo.get("formato") and m_novo.get("formato") != m_velho.get("formato"):
            # o enquadre salvo antes era do quadro de antes: com outro formato, volta ao automático
            for x in por_vaga.values():
                x.pop("enquadre", None)
        for x in m_novo.get("lugares") or []:
            base = por_vaga.get(x["vaga"], {})
            if "midia" in x:
                base = {k: w for k, w in base.items() if k not in ("de", "enquadre") or k in x}
            por_vaga[x["vaga"]] = {**base, **x}
        out["montagem"] = {"lugares": [por_vaga[k] for k in sorted(por_vaga)]}
        if m_novo.get("formato") or m_velho.get("formato"):  # o formato do Salvar mais novo vale
            out["montagem"]["formato"] = m_novo.get("formato") or m_velho["formato"]
    return out


def ensure_token(root: Path) -> str:
    """O código que o celular precisa ter quando o servidor abre para a rede.

    Fica no projeto, não na memória: reiniciar o servidor não obriga ninguém a
    escanear o QR de novo, e o atalho na tela inicial continua entrando.
    """
    p = root / ".preview_cache" / "celular-token"
    try:
        tok = p.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{20,}", tok):
            return tok
    except OSError:
        pass
    tok = secrets.token_urlsafe(18)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(tok, encoding="utf-8")
    if os.name != "nt":
        os.chmod(p, 0o600)
    return tok


def is_local_bind(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def pc_host(bind_host: str) -> str:
    """Por onde o próprio computador abre o editor."""
    return "127.0.0.1" if bind_host in ("0.0.0.0", "") or is_local_bind(bind_host) else bind_host


def phone_hosts(bind_host: str) -> list[tuple[str, str]]:
    """Os endereços pelos quais o celular alcança este computador."""
    if bind_host not in ("0.0.0.0", ""):
        return [("Rede", bind_host)]
    found: list[tuple[str, str]] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # só escolhe a rota de saída; nada é enviado
            ip = s.getsockname()[0]
        if not ip.startswith("127."):
            found.append(("Wi-Fi de casa", ip))
    except OSError:
        pass
    tailnet = ipaddress.ip_network("100.64.0.0/10")
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ipaddress.ip_address(ip) in tailnet and all(ip != f[1] for f in found):
                found.append(("Tailscale (fora de casa)", ip))
    except OSError:
        pass
    return found


def phone_urls(bind_host: str, port: int, token: str) -> list[dict[str, str]]:
    return [{"label": label, "url": f"http://{ip}:{port}/c?t={token}", "ip": ip}
            for label, ip in phone_hosts(bind_host)]


AVISO_REDE_PUBLICA = ("  ! O Windows marcou esta rede como Pública e barra o celular. Para abrir pelo Wi-Fi, mude para "
                      "Rede privada: Configurações > Rede e Internet > Wi-Fi ou Ethernet > Tipo de perfil de rede.")


def rede_publica(ip: str) -> bool:
    """Windows: a rede por onde passa este IP está marcada como Pública? O Windows marca assim muita rede de
    casa, e então o firewall barra o celular mesmo com a permissão do CutMind (ela vale para redes privadas).
    Pergunta pelo nome do tipo (Public/Private), que não vem traduzido."""
    if os.name != "nt":
        return False
    try:
        ip = str(ipaddress.IPv4Address(ip))
    except ValueError:
        return False
    cmd = (f"$i = (Get-NetIPAddress -IPAddress '{ip}' -ErrorAction SilentlyContinue).InterfaceIndex; "
           "if ($i) { (Get-NetConnectionProfile -InterfaceIndex $i -ErrorAction SilentlyContinue).NetworkCategory }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.stdout.strip() == "Public"


def qr_svg(text: str) -> str | None:
    """QR code em SVG. Sem o segno instalado, None: a tela mostra só o link."""
    try:
        import segno
    except ImportError:
        return None
    buf = io.BytesIO()
    # omitsize: sem largura/altura fixas e com viewBox, então o CSS da tela escala
    segno.make(text, error="m").save(buf, kind="svg", scale=6, border=2, omitsize=True,
                                    dark="#0b0e13", light="#ffffff", xmldecl=False)
    return buf.getvalue().decode("utf-8")


def clean_upload_name(raw: str) -> str:
    """Só o nome do arquivo, sem pasta e sem caractere que o Windows recusa."""
    name = raw.replace("\\", "/").split("/")[-1]
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "_", name).strip(" .")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = stem.strip(" .")[:100] or "video"
    if stem.upper() in WINDOWS_RESERVED:
        stem = f"_{stem}"
    return f"{stem}.{ext.lower()}" if ext else stem


def unique_path(folder: Path, name: str) -> Path:
    """Nunca sobrescreve: "video.mp4" ocupado vira "video (2).mp4"."""
    stem, ext = Path(name).stem, Path(name).suffix
    n = 1
    while True:
        cand = name if n == 1 else f"{stem} ({n}){ext}"
        if not (folder / cand).exists() and not (folder / f".{cand}.parte").exists():
            return folder / cand
        n += 1


def upload_kind(name: str) -> str | None:
    ext = Path(name).suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in cam.IMAGE_EXTS:
        return "imagem"
    if ext in cam.AUDIO_EXTS:
        return "audio"
    return None


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def gen_waveform(video: Path, out_json: Path) -> None:
    """Decode audio to mono s16 and store min/max peak pairs per bucket (0-100)."""
    rate = 8000
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vn",
         "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        capture_output=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    per_bucket = max(1, rate // PEAKS_PER_SEC)
    mins: list[int] = []
    maxs: list[int] = []
    for i in range(0, len(samples), per_bucket):
        chunk = samples[i:i + per_bucket]
        if not chunk:
            continue
        mins.append(round(min(chunk) / 32768 * 100))
        maxs.append(round(max(chunk) / 32768 * 100))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_json.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "peaksPerSec": PEAKS_PER_SEC,
        "duration": len(samples) / rate,
        "min": mins,
        "max": maxs,
        "srcMtime": video.stat().st_mtime,
    }))
    tmp.replace(out_json)


def gen_thumbs(video: Path, out_dir: Path) -> None:
    """Filmstrip thumbs: one small jpg every THUMB_EVERY_S seconds."""
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"fps=1/{THUMB_EVERY_S},scale=-2:{THUMB_HEIGHT}",
         "-q:v", "6", str(out_dir / "%04d.jpg")],
        check=False, capture_output=True,
    )
    (out_dir / "meta.json").write_text(json.dumps({
        "everySec": THUMB_EVERY_S,
        "count": len(list(out_dir.glob("*.jpg"))),
        "srcMtime": video.stat().st_mtime,
    }))


class Handler(BaseHTTPRequestHandler):
    root: Path  # set on the class by main(); a tela Projetos troca por outro (_trocar)
    token: str | None = None  # só existe quando o servidor abre para a rede
    arquivo_codigo_tunel: Path | None = None  # o código da porta do túnel (tunel.py), à parte do do Wi-Fi
    porta_tunel: int | None = None
    servidor_principal = None  # o da porta do editor: é ele que fecha numa atualização, nunca o do túnel
    allow_hosts: tuple[str, ...] = ()
    upload_dir: Path | None = None
    upload_dir_fixo = False  # --upload-dir dado: não acompanha a troca de projeto
    max_upload: int = 8 * 1024 ** 3
    bind_host: str = "127.0.0.1"
    pacotes: pk.Pacotes | None = None  # a biblioteca; nasce no primeiro pedido
    protocol_version = "HTTP/1.1"
    # Envio parado (celular saiu do Wi-Fi) não segura uma thread e um .parte para sempre.
    timeout = 300

    # ---- quem pode entrar ----
    def _client_is_local(self) -> bool:
        """Este computador. Na porta do túnel (`remoto`) nunca: pelo túnel todo pedido da internet chega
        como 127.0.0.1, então lá o código é sempre cobrado."""
        return not getattr(self.server, "remoto", False) and self.client_address[0] in LOCAL_CLIENTS

    def _host_ok(self) -> bool:
        """Contra DNS rebinding: um site de fora que aponta um nome dele para este
        computador chega com o NOME dele no Host. IP e localhost passam; nome só
        se for liberado com --allow-host (".ts.net" do Tailscale, Codespaces)."""
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return True
        name = host[1:host.find("]")] if host.startswith("[") else host.split(":")[0]
        try:
            ipaddress.ip_address(name)
            return True
        except ValueError:
            pass
        if name == "localhost":
            return True
        if getattr(self.server, "remoto", False) and name.endswith(".trycloudflare.com"):
            return True  # o nome do túnel, e só na porta dele
        for allowed in self.allow_hosts:
            a = allowed.lower()
            if (a.startswith(".") and (name.endswith(a) or name == a[1:])) or name == a:
                return True
        return False

    def _origem_ok(self) -> bool:
        """Contra CSRF: um site aberto no navegador da pessoa consegue mandar POST para
        127.0.0.1, e o Host chega como IP (o _host_ok deixa). O navegador põe Origin em todo
        POST e Sec-Fetch-Site em todo pedido: passa o que vem do próprio editor, ou de fora do
        navegador (sem esses cabeçalhos: o agente, os testes, o curl)."""
        if (self.headers.get("Sec-Fetch-Site") or "").strip().lower() == "cross-site":
            return False
        origem = self.headers.get("Origin")
        if origem is None:
            return True
        u = urlsplit(origem.strip().lower())
        return u.scheme in ("http", "https") and u.netloc == (self.headers.get("Host") or "").strip().lower()

    def _cookie_token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            jar = SimpleCookie()
            jar.load(raw)
        except CookieError:
            return None
        m = jar.get(TOKEN_COOKIE)
        return m.value if m else None

    def _codigo(self) -> str | None:
        """O código que vale nesta porta: o do projeto na do editor (Wi-Fi); o do túnel na do túnel. Um QR do
        Wi-Fi que vazou não abre o editor pela internet, e trocar de projeto não derruba o celular do túnel."""
        if getattr(self.server, "remoto", False):
            return _codigo_do_tunel(self.arquivo_codigo_tunel)
        return self.token

    def _token_ok(self, value: str | None) -> bool:
        codigo = self._codigo()
        return bool(codigo and value and hmac.compare_digest(value, codigo))

    def _gate(self, path: str) -> bool:
        """True = pode seguir. False = já respondeu com o erro.

        O código só é cobrado nos DADOS (/api, /media, /gen): a interface é o
        código aberto do kit, sem nada do usuário. Assim o manifesto e os ícones,
        que o navegador busca sem cookie, carregam — e a tela do celular abre e
        explica o que falta, em vez de uma página de erro solta."""
        if not self._host_ok():
            self._deny(403, "Endereço não permitido.", path)
            return False
        if not path.startswith(("/api/", "/media/", "/gen/")):
            return True  # interface; /c confere o código do próprio link
        if self._client_is_local() or self._token_ok(self._cookie_token()):
            return True
        self._deny(403, "Este celular ainda não tem o código. Abra pelo link ou pelo QR code "
                        "que aparece no computador.", path)
        return False

    def _idioma(self) -> str:
        """O da tela: o editor manda em cada pedido; a página aberta direto vai pelo do navegador."""
        return idm.do_pedido(self.headers.get("X-CutMind-Idioma"), self.headers.get("Accept-Language"))

    def _descartar_corpo(self, teto: int = 64 * 1024) -> None:
        """Lê e joga fora o corpo pequeno de um pedido negado. Fechar a conexão com dados ainda por ler
        faz o Windows mandar um reset, que às vezes chega antes da resposta: o cliente via "conexão
        interrompida" no lugar do 403 (falha intermitente da suíte, 2 vezes em 26/10/2026). Corpo
        grande (um envio de vídeo) não é lido: a conexão só fecha."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if not 0 < n <= teto:
            return
        antes = self.connection.gettimeout()
        try:
            self.connection.settimeout(2)
            self.rfile.read(n)
        except OSError:
            pass
        finally:
            self.connection.settimeout(antes)

    def _deny(self, code: int, msg: str, path: str) -> None:
        quem = self.client_address[0]
        if getattr(self.server, "remoto", False):  # pelo túnel tudo chega como 127.0.0.1
            ip = re.sub(r"[^0-9A-Fa-f:.]", "", self.headers.get("Cf-Connecting-Ip") or "")[:45]
            quem = f"túnel {ip or '?'}"
        sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] negado {code} {quem} {self.command} {path}\n")
        if self.command in ("POST", "PUT"):
            self._descartar_corpo()
        self.close_connection = True  # o corpo grande de um POST negado fica sem ler
        msg = idm.traduzir(msg, self._idioma())
        if path.startswith(("/api/", "/gen/", "/media/")):
            body = json.dumps({"error": msg}, ensure_ascii=False).encode()
            self._hdr(code, "application/json; charset=utf-8", len(body), {"Connection": "close"})
        else:
            body = ("<!doctype html><meta charset='utf-8'><meta name='viewport' "
                    "content='width=device-width,initial-scale=1'><title>CutMind</title>"
                    "<body style='font:16px/1.5 system-ui,sans-serif;background:#0b0e13;"
                    f"color:#e8ebf0;padding:32px'><p>{msg}</p></body>").encode()
            self._hdr(code, "text/html; charset=utf-8", len(body), {"Connection": "close"})
        self.wfile.write(body)

    def _fail(self, code: int, msg: str) -> None:
        """Erro num POST cujo corpo não foi lido: fecha a conexão depois."""
        self.close_connection = True
        body = json.dumps({"error": idm.traduzir(msg, self._idioma())}, ensure_ascii=False).encode()
        self._hdr(code, "application/json; charset=utf-8", len(body), {"Connection": "close"})
        self.wfile.write(body)

    # ---- helpers ----
    def _hdr(self, code: int, ctype: str, length: int | None = None,
             extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        if length is not None:
            self.send_header("Content-Length", str(length))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, obj: object, code: int = 200) -> None:
        if isinstance(obj, dict) and isinstance(obj.get("error"), str):  # o erro sai no idioma da tela
            obj = {**obj, "error": idm.traduzir(obj["error"], self._idioma())}
        body = json.dumps(obj, ensure_ascii=False).encode()
        self._hdr(code, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        """Static file with HTTP Range support (video scrubbing needs it)."""
        if not path.is_file():
            self._json({"error": f"not found: {path.name}"}, 404)
            return
        size = path.stat().st_size
        ctype = MIME.get(path.suffix.lower(), "application/octet-stream")
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        code = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                code = 206
        length = end - start + 1
        extra = {"Content-Range": f"bytes {start}-{end}/{size}"} if code == 206 else None
        self._hdr(code, ctype, length, extra)
        # Um pedaço por vez, abrindo e fechando o arquivo. O navegador baixa o vídeo devagar, e
        # no Windows um arquivo aberto o tempo todo impede o agente de trocar o cut.mp4 por cima
        # (os.replace dá PermissionError enquanto alguém o tiver aberto, mesmo compartilhando).
        pos, remaining = start, length
        while remaining > 0:
            try:
                with open(path, "rb") as f:
                    f.seek(pos)
                    chunk = f.read(min(1 << 20, remaining))
            except OSError:
                return
            if not chunk:
                break
            try:
                self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            pos += len(chunk)
            remaining -= len(chunk)

    def _safe(self, base: Path, rel: str) -> Path | None:
        # Por partes do caminho, não pelo começo do texto: "edit-x" começa com
        # "edit" e, comparado como texto, uma pasta irmã passava por dentro.
        base = base.resolve()
        p = (base / rel.lstrip("/")).resolve()
        return p if p == base or p.is_relative_to(base) else None

    def _current_video(self) -> Path | None:
        state_p = self.root / "state.json"
        rel = "cut.mp4"
        if state_p.exists():
            try:
                rel = json.loads(state_p.read_text()).get("video") or rel
            except json.JSONDecodeError:
                pass
        p = self._safe(self.root, rel)
        return p if p and p.exists() else None

    # ---- routes ----
    def do_GET(self) -> None:  # noqa: N802
        path, _, query = self.path.partition("?")
        if not self._gate(path):
            return
        # um editor só: o mesmo no computador e no celular, arrumado pela largura da tela
        if path in ("/", "/celular"):
            self._send_file(APP_DIR / "celular.html")
        elif path == "/c":
            self._enter(query)
        elif path == "/api/celular":
            self._celular_info()
        elif path == "/gen/frame":
            self._frame(query)
        elif path == "/gen/recorte":
            self._recorte(query)
        elif path == "/gen/frases":
            self._frases(query)
        elif path.startswith("/assets/"):
            p = self._safe(APP_DIR, path[len("/assets/"):])
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path.startswith("/efeitos/"):
            p = self._safe(EFEITOS_DIR, unquote(path[len("/efeitos/"):]))
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path.startswith("/media/"):
            # o navegador codifica espaço e acento (midia/Grava%C3%A7%C3%A3o.m4a); a
            # trava de pasta (_safe) vem depois de decodificar, então %2e%2e não passa
            p = self._safe(self.root, unquote(path[len("/media/"):]))
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path == "/gen/waveform.json":
            self._waveform()
        elif path.startswith("/gen/thumbs/"):
            self._thumbs(path[len("/gen/thumbs/"):])
        elif path == "/api/state":
            self._state()
        elif path == "/api/projetos":
            self._projetos()
        elif path == "/gen/projeto-capa":
            self._projeto_capa(query)
        elif path == "/api/modelos":
            self._json({"modelos": md.listar()})
        elif path == "/api/montagens":
            self._json({"modelos": [mg.resumo(m) for m in mg.listar()], "mural": bool(mu.endereco())})
        elif path == "/api/mural":
            self._mural_lista(query)
        elif path == "/api/mural/compartilhar":
            self._mural_compartilhar(query)
        elif path == "/api/melhorar":
            self._melhorar()
        elif path == "/api/melhorar/andamento":
            self._json(andamento_preparo(self.root) or {"etapa": None})
        elif path == "/api/trabalho":
            self._json(self._trabalho(tb.andamento(self.root)) or {"etapa": None})
        elif path == "/api/pendente":
            self._pendente()
        elif path == "/api/upload":  # de onde um envio em pedaços continua (a rede caiu no meio)
            envio = _ENVIOS.get((parse_qs(query).get("id") or [""])[0])
            self._json({"recebido": envio["recebido"], "total": envio["total"]} if envio
                       else {"error": "Esse envio não existe mais. Envie o arquivo de novo."}, 200 if envio else 404)
        elif path == "/api/atualizacao":
            self._atualizacao()
        elif path == "/api/sobre":
            # o "Gostou do CutMind?" do editor: a versão e o sistema que vão no formulário do GitHub
            self._json({"versao": (atu.vs.ler(SKILL) or {}).get("versao"), "sistema": sistema(),
                        "repo": f"https://github.com/{atu.REPO}"})
        elif path == "/api/atualizacao/andamento":
            # com o clique esperando um trabalho, o andamento.json ainda é o da atualização ANTERIOR
            a = None if ATUALIZACAO["pedido"] else atu._ler_json(atu.casa() / "atualizacao" / "andamento.json")
            self._json(self._trabalho(a) if a else {"etapa": None})
        elif path == "/api/midia":
            self._midia()
        elif path == "/api/batida":
            self._batida(query)
        elif path == "/api/montagem/midias":
            self._montagem_midias()
        elif path == "/gen/montagem-quadro":
            self._montagem_quadro(query)
        elif path == "/gen/montagem-video":
            self._montagem_video(query)
        elif path == "/api/pacotes":
            self._pacotes_lista(query)
        elif path == "/gen/pacote-previa":
            self._pacote_previa(query)
        elif path == "/gen/voz-previa":
            self._voz_previa(query)
        elif path == "/api/sfx":
            self._json({"itens": es.todos()})
        elif path == "/gen/sfx":
            sid = (parse_qs(query).get("id") or [""])[0]
            try:
                self._send_file(es.arquivo(sid))
            except KeyError:
                self._json({"error": "efeito sonoro desconhecido"}, 404)
            except pk.PacoteErro as e:  # o viral não desceu (sem conexão, arquivo diferente)
                self._json({"error": str(e)}, 502)
        elif path.startswith("/gen/pacote/"):
            self._pacote_arquivo(path[len("/gen/pacote/"):])
        else:
            self._json({"error": "unknown route"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path, _, query = self.path.partition("?")
        if not self._gate(path):
            return
        if not self._origem_ok():
            self._deny(403, "Pedido de outro site recusado.", path)
            return
        if path == "/api/upload":
            self._upload(query)
            return
        if path == "/api/upload/cancelar":
            self._cancelar_envio(query)
            return
        if path in ("/api/pacotes/usar", "/api/pacotes/favorito"):
            self._pacote_post(path)
            return
        if path == "/api/sfx/usar":
            self._sfx_usar()
            return
        if path in ("/api/projetos/abrir", "/api/projetos/novo"):
            self._projeto_post(path)
            return
        if path in ("/api/modelos", "/api/modelos/apagar"):
            self._modelo_post(path)
            return
        if path in ("/api/montagens", "/api/montagens/apagar"):
            self._montagens_post(path)
            return
        if path == "/api/mural/pegar":
            self._mural_pegar()
            return
        if path == "/api/melhorar/preparar":
            self._melhorar_preparar()
            return
        if path == "/api/conferir":
            self._conferir()
            return
        if path == "/api/gerar":
            self._gerar()
            return
        if path == "/api/pronto":
            self._pronto()
            return
        if path == "/api/atualizar":
            self._atualizar()
            return
        if path == "/api/atualizacao/config":
            self._atualizacao_config()
            return
        if path != "/api/save":
            self._fail(404, "unknown route")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._fail(400, "invalid Content-Length")
            return
        if length > MAX_JSON_BYTES:
            self._fail(413, "ajuste grande demais")
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        if not isinstance(body, dict):
            self._json({"error": "invalid JSON"}, 400)
            return
        # o editor manda o id do projeto que ele mostra: se outro aparelho abriu outro
        # projeto no meio, estes ajustes não vão parar na pasta errada
        pid = body.pop("projeto", None)
        if pid is not None and pid != pj.id_de(self.root):
            self._json({"error": "outro projeto foi aberto no editor; volte para este (Projetos) para salvar",
                        "aberto": pj.id_de(self.root)}, 409)
            return
        body["savedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # The style pick goes to its own file (it still wakes the agent). Every other
        # save is a timeline edit, applied here without the agent; the name below is
        # only the switch between the two (nothing writes preview_edits.json any more).
        name = "preview_style.json" if body.get("type") == "style-setup" else "preview_edits.json"
        if name == "preview_edits.json":
            # camadas e efeitos são arquivos do projeto (como num editor): tudo é
            # conferido antes de gravar qualquer coisa
            try:
                if "camadas" in body:
                    body["camadas"] = cam.normalize(body["camadas"])
                if "efeitos" in body:
                    body["efeitos"] = ef.normalize(body["efeitos"])
                if "velocidade" in body:
                    body["velocidade"] = vel.normalize(body["velocidade"])
                if "melhorar" in body:
                    body["melhorar"] = mv.normalizar_escolha(body["melhorar"])
                if isinstance(body.get("editData"), dict) and "cenas" in body["editData"]:
                    conferir_cenas(self.root, body["editData"]["cenas"])
                if "montagem" in body:
                    pedido = body["montagem"]
                    if isinstance(pedido, dict) and "usar" in pedido:  # Usar um modelo: a montagem inteira
                        body["montagem"] = {"usar": conferir_usar(self.root, pedido["usar"])}
                    else:
                        body["montagem"] = conferir_montagem(self.root, self.upload_dir, pedido)
            except CenasInvalidas as e:
                self._json({"error": f"efeitos do vídeo final: {e}"}, 400)
                return
            except MontagemInvalida as e:
                self._json({"error": f"montagem: {e}"}, 400)
                return
            except cam.CamadasInvalidas as e:
                self._json({"error": f"camadas: {e}"}, 400)
                return
            except ef.EfeitosInvalidos as e:
                self._json({"error": f"efeitos: {e}"}, 400)
                return
            except vel.VelocidadeInvalida as e:
                self._json({"error": f"velocidade: {e}"}, 400)
                return
            except mv.VozErro as e:
                self._json({"error": f"melhorar voz: {e}"}, 400)
                return
        # o Salvar que mexe nas tomadas: o servidor refaz o corte sozinho, sem acordar o agente
        # (aplicar_corte.py), depois de perguntar o que ficaria desalinhado
        confirmado = bool(body.pop("confirmado", False))
        corte = name == "preview_edits.json" and isinstance(body.get("edl"), dict)
        # um trabalho rodando lê o projeto (o corte refeito, o vídeo final desenhado): nada muda no meio dele
        if name == "preview_edits.json" and tb.vivo(self.root):
            self._ocupado(tb.vivo(self.root))
            return
        if corte and agente_trabalhando(self.root):
            self._json({"error": "o agente está trabalhando neste projeto: espere ele terminar para mexer no corte"}, 409)
            return
        if corte:
            if not confirmado:
                try:
                    avisos = ac.conferir_projeto(self.root, body["edl"])
                except (OSError, ValueError, KeyError, TypeError) as e:
                    print(f"conferência do corte não rodou: {e}", file=sys.stderr, flush=True)
                    avisos = []
                if avisos:
                    self._json({"error": "antes de aplicar, confira o que fica desalinhado", "avisos": avisos}, 409)
                    return
        # os dados da Fase 2 (blocos, efeitos, gancho, zoom, legenda) vão direto para o edit-data.json:
        # o vídeo final com eles sai no Baixar (gerar.py), sem o agente
        fase2 = None
        if name == "preview_edits.json" and isinstance(body.get("editData"), dict):
            try:
                fase2 = eda.gravar(self.root, body["editData"])
            except (OSError, ValueError, KeyError, TypeError) as e:
                self._json({"error": f"vídeo final: {e}"}, 400)
                return
            body.pop("editData")
            for aviso in fase2["avisos"]:
                print(f"vídeo final: {aviso}", file=sys.stderr, flush=True)
        if name == "preview_edits.json":
            if "camadas" in body:
                cam.save(self.root / "camadas.json", body["camadas"])
            if "efeitos" in body:
                ef.save(self.root / "efeitos.json", body["efeitos"])
            if "velocidade" in body:
                vel.save(self.root / "velocidade.json", body["velocidade"])
        resposta: dict = {"ok": True}
        if corte:
            pasta = tb.pasta(self.root)
            pasta.mkdir(parents=True, exist_ok=True)
            pedido_p = pasta / "pedido-corte.json"
            pedido_p.write_bytes(json.dumps(body.pop("edl"), ensure_ascii=False).encode("utf-8"))
            if not tb.iniciar(self.root, "corte", comando_corte(self.root, pedido_p, pasta / "andamento.json")):
                self._ocupado(tb.vivo(self.root))
                return
            resposta["trabalho"] = "corte"
        if fase2 is not None:
            resposta["avisos"] = fase2["avisos"]
        if name == "preview_style.json":  # a escolha do Estilo continua acordando o agente
            out = self.root / name
            tmp = out.with_suffix(".tmp")
            tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(out)
            resposta["file"] = str(out)
            self._json(resposta)
            return
        # o que espera o Baixar (a montagem, a voz) e o que espera o Pronto (marcações e pedidos):
        # nada disso acorda o agente
        guardar = {k: body[k] for k in ("montagem", "melhorar") if k in body}
        if guardar:
            # soma ao que já estava guardado e SÓ ENTÃO tira o formato igual ao de agora: voltar ao
            # formato da montagem desfaz um pedido de formato salvo antes
            junto = juntar_salvamentos(pend.ler(self.root), guardar)
            if isinstance(junto.get("montagem"), dict):
                sem_formato_novo(self.root, junto)
            pend.gravar(self.root, junto)
        if body.get("notes"):
            resposta["pedidos"] = pend.somar_pedidos(self.root, body["notes"])
        usar = (guardar.get("montagem") or {}).get("usar") if isinstance(guardar.get("montagem"), dict) else None
        if usar and not corte:  # a montagem nova: o servidor monta, sem o agente
            if not tb.iniciar(self.root, "montar", comando_montar(self.root)):
                self._ocupado(tb.vivo(self.root))
                return
            resposta["trabalho"] = "montar"
        self._json(resposta)

    # ---- celular ----
    def _enter(self, query: str) -> None:
        """Entrada pelo link/QR: troca o código da URL por um cookie e tira o
        código da barra de endereço. Lax, não Strict: com Strict o cookie não
        vai no primeiro carregamento quando o link é aberto de outro app."""
        t = (parse_qs(query).get("t") or [""])[0]
        extra = {"Location": "/celular"}
        if self._token_ok(t):
            extra["Set-Cookie"] = (f"{TOKEN_COOKIE}={self._codigo()}; Path=/; Max-Age={TOKEN_MAX_AGE}; "
                                   "HttpOnly; SameSite=Lax" + ("; Secure" if getattr(self.server, "remoto", False) else ""))
        elif not self._client_is_local():
            self._deny(403, "Link vencido ou incompleto. Abra de novo pelo QR code do computador.", "/c")
            return
        self._hdr(303, "text/plain; charset=utf-8", 0, extra)

    def _celular_info(self) -> None:
        # Só o próprio computador vê os links: eles carregam o código.
        if not self._client_is_local():
            self._deny(403, "Só no computador.", "/api/celular")
            return
        urls = [] if is_local_bind(self.bind_host) or not self.token else phone_urls(
            self.bind_host, self.server.server_address[1], self.token)
        tun = tn.estado(atu.casa()) if self.porta_tunel else None
        codigo = _codigo_do_tunel(self.arquivo_codigo_tunel)
        if tun and tun.get("porta") == self.porta_tunel and codigo:  # o túnel deste editor: Wi-Fi ou 4G
            urls.insert(0, {"label": "De qualquer lugar", "url": f"{tun['url']}/c?t={codigo}"})
        for u in urls:
            u["qr"] = qr_svg(u["url"])
        self._json({"enabled": bool(urls), "urls": urls})

    def _source_path(self, name: str) -> Path | None:
        """Um vídeo de origem pelo NOME que o edl.json dá a ele — nunca por um
        caminho vindo do pedido."""
        state: dict = {}
        try:
            state = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        edl_p = self._safe(self.root, str(state.get("edl") or "edl.json"))
        if not edl_p:
            return None
        try:
            sources = json.loads(edl_p.read_text(encoding="utf-8")).get("sources") or {}
        except (OSError, json.JSONDecodeError, AttributeError):
            return None
        rel = sources.get(name) if isinstance(sources, dict) else None
        if not rel:
            return None
        p = Path(rel)
        p = (p if p.is_absolute() else self.root / p).resolve()
        return p if p.is_file() else None

    def _frame(self, query: str) -> None:
        q = parse_qs(query)
        try:
            t = max(0.0, float((q.get("t") or ["0"])[0]))
            h = min(1080, max(120, int(float((q.get("h") or ["480"])[0]))))
        except ValueError:
            self._json({"error": "t ou h inválido"}, 400)
            return
        src = (q.get("src") or [""])[0]
        path = self._source_path(src)
        if not path:
            self._json({"error": f"fonte desconhecida: {src}"}, 404)
            return
        self._quadro_jpg(path, t, h)

    def _quadro_jpg(self, path: Path, t: float, h: int, guardar: bool = False) -> None:
        """Um quadro em JPEG. `guardar`: as miniaturas do Trocar e da tira do Trecho voltam a cada
        abertura do painel, e o mesmo quadro do mesmo arquivo não precisa de outro ffmpeg."""
        st = path.stat()
        chave = (str(path), st.st_size, st.st_mtime_ns, round(t, 2), h)
        with _quadros_lock:
            jpg = _quadros_guardados.get(chave) if guardar else None
        if jpg is None:
            if not _frame_slots.acquire(timeout=5):
                self._json({"error": "ocupado, tente de novo"}, 503)
                return
            # foto sem busca: o JPEG sem o marcador de fim (comum em foto baixada da internet) o ffmpeg
            # lê pelo demuxer image2, e com `-ss` ele descarta o único quadro, sem erro nenhum
            busca = [] if t <= 0 or path.suffix.lower() in cam.IMAGE_EXTS else ["-ss", f"{t:.3f}"]
            try:
                jpg = subprocess.run(
                    ["ffmpeg", "-v", "error", *busca, "-i", str(path),
                     "-frames:v", "1", "-vf", f"scale=-2:{h}", "-q:v", "5",
                     "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                    capture_output=True, timeout=15,
                ).stdout
            except subprocess.TimeoutExpired:
                jpg = b""
            finally:
                _frame_slots.release()
            if jpg and guardar:
                with _quadros_lock:
                    _quadros_guardados[chave] = jpg
                    while len(_quadros_guardados) > QUADROS_GUARDADOS:
                        _quadros_guardados.pop(next(iter(_quadros_guardados)))
        if not jpg:
            self._json({"error": "sem quadro nesse tempo"}, 404)
            return
        self._hdr(200, "image/jpeg", len(jpg))
        self.wfile.write(jpg)

    def _recorte(self, query: str) -> None:
        """A pessoa no quadro `t` (segundos do corte) recortada, em PNG com alfa: os cartões da
        ferramenta Fundo a mostram sobre cada fundo antes de qualquer render. Um por vez, guardado
        em .preview_cache/recorte (o mesmo quadro do mesmo corte não é recortado de novo)."""
        try:
            t = max(0.0, float((parse_qs(query).get("t") or ["0"])[0]))
        except ValueError:
            self._json({"error": "t inválido"}, 400)
            return
        video = self._current_video()
        if not video:
            self._json({"error": "o projeto ainda não tem o corte"}, 404)
            return
        if not recorte_disponivel():
            self._json({"error": "o recorte precisa do onnxruntime, da instalação do kit: rode `uv sync` na pasta do kit"}, 409)
            return
        st = video.stat()
        pasta = self.root / ".preview_cache" / "recorte"
        arq = pasta / f"{round(t * 1000)}-{st.st_size}-{int(st.st_mtime)}.png"
        if not arq.is_file():
            with _recorte_lock:
                if not arq.is_file():  # outro pedido igual pode ter feito enquanto este esperava
                    pasta.mkdir(parents=True, exist_ok=True)
                    tmp = arq.with_name(arq.stem + ".tmp.png")
                    try:
                        recorte_png(video, t, tmp)
                        tmp.replace(arq)
                    except Exception as e:  # o motivo vai para a tela, em vez de um 500 mudo
                        tmp.unlink(missing_ok=True)
                        self._json({"error": f"o recorte falhou: {e}"}, 500)
                        return
                    for velho in sorted(pasta.glob("*.png"), key=lambda p: p.stat().st_mtime)[:-RECORTE_CACHE]:
                        velho.unlink(missing_ok=True)
        self._send_file(arq)

    def _frases(self, query: str) -> None:
        """As frases do Empilhado vêm do diretor do render, não de uma cópia: ele
        junta palavra curta, migra palavra atrasada e segura solo rápido demais, e
        duas versões dessas regras divergiriam. Os outros estilos agrupam por regra
        simples (ou medida na fonte) e o editor faz a conta sozinho."""
        if (parse_qs(query).get("estilo") or [""])[0] != "stacked":
            self._json({"error": "só o Empilhado vem do servidor"}, 400)
            return
        tr = self.root / "transcripts" / "cut.json"
        if not tr.is_file():
            self._json({"frases": []})
            return
        import caption_style  # mesma pasta deste arquivo
        try:
            cues = caption_style.build_cues(caption_style.load_words(tr), caption_style.idioma_da_transcricao(tr))
        except (OSError, ValueError, KeyError) as e:
            self._json({"error": f"transcrição ilegível ({e.__class__.__name__})"}, 500)
            return
        # `cue` leva o que a prévia precisa para desenhar a frase como o render:
        # tipo (pilha ou palavra sozinha), linhas, estilo e realce de cada linha
        self._json({"frases": [{"start": c["startMs"] / 1000, "end": c["endMs"] / 1000,
                                "text": " ".join(w["text"] for ln in c["lines"] for w in ln),
                                "cue": {"preset": c["preset"],
                                        "lines": [[w["text"] for w in ln] for ln in c["lines"]],
                                        "lineStyles": c["lineStyles"], "lineBoost": c["lineBoost"],
                                        "lineEmph": c["lineEmph"]}}
                               for c in cues]})

    def _upload(self, query: str) -> None:
        """Em pedaços, direto para o disco — nunca para a memória. Vídeo vai para a
        pasta dos vídeos (é material novo: o agente é avisado); imagem e áudio vão
        para <edit>/midia/ (são camadas do projeto, que o editor põe na linha do tempo).

        Com `total`, o arquivo chega em vários pedidos (o editor manda pedaços de 8 MB): o 1º (`inicio=0`)
        reserva o nome e recebe um `id`; os seguintes mandam `id` e `inicio`. Pedaço fora de ordem → 409 com
        `recebido`, de onde o editor continua. Sem `total`, o arquivo inteiro vem num pedido só (editor antigo)."""
        if self.upload_dir is None:
            self._fail(404, "envio desligado")
            return
        q = parse_qs(query)
        pid = (q.get("projeto") or [None])[0]
        if pid is not None and pid != pj.id_de(self.root):
            self._fail(409, "outro projeto foi aberto no editor; volte para este (Projetos) para enviar")
            return
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            self._fail(411, "Envio sem tamanho (Content-Length).")
            return
        try:
            length = int(raw_len)
            total = int((q.get("total") or [length])[0])
            inicio = int((q.get("inicio") or [0])[0])
        except ValueError:
            self._fail(400, "Tamanho inválido.")
            return
        em_pedacos = "total" in q
        if length <= 0 or total <= 0:
            self._fail(400, "Arquivo vazio.")
            return
        if em_pedacos and length > PEDACO_MAX:
            self._fail(413, "Pedaço grande demais.")
            return
        if length > total:
            self._fail(400, "Pedaço maior que o arquivo.")
            return
        envio_id = (q.get("id") or [""])[0]
        if envio_id:
            self._upload_pedaco(envio_id, inicio, length)
            return
        if inicio != 0:
            self._fail(400, "O envio começa do início.")
            return
        if total > self.max_upload:
            self._fail(413, f"Arquivo maior que o limite de {self.max_upload / 1024 ** 3:.1f} GB.")
            return
        name = clean_upload_name((q.get("name") or [""])[0])
        kind = upload_kind(name)
        if kind is None:
            self._fail(415, "Só vídeo, imagem ou áudio: mp4, mov, webm, jpg, png, webp, mp3, m4a, wav, ogg.")
            return
        # a foto ou o vídeo de um lugar da montagem (Trocar → Do aparelho) é mídia do projeto: vai
        # para midia/, e o agente não é avisado de material novo para cortar
        # o vídeo posto por cima (camada) também é mídia do projeto, não material para cortar
        para = (q.get("para") or [""])[0]
        para_lugar = para in ("montagem", "camada")
        if para == "montagem" and kind == "audio":
            self._fail(415, "Para um lugar da montagem: foto ou vídeo.")
            return
        folder = self.upload_dir if kind == "video" and not para_lugar else self.root / cam.MIDIA_DIR
        folder.mkdir(exist_ok=True)
        try:
            if total > shutil.disk_usage(folder).free - DISK_MARGIN:
                self._fail(507, "Sem espaço no computador para esse vídeo.")
                return
        except OSError:
            pass
        _limpar_envios_largados(pastas=(folder,))
        with _upload_lock:
            final = unique_path(folder, name)
            part = folder / f".{final.name}.parte"
            part.touch(exist_ok=False)  # reserva o nome antes de soltar a trava
        envio = {"part": part, "final": final, "total": total, "recebido": 0, "kind": kind,
                 "para_lugar": para_lugar, "folder": folder, "name": name, "quando": time.time(),
                 "trava": threading.Lock()}
        if not em_pedacos:
            envio["trava"].acquire()
            if self._gravar_pedaco(envio, length):
                self._envio_chegou(envio)
            return
        envio_id = secrets.token_urlsafe(12)
        with _upload_lock:
            _ENVIOS[envio_id] = envio
        envio["trava"].acquire()
        self._seguir_envio(envio_id, envio, length)

    def _upload_pedaco(self, envio_id: str, inicio: int, length: int) -> None:
        with _upload_lock:
            envio = _ENVIOS.get(envio_id)
        if envio is None:
            self._descartar_corpo()
            self._fail(404, "Esse envio não existe mais. Envie o arquivo de novo.")
            return
        if not envio["trava"].acquire(blocking=False):
            self._descartar_corpo()
            self._json({"error": "outro pedaço deste envio ainda está chegando", "recebido": envio["recebido"]}, 409)
            return
        if inicio != envio["recebido"] or inicio + length > envio["total"]:
            envio["trava"].release()
            self._descartar_corpo()
            self._json({"error": "pedaço fora de ordem", "recebido": envio["recebido"]}, 409)
            return
        self._seguir_envio(envio_id, envio, length)

    def _cancelar_envio(self, query: str) -> None:
        """O Cancelar do editor: o envio sai da lista e o .parte vai embora (sem isso, até 8 GB ficariam
        escondidos na pasta de vídeos). Um pedaço ainda chegando apaga o arquivo quando termina."""
        if self._corpo_pequeno() is None:
            return
        with _upload_lock:
            envio = _ENVIOS.pop((parse_qs(query).get("id") or [""])[0], None)
        if envio is None:
            self._json({"ok": True})
            return
        envio["cancelado"] = True
        if envio["trava"].acquire(timeout=5):
            try:
                envio["part"].unlink(missing_ok=True)
            finally:
                envio["trava"].release()
        self._json({"ok": True})

    def _seguir_envio(self, envio_id: str, envio: dict, length: int) -> None:
        """Grava um pedaço (com a trava do envio já pega) e, no último, entrega o arquivo."""
        try:
            if not self._gravar_pedaco(envio, length, apagar_se_falhar=False):
                return
            if envio.get("cancelado"):
                envio["part"].unlink(missing_ok=True)
                self._json({"error": "Envio cancelado"}, 409)
                return
            envio["quando"] = time.time()
            if envio["recebido"] < envio["total"]:
                self._json({"ok": True, "id": envio_id, "recebido": envio["recebido"]})
                return
            with _upload_lock:
                _ENVIOS.pop(envio_id, None)
            self._envio_chegou(envio)
        finally:
            envio["trava"].release()

    def _gravar_pedaco(self, envio: dict, length: int, apagar_se_falhar: bool = True) -> bool:
        """Anexa `length` bytes do pedido ao .parte. Falhou no meio: o envio de um pedido só é apagado; o em
        pedaços volta ao último pedaço inteiro, de onde o editor retoma."""
        part, inicio = envio["part"], envio["recebido"]
        try:
            with open(part, "r+b") as f:
                f.seek(inicio)
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        raise ConnectionError("o envio parou no meio")
                    f.write(chunk)
                    remaining -= len(chunk)
                f.truncate()
            envio["recebido"] = inicio + length
            return True
        except (OSError, ConnectionError) as e:
            if apagar_se_falhar:
                part.unlink(missing_ok=True)
            else:
                try:
                    with open(part, "r+b") as f:
                        f.truncate(inicio)
                except OSError:
                    pass
            sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] envio de {envio['name']} falhou: {e}\n")
            self.close_connection = True
            try:
                self._json({"error": "O envio parou no meio. Tente de novo.", "recebido": inicio}, 400)
            except OSError:
                pass
            return False

    def _envio_chegou(self, envio: dict) -> None:
        """O arquivo inteiro chegou: troca o .parte pelo nome final e avisa quem precisa saber."""
        part, final, kind, para_lugar, folder = (envio["part"], envio["final"], envio["kind"],
                                                 envio["para_lugar"], envio["folder"])
        length = envio["total"]
        try:
            os.replace(part, final)
        except OSError as e:
            part.unlink(missing_ok=True)
            self._fail(500, f"não consegui guardar o arquivo: {e}")
            return
        if kind != "video" or para_lugar:
            self._json({"ok": True, "file": final.name, "size": length, "tipo": kind,
                        "arquivo": f"{cam.MIDIA_DIR}/{final.name}"})
            return
        # O aviso para o agente: lista, porque dois envios seguidos não podem
        # virar um só. A skill lê, cuida e apaga — como os outros preview_*.json.
        signal = self.root / "preview_upload.json"
        item = {"file": final.name, "path": str(final), "size": length,
                "savedAt": time.strftime("%Y-%m-%d %H:%M:%S")}
        with _upload_lock:
            try:
                data = json.loads(signal.read_text(encoding="utf-8"))
                files = data.get("files") if isinstance(data, dict) else None
            except (OSError, json.JSONDecodeError):
                files = None
            files = (files if isinstance(files, list) else []) + [item]
            tmp = signal.with_suffix(".tmp")
            tmp.write_text(json.dumps({"type": "upload", "folder": str(folder), "files": files,
                                       "savedAt": item["savedAt"]}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(signal)
        self._json({"ok": True, "file": final.name, "size": length, "tipo": "video"})

    def _midia(self) -> None:
        """Imagens e áudios do projeto (o que chegou pelo Enviar)."""
        pasta = self.root / cam.MIDIA_DIR
        itens = []
        if pasta.is_dir():
            for f in sorted(pasta.iterdir(), key=lambda x: x.stat().st_mtime):
                tipo = upload_kind(f.name) if f.is_file() and not f.name.startswith(".") else None
                if tipo in ("imagem", "audio"):
                    itens.append({"arquivo": f"{cam.MIDIA_DIR}/{f.name}", "nome": f.name,
                                  "tipo": tipo, "bytes": f.stat().st_size})
        self._json({"midia": itens})

    def _montagem_midias(self) -> None:
        try:
            self._json({"opcoes": opcoes_da_montagem(self.root)})
        except MontagemInvalida as e:
            self._json({"error": str(e)}, 404)

    def _montagem_quadro(self, query: str) -> None:
        """Um quadro de uma mídia da montagem: as miniaturas do Trocar e a tira do Trecho."""
        q = parse_qs(query)
        try:
            t = max(0.0, float((q.get("t") or ["0"])[0]))
            h = min(1080, max(60, int(float((q.get("h") or ["240"])[0]))))
        except ValueError:
            self._json({"error": "t ou h inválido"}, 400)
            return
        try:
            p = arquivo_da_montagem(self.root, (q.get("midia") or [""])[0])
        except MontagemInvalida as e:
            self._json({"error": str(e)}, 404)
            return
        self._quadro_jpg(p, 0.0 if p.suffix.lower() in cam.IMAGE_EXTS else t, h, guardar=True)

    def _montagem_video(self, query: str) -> None:
        """O clipe original de um lugar, para o Trecho tocar a janela escolhida (com Range)."""
        try:
            p = arquivo_da_montagem(self.root, (parse_qs(query).get("midia") or [""])[0])
        except MontagemInvalida as e:
            self._json({"error": str(e)}, 404)
            return
        if p.suffix.lower() not in VIDEO_EXTS:
            self._json({"error": "só o clipe de vídeo tem trecho"}, 400)
            return
        self._send_file(p)

    def _batida(self, query: str) -> None:
        """A grade de batida de uma música de <edit>/midia/ (o editor pergunta de novo enquanto calcula)."""
        rel = (parse_qs(query).get("arquivo") or [""])[0]  # o parse_qs já decodifica
        if not rel.startswith(cam.MIDIA_DIR + "/") or Path(rel).suffix.lower() not in cam.AUDIO_EXTS:
            self._json({"error": "arquivo: um áudio de midia/"}, 400)
            return
        p = self._safe(self.root, rel)
        if not p or not p.is_file():
            self._json({"error": f"não encontrado: {rel}"}, 404)
            return
        r = grade_da_musica(p, self.root)
        self._json(r, {"pronta": 200, "falhou": 500}.get(r["estado"], 202))

    # ---- biblioteca (pacotes.py) ----
    def _biblioteca(self) -> pk.Pacotes | None:
        cls = type(self)
        if cls.pacotes is None:
            try:
                cls.pacotes = pk.Pacotes.do_ambiente()
            except pk.PacoteErro as e:
                self._json({"error": f"biblioteca: {e}"}, 500)
                return None
        return cls.pacotes

    def _pacotes_lista(self, query: str) -> None:
        pac = self._biblioteca()
        if pac:
            tipo = (parse_qs(query).get("tipo") or [None])[0]
            self._json({"pacotes": pac.listar(tipo=tipo)})

    def _pacote_previa(self, query: str) -> None:
        pac = self._biblioteca()
        if not pac:
            return
        try:
            self._send_file(pac.previa((parse_qs(query).get("id") or [""])[0]))
        except (pk.PacoteIndisponivel, pk.PacoteCorrompido) as e:
            self._json({"error": str(e)}, 502)
        except pk.PacoteErro as e:
            self._json({"error": str(e)}, 404)

    def _voz_previa(self, query: str) -> None:
        """O trecho com o efeito de voz (meio segundo antes e depois), guardado por efeito e janela."""
        q = parse_qs(query)
        efeito = (q.get("efeito") or [""])[0]
        if efeito not in vze.EFEITOS:
            self._json({"error": "efeito de voz desconhecido"}, 404)
            return
        try:
            inicio = float((q.get("inicio") or ["x"])[0])
            duracao = float((q.get("duracao") or ["x"])[0])
        except ValueError:
            inicio = duracao = -1.0
        if not (0 <= inicio < 6 * 3600 and 0.1 <= duracao <= 120):
            self._json({"error": "trecho da voz inválido"}, 400)
            return
        video = gr._video(self.root)
        if not video.is_file():
            self._json({"error": "o projeto ainda não tem o corte"}, 404)
            return
        pasta = self.root / vze.PASTA
        pasta.mkdir(exist_ok=True)
        alvo = pasta / f"previa-{efeito}-{round(inicio * 1000)}-{round(duracao * 1000)}-{int(video.stat().st_mtime)}.wav"
        if not alvo.is_file():
            for velho in pasta.glob("previa-*.wav"):
                velho.unlink(missing_ok=True)
            try:
                vze.previa(self.root, efeito, inicio, duracao, alvo, video)
            except (subprocess.CalledProcessError, OSError) as e:
                self._json({"error": f"a prévia da voz não saiu: {e}"}, 500)
                return
        self._send_file(alvo)

    def _sfx_usar(self) -> None:
        """Um efeito sonoro do kit na pasta das camadas do projeto: o editor o põe na agulha."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._fail(400, "invalid Content-Length")
            return
        if length > 10_000:
            self._fail(413, "pedido grande demais")
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            body = None
        sid = body.get("id") if isinstance(body, dict) else None
        item = next((x for x in es.todos() if x["id"] == sid), None) if isinstance(sid, str) else None
        if item is None:
            self._json({"error": "efeito sonoro desconhecido"}, 404)
            return
        try:
            dest = es.usar(self.root, sid)
        except pk.PacoteErro as e:
            self._json({"error": str(e)}, 502)
            return
        self._json({"arquivo": f"{cam.MIDIA_DIR}/{dest.name}", "id": sid, "nome": item["nome"], "nomeEn": item["nome_en"],
                    "duracao": item["duracao"], "volume": item["volume"], "golpe": item["golpe"]})

    def _pacote_arquivo(self, resto: str) -> None:
        """Um arquivo de filtro/transição, da pasta aberta no cache (baixa e abre na 1ª vez)."""
        pid, _, rel = resto.partition("/")
        rel = unquote(rel)
        pac = self._biblioteca()
        if not pac:
            return
        try:
            pasta = pac.aberto(pid)
        except (pk.PacoteIndisponivel, pk.PacoteCorrompido) as e:
            self._json({"error": str(e)}, 502)
            return
        except pk.PacoteErro as e:
            self._json({"error": str(e)}, 404)
            return
        p = self._safe(pasta, rel) if rel and not rel.startswith(".") else None
        if not p or p == pasta.resolve():
            self._json({"error": "bad path"}, 400)
            return
        self._send_file(p)

    def _pacote_post(self, path: str) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._fail(400, "invalid Content-Length")
            return
        if length > 10_000:
            self._fail(413, "pedido grande demais")
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("id"), str):
            self._json({"error": "pedido sem id"}, 400)
            return
        pac = self._biblioteca()
        if not pac:
            return
        try:
            if path.endswith("/favorito"):
                pac.favorito(body["id"], bool(body.get("on", True)))
                self._json({"ok": True})
                return
            p = pac.pacote(body["id"])
            dest = pac.obter(p["id"], para=self.root / cam.MIDIA_DIR)
        except (pk.PacoteIndisponivel, pk.PacoteCorrompido) as e:
            self._json({"error": str(e)}, 502)
            return
        except pk.PacoteErro as e:
            self._json({"error": str(e)}, 404)
            return
        self._json({"arquivo": f"{cam.MIDIA_DIR}/{dest.name}", "id": p["id"], "nome": p["nome"],
                    "nomeEn": p.get("nome_en"), "duracao": p["duracao"]})

    # ---- dynamic bits ----
    # ---- projetos (a tela Projetos do editor) ----
    def _projetos(self) -> None:
        """Os cartões: os projetos da lista (~/.cutmind/projetos.json), o mais mexido primeiro."""
        atual = pj.id_de(self.root)
        itens = []
        for x in pj.lista():
            try:
                r = pj.resumo(Path(x["edit"]))
            except OSError:
                continue
            r["aberto"] = r["id"] == atual
            itens.append(r)
        if not any(r["aberto"] for r in itens):
            # o aberto sempre aparece, mesmo quando ~/.cutmind não deixou gravar a lista
            try:
                r = pj.resumo(self.root)
                r["aberto"] = True
                itens.append(r)
            except OSError:
                pass
        itens.sort(key=lambda r: r["mudou"], reverse=True)
        self._json({"aberto": atual, "projetos": itens})

    def _projeto_capa(self, query: str) -> None:
        pid = (parse_qs(query).get("id") or [""])[0]
        edit = self.root if pid == pj.id_de(self.root) else pj.por_id(pid)
        if not edit:
            self._json({"error": "projeto fora da lista"}, 404)
            return
        with _frame_slots:
            p = pj.capa(edit)
        if p:
            self._send_file(p)
        else:
            self._json({"error": "projeto sem vídeo ainda"}, 404)

    def _corpo_pequeno(self, limite: int = 10_000) -> dict | None:
        """O JSON de um pedido curto; None quando já respondeu com o erro."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._fail(400, "invalid Content-Length")
            return None
        if length > limite:
            self._fail(413, "pedido grande demais")
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            body = None
        if not isinstance(body, dict):
            self._json({"error": "pedido inválido"}, 400)
            return None
        return body

    # ---- melhorar voz (melhorar_voz.py) ----
    def _melhorar(self) -> None:
        s = mv.situacao(self.root)
        a = andamento_preparo(self.root)
        if a and (a.get("vivo") or a.get("etapa") == "falhou"):
            s["andamento"] = {k: a.get(k) for k in ("etapa", "n", "de", "texto", "fracao", "erro", "vivo")}
            if a.get("vivo"):
                s["preparo"] = "preparando"
        salvo = pend.ler(self.root).get("melhorar")
        if isinstance(salvo, dict):
            s["pendente"] = salvo  # salvo no editor; o Baixar aplica
        self._json(s)

    def _conferir(self) -> None:
        """A pergunta antes do Salvar das tomadas: o que ficaria desalinhado (aplicar_corte.conferir).
        Não grava nada; o editor mostra os avisos e manda o Salvar com `confirmado` se a pessoa mantiver."""
        body = self._corpo_pequeno(MAX_JSON_BYTES)
        if body is None:
            return
        pedido = body.get("edl")
        if not isinstance(pedido, dict) or not isinstance(pedido.get("ranges"), list):
            self._json({"error": "pedido sem as tomadas"}, 400)
            return
        try:
            self._json({"avisos": ac.conferir_projeto(self.root, pedido)})
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"conferência do corte não rodou: {e}", file=sys.stderr, flush=True)
            self._json({"avisos": []})

    # ---- atualização do CutMind (atualizar.py) ----
    def _atualizacao(self) -> None:
        """O que a procura achou (sem esperar a rede), o interruptor e o clique que espera um trabalho."""
        r = dict(resultado_atual() or {"nova": False, "procurando": True})
        r["ligado"] = atu.ligado()
        if ATUALIZACAO["pedido"]:
            r["esperando"] = _esperando(self.root)
        self._json(r)

    def _atualizar(self) -> None:
        """O clique em Atualizar: no meio de um trabalho ou com o agente trabalhando, espera e começa
        sozinho depois (o Papory faz o mesmo com o ditado); senão, lança agora."""
        if self._corpo_pequeno() is None:
            return
        r = resultado_atual() or {}
        if copia_de_desenvolvimento() or r.get("motivo") == "desenvolvimento":
            self._json({"error": "esta é uma cópia de desenvolvimento do CutMind: atualize com git"}, 409)
            return
        if not r.get("nova"):
            self._json({"error": "não há versão nova do CutMind"}, 409)
            return
        esperando = _esperando(self.root)
        if esperando:
            ATUALIZACAO["pedido"] = True
            self._json({"ok": True, "esperando": esperando, "versao": r.get("versao")})
            return
        self._json({"ok": True, "reiniciar": bool(r.get("reiniciar")), "versao": r.get("versao")})
        comecar_atualizacao(self.servidor_principal or self.server, self.root, r)

    def _atualizacao_config(self) -> None:
        """O interruptor "Procurar atualizações" do painel ?: grava e procura de novo, sem prender a página."""
        body = self._corpo_pequeno()
        if body is None:
            return
        if not isinstance(body.get("procurar"), bool):
            self._json({"error": "pedido inválido"}, 400)
            return
        atu.ligar(None, body["procurar"])

        def de_novo() -> None:
            ATUALIZACAO["resultado"] = atu.procurar(forcar=True)

        threading.Thread(target=de_novo, daemon=True).start()
        self._json({"ok": True, "ligado": body["procurar"]})

    def _ocupado(self, tipo: str | None) -> None:
        """A resposta a um pedido que mexeria no projeto com um trabalho rodando nele."""
        if tipo == "gerar":
            self._json({"error": "o vídeo final está sendo gerado: espere terminar"}, 409)
        else:
            self._json({"error": "o corte ainda está sendo refeito: espere terminar para salvar de novo"}, 409)

    def _trabalho(self, a: dict | None) -> dict | None:
        """O andamento do trabalho com o erro (a mensagem do programa, em português) no idioma do editor."""
        if a and a.get("erro"):
            return {**a, "erro": idm.traduzir(a["erro"], self._idioma())}
        return a

    def _pendente(self) -> None:
        """O que o Baixar ainda tem de refazer (gerar.o_que_falta) e o arquivo que ele entrega."""
        try:
            self._json({"falta": gr.o_que_falta(self.root), "entrega": gr.entrega(self.root)})
        except (OSError, ValueError) as e:
            self._json({"error": f"não consegui ver o que falta no vídeo: {e}"}, 500)

    def _gerar(self) -> None:
        """O Baixar: sem nada por refazer, diz o arquivo; senão monta o vídeo final num processo à parte."""
        if self._corpo_pequeno() is None:
            return
        if not gr._video(self.root).is_file():
            self._json({"error": "o projeto ainda não tem o corte"}, 409)
            return
        if tb.vivo(self.root):
            self._ocupado(tb.vivo(self.root))
            return
        if agente_trabalhando(self.root):
            self._json({"error": "o agente está trabalhando neste projeto: espere ele terminar para gerar o vídeo"}, 409)
            return
        try:
            falta = gr.o_que_falta(self.root)
        except (OSError, ValueError) as e:
            self._json({"error": f"não consegui ver o que falta no vídeo: {e}"}, 500)
            return
        if not falta:
            self._json({"ok": True, "pronto": True, "entrega": gr.entrega(self.root)})
            return
        pasta = tb.pasta(self.root)
        pasta.mkdir(parents=True, exist_ok=True)
        if not tb.iniciar(self.root, "gerar", comando_gerar(self.root, pasta / "andamento.json")):
            self._ocupado(tb.vivo(self.root))
            return
        self._json({"ok": True, "trabalho": "gerar", "falta": falta})

    def _pronto(self) -> None:
        """O "Pronto, Claude segue": junta os pedidos que esperavam, o que o editor já aplicou sozinho
        (ajustes_feitos.json) e a fase num pronto.json, que acorda o agente (watch_edits.py) uma vez só."""
        if self._corpo_pequeno() is None:
            return
        if agente_trabalhando(self.root):
            self._json({"error": "o agente já está trabalhando neste projeto: espere ele terminar"}, 409)
            return
        try:
            st = json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        out = self.root / "pronto.json"
        try:  # um Pronto que o agente ainda não pegou: os pedidos somam
            antes = json.loads(out.read_text(encoding="utf-8")).get("pedidos") or []
        except (OSError, ValueError, AttributeError):
            antes = []
        try:
            feitos = json.loads((self.root / "ajustes_feitos.json").read_text(encoding="utf-8")).get("feitos") or []
        except (OSError, ValueError, AttributeError):
            feitos = []
        pedidos = [*antes, *pend.levar_pedidos(self.root)]
        pronto = {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "fase": int(st.get("phase") or 1),
                  "pedidos": pedidos, "feitos": feitos}
        if (self.root / "preview_edits.json").exists():
            pronto["legado"] = True
        tmp = out.with_suffix(".tmp")
        tmp.write_bytes(json.dumps(pronto, ensure_ascii=False, indent=2).encode("utf-8"))
        tmp.replace(out)
        self._json({"ok": True, "pedidos": len(pedidos), "vigia": bool(st.get("vigia"))})

    def _melhorar_preparar(self) -> None:
        if self._corpo_pequeno() is None:
            return
        try:
            mv.video(self.root)
        except mv.VozErro as e:
            self._json({"error": str(e)}, 409)
            return
        if mv.situacao(self.root)["preparo"] == "pronto":
            self._json({"ok": True, "pronto": True})
            return
        try:
            novo = iniciar_preparo(self.root)
        except OSError as e:
            self._json({"error": f"não consegui começar o preparo: {e}"}, 500)
            return
        self._json({"ok": True, "novo": novo, "andamento": andamento_preparo(self.root)})

    def _modelo_post(self, path: str) -> None:
        """Salvar o estilo deste vídeo como modelo, ou apagar um (~/.cutmind/modelos)."""
        body = self._corpo_pequeno(20_000)
        if body is None:
            return
        if path.endswith("/apagar"):
            if md.apagar(body.get("id")):
                self._json({"ok": True})
            else:
                self._json({"error": "modelo não encontrado"}, 404)
            return
        try:
            m = md.salvar(body.get("modelo"))
        except md.ModeloInvalido as e:
            self._json({"error": f"modelo: {e}"}, 400)
            return
        except OSError as e:
            self._json({"error": f"não consegui gravar o modelo: {e}"}, 500)
            return
        self._json({"ok": True, "modelo": m})

    def _montagens_post(self, path: str) -> None:
        """Guardar a montagem aberta como modelo de montagem (com um nome), ou apagar um modelo da
        pessoa (~/.cutmind/montagens). O que vai no modelo sai do projeto gravado, não do pedido."""
        body = self._corpo_pequeno()
        if body is None:
            return
        if path.endswith("/apagar"):
            if mg.apagar(body.get("id")):
                self._json({"ok": True})
            else:
                self._json({"error": "modelo não encontrado (os que vêm com o kit não se apagam)"}, 404)
            return
        try:
            m = mt.capturar(self.root, str(body.get("nome") or ""))
            avisos = m.pop("avisos")
            m = mg.salvar(m)
        except (mt.ErroMontagem, mg.MontagemInvalida, cam.CamadasInvalidas, ef.EfeitosInvalidos) as e:
            self._json({"error": f"modelo de montagem: {e}"}, 400)
            return
        except (OSError, ValueError) as e:
            self._json({"error": f"não consegui guardar o modelo: {e}"}, 500)
            return
        self._json({"ok": True, "modelo": mg.resumo(m), "avisos": avisos})

    def _mural_lista(self, query: str) -> None:
        """A aba Da comunidade do painel: uma página da grade do mural (mural.py)."""
        try:
            self._json(mu.lista((parse_qs(query).get("antes") or [None])[0]))
        except mu.MuralIndisponivel as e:
            self._json({"error": str(e)}, 502)

    def _mural_compartilhar(self, query: str) -> None:
        """O Compartilhar de um modelo da pessoa: redireciona para a página de publicar do mural com
        o modelo no fragmento. É um link (não um pedido do editor) para abrir em outra aba sem
        esbarrar no bloqueio de janela que vem depois de um fetch."""
        try:
            destino = mu.link_publicar((parse_qs(query).get("id") or [""])[0])
        except (mu.MuralIndisponivel, mu.MuralRecusou) as e:
            corpo = f"Não deu para compartilhar: {e}.".encode()
            self._hdr(404 if isinstance(e, mu.MuralRecusou) else 502, "text/plain; charset=utf-8", len(corpo))
            self.wfile.write(corpo)
            return
        self._hdr(303, "text/plain; charset=utf-8", 0, {"Location": destino, "Referrer-Policy": "no-referrer"})

    def _mural_pegar(self) -> None:
        """Da comunidade: traz o modelo do mural para os da pessoa (~/.cutmind/montagens)."""
        body = self._corpo_pequeno()
        if body is None:
            return
        try:
            m = mu.pegar(body.get("codigo"))
        except (mu.MuralRecusou, mg.MontagemInvalida) as e:
            self._json({"error": str(e)}, 400 if isinstance(e, mg.MontagemInvalida) else 404)
            return
        except mu.MuralIndisponivel as e:
            self._json({"error": str(e)}, 502)
            return
        except OSError as e:
            self._json({"error": f"não consegui guardar o modelo: {e}"}, 500)
            return
        self._json({"ok": True, "modelo": mg.resumo(m)})

    def _projeto_post(self, path: str) -> None:
        body = self._corpo_pequeno()
        if body is None:
            return
        if path.endswith("/abrir"):
            # só pelo id da lista: ninguém abre pela rede uma pasta que não esteja nela
            edit = pj.por_id(body.get("id"))
            if not edit or not (edit / "state.json").is_file():
                self._json({"error": "projeto não encontrado"}, 404)
                return
        else:
            # pasta nova ao lado da pasta de vídeos do projeto aberto (Downloads/<nome>/edit)
            try:
                edit = pj.criar(self.root.parent.parent, str(body.get("nome") or ""),
                                montagem=body.get("tipo") == "montagem")
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            except OSError as e:
                self._json({"error": f"não consegui criar a pasta: {e}"}, 500)
                return
        self._trocar(edit)
        self._json({"ok": True, "id": pj.id_de(edit), "pasta": edit.parent.name})

    def _trocar(self, edit: Path) -> None:
        """O editor passa a mostrar outro projeto. O código do celular não muda (fica na
        memória); o agente sabe pelo ~/.cutmind/aberto.json, que o watch_edits.py vigia."""
        cls = type(self)
        with _troca_lock:
            cls.root = edit.resolve()
            if not cls.upload_dir_fixo:
                cls.upload_dir = cls.root.parent
            try:
                pj.registrar(cls.root)
                pj.marcar_aberto(cls.root)
            except OSError as e:
                sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] lista de projetos: {e}\n")

    def _state(self) -> None:
        state_p = self.root / "state.json"
        state: dict = {}
        try:
            if state_p.exists():
                state = json.loads(state_p.read_text())
        except json.JSONDecodeError:
            state = {"error": "state.json inválido"}
        except OSError as e:
            # A read that is refused (macOS privacy, or a permission change made
            # after startup) used to raise here and 500 the endpoint, which the
            # UI shows as its ordinary waiting screen — indistinguishable from
            # "the cut is not rendered yet". Say what happened instead.
            state = {"error": f"sem permissão para ler state.json: {e}"}
        # attach small data files + mtimes so the UI hot-reloads on change
        mtimes: dict[str, float] = {}
        for key in ("video", "finalVideo", "entregaVideo", "edl", "captions", "editData"):
            rel = state.get(key)
            if not rel:
                continue
            p = self._safe(self.root, rel)
            if p and p.exists():
                mtimes[key] = p.stat().st_mtime
        # a entrega acelerada só vale se for mais nova que os trechos (o Baixar compara)
        vel_p = self.root / "velocidade.json"
        if vel_p.exists():
            mtimes["velocidade"] = vel_p.stat().st_mtime
        edl = None
        rel = state.get("edl") or "edl.json"
        p = self._safe(self.root, rel)
        if p and p.exists():
            try:
                edl = json.loads(p.read_text())
            except json.JSONDecodeError:
                pass
        # um preview_edits.json é de um editor anterior: espera o Pronto (o agente o aplica como antes)
        edits_p = self.root / "preview_edits.json"
        # os lugares da montagem salvos e ainda não refeitos: o editor os mostra trocados até o Baixar refazer;
        # e a montagem nova pedida (Usar um modelo), que o editor mostra como "montando"
        mont = pend.ler(self.root).get("montagem")
        mont = mont if isinstance(mont, dict) else {}
        pendente, nova = mont.get("lugares") or None, mont.get("usar") or None
        formato_pendente = mont.get("formato") or None
        video = self._current_video()
        self._json({
            "state": state,
            # o editor recarrega quando este id muda (outro projeto aberto, aqui ou no celular)
            "projeto": {"id": pj.id_de(self.root)},
            "edl": edl,
            "mtimes": mtimes,
            "videoDuration": probe_duration(video) if video else 0,
            "hasPendingEdits": edits_p.exists(),
            "pedidos": len(pend.pedidos(self.root)),
            "agenteTrabalhando": agente_trabalhando(self.root),
            "montagemPendente": pendente,
            "montagemNova": nova,
            "formatoPendente": formato_pendente,
            "trabalho": self._trabalho(trabalho_recente(self.root)),
            "now": time.time(),
        })

    def _waveform(self) -> None:
        video = self._current_video()
        if not video:
            self._json({"error": "sem vídeo ainda"}, 404)
            return
        out = self.root / ".preview_cache" / "waveform.json"
        stale = True
        if out.exists():
            try:
                stale = json.loads(out.read_text()).get("srcMtime") != video.stat().st_mtime
            except json.JSONDecodeError:
                pass
        if stale:
            gen_waveform(video, out)
        self._send_file(out)

    def _thumbs(self, name: str) -> None:
        video = self._current_video()
        if not video:
            self._json({"error": "sem vídeo ainda"}, 404)
            return
        out_dir = self.root / ".preview_cache" / "thumbs"
        meta = out_dir / "meta.json"
        with _thumb_lock:
            stale = True
            if meta.exists():
                try:
                    stale = json.loads(meta.read_text()).get("srcMtime") != video.stat().st_mtime
                except json.JSONDecodeError:
                    pass
            if stale:
                gen_thumbs(video, out_dir)
        p = self._safe(out_dir, name)
        self._send_file(p) if p else self._json({"error": "bad path"}, 400)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # quiet


def _check_access(root: Path) -> None:
    """Fail loudly, at startup, when the edit dir cannot be read or written.

    Without this the failure is silent in the worst way: the server starts, the
    UI opens on its waiting screen, and it waits forever for a state.json that
    the skill was never allowed to write. The user sees a working preview with
    no video and nothing to act on.

    The errno is the diagnosis on macOS. Its privacy layer (TCC) guards
    ~/Documents, ~/Desktop, ~/Downloads and iCloud Drive, and denies with
    EPERM (1) "Operation not permitted" — an app the user never granted Files
    and Folders access to gets that even though the file permissions are fine.
    Ordinary permission or ownership problems come back as EACCES (13). The two
    need completely different fixes, so do not merge the messages.
    """
    probe = root / ".cutmind_write_probe"
    err: OSError | None = None
    try:
        probe.write_text("ok")
        probe.unlink()
        for _ in root.iterdir():
            break
    except OSError as exc:
        # Bind outside the handler: Python deletes the `except` name on exit.
        err = exc
    if err is None:
        return

    where = f"{root}"
    if getattr(err, "errno", None) == 1 and sys.platform == "darwin":
        raise SystemExit(
            f"sem permissão para escrever em {where}\n"
            "\n"
            "No macOS isso é a proteção de privacidade do sistema, não a permissão\n"
            "do arquivo: ~/Documents, ~/Desktop, ~/Downloads e o iCloud Drive são\n"
            "protegidos, e o app precisa ser autorizado uma vez.\n"
            "\n"
            "  Ajustes do Sistema → Privacidade e Segurança → Arquivos e Pastas\n"
            "  (ou Acesso Total ao Disco) → ligue para o Claude / o Terminal\n"
            "\n"
            "Depois feche e reabra o app.\n"
            "\n"
            "SE AS PERMISSÕES JÁ ESTIVEREM LIGADAS: reinicie o Mac. O cache de\n"
            "permissões do macOS às vezes fica preso mostrando a chave ativa sem\n"
            "conceder o acesso, e só o reinício resolve. (Visto em produção — foi\n"
            "exatamente isso, e nenhuma mexida nos Ajustes tinha efeito.)\n"
            "\n"
            "Se preferir não lidar com permissão, mova a pasta dos vídeos para fora\n"
            "dessas três pastas — por exemplo ~/Videos."
        )
    raise SystemExit(
        f"sem permissão para ler/escrever em {where}: {err}\n"
        "Confira o dono e as permissões da pasta."
    )


def add_network_args(ap: argparse.ArgumentParser) -> None:
    """As opções de rede, iguais aqui e no start_preview.py."""
    ap.add_argument("--host", default="127.0.0.1",
                    help="127.0.0.1 = só este computador (padrão); 0.0.0.0 = abre para a "
                         "rede, e o celular entra pelo link com código")
    ap.add_argument("--allow-host", action="append", default=[], metavar="NOME",
                    help="nome liberado no cabeçalho Host além de IP e localhost; "
                         "começando com ponto vale o sufixo (ex.: .ts.net)")
    ap.add_argument("--upload-dir", type=Path, default=None,
                    help="para onde vão os vídeos enviados pelo editor (padrão: a pasta "
                         "dos vídeos, pai do --root)")
    ap.add_argument("--max-upload-gb", type=float, default=8.0)
    ap.add_argument("--tunel-port", type=int, default=None, metavar="PORTA",
                    help="abre uma 2ª porta (só em 127.0.0.1) para o túnel https (tunel.py): nela o código é "
                         "sempre cobrado, porque pelo túnel tudo chega como este computador")


def main() -> None:
    ap = argparse.ArgumentParser(description="CutMind preview interface server")
    ap.add_argument("--root", type=Path, required=True, help="the session <edit> dir")
    ap.add_argument("--port", type=int, default=4820)
    add_network_args(ap)
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.exists():
        raise SystemExit(f"edit dir not found: {root}")
    _check_access(root)
    if not (APP_DIR / "celular.html").exists():
        raise SystemExit(f"app not found at {APP_DIR}")
    upload_dir = (args.upload_dir or root.parent).resolve()
    if not upload_dir.is_dir():
        raise SystemExit(f"pasta de envio não existe: {upload_dir}")

    Handler.root = root
    Handler.allow_hosts = tuple(args.allow_host)
    Handler.upload_dir = upload_dir
    Handler.upload_dir_fixo = args.upload_dir is not None
    Handler.max_upload = int(args.max_upload_gb * 1024 ** 3)
    Handler.bind_host = args.host
    if not is_local_bind(args.host):
        Handler.token = ensure_token(root)
    if args.tunel_port:
        Handler.porta_tunel = args.tunel_port
        Handler.arquivo_codigo_tunel = tn.arquivo_codigo(atu.casa())
        tn.codigo(atu.casa())
    _limpar_envios_largados(pastas=(upload_dir, root / cam.MIDIA_DIR))
    try:  # a tela Projetos lista este projeto, e o agente sabe qual está aberto
        pj.registrar(root)
        pj.marcar_aberto(root)
    except OSError as e:
        print(f"aviso: lista de projetos ({pj.casa()}) não gravada: {e}", flush=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    Handler.servidor_principal = srv
    print(f"CutMind preview -> http://{pc_host(args.host)}:{args.port}  (root: {root})", flush=True)
    if ESPERAS_DLL:
        print(f"as DLLs da instalação nova estavam presas: esperei {ESPERAS_DLL * 0.5:.1f} s", flush=True)
    threading.Thread(target=vigiar_atualizacao, args=(srv, Handler), daemon=True, name="atualizacao").start()
    if args.tunel_port:
        srv_tunel = ThreadingHTTPServer(("127.0.0.1", args.tunel_port), Handler)
        srv_tunel.remoto = True
        threading.Thread(target=srv_tunel.serve_forever, daemon=True, name="tunel").start()
        print(f"porta do túnel: 127.0.0.1:{args.tunel_port} (o código é sempre cobrado nela)", flush=True)
    if Handler.token and not is_local_bind(args.host):
        print("Aberto para a rede: só entra quem tem o link com o código.", flush=True)
        for u in phone_urls(args.host, args.port, Handler.token):
            print(f"  celular ({u['label']}): {u['url']}", flush=True)
            if rede_publica(u["ip"]):
                print(AVISO_REDE_PUBLICA, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
