"""A versão publicada (versao.json), o manifesto dos arquivos e o que uma versão nova muda."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import versao as vs  # noqa: E402


def _raiz(tmp_path: Path, arquivos: dict[str, str]) -> Path:
    for nome, texto in arquivos.items():
        p = tmp_path / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8"))
    return tmp_path


def test_numero_compara_por_partes():
    assert vs.numero("0.10.0") > vs.numero("0.9.3")
    assert vs.numero("1.0.0") == (1, 0, 0)
    assert vs.numero("lixo") == (0,)


def test_manifesto_pega_o_payload_e_pula_cache(tmp_path):
    r = _raiz(tmp_path, {"SKILL.md": "a", "helpers/x.py": "b", "helpers/__pycache__/x.pyc": "c",
                         "tests/t.py": "fora do payload", "versao.json": "{}"})
    m = vs.manifesto(r)
    assert set(m) == {"SKILL.md", "helpers/x.py"}
    assert len(m["SKILL.md"]) == 64


def test_grupo_de_cada_arquivo():
    assert vs.grupo("uv.lock") == "dependencias"
    assert vs.grupo("helpers/render.py") == "servidor"
    assert vs.grupo("assets/i18n/scripts-en.json") == "servidor"
    assert vs.grupo("assets/preview/celular.js") == "editor"
    assert vs.grupo("assets/shortform/package.json") == "remotion"
    assert vs.grupo("assets/shortform/src/Main.tsx") == "modelos"
    assert vs.grupo("references/shortform.md") == "agente"
    assert vs.grupo("README.md") == "outros"


def test_o_que_muda_ve_novo_mudado_e_apagado():
    local = {"a/SKILL.md": "1", "helpers/x.py": "1", "assets/preview/c.js": "1"}
    remoto = {"a/SKILL.md": "1", "helpers/x.py": "2", "helpers/novo.py": "1"}
    assert vs.o_que_muda(local, remoto) == {"servidor", "editor"}


def test_resumo_decide_reiniciar_e_agente():
    loc = {"versao": "0.2.0", "arquivos": {"helpers/x.py": "1", "SKILL.md": "1"}}
    so_tela = {"versao": "0.2.1", "notas": {"pt": ["tela"], "en": ["screen"]},
               "arquivos": {"helpers/x.py": "1", "SKILL.md": "1", "assets/preview/c.js": "1"}}
    r = vs.resumo(loc, so_tela)
    assert r["nova"] and not r["reiniciar"] and not r["agente"] and r["versao"] == "0.2.1"
    servidor = {**so_tela, "versao": "0.3.0", "arquivos": {"helpers/x.py": "2", "SKILL.md": "2"}}
    r = vs.resumo(loc, servidor)
    assert r["reiniciar"] and r["agente"] and r["muda"] == ["agente", "servidor"]
    assert not vs.resumo(loc, {**servidor, "versao": "0.2.0"})["nova"]   # mesma versão: nada


def test_ler_tolera_arquivo_ausente_ou_quebrado(tmp_path):
    assert vs.ler(tmp_path) is None
    (tmp_path / "versao.json").write_bytes(b"{quebrado")
    assert vs.ler(tmp_path) is None


def test_conferir_recusa_arquivo_mudado_sem_subir_a_versao(tmp_path):
    import subprocess as sp
    r = _raiz(tmp_path, {"SKILL.md": "a", "helpers/x.py": "1"})
    for c in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        sp.run(["git", "-C", str(r), *c], check=True)
    sp.run(["git", "-C", str(r), "add", "-A"], check=True)
    vs._escrever(r, {"versao": "0.2.0", "notas": {}, "arquivos": vs.manifesto(r)})
    sp.run(["git", "-C", str(r), "add", "-A"], check=True)
    sp.run(["git", "-C", str(r), "commit", "-qm", "v"], check=True)
    assert vs.conferir(r, "HEAD") == []
    (r / "helpers" / "x.py").write_bytes(b"2")
    assert any("manifesto" in e for e in vs.conferir(r, "HEAD"))
    vs._escrever(r, {"versao": "0.2.0", "notas": {}, "arquivos": vs.manifesto(r)})
    assert any("não subiu" in e for e in vs.conferir(r, "HEAD"))
    vs._escrever(r, {"versao": "0.2.1", "notas": {}, "arquivos": vs.manifesto(r)})
    assert vs.conferir(r, "HEAD") == []


def test_versao_do_repositorio_tem_a_forma_certa():
    # o manifesto em dia é cobrado só ao subir para a main (pre-push): cobrar aqui faria todo commit de
    # trabalho regravar o versao.json
    raiz = Path(__file__).resolve().parents[1]
    d = vs.ler(raiz)
    assert d and vs.numero(d["versao"]) >= (0, 2, 0) and d["notas"]["pt"] and d["notas"]["en"]
    assert len(d["notas"]["pt"]) == len(d["notas"]["en"])
    assert isinstance(d["arquivos"], dict) and "SKILL.md" in d["arquivos"]


def test_o_instalador_leva_o_versao_json():
    import ast
    raiz = Path(__file__).resolve().parents[1]
    arvore = ast.parse((raiz / "cutmind_install.py").read_text(encoding="utf-8"))
    payload = next(ast.literal_eval(n.value) for n in arvore.body if isinstance(n, ast.Assign)
                   and any(getattr(t, "id", "") == "SKILL_PAYLOAD" for t in n.targets))
    assert set(payload) == set(vs.PAYLOAD) | {vs.ARQ}
