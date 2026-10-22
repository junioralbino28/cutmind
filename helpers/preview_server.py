"""CutMind preview server — serves the standard editing interface + session media.

The interface app (assets/preview/) is IMMUTABLE and lives in the skill repo;
per-session it is fed by data only:
  - <edit>/state.json          written by the skill (phase, files, message)
  - <edit>/edl.json            the cut (segments shown/trimmed on the timeline)
  - <edit>/cut.mp4             current render (played + scrubbed)
  - <edit>/preview_edits.json  WRITTEN BY THE UI when the user saves timeline
                               adjustments — the skill reads, validates, applies
                               and re-renders. The UI never touches edl.json.
  - <edit>/preview_style.json  WRITTEN BY THE UI at the Fase 1 → Fase 2 gate:
                               editing style, caption style, edit elements.

Routes:
  /, /celular           the editor (assets/preview/celular.html): one page for the
                        computer and the phone, laid out by the screen width
  /classico             the old desktop editor (index.html), until the switch is approved
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
  /api/state    GET     state.json + mtimes (UI polls this to hot-reload)
  /api/celular  GET     só no computador: links + QR code para abrir no celular
  /api/midia    GET     imagens e áudios do projeto (<edit>/midia/)
  /api/save     POST    body → <edit>/preview_edits.json (atomic), or
                        <edit>/preview_style.json when body.type=="style-setup";
                        com `camadas`, grava também <edit>/camadas.json (camadas.py);
                        com `efeitos`, <edit>/efeitos.json (efeitos.py)
  /api/upload   POST    ?name=<arquivo>, corpo = o arquivo. Vídeo → pasta dos
                        vídeos (pai do <edit>) + aviso em <edit>/preview_upload.json;
                        imagem e áudio → <edit>/midia/ (camadas do projeto)
  /api/pacotes  GET     ?tipo=trilha: a biblioteca do kit (pacotes.py), com o que já
                        está baixado neste computador e os favoritos
  /gen/pacote-previa?id=  a prévia de um pacote (baixa na primeira vez)
  /gen/pacote/<id>/<arq>  um arquivo de filtro/transição, da pasta aberta no
                        cache (baixa e abre o zip na primeira vez)
  /api/pacotes/usar      POST {id}: baixa o pacote e copia para <edit>/midia/
  /api/pacotes/favorito  POST {id, on}: favorito fica no cache, mesmo cheio

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
from urllib.parse import parse_qs, unquote

import camadas as cam  # mesma pasta deste arquivo
import efeitos as ef  # mesma pasta deste arquivo
import pacotes as pk  # mesma pasta deste arquivo

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
_frame_slots = threading.BoundedSemaphore(2)  # ffmpeg de quadro avulso ao mesmo tempo


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
    return [{"label": label, "url": f"http://{ip}:{port}/c?t={token}"}
            for label, ip in phone_hosts(bind_host)]


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
    root: Path  # set on the class by main()
    token: str | None = None  # só existe quando o servidor abre para a rede
    allow_hosts: tuple[str, ...] = ()
    upload_dir: Path | None = None
    max_upload: int = 8 * 1024 ** 3
    bind_host: str = "127.0.0.1"
    pacotes: pk.Pacotes | None = None  # a biblioteca; nasce no primeiro pedido
    protocol_version = "HTTP/1.1"
    # Envio parado (celular saiu do Wi-Fi) não segura uma thread e um .parte para sempre.
    timeout = 300

    # ---- quem pode entrar ----
    def _client_is_local(self) -> bool:
        return self.client_address[0] in LOCAL_CLIENTS

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
        for allowed in self.allow_hosts:
            a = allowed.lower()
            if (a.startswith(".") and (name.endswith(a) or name == a[1:])) or name == a:
                return True
        return False

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

    def _token_ok(self, value: str | None) -> bool:
        return bool(self.token and value and hmac.compare_digest(value, self.token))

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

    def _deny(self, code: int, msg: str, path: str) -> None:
        sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] negado {code} "
                         f"{self.client_address[0]} {self.command} {path}\n")
        self.close_connection = True  # um POST negado deixa o corpo sem ler
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
        body = json.dumps({"error": msg}, ensure_ascii=False).encode()
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
        # um editor só: o mesmo no computador e no celular, arrumado pela largura da tela;
        # a desktop antiga fica em /classico até a troca ser aprovada
        if path in ("/", "/celular"):
            self._send_file(APP_DIR / "celular.html")
        elif path in ("/classico", "/index.html"):
            self._send_file(APP_DIR / "index.html")
        elif path == "/c":
            self._enter(query)
        elif path == "/api/celular":
            self._celular_info()
        elif path == "/gen/frame":
            self._frame(query)
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
        elif path == "/api/midia":
            self._midia()
        elif path == "/api/pacotes":
            self._pacotes_lista(query)
        elif path == "/gen/pacote-previa":
            self._pacote_previa(query)
        elif path.startswith("/gen/pacote/"):
            self._pacote_arquivo(path[len("/gen/pacote/"):])
        else:
            self._json({"error": "unknown route"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path, _, query = self.path.partition("?")
        if not self._gate(path):
            return
        if path == "/api/upload":
            self._upload(query)
            return
        if path in ("/api/pacotes/usar", "/api/pacotes/favorito"):
            self._pacote_post(path)
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
        body["savedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # The style pick goes to its own file. It is a one-time setup decision,
        # not a correction, and sharing preview_edits.json would make one save
        # clobber the other (they are written at different moments, by different
        # screens, and the skill consumes+deletes them independently).
        name = "preview_style.json" if body.get("type") == "style-setup" else "preview_edits.json"
        if name == "preview_edits.json":
            # camadas e efeitos são arquivos do projeto (como num editor): os dois são
            # conferidos antes de gravar qualquer um, e o agente é avisado pelo
            # preview_edits.json como sempre
            try:
                if "camadas" in body:
                    body["camadas"] = cam.normalize(body["camadas"])
                if "efeitos" in body:
                    body["efeitos"] = ef.normalize(body["efeitos"])
            except cam.CamadasInvalidas as e:
                self._json({"error": f"camadas: {e}"}, 400)
                return
            except ef.EfeitosInvalidos as e:
                self._json({"error": f"efeitos: {e}"}, 400)
                return
            if "camadas" in body:
                cam.save(self.root / "camadas.json", body["camadas"])
            if "efeitos" in body:
                ef.save(self.root / "efeitos.json", body["efeitos"])
        out = self.root / name
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(out)
        self._json({"ok": True, "file": str(out)})

    # ---- celular ----
    def _enter(self, query: str) -> None:
        """Entrada pelo link/QR: troca o código da URL por um cookie e tira o
        código da barra de endereço. Lax, não Strict: com Strict o cookie não
        vai no primeiro carregamento quando o link é aberto de outro app."""
        t = (parse_qs(query).get("t") or [""])[0]
        extra = {"Location": "/celular"}
        if self._token_ok(t):
            extra["Set-Cookie"] = (f"{TOKEN_COOKIE}={self.token}; Path=/; Max-Age={TOKEN_MAX_AGE}; "
                                   "HttpOnly; SameSite=Lax")
        elif not self._client_is_local():
            self._deny(403, "Link vencido ou incompleto. Abra de novo pelo QR code do computador.", "/c")
            return
        self._hdr(303, "text/plain; charset=utf-8", 0, extra)

    def _celular_info(self) -> None:
        # Só o próprio computador vê os links: eles carregam o código.
        if not self._client_is_local():
            self._deny(403, "Só no computador.", "/api/celular")
            return
        if not self.token:
            self._json({"enabled": False})
            return
        urls = phone_urls(self.bind_host, self.server.server_address[1], self.token)
        for u in urls:
            u["qr"] = qr_svg(u["url"])
        self._json({"enabled": True, "urls": urls})

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
        if not _frame_slots.acquire(timeout=5):
            self._json({"error": "ocupado, tente de novo"}, 503)
            return
        try:
            jpg = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
                 "-frames:v", "1", "-vf", f"scale=-2:{h}", "-q:v", "5",
                 "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                capture_output=True, timeout=15,
            ).stdout
        except subprocess.TimeoutExpired:
            jpg = b""
        finally:
            _frame_slots.release()
        if not jpg:
            self._json({"error": "sem quadro nesse tempo"}, 404)
            return
        self._hdr(200, "image/jpeg", len(jpg))
        self.wfile.write(jpg)

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
            cues = caption_style.build_cues(caption_style.load_words(tr))
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
        para <edit>/midia/ (são camadas do projeto, que o editor põe na linha do tempo)."""
        if self.upload_dir is None:
            self._fail(404, "envio desligado")
            return
        raw_len = self.headers.get("Content-Length")
        if raw_len is None:
            self._fail(411, "Envio sem tamanho (Content-Length).")
            return
        try:
            length = int(raw_len)
        except ValueError:
            self._fail(400, "Tamanho inválido.")
            return
        if length <= 0:
            self._fail(400, "Arquivo vazio.")
            return
        if length > self.max_upload:
            self._fail(413, f"Arquivo maior que o limite de {self.max_upload / 1024 ** 3:.1f} GB.")
            return
        name = clean_upload_name((parse_qs(query).get("name") or [""])[0])
        kind = upload_kind(name)
        if kind is None:
            self._fail(415, "Só vídeo, imagem ou áudio: mp4, mov, webm, jpg, png, webp, mp3, m4a, wav, ogg.")
            return
        folder = self.upload_dir if kind == "video" else self.root / cam.MIDIA_DIR
        folder.mkdir(exist_ok=True)
        try:
            if length > shutil.disk_usage(folder).free - DISK_MARGIN:
                self._fail(507, "Sem espaço no computador para esse vídeo.")
                return
        except OSError:
            pass
        with _upload_lock:
            final = unique_path(folder, name)
            part = folder / f".{final.name}.parte"
            part.touch(exist_ok=False)  # reserva o nome antes de soltar a trava
        try:
            with open(part, "wb") as f:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        raise ConnectionError("o envio parou no meio")
                    f.write(chunk)
                    remaining -= len(chunk)
            os.replace(part, final)
        except (OSError, ConnectionError) as e:
            part.unlink(missing_ok=True)
            sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] envio de {name} falhou: {e}\n")
            self.close_connection = True
            try:
                self._json({"error": "O envio parou no meio. Tente de novo."}, 400)
            except OSError:
                pass
            return
        if kind != "video":
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
                    "duracao": p["duracao"]})

    # ---- dynamic bits ----
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
        for key in ("video", "finalVideo", "edl", "captions", "editData"):
            rel = state.get(key)
            if not rel:
                continue
            p = self._safe(self.root, rel)
            if p and p.exists():
                mtimes[key] = p.stat().st_mtime
        edl = None
        rel = state.get("edl") or "edl.json"
        p = self._safe(self.root, rel)
        if p and p.exists():
            try:
                edl = json.loads(p.read_text())
            except json.JSONDecodeError:
                pass
        edits_p = self.root / "preview_edits.json"
        video = self._current_video()
        self._json({
            "state": state,
            "edl": edl,
            "mtimes": mtimes,
            "videoDuration": probe_duration(video) if video else 0,
            "hasPendingEdits": edits_p.exists(),
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
    if not (APP_DIR / "index.html").exists():
        raise SystemExit(f"app not found at {APP_DIR}")
    upload_dir = (args.upload_dir or root.parent).resolve()
    if not upload_dir.is_dir():
        raise SystemExit(f"pasta de envio não existe: {upload_dir}")

    Handler.root = root
    Handler.allow_hosts = tuple(args.allow_host)
    Handler.upload_dir = upload_dir
    Handler.max_upload = int(args.max_upload_gb * 1024 ** 3)
    Handler.bind_host = args.host
    if not is_local_bind(args.host):
        Handler.token = ensure_token(root)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"CutMind preview -> http://{pc_host(args.host)}:{args.port}  (root: {root})", flush=True)
    if Handler.token:
        print("Aberto para a rede: só entra quem tem o link com o código.", flush=True)
        for u in phone_urls(args.host, args.port, Handler.token):
            print(f"  celular ({u['label']}): {u['url']}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
