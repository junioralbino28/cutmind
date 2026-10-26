"""One-command installer for the cutmind skill.

    uv run https://raw.githubusercontent.com/junioralbino28/cutmind/main/cutmind_install.py

`uv run <url>` and not `uvx --from <package>`: uvx would resolve and install the
whole cutmind dependency tree — torch, pandas, numpy — merely to run a script that
imports nothing but the stdlib. Measured: 2+ minutes and a from-source build of
pandas, versus 0.4s for the script. Same reason this file stays stdlib-only.

This is the `npx create-video@latest` shape. What it buys over a README full of
shell snippets:

  - ONE command, byte-identical on macOS, Linux and Windows PowerShell. Every
    OS difference (home directory, path separators, no chmod, no symlinks) is
    handled here in Python instead of in two or three shell variants that drift
    apart.
  - No clone step and no symlink/junction, so nothing needs admin rights.
  - It finds the agent by itself — Claude Code, Codex, or anything else with a
    skills directory — instead of asking the user which one they run.
  - It verifies ffmpeg and Node afterwards and prints the exact install command
    for THEIR platform when something is missing. Node.js (Phase 2) it installs by
    itself when absent — winget on Windows, Homebrew on macOS — because "install
    Node first" was the step people skipped; an existing Node is never touched.

Deliberately stdlib-only: it has to run before anything is installed.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path


REPO = "junioralbino28/cutmind"
SKILL_NAME = "cutmind"

# Phase 2 needs Remotion domain knowledge, which lives in a SUBDIRECTORY of its
# own repo — so it cannot be cloned into place and has always been a second
# manual step. Installing it here is the difference between "one command" and
# "one command plus a thing you'll forget".
REMOTION_REPO = "remotion-dev/skills"
REMOTION_NAME = "remotion-best-practices"
# Upstream renamed and restructured this: `skills/remotion` became
# `skills/remotion-best-practices`, a router skill that bundles a dozen
# sub-skills as real directories. Try the current path first and keep the old
# one as a fallback so an older --ref still installs.
REMOTION_SUBDIRS = ("skills/remotion-best-practices", "skills/remotion")

# Every agent that reads Agent-Skills-style directories. Add a line to support
# another one; the rest of the installer needs no change.
AGENT_DIRS: list[tuple[str, Path]] = [
    ("Claude Code", Path.home() / ".claude" / "skills"),
    ("ChatGPT Codex", Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills"),
    # Antigravity / Gemini. Path taken from its own bundled documentation
    # (builtin/skills/agy-customizations): skills live at `skills/<name>/SKILL.md`
    # and the machine-local configuration root is `~/.gemini/config/`. Same
    # frontmatter contract as Claude Code — name + description — and the same
    # optional `references/` convention, so cutmind installs there unchanged.
    ("Google Gemini", Path.home() / ".gemini" / "config" / "skills"),
]

# Only these entries belong in an agent's skill directory. The repository may
# also contain contributor tooling, tests or release infrastructure, none of
# which should leak into ~/.claude/skills or ~/.codex/skills. Keeping the
# payload explicit also makes a future accidental large commit harmless to the
# installed copy.
# Remotion 4 needs Node 18+. Below that we warn and do not upgrade on our own:
# the same Node runs the user's other projects.
NODE_MIN = 18

# Espaço em disco, em GB como o Windows mostra (base 1024). Medido numa instalação no
# Windows em 24/10/2026: o .venv ocupa 2,1 GB; a primeira transcrição em português baixa
# mais 5,3 GB de modelos (Whisper large-v3, o padrão do transcribe.py, 2,9 GB, e o
# alinhador wav2vec2, 2,4 GB); e um projeto editado do começo ao fim ocupou 3,3 GB. Abaixo
# de ESPACO_DEPS_GB o uv sync nem começa: baixaria até encher o disco e pararia no meio do
# torch.
ESPACO_DEPS_GB = 3
ESPACO_TRABALHO_GB = 12

SKILL_PAYLOAD = (
    "README.md",
    "README.pt-BR.md",
    "SKILL.md",
    "agents",
    "assets",
    "cutmind_install.py",
    "helpers",
    "install.md",
    "pyproject.toml",
    "references",
    "uv.lock",
)


# ---- idioma: o instalador fala no idioma de quem instala (--idioma, ou o do sistema) ----
# O português é a chave; uma linha com valor ("  ! falhou para Codex: ...") casa pelo padrão da chave
# ("  ! falhou para {name}: {e}") e o valor de dentro também passa pela tradução. Este arquivo roda
# sozinho (baixado da internet), então leva a própria cópia do que o helpers/idioma.py faz.
IDIOMA = "pt"
EN = {
    "  baixando {repo}@{ref}…": "  downloading {repo}@{ref}…",
    "  ! não consegui baixar {repo}@{ref}: {last}": "  ! couldn't download {repo}@{ref}: {last}",
    "  ! o tarball de {repo} veio vazio": "  ! the {repo} tarball came empty",
    "  ! {dest}": "  ! {dest}",
    "    é um link para {p0} — NÃO foi tocado.": "    is a link to {p0} — NOT touched.",
    "    Atualize o clone com: git -C <caminho> pull --ff-only": "    Update the clone with: git -C <path> pull --ff-only",
    "    Ou apague o link e rode de novo para instalar uma cópia normal.": "    Or delete the link and run again to install a normal copy.",
    "    é um clone git — NÃO foi atualizado.": "    is a git clone — NOT updated.",
    "    clone git limpo — substituído pela versão publicada": "    clean git clone — replaced with the published version",
    "    ! o clone tem alterações locais ou arquivos ignorados": "    ! the clone has local changes or ignored files",
    "    guardado em {name} — apague quando tiver conferido": "    kept in {name} — delete it once you've checked",
    "    ! não consegui remover {name}: {e}": "    ! couldn't remove {name}: {e}",
    "  instalando dependências (torch + whisperx, alguns GB na primeira vez)…": "  installing dependencies (torch + whisperx, a few GB the first time)…",
    "  ! uv sync falhou:": "  ! uv sync failed:",
    "  Mac Intel: {trocadas} cópia(s) a mais do OpenMP trocadas por atalho (sem isso a transcrição cai)":
        "  Intel Mac: {trocadas} extra OpenMP copies replaced with a link (otherwise transcription crashes)",
    "  Node.js não encontrado: instalando a versão LTS pelo winget (Fase 2).": "  Node.js not found: installing the LTS version with winget (Phase 2).",
    "  O Windows pode pedir permissão: é o instalador oficial do Node.js.": "  Windows may ask for permission: it's the official Node.js installer.",
    "  Node.js não encontrado: instalando pelo Homebrew (Fase 2)…": "  Node.js not found: installing with Homebrew (Phase 2)…",
    "  ! a instalação do Node.js não rodou: {e}": "  ! the Node.js install didn't run: {e}",
    "  ! a instalação do Node.js falhou:": "  ! the Node.js install failed:",
    "cutmind — instalação": "cutmind — install",
    "  instalando para {name}: {p1}": "  installing for {name}: {p1}",
    "  ! falhou para {name}: {e}": "  ! failed for {name}: {e}",
    "  instalando skill do Remotion (Fase 2): {p0}": "  installing the Remotion skill (Phase 2): {p0}",
    "  ! Remotion falhou em {skills_dir}: {e}": "  ! Remotion failed in {skills_dir}: {e}",
    "  ! skill do Remotion não instalada (a Fase 1 não depende dela)": "  ! Remotion skill not installed (Phase 1 doesn't depend on it)",
    "verificação:": "check:",
    "  x uv         — necessário: {p0}": "  x uv         — required: {p0}",
    "  x dependências — {motivo}. Sem elas a transcrição não funciona.": "  x dependencies — {motivo}. Without them transcription doesn't work.",
    "  ok dependências": "  ok dependencies",
    "  · espaço     — sobram {p0} em {p1}: a primeira transcrição ainda baixa uns 5 GB de modelos, e um vídeo editado ocupa uns 3 GB. Deixe pelo menos {ESPACO_TRABALHO_GB} GB livres.": "  · space      — {p0} left on {p1}: the first transcription still downloads about 5 GB of models, and an edited video takes about 3 GB. Keep at least {ESPACO_TRABALHO_GB} GB free.",
    "  ok ffmpeg": "  ok ffmpeg",
    "  x ffmpeg     — corte e render (Fase 1). Instale com: {p0}": "  x ffmpeg     — cutting and rendering (Phase 1). Install with: {p0}",
    "  ok node": "  ok node",
    "  ok node       — instalado agora ({info}).": "  ok node       — installed just now ({info}).",
    "                 Abra um terminal novo para ele entrar no PATH.": "                 Open a new terminal for it to be on the PATH.",
    "  x node       — {info} é antigo: o Remotion (Fase 2) pede {NODE_MIN}+. Atualize com: {p2}": "  x node       — {info} is old: Remotion (Phase 2) needs {NODE_MIN}+. Update with: {p2}",
    "  x node       — Remotion (Fase 2). Instale com: {p0}": "  x node       — Remotion (Phase 2). Install with: {p0}",
    "  · git        — o CutMind não usa, mas o Claude Code sim. {p0}": "  · git        — CutMind doesn't use it, but Claude Code does. {p0}",
    "instalado em:": "installed in:",
    "ATENÇÃO — estas pastas NÃO foram atualizadas:": "WARNING — these folders were NOT updated:",
    "    É um link para {alvo}.": "    It's a link to {alvo}.",
    "    Instalação de desenvolvedor — o instalador nunca escreve": "    Developer install — the installer never writes",
    "    através de um link, para não apagar o seu clone.": "    through a link, so it doesn't wipe your clone.",
    "    Para atualizar:  git -C {alvo} pull --ff-only": "    To update:  git -C {alvo} pull --ff-only",
    "    Se você não desenvolve a skill, apague o link e rode de novo": "    If you don't develop the skill, delete the link and run again",
    "    para receber uma cópia normal.": "    to get a normal copy.",
    "    É um clone git. Um clone limpo é substituído pela versão": "    It's a git clone. A clean clone is replaced with the published",
    "    publicada; se tiver alterações suas, ele é guardado ao lado.": "    version; if it has your own changes, it's kept alongside.",
    "    Rode de novo com --force:": "    Run again with --force:",
    "NÃO instalado em:": "NOT installed in:",
    "  {name}: {e}": "  {name}: {e}",
    "  Se for 'já está sendo usado por outro processo', feche esse agente": "  If it says 'being used by another process', close that agent",
    "  e rode este comando de novo — o que já instalou permanece.": "  and run this command again — what's already installed stays.",
    "NÃO terminou: falta espaço no disco. Libere até ter uns {p0} GB livres (Lixeira, arquivos temporários, vídeos e instaladores velhos) e rode este comando de novo.": "NOT finished: the disk is out of space. Free up about {p0} GB (Recycle Bin, temporary files, old videos and installers) and run this command again.",
    "NÃO terminou: as dependências do Python não instalaram (o erro está acima). Resolva e rode este comando de novo.": "NOT finished: the Python dependencies didn't install (the error is above). Fix it and run this command again.",
    "Falta instalar: {p0}. Rode os comandos acima e depois este comando de novo.": "Still to install: {p0}. Run the commands above and then this command again.",
    "Instalação parcial — veja o aviso acima antes de usar.": "Partial install — read the warning above before using it.",
    "CutMind atualizado! Você está na última versão publicada.": "CutMind updated! You're on the latest published version.",
    "Reinicie o agente para ele carregar a nova versão.": "Restart the agent so it loads the new version.",
    "Tudo pronto! O CutMind está instalado e pronto para usar no {onde}.": "All set! CutMind is installed and ready to use in {onde}.",
    "Ele fica na pasta geral de skills e vale para todos os seus projetos, não só para esta pasta.": "It lives in the shared skills folder and works for all your projects, not just this folder.",
    "Reinicie o agente e abra uma nova sessão chamando a skill CutMind.": "Restart the agent and open a new session calling the CutMind skill.",
    "Abra a sessão DENTRO da pasta onde estão os seus vídeos.": "Open the session INSIDE the folder where your videos are.",
    "falta espaço no disco ({p0})": "the disk is out of space ({p0})",
    "o uv sync falhou (o erro está acima)": "uv sync failed (the error is above)",
    "{p0} livres em {p1}": "{p0} free on {p1}",
    "o disco encheu": "the disk filled up",
}
_MARCADOR = re.compile(r"\{(\w+)\}")


def _padroes() -> list:
    out = []
    for k, v in EN.items():
        partes = _MARCADOR.split(k)
        if len(partes) == 1 or len(set(partes[1::2])) < len(partes[1::2]):
            continue
        rx = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)" for i, p in enumerate(partes))
        out.append((sum(len(p) for p in partes[::2]), re.compile(f"^{rx}$", re.S), v))
    return [(rx, v) for _, rx, v in sorted(out, key=lambda x: -x[0])]


_PADROES: list = []


def traduzir(msg: str) -> str:
    if IDIOMA != "en" or not msg:
        return msg
    if msg in EN:
        return EN[msg]
    if not _PADROES:
        _PADROES.extend(_padroes())
    for rx, modelo in _PADROES:
        m = rx.match(msg)
        if m:
            valores = {k: traduzir(x) for k, x in m.groupdict().items()}
            return _MARCADOR.sub(lambda mm: valores.get(mm.group(1), mm.group(0)), modelo)
    return msg


def idioma_do_sistema() -> str:
    """pt ou en pelo idioma do sistema; sem pista nenhuma, pt (o que o instalador sempre falou)."""
    if os.name == "nt":  # o LANG do Git Bash diz en_US até num Windows em português: vale o do Windows
        try:
            import ctypes
            return "pt" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x16 else "en"
        except (AttributeError, OSError):
            pass
    import locale
    for v in (os.environ.get("LC_ALL"), os.environ.get("LC_MESSAGES"), os.environ.get("LANG"),
              locale.getlocale()[0]):
        if v and v.split(".")[0] not in ("C", "POSIX"):
            return "pt" if v.lower().startswith(("pt", "portuguese")) else "en"
    return "pt"


def log(msg: str = "") -> None:
    print(traduzir(msg), flush=True)


def detect_targets(explicit: str | None) -> list[tuple[str, Path]]:
    """Where to install. An explicit --target wins.

    Claude Code is ALWAYS a target, not a fallback. It is the documented home for
    this skill, and its config directory does not necessarily exist yet — a fresh
    install can have `~/.claude.json` and no `~/.claude/`. Gating on that
    directory made the installer skip Claude Code entirely on a machine that also
    had Codex: the "does any agent exist" test passed on Codex alone, so the
    fallback never fired and the user was told everything was fine.

    Other agents are added only when their config directory exists, so we don't
    litter `~/.codex/skills` on a machine that has never run Codex.
    """
    if explicit:
        return [("(--target)", Path(explicit).expanduser())]
    targets = [AGENT_DIRS[0]]
    targets += [(name, d) for name, d in AGENT_DIRS[1:] if d.parent.exists()]
    return targets


def fetch_repo(repo: str, ref: str, into: Path, label: str) -> Path | None:
    """Download and unpack `repo` at `ref`. Returns the unpacked directory.

    A tarball rather than `git clone` on purpose — it needs no git on the user's
    machine, which is one less thing to install on Windows.
    """
    log(f"  baixando {repo}@{ref}…")
    tgz = into / f"{label}.tar.gz"
    last = None
    for kind in ("heads", "tags"):
        try:
            url = f"https://codeload.github.com/{repo}/tar.gz/refs/{kind}/{ref}"
            with urllib.request.urlopen(url, timeout=120) as r, open(tgz, "wb") as f:
                shutil.copyfileobj(r, f)
            break
        except Exception as e:
            last = e
    else:
        log(f"  ! não consegui baixar {repo}@{ref}: {last}")
        return None

    out = into / label
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz) as tf:
        # filter="data" refuses absolute paths and traversal outside the target.
        try:
            tf.extractall(out, filter="data")
        except TypeError:      # Python < 3.12 has no filter=
            tf.extractall(out)
    roots = [p for p in out.iterdir() if p.is_dir()]
    if not roots:
        log(f"  ! o tarball de {repo} veio vazio")
        return None
    return roots[0]


def _validate_payload(src: Path) -> None:
    missing = [entry for entry in SKILL_PAYLOAD if not (src / entry).exists()]
    if missing:
        raise FileNotFoundError(
            "payload da skill incompleto: " + ", ".join(sorted(missing)))


def _copy_payload(src: Path, dest: Path) -> None:
    """Copy only the published skill payload from a CutMind checkout."""
    dest.mkdir(parents=True, exist_ok=True)
    for entry in SKILL_PAYLOAD:
        source = src / entry
        target = dest / entry
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def install_into(src: Path, skills_dir: Path, force: bool,
                 name: str = SKILL_NAME) -> Path | None:
    """Copy a skill into an agent's skills directory, replacing any previous
    copy. Refuses to touch a git checkout — that is somebody's development
    clone, and silently overwriting uncommitted work is unforgivable.

    Returns None when it skipped. That distinction is not cosmetic: this used to
    return `dest` either way, so a skipped directory was listed under "instalado
    em" and handed to uv sync. A user on the old layout re-ran the installer to
    get a new version, was told everything was fine, and kept running the old
    code — which is how a student ended up being asked for a Groq key months
    after that backend was deleted.
    """
    dest = skills_dir / name
    if name == SKILL_NAME:
        # Validate before touching an existing install. A truncated download
        # must not destroy a working skill and only then report what was absent.
        _validate_payload(src)

    # NEVER write through a symlink, with or without --force.
    #
    # The old manual install told people to clone the repo and symlink it into
    # the skills directory. Deleting the "destination" then reaches through the
    # link and empties the real clone — which is how a maintainer lost .git and
    # a directory of gitignored personal templates that had never been pushed
    # anywhere. Replacing the LINK instead of its target would be just as wrong:
    # it silently detaches a developer from their checkout.
    if dest.is_symlink():
        log(f"  ! {dest}")
        log(f"    é um link para {os.path.realpath(dest)} — NÃO foi tocado.")
        log("    Atualize o clone com: git -C <caminho> pull --ff-only")
        log("    Ou apague o link e rode de novo para instalar uma cópia normal.")
        return None

    if (dest / ".git").exists():
        if not force:
            log(f"  ! {dest}")
            log(f"    é um clone git — NÃO foi atualizado.")
            return None
        # --force over a real checkout. A pristine clone — which is what the old
        # manual install leaves on a user's machine — holds nothing that isn't on
        # the remote, so replacing it outright is right and leaves no clutter
        # behind. A DIRTY clone is the opposite: uncommitted edits and gitignored
        # files exist nowhere else, and that is precisely what was destroyed once
        # already. So ask git which one this is, and only keep a copy when the
        # answer says something would be lost.
        if _clone_is_pristine(dest):
            _rmtree(dest)
            log("    clone git limpo — substituído pela versão publicada")
        else:
            backup = dest.with_name(f"{name}.backup-{int(time.time())}")
            dest.rename(backup)
            log(f"    ! o clone tem alterações locais ou arquivos ignorados")
            log(f"    guardado em {backup.name} — apague quando tiver conferido")

    skills_dir.mkdir(parents=True, exist_ok=True)

    # Replace the old copy WITHOUT deleting `.venv` or `.env`.
    #
    # `.env` is the user's keys — not ours to drop. `.venv` is skipped for two
    # reasons. It is the likeliest thing to be locked: on Windows, rmtree dies
    # with WinError 32 if any file in the tree is open, and a running agent (or
    # an antivirus mid-scan) holds the venv's DLLs — measured, that is exactly
    # how a reinstall crashed. And deleting it threw away ~2 GB of torch on
    # every update, so "re-run the same command to update" meant re-downloading
    # the world; `uv sync` reconciles an existing venv in seconds instead.
    # .git is here as a second line of defence: the branches above should mean
    # we never iterate a checkout, but if one ever slips through, losing the
    # repository is unrecoverable while losing a copied file is not.
    KEEP = {".venv", ".env", ".git"}
    if dest.exists():
        for entry in dest.iterdir():
            if entry.name in KEEP:
                continue
            try:
                if entry.is_dir() and not entry.is_symlink():
                    _rmtree(entry)
                else:
                    entry.unlink()
            except OSError as e:
                log(f"    ! não consegui remover {entry.name}: {e}")
    # dirs_exist_ok so the surviving .venv/.env keep their place. CutMind uses an
    # explicit allowlist; third-party skills (currently Remotion) retain their
    # own complete directory structure.
    if name == SKILL_NAME:
        _copy_payload(src, dest)
    else:
        shutil.copytree(src, dest, dirs_exist_ok=True)
    return dest


def _clone_is_pristine(repo: Path) -> bool:
    """True when nothing in `repo` would be lost by deleting it.

    `--ignored` is the load-bearing flag. Plain `git status --porcelain` calls a
    checkout clean while `.venv/`, `.env` and a directory of gitignored personal
    templates sit inside it — which is exactly the set that was destroyed once.

    Anything unexpected (no git on PATH, not a repo, a timeout) returns False.
    The cost of a wrong "pristine" is unrecoverable; the cost of a wrong "dirty"
    is a folder the user deletes by hand.
    """
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--ignored"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode != 0:
        return False
    # The venv and the key file are ours to carry across an install anyway.
    leftovers = [ln for ln in r.stdout.splitlines()
                 if ln.strip() and not ln[3:].startswith((".venv/", ".env", "cutmind.egg-info/"))]
    return not leftovers


def _rmtree(path: Path) -> None:
    """rmtree that clears the read-only bit and retries once.

    Windows refuses to delete read-only files, and git checkouts and some
    unpackers leave them behind. A lock (WinError 32) is a different failure and
    still propagates — chmod cannot help there.

    `onexc` is 3.12+; `onerror` is the 3.10/3.11 spelling and takes the same
    three arguments in the same order, so one handler serves both.
    """
    def handler(func, p, exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            raise
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=handler)
    else:
        shutil.rmtree(path, onerror=handler)


def _python_do_sync() -> list[str]:
    """No Mac Intel o kit fica numa pilha anterior (o pyproject.toml explica por quê): a
    última roda Intel do torch (2.2.2) não existe para Python 3.13, e sem pedir o 3.12 o
    uv escolheria o 3.13 e pararia no meio. Nas outras máquinas nada muda."""
    if sys.platform == "darwin" and platform.machine() == "x86_64":
        return ["--python", "3.12"]
    return []


def run_uv_sync(dest: Path) -> str | None:
    """Install the Python dependencies. Returns None on success, else the end of the error."""
    log("  instalando dependências (torch + whisperx, alguns GB na primeira vez)…")
    r = subprocess.run(["uv", "sync", "--directory", str(dest), *_python_do_sync()],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        erro = (r.stderr or "").strip()[-600:]
        log("  ! uv sync falhou:")
        log("    " + erro)
        return erro or f"uv sync saiu com o código {r.returncode}"
    return None


def um_so_openmp(dest: Path) -> int:
    """No Mac Intel o torch 2.2.2 e o ctranslate2 (o motor do Whisper) trazem cada um a sua cópia do
    libiomp5.dylib, o OpenMP da Intel, e com as duas no mesmo processo a transcrição cai com SIGSEGV
    (faster-whisper #137 e #541; o KMP_DUPLICATE_LIB_OK não resolve, medido). Fica uma cópia só: as
    outras viram atalho para a do ctranslate2. Devolve quantas trocou; nas outras máquinas, 0."""
    if not (sys.platform == "darwin" and platform.machine() == "x86_64"):
        return 0
    trocadas = 0
    for site in (dest / ".venv" / "lib").glob("python3*/site-packages"):
        alvo = site / "ctranslate2" / ".dylibs" / "libiomp5.dylib"
        if not alvo.is_file() or alvo.is_symlink():
            continue
        for outro in sorted(site.rglob("libiomp5.dylib")):
            if outro == alvo or (outro.is_symlink() and outro.resolve() == alvo.resolve()):
                continue
            outro.unlink()
            outro.symlink_to(alvo)
            trocadas += 1
    if trocadas:
        log(f"  Mac Intel: {trocadas} cópia(s) a mais do OpenMP trocadas por atalho (sem isso a transcrição cai)")
    return trocadas


def instalar_dependencias(dests: list[Path]) -> tuple[str, str] | None:
    """uv sync em cada destino. None quando deu certo; senão (tipo, detalhe), com o
    tipo "espaco" (o disco não comporta, ou encheu no meio) ou "falhou".

    O resumo do fim depende disto. No primeiro piloto real o uv sync parou no meio do
    torch com o disco cheio, e a instalação terminou dizendo "Tudo pronto!".
    """
    # Destino sem .venv é instalação do zero, uns 2 GB de pacotes. Com o .venv lá o uv
    # só acerta a diferença, e barrar por espaço impediria uma atualização pequena.
    if any(not (d / ".venv").exists() for d in dests):
        livre = espaco_livre(dests + [p for p in (_cache_do_uv(),) if p])
        if livre and livre[0] < ESPACO_DEPS_GB:
            return "espaco", f"{_gb(livre[0])} livres em {livre[1]}"
    for d in dests:
        erro = run_uv_sync(d)
        if not erro:
            um_so_openmp(d)
        if erro:
            if not _disco_cheio(erro):
                return "falhou", erro
            livre = espaco_livre([d])
            return "espaco", (f"{_gb(livre[0])} livres em {livre[1]}" if livre
                              else "o disco encheu")
    return None


def _disco_cheio(erro: str) -> bool:
    """O uv parou por disco cheio? O texto vem no idioma do sistema ("Espaço
    insuficiente no disco", "No space left on device") e o número do erro não, mas
    112 no Linux é outra coisa (host fora do ar): por isso o número depende do sistema."""
    codigo = 112 if sys.platform == "win32" else 28
    return bool(re.search(rf"os error {codigo}\b|no space left on device"
                          r"|not enough space on the disk|insuficiente no disco", erro, re.I))


def _cache_do_uv() -> Path | None:
    """Onde o uv guarda os pacotes: os GB do torch entram ali antes de chegar ao .venv."""
    try:
        r = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    caminho = (r.stdout or "").strip()
    return Path(caminho) if r.returncode == 0 and caminho else None


def espaco_livre(pastas: list[Path]) -> tuple[float, str] | None:
    """O menor espaço livre (GB) entre os discos dessas pastas, e qual disco é."""
    menor = None
    for p in pastas:
        q = Path(p)
        while not q.exists() and q.parent != q:   # o cache do uv só nasce no 1º download
            q = q.parent
        try:
            gb = shutil.disk_usage(q).free / 2**30
        except OSError:
            continue
        if menor is None or gb < menor[0]:
            menor = (gb, q.anchor or str(q))
    return menor


def _gb(valor: float) -> str:
    n = f"{valor:.1f}"
    return (n.replace(".", ",") if IDIOMA == "pt" else n) + " GB"


def hint(tool: str) -> str:
    """The install command for this platform, not a generic one."""
    if sys.platform == "darwin":
        return {"uv": "brew install uv", "ffmpeg": "brew install ffmpeg",
                "node": "brew install node", "git": "brew install git"}[tool]
    if sys.platform == "win32":
        return {"uv": "winget install astral-sh.uv", "ffmpeg": "winget install Gyan.FFmpeg",
                "node": "winget install OpenJS.NodeJS.LTS",
                "git": "winget install Git.Git"}[tool]
    return {"uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
            "ffmpeg": "sudo apt install ffmpeg  (ou o gerenciador da sua distro)",
            "node": "sudo apt install nodejs npm  (precisa ser 18+)",
            "git": "sudo apt install git"}[tool]


def node_version(exe: str | None = None) -> int | None:
    """The major version of `node` (or of `exe`), or None when absent/unreadable."""
    exe = exe or shutil.which("node")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r"\s*v(\d+)\.", out or "")
    return int(m.group(1)) if m else None


def _node_apos_instalar() -> str | None:
    """winget and brew only reach the PATH of NEW terminals, so this one may not
    see the fresh node: look where they put it."""
    cands = [shutil.which("node")]
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
            if base:
                cands.append(os.path.join(base, "nodejs", "node.exe"))
    elif sys.platform == "darwin":
        cands += ["/opt/homebrew/bin/node", "/usr/local/bin/node"]
    return next((c for c in cands if c and os.path.isfile(c)), None)


def install_node() -> str | None:
    """Node.js LTS by the system's own package manager, with no questions asked.

    Linux is left to the hint on purpose: apt asks for a password and the
    distribution's nodejs is often older than 18. Returns the node path or None.
    """
    if sys.platform == "win32" and shutil.which("winget"):
        cmd = ["winget", "install", "--id", "OpenJS.NodeJS.LTS", "-e", "--silent",
               "--accept-package-agreements", "--accept-source-agreements"]
        log("  Node.js não encontrado: instalando a versão LTS pelo winget (Fase 2).")
        log("  O Windows pode pedir permissão: é o instalador oficial do Node.js.")
    elif sys.platform == "darwin" and shutil.which("brew"):
        cmd = ["brew", "install", "node"]
        log("  Node.js não encontrado: instalando pelo Homebrew (Fase 2)…")
    else:
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1200)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"  ! a instalação do Node.js não rodou: {e}")
        return None
    exe = _node_apos_instalar()
    if not exe and r.returncode != 0:
        log("  ! a instalação do Node.js falhou:")
        log("    " + ((r.stderr or "") + (r.stdout or "")).strip()[-400:])
    return exe


def garantir_node(pode_instalar: bool) -> tuple[str, str]:
    """The state of Node for Phase 2: ("ok", "v24"), ("instalado", path),
    ("velho", "v16") or ("falta", "")."""
    v = node_version()
    if v is not None:
        return ("ok" if v >= NODE_MIN else "velho", f"v{v}")
    if pode_instalar:
        exe = install_node()
        v2 = node_version(exe) if exe else None
        if v2 is not None and v2 >= NODE_MIN:
            return "instalado", exe
    return "falta", ""


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="cutmind-install",
        description="Instala a skill cutmind no seu agente (Claude Code, Codex, …).")
    ap.add_argument("--ref", default="main", help="branch ou tag (padrão: main)")
    ap.add_argument("--target", default=None,
                    help="pasta de skills específica, em vez de detectar")
    ap.add_argument("--force", action="store_true",
                    help="substituir mesmo que o destino seja um clone git")
    ap.add_argument("--no-remotion", action="store_true",
                    help="não instalar a skill do Remotion (só a Fase 1)")
    ap.add_argument("--source", default=None,
                    help="instalar a partir de uma pasta local (um clone), sem baixar")
    ap.add_argument("--skip-deps", action="store_true",
                    help="não rodar o uv sync nem instalar o Node.js (usado nos testes)")
    ap.add_argument("--no-node", action="store_true",
                    help="não instalar o Node.js sozinho quando faltar (só avisar)")
    ap.add_argument("--idioma", "--lang", dest="idioma", choices=("pt", "en"), default=None,
                    help="idioma das mensagens / message language (padrão: o do sistema)")
    args = ap.parse_args()
    global IDIOMA
    IDIOMA = args.idioma or idioma_do_sistema()
    # quem lê esta saída costuma ser o agente, por um pipe: no Windows o pipe sai na página de
    # código antiga e os acentos chegam como "�"
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    log("cutmind — instalação")
    log()

    targets = detect_targets(args.target)
    dests: list[Path] = []
    failed: list[tuple[str, Exception]] = []
    skipped: list[tuple[Path, str]] = []   # (caminho, motivo)
    instalados: list[str] = []             # nomes dos agentes que receberam
    # 'atualização' vs 'primeira vez' tem de ser medido antes da cópia —
    # depois dela todo destino tem um SKILL.md e a pergunta não existe mais.
    ja_existia = any((d / SKILL_NAME / 'SKILL.md').exists() for _, d in targets)
    with tempfile.TemporaryDirectory() as tmp:
        src = (Path(args.source).resolve() if args.source
               else fetch_repo(REPO, args.ref, Path(tmp), SKILL_NAME))
        if src is None:
            sys.exit(1)
        # One agent failing must not cost the others. A locked directory under
        # ~/.codex used to abort the run AFTER Claude Code was already written,
        # so the user got a traceback, no dependency install, no Remotion skill,
        # and no idea that half of it had worked.
        for name, skills_dir in targets:
            log(f"  instalando para {name}: {skills_dir / SKILL_NAME}")
            try:
                d = install_into(src, skills_dir, args.force)
                if d is None:
                    dest = skills_dir / SKILL_NAME
                    # Record WHY. The banner used to assume every skip was a
                    # git clone and prescribe --force — advice that does nothing
                    # for a symlink, which is never touched in either mode.
                    skipped.append((dest, "link" if dest.is_symlink() else "clone"))
                else:
                    dests.append(d)
                    instalados.append(name)
            except Exception as e:
                failed.append((name, e))
                log(f"  ! falhou para {name}: {e}")

        if not args.no_remotion:
            rsrc = fetch_repo(REMOTION_REPO, "main", Path(tmp), "remotion")
            sub = next((rsrc / s for s in REMOTION_SUBDIRS if (rsrc / s).is_dir()),
                       None) if rsrc else None
            if sub and sub.is_dir():
                for _, skills_dir in targets:
                    log(f"  instalando skill do Remotion (Fase 2): {skills_dir / REMOTION_NAME}")
                    try:
                        install_into(sub, skills_dir, args.force, name=REMOTION_NAME)
                    except Exception as e:
                        log(f"  ! Remotion falhou em {skills_dir}: {e}")
            else:
                log("  ! skill do Remotion não instalada (a Fase 1 não depende dela)")

    # Every destination needs its own .venv — helpers run as `uv run python …`
    # from whichever copy the agent loaded. Syncing only the first one left the
    # second agent with a skill that imports nothing. uv hardlinks from its
    # global cache, so the extra copies are cheap.
    # Whether uv exists is asked of the system, never inferred from the sync: a run
    # that skipped every destination has nothing to sync and still has uv.
    have_uv = bool(shutil.which("uv"))
    deps_erro = None
    if have_uv and dests and not args.skip_deps:
        deps_erro = instalar_dependencias(dests)

    log()
    log("verificação:")
    missing = []
    if not have_uv:
        missing.append("uv")
        log(f"  x uv         — necessário: {hint('uv')}")
    else:
        log("  ok uv")
    if deps_erro:
        motivo = (f"falta espaço no disco ({deps_erro[1]})" if deps_erro[0] == "espaco"
                  else "o uv sync falhou (o erro está acima)")
        log(f"  x dependências — {motivo}. Sem elas a transcrição não funciona.")
    elif have_uv and dests and not args.skip_deps:
        log("  ok dependências")
        livre = espaco_livre(dests)
        if livre and livre[0] < ESPACO_TRABALHO_GB:
            log(f"  · espaço     — sobram {_gb(livre[0])} em {livre[1]}: a primeira transcrição"
                " ainda baixa uns 5 GB de modelos, e um vídeo editado ocupa uns 3 GB."
                f" Deixe pelo menos {ESPACO_TRABALHO_GB} GB livres.")
    if shutil.which("ffmpeg"):
        log("  ok ffmpeg")
    else:
        missing.append("ffmpeg")
        log(f"  x ffmpeg     — corte e render (Fase 1). Instale com: {hint('ffmpeg')}")
    # Node only matters for Phase 2, so --no-remotion never installs it.
    estado, info = garantir_node(
        pode_instalar=not (args.skip_deps or args.no_remotion or args.no_node))
    if estado == "ok":
        log("  ok node")
    elif estado == "instalado":
        log(f"  ok node       — instalado agora ({info}).")
        log("                 Abra um terminal novo para ele entrar no PATH.")
    elif estado == "velho":
        missing.append("node")
        log(f"  x node       — {info} é antigo: o Remotion (Fase 2) pede {NODE_MIN}+."
            f" Atualize com: {hint('node')}")
    else:
        missing.append("node")
        log(f"  x node       — Remotion (Fase 2). Instale com: {hint('node')}")
    # git is not a CutMind dependency — the install above used no git at all. But
    # Claude Code leans on it, so its absence is worth a word rather than
    # silence. Deliberately NOT added to `missing`: nothing here is blocked by it.
    if not shutil.which("git"):
        log(f"  · git        — o CutMind não usa, mas o Claude Code sim. {hint('git')}")

    # Say where it landed, explicitly. The failure this replaces was silent: the
    # installer reported success while having skipped the agent the user actually
    # runs, and they only found out when the skill wasn't there.
    log()
    log("instalado em:")
    for d in dests:
        log(f"  {d}")
        if (d.parent / REMOTION_NAME).is_dir():
            log(f"  {d.parent / REMOTION_NAME}")

    if skipped:
        log()
        log("=" * 68)
        log("ATENÇÃO — estas pastas NÃO foram atualizadas:")
        for d, motivo in skipped:
            log(f"  {d}")
            if motivo == "link":
                alvo = os.path.realpath(d)
                log(f"    É um link para {alvo}.")
                log("    Instalação de desenvolvedor — o instalador nunca escreve")
                log("    através de um link, para não apagar o seu clone.")
                log(f"    Para atualizar:  git -C {alvo} pull --ff-only")
                log("    Se você não desenvolve a skill, apague o link e rode de novo")
                log("    para receber uma cópia normal.")
            else:
                log("    É um clone git. Um clone limpo é substituído pela versão")
                log("    publicada; se tiver alterações suas, ele é guardado ao lado.")
                log("    Rode de novo com --force:")
                log("      uv run https://raw.githubusercontent.com/junioralbino28/cutmind/"
                    "main/cutmind_install.py --force")
        log("=" * 68)

    if failed:
        log()
        log("NÃO instalado em:")
        for name, e in failed:
            log(f"  {name}: {e}")
        log("  Se for 'já está sendo usado por outro processo', feche esse agente")
        log("  e rode este comando de novo — o que já instalou permanece.")

    log()
    if deps_erro:
        if deps_erro[0] == "espaco":
            log("NÃO terminou: falta espaço no disco. Libere até ter uns"
                f" {ESPACO_DEPS_GB + ESPACO_TRABALHO_GB} GB livres (Lixeira, arquivos"
                " temporários, vídeos e instaladores velhos) e rode este comando de novo.")
        else:
            log("NÃO terminou: as dependências do Python não instalaram (o erro está acima)."
                " Resolva e rode este comando de novo.")
    if missing:
        log(f"Falta instalar: {', '.join(missing)}. Rode os comandos acima e"
            " depois este comando de novo.")
    if deps_erro:
        sys.exit(1)   # quem roda isto por um agente vê a falha também pelo código de saída
    if missing:
        return

    if skipped:
        log("Instalação parcial — veja o aviso acima antes de usar.")
        return

    # Name the agents it actually wrote to, not the three it supports. Telling
    # someone to use the skill in Codex when they only run Claude Code sends
    # them looking for something that is not there.
    onde = instalados[0] if len(instalados) == 1 else \
        ", ".join(instalados[:-1]) + (" e " if IDIOMA == "pt" else " and ") + instalados[-1]

    if ja_existia:
        log("CutMind atualizado! Você está na última versão publicada.")
        log()
        log("Reinicie o agente para ele carregar a nova versão.")
    else:
        log(f"Tudo pronto! O CutMind está instalado e pronto para usar no {onde}.")
        # A dúvida do primeiro piloto real: instalar "no projeto" ou "no Claude todo".
        # A pasta da conversa da instalação não importa; dizer isso evita que a pessoa
        # instale de novo em cada pasta de vídeos.
        log("Ele fica na pasta geral de skills e vale para todos os seus projetos, não só para esta pasta.")
        log()
        log("Reinicie o agente e abra uma nova sessão chamando a skill CutMind.")
        log()
        # The one operational detail that cannot be dropped: the session has to
        # start in the footage folder. Opened anywhere else the agent has
        # nothing to edit, and Hard Rule 9 puts every output next to the
        # sources — so the wrong folder is a wrong session, not a recoverable
        # mistake. Only said on a first install; by the second run they know.
        log("Abra a sessão DENTRO da pasta onde estão os seus vídeos.")


if __name__ == "__main__":
    main()
