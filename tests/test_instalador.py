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
