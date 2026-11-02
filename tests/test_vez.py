"""Um render pesado por vez, com prioridade baixa e pasta temporária só dele (vez.py).

Edição real de 01/11: duas conversas renderizando ao mesmo tempo travaram o computador; cada render copiava
3 GB para o temporário e as cópias antigas ficavam; a marca de trabalhando do agente vencia no meio do render.
"""
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(AQUI))
import vez  # noqa: E402


@pytest.fixture
def casa(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTMIND_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(vez, "PASSO", 0.1)
    return tmp_path


def _segurar(casa: Path, segundos: float) -> subprocess.Popen:
    """Outro processo com a vez por `segundos` (outra conversa renderizando)."""
    cod = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(AQUI)!r})
        import vez
        with vez.vez(None, "o render da outra conversa"):
            print("peguei", flush=True)
            time.sleep({segundos})
    """)
    p = subprocess.Popen([sys.executable, "-c", cod], stdout=subprocess.PIPE, text=True,
                         env={**os.environ, "CUTMIND_HOME": str(casa / "home")})
    assert p.stdout.readline().strip() == "peguei"
    return p


def test_o_segundo_render_espera_o_primeiro_acabar(casa):
    outro = _segurar(casa, 1.5)
    esperou = []
    t0 = time.time()
    with vez.vez(None, "o meu", ao_esperar=esperou.append):
        dentro = time.time() - t0
        assert vez.quem()["pid"] == os.getpid()
    outro.wait()
    assert dentro >= 1.0 and esperou and esperou[0]["rotulo"] == "o render da outra conversa"
    assert vez.quem() is None  # soltou


def test_a_vez_de_um_render_que_caiu_nao_trava_ninguem(casa):
    arq = vez._arquivo()
    arq.parent.mkdir(parents=True)
    arq.write_text(json.dumps({"pid": 999999, "rotulo": "caiu", "desde": time.time()}), encoding="utf-8")
    t0 = time.time()
    with vez.vez(None, "o meu"):
        pass
    assert time.time() - t0 < 1.0


def test_render_dentro_de_render_nao_espera_por_si_mesmo(casa):
    with vez.vez(None, "fora") as v:
        with vez.vez(None, "dentro"):  # o mesmo processo
            pass
        # um filho do processo que tem a vez (o render.py que o corte_alta chama, por exemplo)
        cod = f"import sys; sys.path.insert(0, {str(AQUI)!r}); import vez\nwith vez.vez(None, 'filho'): print('ok')"
        r = subprocess.run([sys.executable, "-c", cod], capture_output=True, text=True, timeout=20, env=v.env())
        assert r.stdout.strip() == "ok"
        assert vez.quem()["pid"] == os.getpid()


def test_pasta_temporaria_propria_apagada_no_fim(casa):
    with vez.vez(None, "o meu", fila=False) as v:
        tmp = Path(v.env()["TEMP"])
        assert tmp.is_dir() and v.env()["TMPDIR"] == str(tmp)
        (tmp / "remotion-webpack-bundle-x").mkdir()  # o que o Remotion deixaria
        (tmp / "remotion-webpack-bundle-x" / "f.mov").write_bytes(b"x" * 1000)
    assert not tmp.exists()


@pytest.mark.skipif(os.name != "nt", reason="classe de prioridade do Windows")
def test_o_processo_do_render_roda_com_prioridade_baixa(casa):
    import ctypes
    with vez.vez(None, "o meu", fila=False) as v:
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1)"], **v.criar)
        try:
            classe = ctypes.windll.kernel32.GetPriorityClass(int(p._handle))
        finally:
            p.wait()
    assert classe == 0x4000  # BELOW_NORMAL_PRIORITY_CLASS: o mouse e os outros programas passam na frente


def test_a_marca_do_agente_nao_vence_durante_o_render(casa, monkeypatch):
    edit = casa / "edit"
    edit.mkdir()
    (edit / "state.json").write_text(json.dumps({"agente": {"trabalhando": True, "desde": 100.0}}), encoding="utf-8")
    monkeypatch.setattr(vez, "RENOVA", 0.2)
    with vez.vez(edit, "o meu", fila=False):
        time.sleep(0.7)
    assert json.loads((edit / "state.json").read_text(encoding="utf-8"))["agente"]["desde"] > time.time() - 5
    (edit / "state.json").write_text(json.dumps({"phase": 2}), encoding="utf-8")  # sem marca: não cria uma
    with vez.vez(edit, "o meu", fila=False):
        time.sleep(0.5)
    assert "agente" not in json.loads((edit / "state.json").read_text(encoding="utf-8"))


def test_os_renders_do_kit_passam_pela_vez():
    for arq, trecho in (("gerar.py", "vez.vez(rem.parent"), ("montagem.py", "vez.vez(edit, \"o render da montagem\")"),
                        ("render_janelas.py", "vez.vez(remotion.parent"), ("efeitos_render.py", "vez.vez(Path(projeto).parent"),
                        ("corte_alta.py", "vez.vez(edit, \"o corte em 4K\")")):
        s = (AQUI / arq).read_text(encoding="utf-8")
        assert trecho in s and ".criar)" in s and ".env(" in s, arq


def test_a_pasta_de_um_render_que_acabou_e_varrida_e_a_de_um_vivo_fica(casa, monkeypatch):
    import tempfile
    base = casa / "tmp"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    morto, vivo_ = base / "cutmind-999999-abc", base / f"cutmind-{os.getppid()}-def"
    outro = base / "cutmind-acorn"  # de outra coisa: o nome não tem pid
    for p in (morto, vivo_, outro):
        (p / "perfil").mkdir(parents=True)
    with vez.vez(None, "o meu", fila=False):
        pass
    assert not morto.exists() and vivo_.exists() and outro.exists()
