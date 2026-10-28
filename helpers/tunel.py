#!/usr/bin/env python3
"""O editor no celular de qualquer lugar: um túnel https da Cloudflare (Quick Tunnel, sem conta) até a porta
do túnel do editor. O agente manda o link e ele abre no Wi-Fi ou no 4G, sem mexer em rede nem em firewall.

    uv run python -X utf8 helpers/tunel.py ligar --porta 4821
    uv run python -X utf8 helpers/tunel.py estado
    uv run python -X utf8 helpers/tunel.py desligar

O `cloudflared` é baixado só na primeira vez (para ~/.cutmind/bin, sem admin), numa versão fixa e conferido
pelo sha256 publicado pela Cloudflare. Ele roda solto, à parte do editor: reiniciar o editor (atualização)
não troca o link; `tunel.json` guarda url, pid e porta. A Cloudflare diz que o Quick Tunnel é "para testes":
sem garantia de ficar no ar. Quem tem o link e o código entra; o código é cobrado na porta do túnel.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import os
import platform
import re
import secrets
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import atualizar as atu  # mesma pasta deste arquivo

VERSAO = "2026.10.5"
BASE = f"https://github.com/cloudflare/cloudflared/releases/download/{VERSAO}/"
# (sistema, máquina) → (arquivo, sha256, bytes); lidos da API do GitHub em 27/10/2026
BINARIOS = {
    ("win32", "amd64"): ("cloudflared-windows-amd64.exe",
                         "db4e4c413612a0916f3e1679d3caaf376f94911952d163028fb726fb2e0516a9", 55343328),
    ("darwin", "x86_64"): ("cloudflared-darwin-amd64.tgz",
                           "6699392fed92367808c248c2d90bed66e49bbf66e1b4ee3e4141230f3f7391b3", 21798374),
    ("darwin", "arm64"): ("cloudflared-darwin-arm64.tgz",
                          "184c7d4f5f977348243a6d7ca8f6cf6073b9b2746cfe8c1fe15aa59e9a522bf0", 19840425),
    ("linux", "x86_64"): ("cloudflared-linux-amd64",
                          "e1bc0cf084fd9e590554fe769a86b1db46701c3f847a43d902f7b974a4e16298", 40263303),
    ("linux", "arm64"): ("cloudflared-linux-arm64",
                         "72e0d05a67e09da87cf495e409a28c3cc5994dd23fc66a982eebea6a55923b7d", 37662975),
}
MAQUINA = {"amd64": "amd64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
PRAZO_URL = 60.0       # o cloudflared imprime a URL em segundos
PRAZO_RESPOSTA = 45.0  # o DNS do nome novo leva de 3 a 33 s
GRACA_S = 600.0        # porta sem ninguém: o editor volta de um reinício (atualização) com o mesmo link
INTERVALO_S = 5.0


class ErroTunel(RuntimeError):
    """O túnel não ligou, por um motivo que a pessoa entende."""


def _pasta(casa: Path) -> Path:
    return Path(casa) / "tunel"


def _arquivo_do_sistema() -> tuple[str, str, int]:
    sistema = "win32" if os.name == "nt" else sys.platform
    if sistema.startswith("linux"):
        sistema = "linux"
    maq = MAQUINA.get(platform.machine().lower(), "")
    if sistema == "win32":
        maq = "amd64"  # o Windows em ARM roda o de x64
    escolha = BINARIOS.get((sistema, maq))
    if escolha is None:
        raise ErroTunel(f"o túnel não tem versão para este sistema ({sistema} {platform.machine()})")
    return escolha


def binario(casa: Path, baixar=None) -> Path:
    """O cloudflared desta versão, conferido pelo sha256; baixa na primeira vez."""
    nome, sha, tamanho = _arquivo_do_sistema()
    pasta = _pasta(casa) / "bin"
    exe = pasta / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
    marca = pasta / "versao.txt"
    if exe.is_file() and marca.is_file() and marca.read_text(encoding="utf-8").strip() == f"{VERSAO} {sha}":
        return exe
    pasta.mkdir(parents=True, exist_ok=True)
    parte = pasta / f"{nome}.parte"
    try:
        (baixar or _baixar)(BASE + nome, parte)
        dados = parte.read_bytes()
        if len(dados) != tamanho or hashlib.sha256(dados).hexdigest() != sha:
            raise ErroTunel("o cloudflared baixado não bate com o publicado pela Cloudflare; nada foi instalado")
        if nome.endswith(".tgz"):
            with tarfile.open(parte, "r:gz") as tar:
                membro = next((m for m in tar.getmembers() if m.isfile() and Path(m.name).name == "cloudflared"), None)
                if membro is None:
                    raise ErroTunel("o pacote do cloudflared veio sem o programa")
                exe.write_bytes(tar.extractfile(membro).read())
        else:
            os.replace(parte, exe)
        if os.name != "nt":
            exe.chmod(0o755)
        marca.write_text(f"{VERSAO} {sha}", encoding="utf-8")
        return exe
    finally:
        parte.unlink(missing_ok=True)


def _baixar(url: str, destino: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(destino, "wb") as f:
            while True:
                bloco = r.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)
    except (urllib.error.URLError, OSError) as e:
        raise ErroTunel(f"não consegui baixar o cloudflared ({e}); confira a internet") from e


def arquivo_codigo(casa: Path) -> Path:
    return _pasta(casa) / "codigo"


def codigo(casa: Path, novo: bool = False) -> str:
    """O código do celular pelo túnel. É só dele (o do Wi-Fi não abre o túnel) e mora na casa do CutMind, não
    no projeto: trocar de projeto ou atualizar não derruba o celular. Um túnel novo ganha código novo."""
    arq = arquivo_codigo(casa)
    if not novo:
        try:
            atual = arq.read_text(encoding="utf-8").strip()
            if len(atual) >= 20:
                return atual
        except OSError:
            pass
    arq.parent.mkdir(parents=True, exist_ok=True)
    c = secrets.token_urlsafe(18)
    tmp = arq.with_name(arq.name + ".tmp")
    tmp.write_bytes(c.encode("ascii"))
    for _ in range(40):  # o editor lê o arquivo a cada pedido; no Windows a troca falha enquanto ele lê
        try:
            os.replace(tmp, arq)
            return c
        except PermissionError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)
    raise ErroTunel(f"não consegui gravar o código do túnel em {arq}")


def _mesmo_arquivo(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _e_o_tunel(pid: int, exe: str | None = None) -> bool:
    """O processo vivo com esse número é o NOSSO cloudflared (o programa em ~/.cutmind/tunel/bin)? Depois de o
    computador reiniciar, o número gravado pode ser de outro programa, até de um cloudflared da própria pessoa,
    e desligar o túnel o derrubaria."""
    if not exe or not atu._vivo(pid):
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            nome = ctypes.create_unicode_buffer(1024)
            tamanho = wintypes.DWORD(len(nome))
            if not k.QueryFullProcessImageNameW(h, 0, nome, ctypes.byref(tamanho)):
                return False
            return _mesmo_arquivo(nome.value, exe)
        finally:
            k.CloseHandle(h)
    r = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True)
    return r.stdout.strip().startswith(str(exe) + " ")


def estado(casa: Path) -> dict | None:
    """O túnel vivo: {url, pid, porta, desde}, ou None."""
    d = atu._ler_json(_pasta(casa) / "tunel.json")
    if not d.get("url") or not isinstance(d.get("pid"), int) or not _e_o_tunel(d["pid"], d.get("exe")):
        return None
    return d


def responde(url: str, timeout: float = 8.0) -> bool:
    try:
        with urllib.request.urlopen(url + "/", timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _lancar(exe: Path, porta: int, log: Path, casa: Path) -> subprocess.Popen:
    """Solto, como o editor: sobrevive a quem o lançou. HOME isolada: um config.yml em ~/.cloudflared
    impede o Quick Tunnel de funcionar."""
    casa_do_tunel = _pasta(casa) / "home"
    casa_do_tunel.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "HOME": str(casa_do_tunel), "USERPROFILE": str(casa_do_tunel)}
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    with log.open("wb") as saida:
        return subprocess.Popen([str(exe), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{porta}"],
                                stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT, env=env,
                                close_fds=True, creationflags=flags, start_new_session=os.name != "nt")


def _url_no_log(log: Path, proc: subprocess.Popen, prazo: float) -> str:
    fim = time.time() + prazo
    while time.time() < fim:
        try:
            m = URL_RE.search(log.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            m = None
        if m:
            return m.group(0)
        if proc.poll() is not None:
            raise ErroTunel("o cloudflared fechou antes de dar o link; veja " + str(log))
        time.sleep(0.5)
    raise ErroTunel("o cloudflared não deu o link a tempo; confira a internet")


def ligar(porta: int, casa: Path | None = None, exe: Path | None = None) -> dict:
    """Liga (ou reaproveita) o túnel até 127.0.0.1:<porta>. Devolve {url, pid, porta, desde, responde, codigo}."""
    casa = Path(casa or atu.casa())
    vivo = estado(casa)
    if vivo and vivo.get("porta") == porta and responde(vivo["url"]):
        return {**vivo, "responde": True, "codigo": codigo(casa)}
    if vivo:
        desligar(casa)
    exe = exe or binario(casa)
    pasta = _pasta(casa)
    log = pasta / "tunel.log"
    cod = codigo(casa, novo=True)
    proc = _lancar(exe, porta, log, casa)
    url = _url_no_log(log, proc, PRAZO_URL)
    d = {"url": url, "pid": proc.pid, "porta": porta, "exe": str(Path(exe).resolve()),
         "desde": time.strftime("%Y-%m-%d %H:%M:%S")}
    atu._gravar_json(pasta / "tunel.json", d)
    _lancar_vigia(porta, proc.pid, casa)
    time.sleep(3)  # perguntar antes do nome existir deixa o "não existe" guardado no DNS
    fim = time.time() + PRAZO_RESPOSTA
    ok = False
    while time.time() < fim and not (ok := responde(url)):
        time.sleep(2)
    return {**d, "responde": ok, "codigo": cod}


def desligar(casa: Path | None = None) -> bool:
    casa = Path(casa or atu.casa())
    arq = _pasta(casa) / "tunel.json"
    d = atu._ler_json(arq)
    pid = d.get("pid")
    if isinstance(pid, int) and _e_o_tunel(pid, d.get("exe")):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
    arq.unlink(missing_ok=True)
    return bool(pid)


def _quem_atende(porta: int) -> str:
    """Quem está na porta para onde o túnel manda a internet: "editor" (a porta do túnel de um editor CutMind),
    "ninguem" ou "outro". Pergunta com o nome do túnel, como a Cloudflare faz: a porta comum do editor recusa."""
    conn = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
    try:
        conn.request("GET", "/", headers={"Host": "vigia.trycloudflare.com"})
        r = conn.getresponse()
        corpo = r.read(1 << 16)
    except ConnectionRefusedError:
        return "ninguem"
    except (OSError, http.client.HTTPException):
        return "ninguem"   # tempo esgotado ou conexão cortada: conta como ausência, dentro da carência
    finally:
        conn.close()
    return "editor" if r.status == 200 and b"CutMind" in corpo else "outro"


def vigiar(porta: int, pid: int, casa: Path, graca: float = GRACA_S, intervalo: float = INTERVALO_S,
           agora=time.time, dormir=time.sleep) -> str:
    """Fica de olho na porta enquanto o túnel vive, a cada `intervalo` segundos. Outro programa nela: desliga
    (a internet chegaria nele). Ninguém nela por `graca` segundos: desliga (o editor fechou). O editor voltando
    antes disso, o link continua o mesmo."""
    livre_desde = None
    while True:
        d = atu._ler_json(_pasta(casa) / "tunel.json")
        if d.get("pid") != pid or not _e_o_tunel(pid, d.get("exe")):
            return "o túnel já não está ligado"
        quem = _quem_atende(porta)
        if quem == "outro":
            desligar(casa)
            return "outro programa na porta do túnel"
        if quem == "editor":
            livre_desde = None
        else:
            livre_desde = livre_desde if livre_desde is not None else agora()
            if agora() - livre_desde >= graca:
                desligar(casa)
                return "o editor fechou"
        dormir(intervalo)


def _lancar_vigia(porta: int, pid: int, casa: Path) -> None:
    """Pelo Python base, não pelo do .venv: um processo vivo com o python do .venv prenderia o arquivo
    durante uma atualização. O vigia só usa a biblioteca padrão."""
    py = getattr(sys, "_base_executable", None) or sys.executable
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    subprocess.Popen([py, "-X", "utf8", str(Path(__file__).resolve()), "vigiar", "--porta", str(porta),
                      "--pid", str(pid)], env={**os.environ, "CUTMIND_HOME": str(casa)}, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags,
                     start_new_session=os.name != "nt")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=("ligar", "estado", "desligar", "vigiar"))
    ap.add_argument("--porta", type=int, default=4821, help="a porta do túnel do editor (a do editor + 1)")
    ap.add_argument("--pid", type=int, help="vigiar: o PID do cloudflared")
    a = ap.parse_args()
    if a.acao == "vigiar":
        vigiar(a.porta, a.pid, atu.casa())
        return 0
    if a.acao == "estado":
        d = estado(atu.casa())
        print(d["url"] if d else "desligado")
        return 0
    if a.acao == "desligar":
        print("túnel desligado" if desligar() else "não havia túnel ligado")
        return 0
    try:
        d = ligar(a.porta)
    except ErroTunel as e:
        print(str(e), file=sys.stderr)
        return 1
    print(d["url"] + ("" if d["responde"] else "  (ainda não respondeu: espere alguns segundos)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
