"""Isola os testes da pasta do kit no usuário (~/.cutmind): lista de projetos, projeto
aberto e modelos.

Sem isso, um teste que sobe o servidor de verdade registraria pastas temporárias na lista
de quem roda a suíte e trocaria o aberto.json, e o vigia do agente acharia que o editor
abriu outro projeto. O processo filho herda a variável.
"""
import pytest


@pytest.fixture(autouse=True)
def _casa_isolada(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("CUTMIND_HOME", str(tmp_path_factory.mktemp("cutmind-home")))
    # a procura da versão nova nunca pergunta ao GitHub de verdade (test_atualizar.py liga com o GitHub de mentira)
    monkeypatch.setenv("CUTMIND_SEM_ATUALIZACAO", "1")
