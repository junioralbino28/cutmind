#!/usr/bin/env python3
"""Start the CutMind preview as a detached, UTF-8-safe local process."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
SERVER = HERE / "preview_server.py"
sys.path.insert(0, str(HERE))
from preview_server import (AVISO_REDE_PUBLICA, add_network_args, ensure_token, is_local_bind,  # noqa: E402
                            pc_host, phone_urls, rede_publica)
import tunel as tn  # noqa: E402


def port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _responde(porta: int, prazo: float = 30.0) -> bool:
    fim = time.time() + prazo
    while time.time() < fim:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=3) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def ligar_tunel(porta: int) -> None:
    """Espera a porta do túnel do editor subir e liga o túnel até ela (ou reaproveita o que está vivo)."""
    if not _responde(porta):
        print(f"  ! o editor não abriu a porta do túnel ({porta}): veja preview-server.err.log")
        return
    try:
        d = tn.ligar(porta)
    except tn.ErroTunel as e:
        print(f"  ! o túnel não ligou: {e}. O editor segue no computador.")
        return
    print("Túnel ligado: o editor abre no celular de qualquer lugar (Wi-Fi ou 4G); só entra quem tem o link.")
    print(f"  celular (de qualquer lugar): {d['url']}/c?t={d['codigo']}")
    if not d.get("responde"):
        print("  (o link ainda não respondeu: espere uns segundos antes de abrir)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the CutMind preview server in the background"
    )
    parser.add_argument("--root", type=Path, required=True, help="session edit dir")
    parser.add_argument("--port", type=int, default=4820)
    add_network_args(parser)
    parser.add_argument("--tunel", action="store_true",
                        help="o editor no celular de qualquer lugar (Wi-Fi ou 4G): túnel https da Cloudflare até "
                             "a porta do túnel (a do editor + 1); imprime o link com o código")
    args = parser.parse_args()
    if args.tunel and not args.tunel_port:
        args.tunel_port = args.port + 1

    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"edit dir not found: {root}")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not SERVER.is_file():
        parser.error(f"preview server not found: {SERVER}")
    if not port_available(args.port) or not port_available(args.port, args.host):
        parser.error(f"port {args.port} is already in use")
    if args.tunel_port and not port_available(args.tunel_port):
        parser.error(f"port {args.tunel_port} (a do túnel) is already in use")

    # Antes de ligar o servidor: ele lê este mesmo código do projeto. Criado
    # depois, os dois podiam gravar códigos diferentes e o link impresso não entrava.
    token = None if is_local_bind(args.host) else ensure_token(root)

    stdout_path = root / "preview-server.log"
    stderr_path = root / "preview-server.err.log"
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(SERVER),
        "--root",
        str(root),
        "--port",
        str(args.port),
        "--host",
        args.host,
        "--max-upload-gb",
        str(args.max_upload_gb),
    ]
    for name in args.allow_host:
        command += ["--allow-host", name]
    if args.tunel_port:
        command += ["--tunel-port", str(args.tunel_port)]
    if args.upload_dir:
        command += ["--upload-dir", str(args.upload_dir.resolve())]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    creationflags = 0
    start_new_session = os.name != "nt"
    if os.name == "nt":
        # Console escondido, herdado pelo ffprobe/ffmpeg que o servidor chama.
        # Com DETACHED_PROCESS o CREATE_NO_WINDOW é ignorado e cada chamada abre
        # uma janela de terminal nova.
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        process = subprocess.Popen(
            command,
            cwd=HERE,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )

    print(
        f"CutMind preview started (PID {process.pid}) -> "
        f"http://{pc_host(args.host)}:{args.port}"
    )
    if args.tunel:
        ligar_tunel(args.tunel_port)
    if token:
        print("Aberto para a rede: só entra quem tem o link com o código.")
        for u in phone_urls(args.host, args.port, token):
            print(f"  celular ({u['label']}): {u['url']}")
            if rede_publica(u["ip"]):
                print(AVISO_REDE_PUBLICA)
    print(f"logs: {stdout_path} | {stderr_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
