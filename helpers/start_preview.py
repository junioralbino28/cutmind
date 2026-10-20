#!/usr/bin/env python3
"""Start the CENNO Edit preview as a detached, UTF-8-safe local process."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SERVER = HERE / "preview_server.py"
sys.path.insert(0, str(HERE))
from preview_server import add_network_args, ensure_token, is_local_bind, phone_urls  # noqa: E402


def port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the CENNO Edit preview server in the background"
    )
    parser.add_argument("--root", type=Path, required=True, help="session edit dir")
    parser.add_argument("--port", type=int, default=4820)
    add_network_args(parser)
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"edit dir not found: {root}")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not SERVER.is_file():
        parser.error(f"preview server not found: {SERVER}")
    if not port_available(args.port) or not port_available(args.port, args.host):
        parser.error(f"port {args.port} is already in use")

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
        f"CENNO Edit preview started (PID {process.pid}) -> "
        f"http://127.0.0.1:{args.port}"
    )
    if token:
        print("Aberto para a rede: só entra quem tem o link com o código.")
        for u in phone_urls(args.host, args.port, token):
            print(f"  celular ({u['label']}): {u['url']}")
    print(f"logs: {stdout_path} | {stderr_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
