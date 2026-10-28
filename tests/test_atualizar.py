"""A atualização do CutMind: procurar, baixar e conferir, aplicar com volta automática."""
import http.server
import io
import json
import sys
import tarfile
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import atualizar as at  # noqa: E402
import versao as vs  # noqa: E402


@pytest.fixture
def github(tmp_path, monkeypatch):
    """Serve <tmp>/pub/versao.json e <tmp>/pub/pacote.tar.gz, como o raw e o codeload; conta os pedidos."""
    pub = tmp_path / "pub"
    pub.mkdir()
    pedidos = []

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(pub), **k)

        def log_message(self, *a):
            pedidos.append(self.path)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("CUTMIND_ATUALIZACAO_URL", f"{base}/versao.json")
    monkeypatch.setenv("CUTMIND_ATUALIZACAO_PACOTE", f"{base}/pacote.tar.gz")
    monkeypatch.delenv("CUTMIND_SEM_ATUALIZACAO", raising=False)
    yield pub, pedidos
    srv.shutdown()
    srv.server_close()


def _arquivos(raiz: Path, arquivos: dict[str, str]) -> None:
    for nome, texto in arquivos.items():
        p = raiz / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8"))


def _skill(tmp_path, versao="0.2.0", arquivos=None) -> Path:
    """Uma instalação de mentira: os arquivos, um .venv e o versao.json com o manifesto deles."""
    s = tmp_path / "skill"
    _arquivos(s, arquivos or {"SKILL.md": "velho", "helpers/x.py": "1"})
    _arquivos(s, {".venv/pyvenv.cfg": "home = x"})
    vs._escrever(s, {"versao": versao, "notas": {}, "arquivos": vs.manifesto(s)})
    return s


def _publicar(pub: Path, versao: str, arquivos: dict[str, str], estragar: str | None = None) -> dict:
    """Publica uma versão no GitHub de mentira: o pacote como o codeload entrega (cutmind-main/...) e o
    versao.json com o manifesto. `estragar` muda um arquivo do pacote DEPOIS do manifesto."""
    raiz = pub / "_fonte" / f"v{versao}" / "cutmind-main"
    _arquivos(raiz, arquivos)
    d = {"versao": versao, "data": "2026-10-27", "notas": {"pt": [f"nota {versao}"], "en": [f"note {versao}"]},
         "arquivos": vs.manifesto(raiz)}
    vs._escrever(raiz, d)
    (pub / "versao.json").write_bytes(json.dumps(d).encode("utf-8"))
    if estragar:
        (raiz / estragar).write_bytes(b"trocado no caminho")
    with tarfile.open(pub / "pacote.tar.gz", "w:gz") as tar:
        tar.add(raiz, arcname="cutmind-main")
    return d


# ---- procurar

def test_acha_versao_nova_e_guarda_por_6_horas(tmp_path, github):
    pub, pedidos = github
    _publicar(pub, "0.3.0", {"SKILL.md": "velho", "helpers/x.py": "2"})
    s, casa = _skill(tmp_path), tmp_path / "casa"
    r = at.procurar(s, casa, agora=1000.0)
    assert r["nova"] and r["reiniciar"] and not r["agente"] and r["versao"] == "0.3.0"
    at.procurar(s, casa, agora=1000.0 + 3600)
    assert len(pedidos) == 1                       # dentro das 6 h: do cache
    at.procurar(s, casa, agora=1000.0 + 7 * 3600)
    assert len(pedidos) == 2


def test_sem_internet_ou_404_nao_acusa_nada(tmp_path, github, monkeypatch):
    s, casa = _skill(tmp_path), tmp_path / "casa"
    assert at.procurar(s, casa)["nova"] is False   # 404 (o repositório ainda privado)
    monkeypatch.setenv("CUTMIND_ATUALIZACAO_URL", "http://127.0.0.1:9/versao.json")
    assert at.procurar(s, casa, forcar=True)["nova"] is False


def test_desligado_e_copia_de_desenvolvimento_nao_procuram(tmp_path, github, monkeypatch):
    pub, pedidos = github
    s, casa = _skill(tmp_path), tmp_path / "casa"
    monkeypatch.setenv("CUTMIND_SEM_ATUALIZACAO", "1")
    assert at.procurar(s, casa)["motivo"] == "desligado"
    monkeypatch.delenv("CUTMIND_SEM_ATUALIZACAO")
    at.ligar(casa, False)                          # o interruptor do painel "?"
    assert at.procurar(s, casa)["motivo"] == "desligado" and at.ligado(casa) is False
    at.ligar(casa, True)
    (s / ".git").mkdir()
    assert at.procurar(s, casa)["motivo"] == "desenvolvimento"
    assert pedidos == []


# ---- baixar e conferir

