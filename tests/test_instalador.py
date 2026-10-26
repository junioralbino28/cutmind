"""O instalador copia o kit para o Claude Code e, se existir, para o Codex,
a partir de uma pasta local, sem levar tests/."""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
INSTALADOR = RAIZ / "cutmind_install.py"


def rodar(home: Path):
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    env.pop("CODEX_HOME", None)
    return subprocess.run(
        [sys.executable, str(INSTALADOR), "--source", str(RAIZ),
         "--skip-deps", "--no-remotion"],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)


def test_instala_no_claude_e_no_codex(tmp_path):
    (tmp_path / ".codex").mkdir()
    r = rodar(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    for agente in (".claude", ".codex"):
        destino = tmp_path / agente / "skills" / "cutmind"
        assert (destino / "SKILL.md").is_file(), agente
        assert (destino / "helpers" / "render.py").is_file(), agente
        assert not (destino / "tests").exists(), agente
    # --no-remotion: o resumo não pode anunciar uma skill que não foi instalada
    assert "remotion-best-practices" not in r.stdout


def test_sem_codex_instala_so_no_claude(tmp_path):
    r = rodar(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / ".claude" / "skills" / "cutmind" / "SKILL.md").is_file()
    assert not (tmp_path / ".codex").exists()


# ---- o idioma: o instalador fala no idioma de quem instala ----
def rodar_no_idioma(home: Path, idioma: str):
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1")
    env.pop("CODEX_HOME", None)
    return subprocess.run(
        [sys.executable, str(INSTALADOR), "--source", str(RAIZ), "--skip-deps", "--no-remotion",
         "--idioma", idioma],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)


def test_em_ingles_a_saida_inteira_sai_em_ingles(tmp_path):
    en = rodar_no_idioma(tmp_path / "en", "en")
    assert en.returncode == 0, en.stdout + en.stderr
    assert "check:" in en.stdout and "installed in:" in en.stdout and "verificação" not in en.stdout
    import re
    pt = [linha for linha in en.stdout.splitlines()
          if re.search(r"[ãõçáéíóúâê]|\b(não|para|instalando|rode|pasta)\b", linha, re.I)
          and "/" not in linha and chr(92) not in linha]  # caminho de pasta pode ter acento
    assert not pt, pt
    br = rodar_no_idioma(tmp_path / "pt", "pt")
    assert "verificação:" in br.stdout and "instalado em:" in br.stdout


def test_toda_mensagem_do_instalador_tem_ingles():
    """Lê as chamadas de log() do instalador (literal ou f-string) e exige a frase no EN dele."""
    import ast
    import importlib.util
    import re
    spec = importlib.util.spec_from_file_location("instalador_idioma", INSTALADOR)
    inst = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inst)

    def texto(no):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            return no.value
        if isinstance(no, ast.JoinedStr):
            out, n = [], 0
            for v in no.values:
                if isinstance(v, ast.Constant):
                    out.append(v.value)
                else:
                    e = v.value
                    nome = e.id if isinstance(e, ast.Name) else e.attr if isinstance(e, ast.Attribute) else f"p{n}"
                    n += 1
                    out.append("{" + nome + "}")
            return "".join(out)
        return None

    logs = [texto(no.args[0]) for no in ast.walk(ast.parse(INSTALADOR.read_text(encoding="utf-8")))
            if isinstance(no, ast.Call) and getattr(no.func, "id", "") == "log" and no.args]
    logs = [s for s in logs if s]
    assert "verificação:" in logs and "  ! falhou para {name}: {e}" in logs  # o leitor acha os log()
    faltam = [s for s in logs if re.search(r"[ãõçáéíóúâêô]|\b(não|para|em|de|rode|falta)\b", s, re.I)
              and s not in inst.EN and not s.startswith("      uv run https")]
    assert not faltam, faltam
