#!/usr/bin/env python3
"""A lista de projetos do editor (a tela Projetos) e qual deles está aberto.

Fica fora de qualquer projeto, em `~/.cutmind` (ou na pasta de `CUTMIND_HOME`):

    projetos.json  {"versao": 1, "projetos": [{"id": "…", "edit": "<caminho absoluto>", "visto": <epoch>}]}
    aberto.json    {"id": "…", "edit": "…", "nome": "…", "quando": <epoch>}

Um projeto é uma pasta `edit/` com o `state.json` do kit. O id é um hash curto do
caminho: o editor pede para abrir PELO ID, nunca por caminho, então nenhum pedido
pela rede abre uma pasta que não esteja na lista. Pasta que sumiu sai da lista.

`aberto.json` diz qual projeto o editor está mostrando. O servidor grava ao subir e a
cada troca; o `watch_edits.py` vigia esse arquivo e avisa o agente quando o usuário
abre outro projeto (ou cria um novo) pelo editor.

    python projetos.py listar
    python projetos.py procurar <pasta> [<pasta> ...] [--fundo 4]
    python projetos.py registrar <edit>
    python projetos.py aberto
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

VERSAO = 1
MAX_PROJETOS = 500
# o que conta como "mexeram no projeto": a última mudança de qualquer um destes
MUDANCAS = ("state.json", "edl.json", "preview_edits.json", "preview_style.json", "camadas.json",
            "efeitos.json", "velocidade.json", "cut.mp4", "final.mp4", "final-entrega.mp4")
# pastas que nunca têm projeto dentro e custam caro de varrer
PULAR = {"node_modules", ".git", ".venv", "venv", "__pycache__", "remotion", ".preview_cache",
         "clips_graded", "transcripts", "verify", "AppData", "Library", ".cache"}
NOME_MAX = 60
# nomes que o Windows não deixa usar como pasta
RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_lock = threading.Lock()


def casa() -> Path:
    """A pasta do kit no usuário (a lista, o aberto e os modelos)."""
    return Path(os.environ.get("CUTMIND_HOME") or Path.home() / ".cutmind")


def _chave(edit: Path) -> str:
    s = str(Path(edit).resolve())
    return s.casefold() if os.name == "nt" else s


def id_de(edit: Path) -> str:
    return hashlib.sha1(_chave(edit).encode("utf-8")).hexdigest()[:12]


def _ler(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(json.dumps(d, ensure_ascii=False, indent=2).encode("utf-8"))
    for vez in range(40):  # até 2 s: no Windows a troca falha enquanto outro processo lê o arquivo
        try:                # (o vigia lê o aberto.json a cada meio segundo)
            tmp.replace(p)
            return
        except PermissionError:
            if vez == 39:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def lista() -> list[dict]:
    """Os projetos registrados que ainda existem (os que sumiram saem do arquivo)."""
    with _lock:
        d = _ler(casa() / "projetos.json")
        itens = [x for x in d.get("projetos", []) if isinstance(x, dict) and isinstance(x.get("edit"), str)]
        vivos = [x for x in itens if (Path(x["edit"]) / "state.json").is_file() or Path(x["edit"]).is_dir()]
        if len(vivos) != len(itens):
            _gravar(casa() / "projetos.json", {"versao": VERSAO, "projetos": vivos})
        return vivos


def registrar(edit: Path) -> str:
    """Põe (ou atualiza) a pasta `edit/` na lista e devolve o id."""
    edit = Path(edit).resolve()
    if not edit.is_dir():
        raise FileNotFoundError(f"pasta do projeto não existe: {edit}")
    pid = id_de(edit)
    with _lock:
        d = _ler(casa() / "projetos.json")
        itens = [x for x in d.get("projetos", []) if isinstance(x, dict) and x.get("id") != pid]
        itens.insert(0, {"id": pid, "edit": str(edit), "visto": time.time()})
        _gravar(casa() / "projetos.json", {"versao": VERSAO, "projetos": itens[:MAX_PROJETOS]})
    return pid


def por_id(pid: str) -> Path | None:
    if not isinstance(pid, str) or not re.fullmatch(r"[0-9a-f]{12}", pid):
        return None
    for x in lista():
        if x.get("id") == pid:
            p = Path(x["edit"])
            return p if p.is_dir() else None
    return None


def procurar(pastas: list[Path], fundo: int = 4) -> list[Path]:
    """Acha as pastas `edit/` com `state.json` até `fundo` níveis abaixo de cada pasta."""
    achados: list[Path] = []

    def andar(p: Path, nivel: int) -> None:
        if nivel > fundo:
            return
        try:
            filhos = list(os.scandir(p))
        except OSError:
            return
        for f in filhos:
            if not f.is_dir(follow_symlinks=False) or f.name in PULAR or f.name.startswith("."):
                continue
            if f.name == "edit" and os.path.isfile(os.path.join(f.path, "state.json")):
                achados.append(Path(f.path).resolve())
                continue
            andar(Path(f.path), nivel + 1)

    for pasta in pastas:
        pasta = Path(pasta)
        if (pasta / "state.json").is_file():
            achados.append(pasta.resolve())
        elif pasta.is_dir():
            andar(pasta, 0)
    return achados


def nome_seguro(nome: str) -> str:
    """O nome de pasta de um projeto novo: letras (com acento), números, espaço, - e _."""
    s = re.sub(r"[^\w \-]", "", str(nome or ""), flags=re.UNICODE).strip()
    s = re.sub(r"\s+", " ", s)[:NOME_MAX].strip()
    if not s or s.upper() in RESERVADOS:
        raise ValueError("nome do projeto vazio ou inválido")
    return s


def criar(base: Path, nome: str, montagem: bool = False) -> Path:
    """Pasta nova `<base>/<nome>/edit/` com um state.json esperando os vídeos (com `montagem`, um
    modelo de montagem, a música e as fotos e clipes: o editor abre o painel Modelos de montagem).

    O nome repetido ganha " 2", " 3"…; devolve a pasta `edit/` (já registrada).
    """
    limpo = nome_seguro(nome)
    base = Path(base).resolve()
    pasta, n = base / limpo, 2
    while pasta.exists():
        pasta, n = base / f"{limpo} {n}", n + 1
    edit = pasta / "edit"
    edit.mkdir(parents=True)
    estado = {"project": nome.strip()[:NOME_MAX], "phase": 0, "video": "cut.mp4", "edl": "edl.json",
              "message": "Projeto novo: escolha o vídeo e o agente começa o corte.", "novo": True}
    if montagem:
        estado.update(message="Montagem nova: escolha um modelo, a música e as fotos e clipes.", montagem=True)
    _gravar(edit / "state.json", estado)
    registrar(edit)
    return edit


def _video_capa(edit: Path, estado: dict) -> Path | None:
    for rel in (estado.get("finalVideo"), estado.get("video"), "final.mp4", "cut.mp4"):
        if isinstance(rel, str) and rel:
            p = (edit / rel).resolve()
            if p.is_file() and p.is_relative_to(edit.resolve()):
                return p
    # projeto sem corte ainda: o primeiro vídeo da pasta de cima
    for ext in (".mp4", ".mov", ".m4v", ".mkv", ".webm"):
        for p in sorted(edit.parent.glob(f"*{ext}")) + sorted(edit.parent.glob(f"*{ext.upper()}")):
            if p.is_file():
                return p
    return None


def _duracao(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(video)], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def resumo(edit: Path) -> dict:
    """O cartão de um projeto: nome, fase, mensagem, duração e a última mudança."""
    edit = Path(edit)
    estado = _ler(edit / "state.json")
    cache_p = edit / ".preview_cache" / "projeto.json"
    video = _video_capa(edit, estado)
    dur = 0.0
    if video:
        st = video.stat()
        sig = f"{video}|{st.st_mtime_ns}|{st.st_size}"
        cache = _ler(cache_p)
        if cache.get("sig") == sig and isinstance(cache.get("duracao"), (int, float)):
            dur = float(cache["duracao"])
        else:
            dur = _duracao(video)
            try:
                _gravar(cache_p, {"sig": sig, "duracao": dur})
            except OSError:
                pass
    mudou = 0.0
    for nome in MUDANCAS:
        try:
            mudou = max(mudou, (edit / nome).stat().st_mtime)
        except OSError:
            pass
    fase = estado.get("phase")
    return {
        "id": id_de(edit),
        "nome": str(estado.get("project") or edit.parent.name)[:120],
        "pasta": edit.parent.name,
        "fase": fase if isinstance(fase, int) else None,
        "aguardandoEstilo": bool(estado.get("awaitingStyle")),
        "novo": bool(estado.get("novo")) and not (edit / "edl.json").exists(),
        "mensagem": str(estado.get("message") or "")[:300],
        "duracao": round(dur, 2),
        "mudou": mudou,
        "temCapa": video is not None,
    }


def capa(edit: Path) -> Path | None:
    """Um quadro do vídeo do projeto (JPEG de 360 px de altura), refeito só quando o vídeo muda."""
    edit = Path(edit)
    video = _video_capa(edit, _ler(edit / "state.json"))
    if not video:
        return None
    out = edit / ".preview_cache" / "capa.jpg"
    sig_p = edit / ".preview_cache" / "capa.json"
    st = video.stat()
    sig = f"{video}|{st.st_mtime_ns}|{st.st_size}"
    if out.is_file() and _ler(sig_p).get("sig") == sig:
        return out
    dur = resumo(edit)["duracao"] or 0
    t = min(1.5, dur * 0.3) if dur else 0
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("capa.tmp.jpg")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=-2:360", "-q:v", "4", str(tmp)], capture_output=True)
    if r.returncode != 0 or not tmp.is_file():
        return None
    tmp.replace(out)
    _gravar(sig_p, {"sig": sig})
    return out


def marcar_aberto(edit: Path) -> None:
    edit = Path(edit).resolve()
    estado = _ler(edit / "state.json")
    _gravar(casa() / "aberto.json", {"id": id_de(edit), "edit": str(edit),
                                     "nome": str(estado.get("project") or edit.parent.name),
                                     "quando": time.time()})


def aberto() -> dict | None:
    d = _ler(casa() / "aberto.json")
    return d if d.get("edit") else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar")
    pr = sub.add_parser("procurar")
    pr.add_argument("pastas", nargs="+", type=Path)
    pr.add_argument("--fundo", type=int, default=4)
    rg = sub.add_parser("registrar")
    rg.add_argument("edit", type=Path)
    sub.add_parser("aberto")
    a = ap.parse_args()
    if a.cmd == "listar":
        for x in lista():
            r = resumo(Path(x["edit"]))
            print(f"{r['id']}  {r['nome']}  · fase {r['fase']} · {r['duracao']:.0f} s · {x['edit']}")
    elif a.cmd == "procurar":
        achados = procurar(a.pastas, a.fundo)
        for edit in achados:
            registrar(edit)
            print(f"registrado: {edit}")
        print(f"{len(achados)} projeto(s)")
    elif a.cmd == "registrar":
        print(registrar(a.edit))
    elif a.cmd == "aberto":
        ab = aberto()
        print(json.dumps(ab, ensure_ascii=False) if ab else "nenhum")
    return 0


if __name__ == "__main__":
    sys.exit(main())
