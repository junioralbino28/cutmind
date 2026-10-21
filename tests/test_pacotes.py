"""Pacotes sob demanda: o catálogo diz o que existe, `obter` baixa só quando usa.

Um servidor HTTP local faz o papel da Release (mesma árvore: <release>/<arquivo>),
então nada sai para a internet.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import threading
import urllib.error
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import camadas as cam  # noqa: E402
import pacotes as pk  # noqa: E402


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _item(pid, nome, clima, dados, previa, tags=(), duracao=60.0, tipo="trilha"):
    return {"id": pid, "tipo": tipo, "nome": nome, "clima": clima, "tags": list(tags),
            "duracao": duracao, "release": "trilhas-1", "arquivo": f"{pid}.m4a",
            "tamanho": len(dados), "sha256": _sha(dados),
            "previa": {"arquivo": f"{pid}.previa.m4a", "tamanho": len(previa), "sha256": _sha(previa)}}


@pytest.fixture
def rel(tmp_path):
    """Uma Release de mentira com três trilhas, servida por HTTP local."""
    raiz = tmp_path / "release"
    (raiz / "trilhas-1").mkdir(parents=True)
    arquivos = {
        "calma-01": (b"A" * 4000, b"a" * 500),
        "animada-01": (b"B" * 4000, b"b" * 500),
        "animada-02": (b"C" * 4000, b"c" * 500),
    }
    pedidos: list[str] = []

    class H(SimpleHTTPRequestHandler):
        def log_message(self, *a):  # silêncio no teste
            pass

        def do_GET(self):  # noqa: N802
            pedidos.append(self.path)
            super().do_GET()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(H, directory=str(raiz)))
    threading.Thread(target=partial(srv.serve_forever, poll_interval=0.05), daemon=True).start()
    for pid, (d, p) in arquivos.items():
        (raiz / "trilhas-1" / f"{pid}.m4a").write_bytes(d)
        (raiz / "trilhas-1" / f"{pid}.previa.m4a").write_bytes(p)
    cat = {"versao": 1, "gerado": "2026-10-21T12:00:00Z", "repo": "dono/pacotes",
           "base": f"http://127.0.0.1:{srv.server_address[1]}",
           "pacotes": [_item("calma-01", "Manhã leve", "calma", *arquivos["calma-01"], tags=["violão"]),
                       _item("animada-01", "Pulo", "animada", *arquivos["animada-01"], duracao=30.0),
                       _item("animada-02", "Corrida", "animada", *arquivos["animada-02"])]}
    yield SimpleNamespace(raiz=raiz, cat=cat, pedidos=pedidos, cache=tmp_path / "cache",
                          arquivos=arquivos, tmp=tmp_path)
    srv.shutdown()
    srv.server_close()


def _pac(rel, limite=10**9, base=None):
    return pk.Pacotes(pk.validar(json.loads(json.dumps(rel.cat))), rel.cache, limite, base=base)


# ---- catálogo ----
@pytest.mark.parametrize("estrago", [
    lambda c: c["pacotes"][0].update(id="../fora"),
    lambda c: c["pacotes"][0].update(arquivo="../../x.m4a"),
    lambda c: c["pacotes"][0].update(arquivo=".escondido"),
    lambda c: c["pacotes"][0].update(release="a/b"),
    lambda c: c["pacotes"][0].update(sha256="nao-e-hex"),
    lambda c: c["pacotes"][0].update(tamanho=-1),
    lambda c: c["pacotes"][0].update(tipo="programa"),
    lambda c: c["pacotes"][1].update(id="calma-01"),
    lambda c: c["pacotes"][0]["previa"].update(arquivo="x/y.m4a"),
])
def test_catalogo_com_defeito_e_recusado(rel, estrago):
    c = json.loads(json.dumps(rel.cat))
    estrago(c)
    with pytest.raises(pk.CatalogoInvalido):
        pk.validar(c)


def test_listar_filtra_por_tipo_e_busca_sem_acento(rel):
    p = _pac(rel)
    assert [x["id"] for x in p.listar(tipo="trilha", busca="animada")] == ["animada-01", "animada-02"]
    assert [x["id"] for x in p.listar(busca="manha")] == ["calma-01"]  # "Manhã", sem o til
    assert [x["id"] for x in p.listar(busca="VIOLAO")] == ["calma-01"]  # pelas tags
    assert p.listar(tipo="filtro") == []
    assert p.listar()[0]["baixado"] is False and p.listar()[0]["favorito"] is False


# ---- baixar ----
def test_obter_baixa_confere_e_nao_baixa_de_novo(rel):
    p = _pac(rel)
    caminho = p.obter("calma-01")
    assert caminho.read_bytes() == rel.arquivos["calma-01"][0]
    assert caminho.is_relative_to(rel.cache)
    assert p.obter("calma-01") == caminho
    assert rel.pedidos.count("/trilhas-1/calma-01.m4a") == 1
    assert next(x for x in p.listar() if x["id"] == "calma-01")["baixado"] is True


def test_arquivo_adulterado_nao_fica_no_cache(rel):
    (rel.raiz / "trilhas-1" / "animada-01.m4a").write_bytes(b"X" * 4000)  # mesmo tamanho, outro conteúdo
    p = _pac(rel)
    with pytest.raises(pk.PacoteCorrompido):
        p.obter("animada-01")
    assert not [f for f in rel.cache.rglob("*") if f.is_file() and f.name != "estado.json"]


def test_arquivo_maior_que_o_catalogo_e_cortado_e_recusado(rel):
    (rel.raiz / "trilhas-1" / "animada-01.m4a").write_bytes(b"B" * 9000)
    with pytest.raises(pk.PacoteCorrompido):
        _pac(rel).obter("animada-01")


def test_previa_baixa_so_a_previa(rel):
    p = _pac(rel)
    assert p.previa("animada-02").read_bytes() == rel.arquivos["animada-02"][1]
    assert "/trilhas-1/animada-02.m4a" not in rel.pedidos


def test_pacote_que_nao_existe(rel):
    with pytest.raises(pk.PacoteErro):
        _pac(rel).obter("nao-existe")


def test_fora_do_ar_da_erro_claro(rel):
    p = _pac(rel, base="http://127.0.0.1:9")  # porta fechada
    with pytest.raises(pk.PacoteIndisponivel):
        p.obter("calma-01")


def test_base_do_ambiente_troca_o_endereco(rel, monkeypatch):
    espelho = rel.tmp / "espelho"
    (espelho / "trilhas-1").mkdir(parents=True)
    (espelho / "trilhas-1" / "calma-01.m4a").write_bytes(rel.arquivos["calma-01"][0])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(espelho)))
    threading.Thread(target=partial(srv.serve_forever, poll_interval=0.05), daemon=True).start()
    try:
        cat_p = rel.tmp / "catalogo.json"
        cat_p.write_text(json.dumps(rel.cat), encoding="utf-8")
        monkeypatch.setenv("CUTMIND_PACOTES_CATALOGO", str(cat_p))
        monkeypatch.setenv("CUTMIND_PACOTES_DIR", str(rel.cache))
        monkeypatch.setenv("CUTMIND_PACOTES_BASE", f"http://127.0.0.1:{srv.server_address[1]}")
        pk.Pacotes.do_ambiente().obter("calma-01")
        assert rel.pedidos == []  # nada foi pedido à Release original
    finally:
        srv.shutdown()
        srv.server_close()


def test_github_privado_cai_no_gh(rel, monkeypatch):
    c = json.loads(json.dumps(rel.cat))
    c["base"] = "https://github.com/dono/pacotes/releases/download"
    p = pk.Pacotes(pk.validar(c), rel.cache, 10**9)

    def http_404(url, destino, limite):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    usados = []

    def gh(repo, release, arquivo, destino):
        usados.append((repo, release, arquivo))
        destino.write_bytes(rel.arquivos["calma-01"][0])

    monkeypatch.setattr(pk, "_http_baixar", http_404)
    monkeypatch.setattr(pk, "_gh_baixar", gh)
    assert p.obter("calma-01").read_bytes() == rel.arquivos["calma-01"][0]
    assert usados == [("dono/pacotes", "trilhas-1", "calma-01.m4a")]


# ---- cache ----
def test_cache_cheio_tira_o_menos_usado_e_guarda_o_favorito(rel, monkeypatch):
    relogio = iter(range(100, 200))
    monkeypatch.setattr(pk, "_agora", lambda: next(relogio))
    p = _pac(rel, limite=9000)  # cabem dois arquivos de 4000
    p.favorito("calma-01")
    a = p.obter("calma-01")
    b = p.obter("animada-01")
    c = p.obter("animada-02")  # passa do limite: sai o menos usado que não é favorito (animada-01)
    assert a.exists() and c.exists() and not b.exists()
    assert p.cache_info()["bytes"] <= 9000
    p.favorito("calma-01", False)
    p.obter("animada-01")  # agora a calma-01 é a menos usada e pode sair
    assert not a.exists()


def test_obter_para_a_pasta_do_projeto_sem_sobrescrever(rel):
    p = _pac(rel)
    midia = rel.tmp / "edit" / "midia"
    midia.mkdir(parents=True)
    (midia / "calma-01.m4a").write_bytes(b"audio da pessoa")
    d1 = p.obter("calma-01", para=midia)
    assert d1.name == "calma-01-2.m4a" and (midia / "calma-01.m4a").read_bytes() == b"audio da pessoa"
    assert p.obter("calma-01", para=midia) == d1  # a mesma trilha de novo reaproveita a cópia


def test_atualizar_guarda_o_catalogo_mais_novo(rel, monkeypatch):
    novo = json.loads(json.dumps(rel.cat))
    novo["gerado"] = "2026-11-01T00:00:00Z"
    novo["pacotes"] = novo["pacotes"][:1]
    (rel.raiz / "catalogo").mkdir()
    (rel.raiz / "catalogo" / "catalogo.json").write_text(json.dumps(novo), encoding="utf-8")
    kit = rel.tmp / "kit-catalogo.json"
    kit.write_text(json.dumps(rel.cat), encoding="utf-8")
    monkeypatch.setenv("CUTMIND_PACOTES_CATALOGO", str(kit))
    monkeypatch.setenv("CUTMIND_PACOTES_DIR", str(rel.cache))
    monkeypatch.delenv("CUTMIND_PACOTES_BASE", raising=False)
    assert pk.Pacotes.do_ambiente().atualizar() is True
    assert [x["id"] for x in pk.Pacotes.do_ambiente().listar()] == ["calma-01"]  # o do cache é mais novo


# ---- a trilha na linha do tempo do projeto ----
def test_camada_poe_a_trilha_no_projeto(rel):
    edit = rel.tmp / "edit"
    edit.mkdir()
    p = _pac(rel)
    faixa = pk.por_na_linha(p, edit, "calma-01", duracao_video=45.0, inicio=2.0)
    c = cam.load(edit / "camadas.json")
    assert c["faixas"] == [faixa]
    it = faixa["itens"][0]
    assert faixa["tipo"] == "audio" and it["trilha"] == "calma-01"
    assert it["arquivo"] == "midia/calma-01.m4a" and (edit / it["arquivo"]).is_file()
    assert it["inicio"] == 2.0 and it["duracao"] == 43.0  # até o fim do vídeo, não os 60 s da trilha
    assert it["volume"] == pk.TRILHA_VOLUME
    # a segunda vira outra faixa, sem repetir id
    f2 = pk.por_na_linha(p, edit, "animada-01", duracao_video=45.0)
    assert f2["id"] != faixa["id"] and f2["itens"][0]["duracao"] == 30.0


# ---- efeitos: o zip é aberto no cache para o motor de efeitos ler ----
def _zip(arquivos: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, dados in arquivos.items():
            z.writestr(nome, dados)
    return buf.getvalue()


@pytest.fixture
def efeitos(rel):
    """A mesma Release, agora com filtros em zip: um bom e dois montados errado."""
    (rel.raiz / "efeitos-1").mkdir()
    bons = {"efeito.json": b'{"formato": 1}', "efeito.frag": b"void main(){}", "textura1.png": b"png"}
    zips = {"filme-pb": _zip(bons),
            "fuga": _zip({"efeito.json": b"{}", "../../fora.txt": b"escapou"}),
            "sem-manifesto": _zip({"efeito.frag": b"x"})}
    c = json.loads(json.dumps(rel.cat))
    for pid, dados in zips.items():
        (rel.raiz / "efeitos-1" / f"{pid}.zip").write_bytes(dados)
        c["pacotes"].append({"id": pid, "tipo": "filtro", "nome": pid, "release": "efeitos-1",
                             "arquivo": f"{pid}.zip", "tamanho": len(dados), "sha256": _sha(dados)})
    return SimpleNamespace(cat=c, bons=bons, zips=zips)


def test_efeito_e_aberto_no_cache_uma_vez(rel, efeitos):
    p = pk.Pacotes(pk.validar(efeitos.cat), rel.cache, 10**9)
    pasta = p.aberto("filme-pb")
    assert pasta.is_relative_to(rel.cache)
    assert {f.name: f.read_bytes() for f in pasta.iterdir() if not f.name.startswith(".")} == efeitos.bons
    antes = (pasta / "efeito.frag").stat().st_mtime_ns
    assert p.aberto("filme-pb") == pasta and (pasta / "efeito.frag").stat().st_mtime_ns == antes
    assert rel.pedidos.count("/efeitos-1/filme-pb.zip") == 1


def test_zip_montado_para_sair_da_pasta_nao_abre(rel, efeitos):
    p = pk.Pacotes(pk.validar(efeitos.cat), rel.cache, 10**9)
    with pytest.raises(pk.PacoteCorrompido, match="caminho"):
        p.aberto("fuga")
    assert not list(rel.tmp.rglob("fora.txt"))
    assert not [d for d in (rel.cache / "filtro").iterdir() if d.is_dir()]  # nem a pasta pela metade fica
    with pytest.raises(pk.PacoteCorrompido, match="efeito.json"):
        p.aberto("sem-manifesto")


def test_trilha_nao_abre_como_efeito(rel, efeitos):
    with pytest.raises(pk.PacoteErro, match="não é pacote de efeito"):
        pk.Pacotes(pk.validar(efeitos.cat), rel.cache, 10**9).aberto("calma-01")


def test_cache_cheio_tira_o_efeito_e_a_pasta_aberta_juntos(rel, efeitos, monkeypatch):
    relogio = iter(range(100, 200))
    monkeypatch.setattr(pk, "_agora", lambda: next(relogio))
    p = pk.Pacotes(pk.validar(efeitos.cat), rel.cache, 8200)  # cabem as duas trilhas, o filtro não
    pasta = p.aberto("filme-pb")
    p.obter("calma-01")
    p.obter("animada-01")
    assert not pasta.exists() and not p._local(p.pacote("filme-pb")).exists()
    assert p.cache_info()["bytes"] <= 8200


def test_so_trilha_vai_para_a_linha_do_tempo(rel):
    c = json.loads(json.dumps(rel.cat))
    c["pacotes"][0]["tipo"] = "filtro"
    p = pk.Pacotes(pk.validar(c), rel.cache, 10**9)
    with pytest.raises(pk.PacoteErro):
        pk.por_na_linha(p, rel.tmp, "calma-01", duracao_video=10.0)
