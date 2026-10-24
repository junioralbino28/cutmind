"""A troca do código de template de um projeto montado com um kit anterior (atualizar_template.py),
e a trava do cenas_edit_data.py que manda rodá-la: sem ela, os efeitos saíam fora do render de um
projeto antigo, sem erro nenhum."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))
import atualizar_template as at  # noqa: E402
import cenas_edit_data as ced  # noqa: E402


def _escreve(base: Path, arquivos: dict[str, str]) -> None:
    for rel, texto in arquivos.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(texto.encode("utf-8"))


@pytest.fixture
def kit(tmp_path):
    assets = tmp_path / "kit" / "assets"
    _escreve(assets / "shortform", {
        "src/Main.tsx": "import {Cenas} from './cenas';\n<Cenas />\n", "src/CustomGraphics.tsx": "// do kit\n",
        "src/cenas/index.tsx": "export const TIPOS = {fundo: 1};\n", "scripts/partes.mjs": "// partes\n",
        "package.json": '{"dependencies": {"remotion": "4.0.482"}}\n', "remotion.config.ts": "// config\n",
        "tsconfig.json": "{}\n", "public/edit-data.json": '{"exemplo": true}\n', "README.md": "# kit\n"})
    return assets


@pytest.fixture
def projeto(tmp_path):
    edit = tmp_path / "edit"
    _escreve(edit / "remotion", {
        "src/Main.tsx": "// Main antigo, sem os efeitos\n", "src/CustomGraphics.tsx": "// gráfico feito para ESTE vídeo\n",
        "package.json": '{"dependencies": {"remotion": "4.0.482"}}\r\n', "public/edit-data.json": '{"do": "video"}\n'})
    return edit


def _sem_npm(*a, **k):
    raise AssertionError("o npm não devia rodar: o package.json não mudou")


def test_troca_o_codigo_e_guarda_o_que_e_do_projeto(kit, projeto):
    pl = at.aplicar(projeto, assets=kit, rodar=_sem_npm)
    rem = projeto / "remotion"
    assert pl["trilha"] == "shortform"
    assert sorted(pl["novos"]) == ["remotion.config.ts", "scripts/partes.mjs", "src/cenas/index.tsx", "tsconfig.json"]
    assert pl["trocados"] == ["src/Main.tsx"]  # o package.json só difere no fim de linha: igual
    assert "<Cenas />" in (rem / "src/Main.tsx").read_text(encoding="utf-8")
    assert (rem / "src/CustomGraphics.tsx").read_text(encoding="utf-8") == "// gráfico feito para ESTE vídeo\n"
    assert json.loads((rem / "public/edit-data.json").read_text(encoding="utf-8")) == {"do": "video"}
    assert not (rem / "README.md").exists()
    assert (pl["copia"] / "src/Main.tsx").read_text(encoding="utf-8") == "// Main antigo, sem os efeitos\n"
    assert pl["copia"].parent == projeto / ".template-anterior"  # fora do remotion/


def test_a_segunda_vez_nao_tem_nada_a_trocar(kit, projeto):
    at.aplicar(projeto, assets=kit, rodar=_sem_npm)
    pl = at.aplicar(projeto, assets=kit, rodar=_sem_npm)
    assert pl["novos"] == pl["trocados"] == [] and pl["copia"] is None


def test_efeito_feito_a_mao_trava_a_troca(kit, projeto):
    _escreve(projeto / "remotion", {"src/cenas/revelacao.tsx": "// feito à mão\n"})
    with pytest.raises(at.ErroTemplate, match="src/cenas/revelacao.tsx"):
        at.aplicar(projeto, assets=kit, rodar=_sem_npm)
    assert (projeto / "remotion/src/Main.tsx").read_text(encoding="utf-8") == "// Main antigo, sem os efeitos\n"
    at.aplicar(projeto, forcar=True, assets=kit, rodar=_sem_npm)
    assert (projeto / "remotion/src/cenas/revelacao.tsx").is_file()  # fica, só deixa de ser usado


def test_package_json_novo_roda_o_npm_install(kit, projeto, monkeypatch):
    _escreve(kit / "shortform", {"package.json": '{"dependencies": {"remotion": "4.0.500"}}\n'})
    chamadas = []
    monkeypatch.setattr(at.shutil, "which", lambda nome: "npm")
    pl = at.aplicar(projeto, assets=kit, rodar=lambda cmd, cwd: chamadas.append((cmd, cwd)) or SimpleNamespace(returncode=0))
    assert chamadas == [(["npm", "install"], str(projeto / "remotion"))] and pl["npm_feito"]
    assert at.aplicar(projeto, assets=kit, rodar=_sem_npm)["npm"] is False  # já igual: não roda de novo


def test_simular_nao_grava_nada(kit, projeto):
    pl = at.planejar(projeto, assets=kit)
    assert pl["trocados"] == ["src/Main.tsx"]
    assert not (projeto / "remotion/src/cenas").exists() and not (projeto / ".template-anterior").exists()


def test_longform_e_o_projeto_sem_custom_graphics(kit, tmp_path):
    _escreve(kit / "longform", {"src/Main.tsx": "// longo\n", "package.json": "{}\n"})
    edit = tmp_path / "longo"
    _escreve(edit / "remotion", {"src/Main.tsx": "// longo antigo\n", "package.json": "{}\n"})
    assert at.planejar(edit, assets=kit)["trilha"] == "longform"


# ---- a trava do cenas_edit_data.py, contra o template de verdade do kit

def _projeto_com_fundo(tmp_path, com_template: bool) -> Path:
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    (public / "edit-data.json").write_text(json.dumps({"fps": 30, "cenas": [
        {"tipo": "fundo", "start": 1.0, "end": 3.0, "fundo": "fundos/lousa"}]}), encoding="utf-8")
    src = edit / "remotion" / "src"
    if com_template:
        shutil.copytree(RAIZ / "assets" / "shortform" / "src", src)
    else:  # o template de antes dos efeitos: Main sem <Cenas /> e sem src/cenas/
        src.mkdir()
        (src / "Main.tsx").write_text("// Main de antes dos efeitos\n", encoding="utf-8")
    return edit


def test_template_antigo_para_antes_de_recortar(tmp_path):
    edit = _projeto_com_fundo(tmp_path, com_template=False)
    antes = (edit / "remotion/public/edit-data.json").read_bytes()
    r = ced.aplicar(edit, edit / "remotion/public/edit-data.json", recortar=False)
    assert "src/Main.tsx" in r["template"] and "src/cenas/index.tsx" in r["template"]
    assert (edit / "remotion/public/edit-data.json").read_bytes() == antes and r["pendentes"] == []


def test_template_do_kit_passa_pela_trava(tmp_path):
    edit = _projeto_com_fundo(tmp_path, com_template=True)
    r = ced.aplicar(edit, edit / "remotion/public/edit-data.json", recortar=False)
    assert r["template"] == [] and len(r["pendentes"]) == 1  # seguiu: o recorte ficou só avisado
