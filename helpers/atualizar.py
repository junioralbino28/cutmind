#!/usr/bin/env python3
"""A atualização do CutMind pelo editor: procura a versão nova na main do GitHub, baixa, confere pelo
manifesto do versao.json, instala com o instalador de sempre (cópia de segurança e volta automática) e
religa o servidor do editor quando a mudança pede. O mesmo desenho do atualizador do Papory (0.1.8/0.1.9).

    uv run python -X utf8 helpers/atualizar.py procurar [--forcar]
    uv run python -X utf8 helpers/atualizar.py aplicar [--andamento A] [--servidor S]

Só a pergunta sai do computador (qual é a versão mais nova); nada da pessoa vai junto. Endereços:
CUTMIND_ATUALIZACAO_URL e CUTMIND_ATUALIZACAO_PACOTE trocam o GitHub (testes e e2e); CUTMIND_SEM_ATUALIZACAO=1
ou o interruptor "Procurar atualizações" (~/.cutmind/config.json) desligam.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import trabalhos as tb  # mesma pasta deste arquivo
import versao as vs  # mesma pasta deste arquivo

SKILL = Path(__file__).resolve().parents[1]
REPO = "junioralbino28/cutmind"
URL = f"https://raw.githubusercontent.com/{REPO}/main/versao.json"
PACOTE = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/main"
CACHE_S = 6 * 3600       # de quanto em quanto tempo pergunta de novo (como o Papory)
TEMPO_REDE = 4.0         # a pergunta nunca prende o editor
PACOTE_MAX = 500 * 1024 ** 2


class ErroAtualizar(RuntimeError):
    """A atualização não aconteceu, por um motivo que a pessoa entende."""


def _sem_andamento(etapa: str, texto: str, fracao: float, **extra) -> None:
    pass


def casa() -> Path:
    return Path(os.environ.get("CUTMIND_HOME") or Path.home() / ".cutmind")


def endereco() -> tuple[str, str]:
    return os.environ.get("CUTMIND_ATUALIZACAO_URL") or URL, os.environ.get("CUTMIND_ATUALIZACAO_PACOTE") or PACOTE


def _ler_json(p: Path) -> dict:
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _gravar_json(p: Path, d: dict) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(json.dumps(d, ensure_ascii=False, indent=2).encode("utf-8"))
    for _ in range(40):  # o servidor pode estar lendo o arquivo nesse instante (Windows)
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05)
    tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------- procurar

def ligado(c: Path | None = None) -> bool:
    """O interruptor "Procurar atualizações" (ligado se nunca foi mexido)."""
    return _ler_json(Path(c or casa()) / "config.json").get("procurarAtualizacao") is not False


def ligar(c: Path | None, sim: bool) -> None:
    p = Path(c or casa()) / "config.json"
    d = _ler_json(p)
    d["procurarAtualizacao"] = bool(sim)
    _gravar_json(p, d)


def _remoto(url: str) -> dict | None:
    pedido = urllib.request.Request(url, headers={"User-Agent": "CutMind", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_REDE) as r:
            d = json.loads(r.read(4 * 1024 * 1024).decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None  # sem internet, GitHub fora ou o repositório ainda privado (404): tenta de novo depois
    ok = isinstance(d, dict) and isinstance(d.get("versao"), str) and isinstance(d.get("arquivos"), dict)
    return d if ok else None


def remoto(c: Path | None = None, forcar: bool = False, agora: float | None = None) -> dict | None:
    """O versao.json da main, guardado por 6 h em ~/.cutmind/atualizacao.json."""
    c, agora = Path(c or casa()), time.time() if agora is None else agora
    guardado = _ler_json(c / "atualizacao.json")
    quando = guardado.get("quando")
    if not forcar and isinstance(quando, (int, float)) and 0 <= agora - quando < CACHE_S:
        return guardado.get("remoto")
    d = _remoto(endereco()[0])
    _gravar_json(c / "atualizacao.json", {"quando": agora, "remoto": d})
    return d


def procurar(skill: Path = SKILL, c: Path | None = None, forcar: bool = False, agora: float | None = None) -> dict:
    """{"nova": bool, ...versao.resumo}; com "motivo" quando nem procurou. Nunca levanta: sem rede = nada novo."""
    c = Path(c or casa())
    if os.environ.get("CUTMIND_SEM_ATUALIZACAO") == "1" or not ligado(c):
        return {"nova": False, "motivo": "desligado"}
    if (Path(skill) / ".git").exists():
        return {"nova": False, "motivo": "desenvolvimento"}  # quem desenvolve atualiza com git
    return vs.resumo(vs.ler(skill), remoto(c, forcar, agora))


# ---------------------------------------------------------------- baixar e conferir

def _baixar_pacote(destino: Path, progresso) -> Path:
    arq = destino / "pacote.tar.gz"
    pedido = urllib.request.Request(endereco()[1], headers={"User-Agent": "CutMind"})
    try:
        with urllib.request.urlopen(pedido, timeout=60) as r, arq.open("wb") as f:
            total, feito = int(r.headers.get("Content-Length") or 0), 0
            while True:
                bloco = r.read(1024 * 1024)
                if not bloco:
                    break
                feito += len(bloco)
                if feito > PACOTE_MAX:
                    raise ErroAtualizar("o pacote da versão nova é grande demais")
                f.write(bloco)
                progresso(feito, total or feito)
    except (urllib.error.URLError, OSError) as e:
        raise ErroAtualizar(f"não deu para baixar a versão nova: confira a internet ({e})") from e
    return arq


def _extrair(arq: Path, destino: Path) -> Path:
    """Extrai o pacote recusando caminho para fora da pasta e link; devolve a pasta de cima (cutmind-main)."""
    try:
        with tarfile.open(arq, "r:gz") as tar:
            membros = tar.getmembers()
            for m in membros:
                partes = Path(m.name).parts
                if m.name.startswith(("/", "\\")) or ".." in partes or (partes and ":" in partes[0]):
                    raise ErroAtualizar(f"o pacote tem um caminho para fora da pasta: {m.name}")
                if m.issym() or m.islnk() or not (m.isfile() or m.isdir()):
                    raise ErroAtualizar(f"o pacote tem um link ou arquivo especial: {m.name}")
            pasta = destino / "x"
            if hasattr(tarfile, "data_filter"):
                tar.extractall(pasta, members=membros, filter="data")
            else:
                tar.extractall(pasta, members=membros)
    except tarfile.TarError as e:
        raise ErroAtualizar(f"o pacote da versão nova veio quebrado ({e})") from e
    topo = [p for p in pasta.iterdir() if p.is_dir()]
    if len(topo) != 1:
        raise ErroAtualizar("o pacote da versão nova não tem a pasta esperada")
    return topo[0]


def baixar(destino: Path, rem: dict, progresso=lambda feito, total: None) -> tuple[Path, dict]:
    """Baixa a main e confere pelo manifesto. A main pode ter andado entre a pergunta e o download: aí
    pergunta de novo e baixa uma vez mais. Não bateu, apaga tudo e dá ErroAtualizar."""
    destino = Path(destino)
    for tentativa in range(2):
        shutil.rmtree(destino, ignore_errors=True)
        destino.mkdir(parents=True)
        try:
            raiz = _extrair(_baixar_pacote(destino, progresso), destino)
            if vs.manifesto(raiz) == rem.get("arquivos"):
                return raiz, rem
        except ErroAtualizar:
            shutil.rmtree(destino, ignore_errors=True)
            raise
        novo = _remoto(endereco()[0]) if tentativa == 0 else None
        if not novo or novo.get("arquivos") == rem.get("arquivos"):
            break
        rem = novo
    shutil.rmtree(destino, ignore_errors=True)
    raise ErroAtualizar(f"o pacote baixado não bate com a versão {rem.get('versao')} publicada")


# ---------------------------------------------------------------- instalar, voltar, religar

def comando_instalar(pasta: Path, skill: Path) -> list[str]:
    """O instalador da versão NOVA, a partir da pasta baixada: o mesmo caminho de quem roda o comando do
    README. Ele atualiza todas as cópias (Claude Code e Codex); `skill` serve só aos testes. Sem pedir a
    permissão de rede do Windows: ela foi oferecida na instalação, e quem atualiza pode estar no celular."""
    return ["uv", "run", "--no-project", str(Path(pasta) / "cutmind_install.py"), "--source", str(pasta),
            "--no-firewall"]


def sincronizar(skill: Path) -> None:
    """As dependências de volta ao uv.lock de antes, depois de devolver os arquivos."""
    subprocess.run(["uv", "sync", "--directory", str(skill)], capture_output=True)


def guardar(skill: Path, destino: Path) -> None:
    """A cópia instalada sem o .venv nem o .env, para voltar se a instalação falhar."""
    shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True)
    for entrada in (*vs.PAYLOAD, vs.ARQ):
        p = Path(skill) / entrada
        if p.is_dir():
            shutil.copytree(p, destino / entrada, ignore=shutil.ignore_patterns("__pycache__"))
        elif p.is_file():
            shutil.copy2(p, destino / entrada)


def _esvaziar(pasta: Path) -> None:
    """Tira tudo de dentro e deixa a pasta: no Windows a pasta atual de um processo vivo não pode ser apagada, e
    este atualizador roda com a pasta atual em helpers/ (o rmtree calado dela deixava a pasta e o copytree caía)."""
    for p in Path(pasta).iterdir():
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        else:
            p.unlink()


def voltar(skill: Path, origem: Path) -> None:
    for entrada in (*vs.PAYLOAD, vs.ARQ):
        alvo, p = Path(skill) / entrada, Path(origem) / entrada
        if alvo.is_dir() and p.is_dir():
            _esvaziar(alvo)
        elif alvo.is_dir():
            shutil.rmtree(alvo)
        elif alvo.exists():
            alvo.unlink()
        if p.is_dir():
            shutil.copytree(p, alvo, dirs_exist_ok=True)
        elif p.is_file():
            shutil.copy2(p, alvo)
    sincronizar(skill)


def _vivo(pid: int) -> bool:
    if os.name == "nt":
        # pergunta ao Windows, sem ler texto: o tasklist responde "processo não existe" no código de página do
        # console (acentuado), e a leitura em UTF-8 derrubava o atualizador com o editor já fechado
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259   # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def esperar_sair(pid: int, prazo: float = 30.0) -> None:
    fim = time.time() + prazo
    while time.time() < fim and _vivo(pid):
        time.sleep(0.25)
    if _vivo(pid):
        raise ErroAtualizar("o editor não fechou para a atualização")


def _porta(argv: list[str]) -> int:
    return int(argv[argv.index("--port") + 1]) if "--port" in argv else 4820


def respondendo(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def religar(servidor: dict, prazo: float = 60.0) -> int:
    """Liga o servidor do editor de novo com a mesma linha de comando (mesma pasta, porta e código do celular)
    e só conta como pronto quando ele RESPONDE (aprendizado do Papory). Devolve o PID novo."""
    argv = list(servidor["argv"])
    raiz = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path(servidor.get("cwd") or ".")
    script = Path(servidor.get("script") or SKILL / "helpers" / "preview_server.py")
    cmd = [servidor.get("python") or sys.executable, "-X", "utf8", str(script), *argv[1:]]
    env = {**os.environ, "PYTHONUTF8": "1"}
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    with (raiz / "preview-server.log").open("ab") as out, (raiz / "preview-server.err.log").open("ab") as err:
        proc = subprocess.Popen(cmd, cwd=script.parent, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                close_fds=True, creationflags=flags, start_new_session=os.name != "nt")
    fim, porta = time.time() + prazo, _porta(argv)
    while time.time() < fim:
        if respondendo(porta):
            return proc.pid
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    try:
        cauda = (raiz / "preview-server.err.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
    except OSError:
        cauda = []
    detalhe = " ".join(cauda)
    raise ErroAtualizar(f"o editor não voltou depois da atualização: {detalhe}")


def _trocar(skill: Path, pasta: Path, raiz: Path, versao: str, servidor: dict | None, andamento) -> None:
    """Espera o editor fechar (quando a versão pede reinício), guarda a versão de agora e instala a nova.
    Qualquer erro sai como ErroAtualizar, com os arquivos de antes de volta: nada fica pela metade."""
    guardou = False
    try:
        if servidor:
            andamento("fechando", "Fechando o editor para trocar os arquivos", 0.52)
            esperar_sair(int(servidor["pid"]))
        andamento("guardando", "Guardando a versão de agora", 0.55)
        guardar(skill, pasta / "anterior")
        guardou = True
        andamento("instalando", "Instalando", 0.6)
        p = subprocess.run(comando_instalar(raiz, skill), capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        (pasta / "instalador.log").write_bytes((p.stdout + p.stderr).encode("utf-8"))
        if p.returncode != 0:
            ultima = next((x for x in reversed((p.stdout + p.stderr).splitlines()) if x.strip()), "")
            andamento("voltando", "Voltando para a versão de antes", 0.85)
            voltar(skill, pasta / "anterior")
            raise ErroAtualizar(f"a instalação falhou; o CutMind continua na versão de antes ({ultima.strip()})")
        if (vs.ler(skill) or {}).get("versao") != versao:
            raise ErroAtualizar(f"a instalação não chegou nesta pasta ({skill}); rode o comando de instalação do README")
    except ErroAtualizar:
        raise
    except Exception as e:  # noqa: BLE001 (o editor fechado não pode ficar desligado nem pela metade)
        if guardou:
            try:
                voltar(skill, pasta / "anterior")
            except Exception as e2:  # noqa: BLE001 (sai como ErroAtualizar: o editor religa e o andamento conta)
                raise ErroAtualizar(f"a atualização parou no meio ({e}) e não deu para voltar à versão de antes "
                                    f"({e2}); rode o comando de instalação do README") from e2
        raise ErroAtualizar(f"a atualização parou no meio ({e}); o CutMind continua na versão de antes") from e


def aplicar(skill: Path = SKILL, c: Path | None = None, servidor: dict | None = None, andamento=_sem_andamento) -> dict:
    """Procura, baixa, confere, guarda a versão de agora, instala e religa o servidor quando a mudança pede.
    Falhou no meio: a versão de antes volta (arquivos e dependências) e o editor religa nela."""
    skill, c = Path(skill), Path(c or casa())
    pasta = c / "atualizacao"
    andamento("procurando", "Procurando a versão nova", 0.02)
    rem = remoto(c, forcar=True)
    r = vs.resumo(vs.ler(skill), rem)
    if not r.get("nova"):
        andamento("pronto", "Já está na versão mais nova", 1.0, versao=(vs.ler(skill) or {}).get("versao"), nada=True)
        return {**r, "nada": True}
    baixado = pasta / "baixado"
    try:
        raiz, rem = baixar(baixado, rem, lambda feito, total: andamento(
            "baixando", "Baixando a versão nova", 0.05 + 0.45 * feito / max(total, 1), feito=feito, total=total))
    except ErroAtualizar as e:
        andamento("falhou", str(e), 1.0, erro=str(e))
        raise
    r = vs.resumo(vs.ler(skill), rem)
    reinicio = bool(servidor and r["reiniciar"])   # o editor se desliga sozinho logo depois do clique
    try:
        _trocar(skill, pasta, raiz, rem["versao"], servidor if reinicio else None, andamento)
    except ErroAtualizar as e:
        if reinicio and not _vivo(int(servidor["pid"])):
            try:
                religar(servidor)
            except Exception as e2:  # noqa: BLE001 (o erro que importa é o da atualização; este fica no log)
                print(f"o editor não religou: {e2}", file=sys.stderr)
        andamento("falhou", str(e), 1.0, erro=str(e))
        raise
    finally:
        shutil.rmtree(baixado, ignore_errors=True)
    if reinicio:
        andamento("religando", "Ligando o editor de novo", 0.95)
        religar(servidor)
    fim = {"versao": rem["versao"], "agente": r["agente"], "remotion": r["remotion"], "reiniciou": reinicio}
    andamento("pronto", "Atualizado", 1.0, **fim)
    return {**r, **fim}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("acao", choices=("procurar", "aplicar"))
    ap.add_argument("--forcar", action="store_true", help="pergunta ao GitHub agora, sem o cache de 6 h")
    ap.add_argument("--andamento", type=Path, help="arquivo de andamento que o editor lê")
    ap.add_argument("--servidor", type=Path, help="o servidor.json do editor que pediu (para religar)")
    a = ap.parse_args()
    if a.acao == "procurar":
        print(json.dumps(procurar(forcar=a.forcar), ensure_ascii=False, indent=2))
        return 0
    escrever = tb.escritor(a.andamento, "atualizar") if a.andamento else _sem_andamento
    servidor = _ler_json(a.servidor) if a.servidor else None
    try:
        r = aplicar(SKILL, casa(), servidor or None, escrever)
    except ErroAtualizar as e:
        print(str(e), file=sys.stderr)
        return 1
    if r.get("nada"):
        print(f"o CutMind já está na versão mais nova ({r.get('versao') or r.get('atual')})")
    else:
        print(f"CutMind atualizado para a versão {r['versao']}"
              + ("; comece uma conversa nova com o agente para ele usar as instruções novas" if r["agente"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
