"""Pacotes do kit (trilhas, filtros e transições; depois, efeitos e textos): baixar só quando usar.

O catálogo diz o que existe e de onde vem. Cada pacote é um arquivo de uma Release do
repositório de pacotes, no endereço `<base>/<release>/<arquivo>`. `obter` baixa para o
cache deste computador, confere tamanho e sha256 e só então guarda. Os favoritos ficam;
os outros saem, do menos usado para o mais usado, quando o cache passa do limite.
Filtro e transição são um zip que `aberto` abre numa pasta ao lado, lida pelo motor de
efeitos (assets/efeitos/motor.js); a pasta sai do cache junto com o zip.

Quem usa: o agente, pela linha de comando, e o servidor do editor (o celular toca em
"Usar" e o servidor baixa, sem agente no meio).

    python helpers/pacotes.py listar [--tipo trilha] [--busca calma]
    python helpers/pacotes.py obter <id> [--para <edit>/midia]
    python helpers/pacotes.py abrir <id>                        # filtro/transição: a pasta aberta
    python helpers/pacotes.py camada <edit> <id> [--inicio 0]   # trilha na linha do tempo
    python helpers/pacotes.py favorito <id> [--tirar]
    python helpers/pacotes.py cache                             # o que está guardado
    python helpers/pacotes.py atualizar                         # catálogo novo, sem atualizar o kit

Variáveis (todas opcionais):
    CUTMIND_PACOTES_DIR         o cache (padrão ~/.cutmind/pacotes)
    CUTMIND_PACOTES_LIMITE_GB   o tamanho do cache (padrão 2)
    CUTMIND_PACOTES_BASE        outro servidor com a mesma árvore da Release (plano B)
    CUTMIND_PACOTES_CATALOGO    outro catálogo (testes)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import quote, urlparse

import camadas as cam  # mesma pasta deste arquivo

KIT = Path(__file__).resolve().parent.parent
CATALOGO_KIT = KIT / "assets" / "pacotes" / "catalogo.json"
TIPOS = ("trilha", "efeito", "transicao", "filtro", "texto")
TRILHA_VOLUME = 0.15  # trilha normalizada em -14 LUFS, embaixo da voz: ~16 dB abaixo
LIMITE_PADRAO_GB = 2.0
MAX_ARQUIVO = 2 * 1024 ** 3  # o teto de um arquivo de Release
ABERTOS = ("filtro", "transicao")  # chegam em zip e o motor de efeitos lê a pasta aberta
MAX_ABERTO = 256 * 1024 ** 2  # zip que abre em mais que isso não é efeito, é bomba
MAX_ENTRADAS = 200

_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,60}")
_ARQ = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}")  # também o nome dentro do zip: solto, sem pasta
_SHA = re.compile(r"[0-9a-f]{64}")
_LOCK = threading.RLock()  # o servidor atende pedidos em paralelo
_agora = time.time  # o relógio do "menos usado" (os testes trocam)


class PacoteErro(Exception):
    pass


class CatalogoInvalido(PacoteErro):
    pass


class PacoteCorrompido(PacoteErro):
    pass


class PacoteIndisponivel(PacoteErro):
    pass


# ---- catálogo ----
def _arquivo(v: object, onde: str) -> dict:
    if not isinstance(v, dict):
        raise CatalogoInvalido(f"{onde}: não é um objeto")
    nome, tam, sha = v.get("arquivo"), v.get("tamanho"), v.get("sha256")
    if not isinstance(nome, str) or not _ARQ.fullmatch(nome) or ".." in nome:
        raise CatalogoInvalido(f"{onde}: nome de arquivo inválido")
    if not isinstance(tam, int) or isinstance(tam, bool) or not 0 < tam <= MAX_ARQUIVO:
        raise CatalogoInvalido(f"{onde}: tamanho inválido")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise CatalogoInvalido(f"{onde}: sha256 inválido")
    return {"arquivo": nome, "tamanho": tam, "sha256": sha}


def validar(cat: object) -> dict:
    """Confere o catálogo inteiro: id, nomes de arquivo sem caminho, tamanho e sha256."""
    if not isinstance(cat, dict) or not isinstance(cat.get("pacotes"), list):
        raise CatalogoInvalido("catálogo sem lista de pacotes")
    base = cat.get("base")
    if not isinstance(base, str) or urlparse(base).scheme not in ("http", "https"):
        raise CatalogoInvalido("base precisa ser um endereço http(s)")
    repo = cat.get("repo") or ""
    if repo and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise CatalogoInvalido("repo inválido")
    pacotes, ids = [], set()
    for p in cat["pacotes"]:
        if not isinstance(p, dict):
            raise CatalogoInvalido("pacote não é um objeto")
        pid = p.get("id")
        if not isinstance(pid, str) or not _ID.fullmatch(pid) or pid in ids:
            raise CatalogoInvalido(f"id inválido ou repetido: {pid!r}")
        ids.add(pid)
        if p.get("tipo") not in TIPOS:
            raise CatalogoInvalido(f"{pid}: tipo desconhecido")
        rel = p.get("release")
        if not isinstance(rel, str) or not _ARQ.fullmatch(rel) or ".." in rel:
            raise CatalogoInvalido(f"{pid}: release inválida")
        dur = p.get("duracao", 0)
        if not isinstance(dur, (int, float)) or isinstance(dur, bool) or not 0 <= dur < 6 * 3600:
            raise CatalogoInvalido(f"{pid}: duração inválida")
        tags = p.get("tags") or []
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise CatalogoInvalido(f"{pid}: tags inválidas")
        item = {"id": pid, "tipo": p["tipo"], "nome": str(p.get("nome") or pid)[:80],
                "clima": str(p.get("clima") or "")[:40], "tags": [t[:40] for t in tags][:20],
                "duracao": float(dur), "release": rel, **_arquivo(p, pid)}
        if p.get("previa") is not None:
            item["previa"] = _arquivo(p["previa"], f"{pid} (prévia)")
        pacotes.append(item)
    return {"versao": 1, "gerado": str(cat.get("gerado") or ""), "repo": repo,
            "base": base.rstrip("/"), "pacotes": pacotes}


def ler_catalogo(p: Path) -> dict:
    try:
        return validar(json.loads(Path(p).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as e:
        raise CatalogoInvalido(f"catálogo ilegível: {Path(p).name} ({e.__class__.__name__})") from None


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# ---- transporte (trocados nos testes) ----
def _http_baixar(url: str, destino: Path, limite: int) -> None:
    """Grava em `destino` no máximo `limite` + 1 bytes: arquivo maior que o catálogo
    diz é cortado aqui e reprovado na conferência, sem encher o disco."""
    req = urllib.request.Request(url, headers={"User-Agent": "cutmind-pacotes"})
    with urllib.request.urlopen(req, timeout=60) as r, open(destino, "wb") as f:
        resta = limite + 1
        while resta > 0:
            bloco = r.read(min(1 << 16, resta))
            if not bloco:
                break
            f.write(bloco)
            resta -= len(bloco)


def _gh_baixar(repo: str, release: str, arquivo: str, destino: Path) -> None:
    """Release de repositório privado: o endereço público dá 404, o `gh` logado baixa."""
    if not shutil.which("gh"):
        raise PacoteIndisponivel("o repositório de pacotes é privado e o gh não está instalado")
    r = subprocess.run(["gh", "release", "download", release, "-R", repo, "-p", arquivo,
                        "-O", str(destino), "--clobber"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    if r.returncode != 0:
        raise PacoteIndisponivel(f"gh não baixou {arquivo}: {r.stderr.strip()[:200]}")


class Pacotes:
    def __init__(self, catalogo: dict, cache: Path, limite: int, base: str | None = None):
        self.cat = catalogo
        self.cache = Path(cache)
        self.limite = int(limite)
        self.base = (base or catalogo["base"]).rstrip("/")
        self._por_id = {p["id"]: p for p in catalogo["pacotes"]}

    @classmethod
    def do_ambiente(cls) -> "Pacotes":
        """O catálogo mais novo entre o do kit e o baixado por `atualizar`."""
        cache = Path(os.environ.get("CUTMIND_PACOTES_DIR") or Path.home() / ".cutmind" / "pacotes")
        kit = Path(os.environ.get("CUTMIND_PACOTES_CATALOGO") or CATALOGO_KIT)
        cats = [ler_catalogo(kit)]
        if (cache / "catalogo.json").is_file():
            try:
                cats.append(ler_catalogo(cache / "catalogo.json"))
            except CatalogoInvalido:
                pass  # cópia estragada: vale a do kit
        cat = max(cats, key=lambda c: c["gerado"])
        gb = float(os.environ.get("CUTMIND_PACOTES_LIMITE_GB") or LIMITE_PADRAO_GB)
        return cls(cat, cache, int(gb * 1024 ** 3), base=os.environ.get("CUTMIND_PACOTES_BASE") or None)

    # ---- consulta ----
    def pacote(self, pid: str) -> dict:
        p = self._por_id.get(pid)
        if not p:
            raise PacoteErro(f"pacote desconhecido: {pid}")
        return p

    def _local(self, p: dict) -> Path:
        return self.cache / p["tipo"] / p["arquivo"]

    def _local_previa(self, p: dict) -> Path:
        return self.cache / "previas" / p["previa"]["arquivo"]

    def listar(self, tipo: str | None = None, busca: str | None = None) -> list[dict]:
        est = self._estado()
        q = _sem_acento(busca or "").split()
        out = []
        for p in self.cat["pacotes"]:
            if tipo and p["tipo"] != tipo:
                continue
            texto = _sem_acento(" ".join([p["id"], p["nome"], p["clima"], *p["tags"]]))
            if q and not all(w in texto for w in q):
                continue
            out.append({k: p[k] for k in ("id", "tipo", "nome", "clima", "tags", "duracao")}
                       | {"previa": "previa" in p, "baixado": self._local(p).is_file(),
                          "favorito": p["id"] in est["favoritos"]})
        return out

    # ---- estado do cache: último uso e favoritos ----
    def _estado(self) -> dict:
        try:
            e = json.loads((self.cache / "estado.json").read_text(encoding="utf-8"))
            return {"uso": dict(e.get("uso") or {}), "favoritos": list(e.get("favoritos") or [])}
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            return {"uso": {}, "favoritos": []}

    def _gravar_estado(self, e: dict) -> None:
        self.cache.mkdir(parents=True, exist_ok=True)
        tmp = self.cache / f"estado.{os.getpid()}.{threading.get_ident()}.tmp"
        tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.cache / "estado.json")

    def _usou(self, chave: str) -> None:
        e = self._estado()
        e["uso"][chave] = _agora()
        self._gravar_estado(e)

    def favorito(self, pid: str, on: bool = True) -> None:
        self.pacote(pid)
        with _LOCK:
            e = self._estado()
            fav = [x for x in e["favoritos"] if x != pid] + ([pid] if on else [])
            e["favoritos"] = fav
            self._gravar_estado(e)

    def _guardados(self) -> list[tuple[str, str, Path]]:
        """(chave de uso, id, arquivo) de tudo que está no cache."""
        out = []
        for p in self.cat["pacotes"]:
            if self._local(p).is_file():
                out.append((p["id"], p["id"], self._local(p)))
            if "previa" in p and self._local_previa(p).is_file():
                out.append((f"previa:{p['id']}", p["id"], self._local_previa(p)))
        return out

    def cache_info(self) -> dict:
        g = self._guardados()
        return {"pasta": str(self.cache), "limite": self.limite, "arquivos": len(g),
                "bytes": sum(_ocupa(f) for _, _, f in g), "favoritos": self._estado()["favoritos"]}

    def _abrir_espaco(self, manter: Path) -> None:
        e = self._estado()
        g = self._guardados()
        total = sum(_ocupa(f) for _, _, f in g)
        for chave, pid, f in sorted(g, key=lambda x: e["uso"].get(x[0], 0)):
            if total <= self.limite:
                break
            if pid in e["favoritos"] or f == manter:
                continue
            total -= _ocupa(f)
            _apagar(f)
            e["uso"].pop(chave, None)
        self._gravar_estado(e)

    # ---- baixar ----
    def _github(self) -> bool:
        return urlparse(self.base).hostname == "github.com" and bool(self.cat["repo"])

    def _baixar(self, release: str, arq: dict, destino: Path) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_name(f".{destino.name}.{os.getpid()}.{threading.get_ident()}.part")
        url = f"{self.base}/{quote(release)}/{quote(arq['arquivo'])}"
        try:
            try:
                _http_baixar(url, tmp, arq["tamanho"])
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 404) and self._github():
                    _gh_baixar(self.cat["repo"], release, arq["arquivo"], tmp)
                else:
                    raise PacoteIndisponivel(f"{arq['arquivo']} não está no servidor de pacotes "
                                             f"(resposta {e.code})") from None
            except (urllib.error.URLError, OSError) as e:
                raise PacoteIndisponivel(f"{arq['arquivo']}: sem conexão com {urlparse(url).hostname} "
                                         f"({e.__class__.__name__})") from None
            if tmp.stat().st_size != arq["tamanho"] or _sha256(tmp) != arq["sha256"]:
                raise PacoteCorrompido(f"{arq['arquivo']} chegou diferente do catálogo; nada foi guardado")
            tmp.replace(destino)
        finally:
            tmp.unlink(missing_ok=True)

    def obter(self, pid: str, para: Path | None = None) -> Path:
        """O pacote no cache (baixa se faltar). Com `para`, devolve uma cópia nessa pasta."""
        p = self.pacote(pid)
        local = self._local(p)
        with _LOCK:
            if not local.is_file():
                self._baixar(p["release"], p, local)
            self._usou(pid)
            self._abrir_espaco(manter=local)
        return _copiar(local, Path(para), p["sha256"]) if para is not None else local

    def aberto(self, pid: str) -> Path:
        """Filtro e transição: a pasta com o zip do pacote aberto (baixa e abre na primeira vez)."""
        p = self.pacote(pid)
        if p["tipo"] not in ABERTOS:
            raise PacoteErro(f"{pid} é {p['tipo']}: não é pacote de efeito")
        with _LOCK:
            z = self.obter(pid)
            pasta = _aberta_de(z)
            marca = pasta / ".sha256"
            if not (marca.is_file() and marca.read_text(encoding="ascii") == p["sha256"]):
                _abrir_zip(z, pasta, p["sha256"])
        return pasta

    def previa(self, pid: str) -> Path:
        p = self.pacote(pid)
        if "previa" not in p:
            raise PacoteErro(f"{pid} não tem prévia")
        local = self._local_previa(p)
        with _LOCK:
            if not local.is_file():
                self._baixar(p["release"], p["previa"], local)
            self._usou(f"previa:{pid}")
            self._abrir_espaco(manter=local)
        return local

    def atualizar(self) -> bool:
        """Baixa o catálogo da Release `catalogo` para o cache. True se veio um mais novo."""
        destino = self.cache / "catalogo.json"
        tmp = self.cache / f"catalogo.{os.getpid()}.part"
        self.cache.mkdir(parents=True, exist_ok=True)
        try:
            try:
                _http_baixar(f"{self.base}/catalogo/catalogo.json", tmp, 20 * 1024 ** 2)
            except urllib.error.HTTPError as e:
                if e.code in (401, 403, 404) and self._github():
                    _gh_baixar(self.cat["repo"], "catalogo", "catalogo.json", tmp)
                else:
                    raise PacoteIndisponivel(f"catálogo: o servidor respondeu {e.code}") from None
            except (urllib.error.URLError, OSError) as e:
                raise PacoteIndisponivel(f"catálogo: sem conexão ({e.__class__.__name__})") from None
            novo = ler_catalogo(tmp)
            if novo["gerado"] <= self.cat["gerado"]:
                return False
            tmp.replace(destino)
            return True
        finally:
            tmp.unlink(missing_ok=True)


def _aberta_de(arquivo: Path) -> Path:
    return arquivo.with_name(f"{arquivo.stem}.aberto")


def _ocupa(arquivo: Path) -> int:
    """O arquivo e, se for zip de efeito, a pasta aberta dele: saem juntos do cache."""
    pasta = _aberta_de(arquivo)
    extra = sum(f.stat().st_size for f in pasta.iterdir() if f.is_file()) if pasta.is_dir() else 0
    return arquivo.stat().st_size + extra


def _apagar(arquivo: Path) -> None:
    arquivo.unlink(missing_ok=True)
    shutil.rmtree(_aberta_de(arquivo), ignore_errors=True)


def _abrir_zip(z: Path, pasta: Path, sha: str) -> None:
    """Abre numa pasta nova e troca de uma vez. Só arquivos soltos (sem pasta, sem '..',
    sem nome repetido), com teto de quantidade e de tamanho: um zip montado para escapar
    da pasta ou encher o disco para aqui, antes de gravar qualquer coisa."""
    tmp = pasta.with_name(f".{pasta.name}.{os.getpid()}.{threading.get_ident()}.part")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        with zipfile.ZipFile(z) as zf:
            infos = zf.infolist()
            nomes = [i.filename for i in infos]
            if len(infos) > MAX_ENTRADAS or sum(i.file_size for i in infos) > MAX_ABERTO:
                raise PacoteCorrompido(f"{z.name}: grande demais para abrir")
            for i in infos:
                if i.is_dir() or not _ARQ.fullmatch(i.filename) or ".." in i.filename:
                    raise PacoteCorrompido(f"{z.name}: caminho não permitido dentro do pacote "
                                           f"({i.filename[:60]!r})")
            if len({n.lower() for n in nomes}) != len(nomes):
                raise PacoteCorrompido(f"{z.name}: nome repetido dentro do pacote")
            if "efeito.json" not in nomes:
                raise PacoteCorrompido(f"{z.name}: sem efeito.json")
            tmp.mkdir(parents=True)
            for i in infos:
                with zf.open(i) as src:
                    dados = src.read(i.file_size + 1)
                if len(dados) != i.file_size:
                    raise PacoteCorrompido(f"{z.name}: {i.filename} não tem o tamanho que diz")
                (tmp / i.filename).write_bytes(dados)
        (tmp / ".sha256").write_text(sha, encoding="ascii")
        shutil.rmtree(pasta, ignore_errors=True)
        tmp.replace(pasta)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError) as e:
        raise PacoteCorrompido(f"{z.name} não abre como zip ({e.__class__.__name__})") from None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _copiar(src: Path, pasta: Path, sha: str) -> Path:
    """Copia para a pasta do projeto sem sobrescrever arquivo de outra pessoa: o mesmo
    pacote de novo reaproveita a cópia, um nome ocupado por outro conteúdo ganha -2, -3…"""
    pasta.mkdir(parents=True, exist_ok=True)
    stem, ext = src.stem, src.suffix
    cand, n = pasta / src.name, 2
    while cand.exists():
        if cand.is_file() and cand.stat().st_size == src.stat().st_size and _sha256(cand) == sha:
            return cand
        cand, n = pasta / f"{stem}-{n}{ext}", n + 1
    tmp = pasta / f".{cand.name}.{os.getpid()}.part"
    shutil.copyfile(src, tmp)
    tmp.replace(cand)
    return cand


def por_na_linha(pac: Pacotes, edit: Path, pid: str, duracao_video: float,
                 inicio: float = 0.0, volume: float = TRILHA_VOLUME) -> dict:
    """A trilha vira uma faixa de áudio nova no camadas.json do projeto, de `inicio` até o
    fim da trilha ou do vídeo, o que vier antes. É o mesmo arquivo que o editor grava."""
    p = pac.pacote(pid)
    if p["tipo"] != "trilha":
        raise PacoteErro(f"{pid} é {p['tipo']}, não trilha")
    edit = Path(edit)
    destino = pac.obter(pid, para=edit / cam.MIDIA_DIR)
    c = cam.load(edit / "camadas.json")
    usados = {f["id"] for f in c["faixas"]}
    n = 1
    while f"a{n}" in usados:
        n += 1
    fid = f"a{n}"
    dur = max(0.05, min(p["duracao"] or duracao_video, duracao_video - inicio))
    faixa = {"id": fid, "tipo": "audio", "mudo": False, "travado": False,
             "itens": [{"id": f"{fid}-1", "arquivo": f"{cam.MIDIA_DIR}/{destino.name}",
                        "inicio": round(inicio, 3), "duracao": round(dur, 3), "corte": 0.0,
                        "volume": volume, "melhorar": False, "trilha": pid}]}
    c["faixas"].append(faixa)
    cam.save(edit / "camadas.json", c)
    return cam.load(edit / "camadas.json")["faixas"][-1]


def _duracao_video(edit: Path) -> float:
    try:
        rel = json.loads((edit / "state.json").read_text(encoding="utf-8")).get("video") or "cut.mp4"
    except (OSError, json.JSONDecodeError):
        rel = "cut.mp4"
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(edit / rel)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _fmt(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Pacotes do kit: listar, baixar, favoritos e cache.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("listar")
    a.add_argument("--tipo", choices=TIPOS)
    a.add_argument("--busca")
    a.add_argument("--json", action="store_true")
    a = sub.add_parser("obter")
    a.add_argument("id")
    a.add_argument("--para", type=Path)
    a = sub.add_parser("abrir")
    a.add_argument("id")
    a = sub.add_parser("camada")
    a.add_argument("edit", type=Path)
    a.add_argument("id")
    a.add_argument("--inicio", type=float, default=0.0)
    a.add_argument("--volume", type=float, default=TRILHA_VOLUME)
    a = sub.add_parser("favorito")
    a.add_argument("id")
    a.add_argument("--tirar", action="store_true")
    sub.add_parser("cache")
    sub.add_parser("atualizar")
    args = ap.parse_args()
    try:
        pac = Pacotes.do_ambiente()
        if args.cmd == "listar":
            itens = pac.listar(args.tipo, args.busca)
            if args.json:
                print(json.dumps(itens, ensure_ascii=False, indent=1))
            for p in [] if args.json else itens:
                marca = ("★" if p["favorito"] else " ") + ("↓" if p["baixado"] else " ")
                print(f"{marca} {p['id']:<22} {p['tipo']:<9} {_fmt(p['duracao']):>5}  "
                      f"{p['clima']:<10} {p['nome']}")
        elif args.cmd == "obter":
            print(pac.obter(args.id, para=args.para))
        elif args.cmd == "abrir":
            print(pac.aberto(args.id))
        elif args.cmd == "camada":
            f = por_na_linha(pac, args.edit, args.id, _duracao_video(args.edit), args.inicio, args.volume)
            it = f["itens"][0]
            print(f"{f['id']}: {it['arquivo']} de {it['inicio']:.1f} s, {it['duracao']:.1f} s, "
                  f"volume {it['volume']:.0%}")
        elif args.cmd == "favorito":
            pac.favorito(args.id, not args.tirar)
        elif args.cmd == "cache":
            i = pac.cache_info()
            print(f"{i['pasta']}: {i['arquivos']} arquivo(s), {i['bytes'] / 1e6:.1f} MB "
                  f"de {i['limite'] / 1024 ** 3:.1f} GB; favoritos: {', '.join(i['favoritos']) or 'nenhum'}")
        elif args.cmd == "atualizar":
            print("catálogo novo guardado" if pac.atualizar() else "o catálogo já é o mais novo")
    except PacoteErro as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