def test_baixar_confere_o_manifesto(tmp_path, github):
    pub, _ = github
    d = _publicar(pub, "0.3.0", {"SKILL.md": "novo", "helpers/x.py": "2"})
    marcas = []
    raiz, usado = at.baixar(tmp_path / "baixa", d, lambda feito, total: marcas.append((feito, total)))
    assert usado["versao"] == "0.3.0" and vs.manifesto(raiz) == d["arquivos"]
    assert (raiz / "helpers" / "x.py").read_bytes() == b"2"
    assert marcas and marcas[-1][0] == marcas[-1][1] > 0


def test_baixar_recusa_pacote_diferente_do_publicado(tmp_path, github):
    pub, _ = github
    d = _publicar(pub, "0.3.0", {"SKILL.md": "novo", "helpers/x.py": "2"}, estragar="helpers/x.py")
    with pytest.raises(at.ErroAtualizar, match="não bate"):
        at.baixar(tmp_path / "baixa", d)
    assert not (tmp_path / "baixa").exists()        # nada do pacote recusado fica no disco


def test_baixar_recusa_caminho_para_fora_antes_de_extrair(tmp_path, github):
    pub, _ = github
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for nome in ("cutmind-main/SKILL.md", "cutmind-main/../../fora.txt"):
            info = tarfile.TarInfo(nome)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
    (pub / "pacote.tar.gz").write_bytes(buf.getvalue())
    with pytest.raises(at.ErroAtualizar, match="caminho"):
        at.baixar(tmp_path / "baixa", {"versao": "0.3.0", "arquivos": {}})
    assert not (tmp_path / "fora.txt").exists()


# ---- aplicar

COPIA = ("import shutil, sys; from pathlib import Path\n"
         "src, dst = Path(sys.argv[1]), Path(sys.argv[2])\n"
         "for p in src.iterdir():\n"
         "    (shutil.copytree(p, dst / p.name, dirs_exist_ok=True) if p.is_dir() else shutil.copy2(p, dst / p.name))\n")
QUEBRA = ("import sys; from pathlib import Path\n"
          "dst = Path(sys.argv[2]); (dst / 'helpers' / 'x.py').unlink(); (dst / 'SKILL.md').write_bytes(b'pela metade')\n"
          "print('instalando...'); print('erro de teste: uv sync caiu'); sys.exit(1)\n")


@pytest.fixture
def instalador(monkeypatch):
    estado = {"script": COPIA, "sincronizou": []}
    monkeypatch.setattr(at, "comando_instalar", lambda pasta, skill: [sys.executable, "-c", estado["script"],
                                                                        str(pasta), str(skill)])
    monkeypatch.setattr(at, "sincronizar", lambda skill: estado["sincronizou"].append(skill))
    return estado


def test_aplicar_instala_e_guarda_a_versao_de_antes(tmp_path, github, instalador):
    pub, _ = github
    s, casa = _skill(tmp_path), tmp_path / "casa"
    _publicar(pub, "0.3.0", {"SKILL.md": "novo", "helpers/x.py": "2"})
    etapas = []
    r = at.aplicar(s, casa, None, lambda etapa, texto, fracao, **x: etapas.append((etapa, x)))
    assert vs.ler(s)["versao"] == "0.3.0" and (s / "helpers" / "x.py").read_bytes() == b"2"
    assert (s / ".venv" / "pyvenv.cfg").exists()
    anterior = casa / "atualizacao" / "anterior"
    assert (anterior / "helpers" / "x.py").read_bytes() == b"1" and not (anterior / ".venv").exists()
    vistas = [e for e, _ in etapas]
    assert vistas.index("baixando") < vistas.index("guardando") < vistas.index("instalando") < vistas.index("pronto")
    fim = etapas[-1][1]
    assert fim["versao"] == "0.3.0" and fim["agente"] is True and fim["reiniciou"] is False
    assert r["versao"] == "0.3.0" and not (casa / "atualizacao" / "baixado").exists()


def test_aplicar_que_falha_volta_a_versao_de_antes(tmp_path, github, instalador):
    pub, _ = github
    s, casa = _skill(tmp_path), tmp_path / "casa"
    _publicar(pub, "0.3.0", {"SKILL.md": "novo", "helpers/x.py": "2"})
    instalador["script"] = QUEBRA
    etapas = []
    with pytest.raises(at.ErroAtualizar, match="uv sync caiu"):
        at.aplicar(s, casa, None, lambda etapa, texto, fracao, **x: etapas.append((etapa, x)))
    assert (s / "helpers" / "x.py").read_bytes() == b"1" and (s / "SKILL.md").read_bytes() == b"velho"
    assert vs.ler(s)["versao"] == "0.2.0" and instalador["sincronizou"] == [s]
    assert etapas[-1][0] == "falhou" and "uv sync caiu" in etapas[-1][1]["erro"]


