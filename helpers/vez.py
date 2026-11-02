"""Um render pesado por vez no computador, com prioridade baixa e pasta temporária só dele.

Edição real de 01/11: duas conversas renderizando no Remotion ao mesmo tempo, num i3 de 4 núcleos com 16 GB,
travaram o computador inteiro ("travava por tudo"). Cada render abre metade das threads, copia a pasta
public/ inteira para o temporário (3 GB naquele projeto) e as cópias de renders antigos ficavam lá. E a
marca de trabalhando do agente (agente.py) vencia aos 30 min, no meio de um render de 35 a 50.

O que `vez()` faz em volta do render:
- a fila: `~/.cutmind/render.vez` guarda quem está renderizando; o segundo espera o primeiro acabar. Um
  render dentro de outro (o mesmo processo, ou um filho dele) não espera por si mesmo;
- a prioridade baixa: no Windows BELOW_NORMAL (o Node, o Chrome e o ffmpeg que ele abre herdam); no Mac e
  no Linux, nice 10. O mouse e os outros programas passam na frente; com o computador parado, o render
  leva o mesmo tempo;
- a pasta temporária: TEMP, TMP e TMPDIR do render apontam para uma pasta só dele, apagada inteira no
  fim (o bundle do Remotion e as pastas remotion-v* vão junto, e ninguém apaga a pasta de outro);
- a marca de trabalhando do agente, se existir, é renovada a cada 10 min.

    with vez.vez(edit, "render do vídeo final") as v:
        subprocess.run(cmd, cwd=..., env=v.env(), **v.criar)
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

MARCA_PAI = "CUTMIND_VEZ"  # o pid de quem tem a vez, para os filhos dele não esperarem por ele
VELHA = 4 * 3600  # uma vez mais velha que isso é de um render que caiu sem soltar
PASSO = 5.0  # s entre uma olhada e outra na fila
RENOVA = 10 * 60  # s entre uma renovação e outra da marca do agente

_dono = threading.local()


def home() -> Path:
    return Path(os.environ.get("CUTMIND_HOME") or Path.home() / ".cutmind")


def _arquivo() -> Path:
    return home() / "render.vez"


def vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            codigo = ctypes.c_ulong()
            return bool(k.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259  # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def quem() -> dict | None:
    """Quem tem a vez agora (pid, rotulo, desde), ou None."""
    try:
        d = json.loads(_arquivo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not vivo(int(d.get("pid") or 0)) or time.time() - float(d.get("desde") or 0) > VELHA:
        return None
    return d


def _pegar(rotulo: str) -> bool:
    arq = _arquivo()
    arq.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(arq, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if quem() is None:  # de um render que caiu: tira e tenta de novo
            with contextlib.suppress(OSError):
                arq.unlink()
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "rotulo": rotulo, "desde": time.time()}, f, ensure_ascii=False)
    return True


def _soltar() -> None:
    d = None
    with contextlib.suppress(OSError, ValueError):
        d = json.loads(_arquivo().read_text(encoding="utf-8"))
    if isinstance(d, dict) and int(d.get("pid") or 0) == os.getpid():
        with contextlib.suppress(OSError):
            _arquivo().unlink()


@contextlib.contextmanager
def _fila(rotulo: str, ao_esperar: Callable[[dict], None] | None) -> Iterator[None]:
    pai = int(os.environ.get(MARCA_PAI) or 0)
    if getattr(_dono, "n", 0) or (pai and pai != os.getpid() and vivo(pai) and (quem() or {}).get("pid") == pai):
        _dono.n = getattr(_dono, "n", 0) + 1  # já é a vez deste processo (ou do pai dele)
        try:
            yield
        finally:
            _dono.n -= 1
        return
    avisou = False
    while not _pegar(rotulo):
        outro = quem()
        if outro and not avisou:
            (ao_esperar or _avisar)(outro)
            avisou = True
        time.sleep(PASSO)
    _dono.n = 1
    try:
        yield
    finally:
        _dono.n = 0
        _soltar()


def _avisar(outro: dict) -> None:
    print(f"esperando o outro render terminar ({outro.get('rotulo', 'render')}, desde "
          f"{time.strftime('%H:%M', time.localtime(float(outro.get('desde') or 0)))}): um por vez, para o "
          "computador não travar", flush=True)


@contextlib.contextmanager
def _renovando(edit: Path | None) -> Iterator[None]:
    """Enquanto o render roda, a marca de trabalhando do agente (se ele pôs) não vence."""
    if edit is None:
        yield
        return
    parar = threading.Event()

    def laco() -> None:
        import agente  # mesma pasta deste arquivo
        while not parar.wait(RENOVA):
            try:
                st = json.loads((Path(edit) / "state.json").read_text(encoding="utf-8"))
                if (st.get("agente") or {}).get("trabalhando"):
                    agente.marcar(Path(edit), True)
            except (OSError, ValueError):
                pass

    th = threading.Thread(target=laco, daemon=True)
    th.start()
    try:
        yield
    finally:
        parar.set()
        th.join(timeout=5)


class Vez:
    """O ambiente de um processo pesado: `env()` (com a pasta temporária) e `criar` (a prioridade)."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        if os.name == "nt":
            self.criar: dict = {"creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS}
        else:
            self.criar = {"preexec_fn": lambda: os.nice(10)}

    def env(self, extra: dict | None = None) -> dict:
        e = {**os.environ, **(extra or {})}
        e.update({"TEMP": str(self.tmp), "TMP": str(self.tmp), "TMPDIR": str(self.tmp), MARCA_PAI: str(os.getpid())})
        return e


@contextlib.contextmanager
def vez(edit: Path | None = None, rotulo: str = "render", fila: bool = True,
        ao_esperar: Callable[[dict], None] | None = None) -> Iterator[Vez]:
    """A vez de um render pesado (ver o começo do arquivo). `fila=False`: só prioridade e pasta própria,
    sem esperar ninguém (o que a pessoa espera na tela, como o corte do Salvar)."""
    _varrer()
    tmp = Path(tempfile.mkdtemp(prefix=f"cutmind-{os.getpid()}-"))
    try:
        with (_fila(rotulo, ao_esperar) if fila else contextlib.nullcontext()), _renovando(edit):
            yield Vez(tmp)
    finally:
        _apagar(tmp)


def _apagar(pasta: Path, prazo: float = 10.0) -> None:
    """Apaga a pasta temporária do render. O Chrome do Remotion ainda fecha por um instante depois que o
    Node termina e segura o perfil dele lá dentro: tenta de novo por `prazo` segundos; o que sobrar, o
    próximo render varre (_varrer)."""
    fim = time.time() + prazo
    while True:
        shutil.rmtree(pasta, ignore_errors=True)
        if not pasta.exists() or time.time() > fim:
            return
        time.sleep(0.5)


def _varrer() -> None:
    """As pastas temporárias de renders que já acabaram: só as `cutmind-<pid>-*` cujo processo morreu.
    Nunca pelo conteúdo, nunca a de um processo vivo (pode ser outro render rodando agora)."""
    base = Path(tempfile.gettempdir())
    for p in base.glob("cutmind-*-*"):
        pid = p.name.split("-")[1]
        if p.is_dir() and pid.isdigit() and int(pid) != os.getpid() and not vivo(int(pid)):
            shutil.rmtree(p, ignore_errors=True)


def main() -> int:
    """`vez.py -- <comando ...>`: roda um comando pesado na vez (o agente usa para o render do Remotion)."""
    args = sys.argv[1:]
    edit = pasta = None
    while args[:1] in (["--edit"], ["--cwd"]) and len(args) > 1:
        if args[0] == "--edit":
            edit = Path(args[1])
        else:
            pasta = Path(args[1])
        args = args[2:]
    if args[:1] == ["--"]:
        args = args[1:]
    if not args:
        print("uso: vez.py [--edit <edit>] [--cwd <pasta>] -- <comando ...>", file=sys.stderr)
        return 2
    exe = shutil.which(args[0]) or args[0]  # no Windows o npx é npx.cmd
    with vez(edit, rotulo=" ".join(args)[:80]) as v:
        return subprocess.run([exe, *args[1:]], cwd=pasta, env=v.env(), **v.criar).returncode


if __name__ == "__main__":
    sys.exit(main())