def test_aplicar_sem_versao_nova_nao_mexe(tmp_path, github, instalador):
    pub, _ = github
    s, casa = _skill(tmp_path), tmp_path / "casa"
    _publicar(pub, "0.2.0", {"SKILL.md": "velho", "helpers/x.py": "1"})
    etapas = []
    at.aplicar(s, casa, None, lambda etapa, texto, fracao, **x: etapas.append((etapa, x)))
    assert etapas[-1][0] == "pronto" and etapas[-1][1].get("nada") is True
    assert not (casa / "atualizacao" / "anterior").exists()


def test_aplicar_confere_que_a_instalacao_chegou_nesta_pasta(tmp_path, github, instalador):
    pub, _ = github
    s, casa = _skill(tmp_path), tmp_path / "casa"
    _publicar(pub, "0.3.0", {"SKILL.md": "novo", "helpers/x.py": "2"})
    instalador["script"] = "print('instalado em outra pasta')"
    with pytest.raises(at.ErroAtualizar, match="não chegou"):
        at.aplicar(s, casa, None, lambda *a, **k: None)
    assert vs.ler(s)["versao"] == "0.2.0"


def test_processo_que_ja_saiu_nao_esta_vivo():
    """No Windows em português o tasklist responde "não existe" com acento no código de página do console;
    lido como UTF-8, derrubava o atualizador com o editor já fechado (visto na prova no navegador)."""
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert at._vivo(p.pid) is False
    import os
    assert at._vivo(os.getpid()) is True


def test_erro_inesperado_com_o_editor_fechado_religa_e_conta(tmp_path, github, instalador, monkeypatch):
    """Qualquer erro depois que o editor se desligou: ele liga de novo na versão de antes."""
    pub, _ = github
    s, casa = _skill(tmp_path), tmp_path / "casa"
    _publicar(pub, "0.3.0", {"SKILL.md": "novo", "helpers/x.py": "2"})      # helpers/: pede reinício
    religados = []
    monkeypatch.setattr(at, "esperar_sair", lambda pid: (_ for _ in ()).throw(TypeError("tasklist quebrou")))
    monkeypatch.setattr(at, "_vivo", lambda pid: False)
    monkeypatch.setattr(at, "religar", lambda servidor: religados.append(servidor) or 1)
    etapas = []
    servidor = {"pid": 4242, "argv": ["x.py", "--port", "1"], "python": sys.executable}
    with pytest.raises(at.ErroAtualizar, match="parou no meio"):
        at.aplicar(s, casa, servidor, lambda etapa, texto, fracao, **x: etapas.append((etapa, x)))
    assert religados == [servidor] and vs.ler(s)["versao"] == "0.2.0"
    assert etapas[-1][0] == "falhou" and "tasklist quebrou" in etapas[-1][1]["erro"]


def test_erro_inesperado_no_meio_da_instalacao_volta_os_arquivos(tmp_path, github, instalador, monkeypatch):
    pub, _ = github
    s, casa = _skill(tmp_path), tmp_path / "casa"
    _publicar(pub, "0.3.0", {"SKILL.md": "novo", "helpers/x.py": "2"})
    monkeypatch.setattr(at, "comando_instalar", lambda pasta, skill: ["programa-que-nao-existe-cutmind"])
    with pytest.raises(at.ErroAtualizar, match="parou no meio"):
        at.aplicar(s, casa, None, lambda *a, **k: None)
    assert instalador["sincronizou"] == [s] and vs.ler(s)["versao"] == "0.2.0"


# ---- religar (integração: um servidor do editor de verdade)

def _matar_arvore(pid: int) -> None:
    import os
    import signal
    import subprocess
    if os.name == "nt":  # o python do .venv no Windows abre um filho: a árvore inteira
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        os.killpg(os.getpgid(pid), signal.SIGTERM)


def test_religar_liga_o_editor_e_so_conta_quando_ele_responde(tmp_path, monkeypatch):
    import socket
    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "state.json").write_bytes(json.dumps({"project": "t", "phase": 1, "video": "cut.mp4"}).encode("utf-8"))
    monkeypatch.setenv("CUTMIND_HOME", str(tmp_path / "casa"))     # nunca a lista de projetos da pessoa
    monkeypatch.setenv("CUTMIND_SEM_ATUALIZACAO", "1")              # o servidor religado não sai na rede
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    script = Path(at.__file__).resolve().parent / "preview_server.py"
    servidor = {"argv": [str(script), "--root", str(edit), "--port", str(porta)], "python": sys.executable,
                "script": str(script)}
    pid = at.religar(servidor, prazo=60)
    try:
        assert at.respondendo(porta)
        assert "CutMind preview" in (edit / "preview-server.log").read_text(encoding="utf-8", errors="replace")
    finally:
        _matar_arvore(pid)


def test_religar_que_nao_responde_conta_o_erro(tmp_path):
    edit = tmp_path / "edit"
    edit.mkdir()
    servidor = {"argv": ["x", "--root", str(edit), "--port", "9"], "python": sys.executable,
                "script": str(tmp_path / "nao_existe.py")}
    with pytest.raises(at.ErroAtualizar, match="não voltou"):
        at.religar(servidor, prazo=5)
