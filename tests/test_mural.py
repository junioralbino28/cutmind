"""A ponte com o mural de modelos (mural.py) e as rotas do editor que usam ela. O mural aqui é um
servidor falso local: o que ele responde é o que um mural qualquer (ou um impostor) poderia mandar,
e nada disso chega ao editor ou aos modelos da pessoa sem ser conferido."""
from __future__ import annotations

import base64
import http.client
import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import montagens as mg  # noqa: E402
import mural as mu  # noqa: E402
import preview_server as ps  # noqa: E402

MODELO = {"versao": 1, "comeca": "forte", "drop_na_vaga": 3, "golpe": True, "formato": "1:1",
          "vagas": [{"batidas": 4, "repetir": 2}, {"batidas": 1, "repetir": 8}],
          "textos": [{"nome": "Título", "texto": "OI", "vaga": 1, "batidas": 8, "x": 540, "y": 540, "estilo": {}}],
          "transicoes": [{"vaga": 3, "pacote": "flash-branco", "duracao": 0.4}]}


def _item(ident="AAAAAAAAAAA1", **mais):
    base = {"id": ident, "nome": "Viagem", "autor": "fulana.cria", "post": "https://www.instagram.com/reel/ABCdef12345/",
            "plataforma": "instagram", "criado": 1, "resumo": {
                "lugares": 3, "batidas": 6, "ritmo": [4, 1, 1], "drop_na_vaga": 2, "formato": "9:16",
                "textos": [{"nome": "Título", "vaga": 1, "batidas": 4}], "transicoes": 1}}
    return {**base, **mais}


@pytest.fixture
def falso(monkeypatch):
    """O mural falso: `lista` e `modelos` dizem o que ele responde; `pedidos` guarda o que pediram."""
    estado = SimpleNamespace(lista={"modelos": [], "seguinte": None}, modelos={}, pedidos=[], bruto=None, redirecionar=None)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):  # noqa: N802
            estado.pedidos.append(self.path)
            caminho = urlsplit(self.path).path
            if estado.redirecionar and not caminho.startswith("/destino"):
                self.send_response(302)
                self.send_header("Location", estado.redirecionar)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if estado.bruto is not None:
                corpo, codigo = estado.bruto, 200
            elif caminho == "/api/modelos":
                corpo, codigo = json.dumps(estado.lista).encode(), 200
            elif caminho.removeprefix("/api/modelos/") in estado.modelos:
                corpo, codigo = json.dumps(estado.modelos[caminho.removeprefix("/api/modelos/")]).encode(), 200
            else:
                corpo, codigo = b'{"erro":"modelo n\\u00e3o encontrado"}', 404
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    monkeypatch.setenv("CUTMIND_MURAL", f"http://127.0.0.1:{servidor.server_address[1]}/")
    yield estado
    servidor.shutdown()
    servidor.server_close()


def _no_mural(estado, codigo, modelo, nome="Viagem"):
    estado.modelos[codigo] = {"id": codigo, "nome": nome, "modelo": {**modelo, "nome": nome}}


# ---- o endereço ----
@pytest.mark.parametrize("valor, esperado", [
    ("", None), ("ftp://mural.example", None), ("mural.example", None), ("https://mural.example/?x=1", None),
    ("http://mural.example", None),  # http só para um mural de teste neste computador
    ("https://mural.example/", "https://mural.example"), ("http://127.0.0.1:4851", "http://127.0.0.1:4851"),
    ("http://localhost:4851", "http://localhost:4851"),
])
def test_endereco(monkeypatch, valor, esperado):
    monkeypatch.setenv("CUTMIND_MURAL", valor)
    assert mu.endereco() == esperado


def test_sem_endereco_nada_sai(monkeypatch):
    monkeypatch.delenv("CUTMIND_MURAL", raising=False)
    with pytest.raises(mu.MuralIndisponivel):
        mu.lista()
    with pytest.raises(mu.MuralIndisponivel):
        mu.link_publicar("qualquer")


# ---- a lista ----
def test_cartao_refeito_campo_a_campo():
    c = mu.cartao(_item())
    assert c["perfil"] == "https://www.instagram.com/fulana.cria/" and c["post"].endswith("/ABCdef12345/")
    assert c["ritmo"] == [4, 1, 1] and c["lugares"] == 3 and c["batidas"] == 6 and c["doMural"]
    assert mu.cartao(_item(plataforma="tiktok", post="https://www.tiktok.com/@x/video/7300000000000000000"))["perfil"] \
        == "https://www.tiktok.com/@fulana.cria"


@pytest.mark.parametrize("mudanca, campo, esperado", [
    ({"post": "javascript:alert(1)"}, "post", None),
    ({"post": "https://evil.example/reel/ABCdef12345/"}, "post", None),
    ({"plataforma": "myspace"}, "post", None),
    ({"autor": "<b>x</b>"}, "autor", None),
    ({"autor": "<b>x</b>"}, "perfil", None),
])
def test_cartao_larga_o_que_nao_confere(mudanca, campo, esperado):
    assert mu.cartao(_item(**mudanca))[campo] == esperado


@pytest.mark.parametrize("mudanca", [
    {"id": "../../etc"}, {"nome": ""}, {"nome": "x" * 61}, {"resumo": None},
    {"resumo": {**_item()["resumo"], "ritmo": [4, 0]}}, {"resumo": {**_item()["resumo"], "ritmo": "4,4"}},
])
def test_cartao_torto_some(mudanca):
    assert mu.cartao(_item(**mudanca)) is None


def test_lista_passa_so_o_cursor_que_confere(falso):
    falso.lista = {"modelos": [_item(), _item(ident="x"), "lixo"], "seguinte": "100.AAAAAAAAAAA1"}
    d = mu.lista()
    assert [c["id"] for c in d["modelos"]] == ["AAAAAAAAAAA1"] and d["seguinte"] == "100.AAAAAAAAAAA1"
    mu.lista("100.AAAAAAAAAAA1")
    mu.lista("1 OR 1=1")
    assert falso.pedidos == ["/api/modelos?n=24", "/api/modelos?n=24&antes=100.AAAAAAAAAAA1", "/api/modelos?n=24"]


def test_a_ponte_nao_segue_redirecionamento(falso):
    """Um mural que manda para outro endereço levaria o computador da pessoa a pedir esse
    endereço (outro serviço da rede dela, por exemplo): a ponte para no 302."""
    falso.redirecionar = f"{mu.endereco()}/destino"
    with pytest.raises(mu.MuralIndisponivel, match="302"):
        mu.lista()
    assert not any(p.startswith("/destino") for p in falso.pedidos)


def test_mural_estranho_e_indisponivel(falso, monkeypatch):
    falso.bruto = b"<html>nao sou o mural</html>"
    with pytest.raises(mu.MuralIndisponivel):
        mu.lista()
    falso.bruto = b"[" + b"1," * 300_000 + b"1]"
    with pytest.raises(mu.MuralIndisponivel, match="grande demais"):
        mu.lista()
    monkeypatch.setenv("CUTMIND_MURAL", "http://127.0.0.1:9")  # ninguém ouvindo
    with pytest.raises(mu.MuralIndisponivel):
        mu.lista()


# ---- pegar ----
def test_pegar_grava_nos_modelos_da_pessoa_e_nao_duplica(falso):
    _no_mural(falso, "AAAAAAAAAAA1", {**MODELO, "lixo": 1})
    m = mu.pegar("AAAAAAAAAAA1")
    assert m["id"] == "viagem" and m["formato"] == "1:1" and "lixo" not in m
    assert (mg.pasta() / "viagem.json").is_file()
    assert mu.pegar("AAAAAAAAAAA1")["id"] == "viagem"  # o mesmo de novo: nada novo
    assert sorted(p.name for p in mg.pasta().glob("*.json")) == ["viagem.json"]


def test_pegar_nunca_troca_um_modelo_que_ja_existe(falso):
    _no_mural(falso, "AAAAAAAAAAA1", MODELO)
    _no_mural(falso, "AAAAAAAAAAA2", {**MODELO, "formato": "9:16"})
    _no_mural(falso, "AAAAAAAAAAA3", MODELO, nome="Drop cedo")  # o nome de um do kit
    assert mu.pegar("AAAAAAAAAAA1")["nome"] == "Viagem"
    assert mu.pegar("AAAAAAAAAAA2")["nome"] == "Viagem (2)"
    assert mu.pegar("AAAAAAAAAAA3")["nome"] == "Drop cedo (2)"
    assert mg.obter("drop-cedo")["doKit"] and mg.obter("viagem")["formato"] == "1:1"


def test_pegar_nome_longo_repetido_termina(falso):
    """O id sai dos 40 primeiros caracteres do nome: com o número depois dos 60, o id não
    mudava e o laço não acabava (o servidor do editor ficava preso)."""
    longo = "Montagem de viagem pela praia com amigos no verão de 2026!"
    for k, formato in enumerate(("9:16", "1:1", "16:9"), 1):
        _no_mural(falso, f"AAAAAAAAAAA{k}", {**MODELO, "formato": formato}, nome=longo)
    nomes = [mu.pegar(f"AAAAAAAAAAA{k}")["nome"] for k in (1, 2, 3)]
    assert nomes == [longo, "Montagem de viagem pela praia (2)", "Montagem de viagem pela praia (3)"]
    assert len(list(mg.pasta().glob("*.json"))) == 3


def test_pegar_para_num_teto_de_nomes(falso, monkeypatch):
    monkeypatch.setattr(mu, "LIMITE_DE_NOMES", 2)
    for k, formato in enumerate(("9:16", "1:1", "16:9", "9:16"), 1):
        _no_mural(falso, f"AAAAAAAAAAA{k}", {**MODELO, "formato": formato, "golpe": k != 4})
    for k in (1, 2, 3):
        mu.pegar(f"AAAAAAAAAAA{k}")
    with pytest.raises(mu.MuralRecusou, match="apague um"):
        mu.pegar("AAAAAAAAAAA4")


def test_pegar_nome_sem_letra_leva_o_codigo(falso):
    _no_mural(falso, "AbC-dEf_1234", MODELO, nome="🔥🔥🔥")
    assert mu.pegar("AbC-dEf_1234")["nome"] == "Modelo AbC-dEf_1234"


def test_pegar_recusa(falso):
    with pytest.raises(mu.MuralRecusou):
        mu.pegar("../segredo")
    with pytest.raises(mu.MuralRecusou):
        mu.pegar("AAAAAAAAAAA9")  # 404 do mural
    _no_mural(falso, "AAAAAAAAAAA1", {**MODELO, "formato": "4:3"})
    with pytest.raises(mg.MontagemInvalida):
        mu.pegar("AAAAAAAAAAA1")
    falso.modelos["AAAAAAAAAAA2"] = {"modelo": "não é objeto"}
    with pytest.raises(mu.MuralIndisponivel):
        mu.pegar("AAAAAAAAAAA2")
    assert not mg.pasta().is_dir() or not list(mg.pasta().glob("*.json"))


# ---- o link de publicar ----
def test_link_publicar_leva_o_modelo_no_fragmento(falso):
    salvo = mg.salvar({**MODELO, "nome": "Meu ritmo"})
    link = mu.link_publicar("meu-ritmo")
    base, _, frag = link.partition("#m=")
    assert base == f"{mu.endereco()}/publicar"
    dados = json.loads(base64.urlsafe_b64decode(frag + "=" * (-len(frag) % 4)))
    assert dados == {k: v for k, v in salvo.items() if k not in ("id", "criado")}
    with pytest.raises(mu.MuralRecusou, match="kit"):
        mu.link_publicar("drop-cedo")
    with pytest.raises(mu.MuralRecusou):
        mu.link_publicar("nao-existe")


# ---- o mural e o kit conferem igual ----
MURAL_MODELO = Path(__file__).resolve().parents[1] / "mural" / "src" / "modelo.js"


@pytest.mark.skipif(not shutil.which("node"), reason="sem Node")
def test_o_mural_aceita_inteiro_o_que_o_kit_aceita():
    """Um modelo do kit vai ao mural e volta: se a conferência do mural (JavaScript) largasse um
    campo que a do kit aceita, o modelo voltaria empobrecido sem erro nenhum."""
    cheio = {**MODELO, "nome": "Cheio", "vagas": [{"batidas": 64, "movimento": "zoom-out"}, {"batidas": 1, "repetir": 399}],
             "textos": [{"nome": f"T{i}", "texto": "linha\num", "vaga": i + 1, "batidas": 3, "x": -1080, "y": 3840,
                         "estilo": {"fonte": "Bebas Neue", "peso": 700, "cor": "#ABCDEF", "corContorno": "#000000",
                                    "tamanho": 0.2, "contorno": 60}} for i in range(20)],
             "transicoes": [{"vaga": 2, "pacote": "t-zoom-central", "duracao": 5.0}, {"vaga": 400, "pacote": "x", "duracao": 0.1}]}
    kit = sorted((mg.KIT).glob("*.json"))
    assert kit
    modelos = [mg.normalize(json.loads(p.read_text(encoding="utf-8"))) for p in kit] + [mg.normalize(cheio)]
    dados = [{k: v for k, v in m.items() if k not in ("id", "nome", "criado")} for m in modelos]
    script = (f"import {{ conferirModelo }} from {json.dumps(MURAL_MODELO.as_uri())};"
              "let s='';process.stdin.on('data',(d)=>{s+=d});"
              "process.stdin.on('end',()=>{process.stdout.write(JSON.stringify(JSON.parse(s).map(conferirModelo)))});")
    r = subprocess.run(["node", "--input-type=module", "-e", script], input=json.dumps(dados).encode(),
                       capture_output=True, check=True)
    assert json.loads(r.stdout) == dados


# ---- as rotas do editor ----
@pytest.fixture
def srv(tmp_path):
    edit = tmp_path / "videos" / "edit"
    edit.mkdir(parents=True)
    (edit / "state.json").write_text(json.dumps({"project": "t", "phase": 1}), encoding="utf-8")

    class H(ps.Handler):
        pass

    H.root = edit.resolve()
    H.token = "codigo-de-teste-0123456789"
    H.allow_hosts = ()
    H.upload_dir = edit.parent.resolve()
    H.max_upload = 1000
    H.bind_host = "127.0.0.1"
    server = ps.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def pedir(port, caminho, metodo="GET", corpo=None, cabecalhos=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    dados = None if corpo is None else json.dumps(corpo).encode()
    conn.request(metodo, caminho, body=dados, headers={**({} if dados is None else
                 {"Content-Type": "application/json", "Content-Length": str(len(dados))}), **(cabecalhos or {})})
    r = conn.getresponse()
    out = r.read()
    conn.close()
    return r, out


def test_rotas_do_editor(falso, srv):
    assert json.loads(pedir(srv, "/api/montagens")[1])["mural"] is True
    falso.lista = {"modelos": [_item(ident="AAAAAAAAAAA1")], "seguinte": None}
    r, dados = pedir(srv, "/api/mural?antes=1.AAAAAAAAAAA1")
    assert r.status == 200 and json.loads(dados)["modelos"][0]["id"] == "AAAAAAAAAAA1"
    assert falso.pedidos[-1] == "/api/modelos?n=24&antes=1.AAAAAAAAAAA1"

    _no_mural(falso, "AAAAAAAAAAA1", MODELO)
    r, dados = pedir(srv, "/api/mural/pegar", "POST", {"codigo": "AAAAAAAAAAA1"})
    assert r.status == 200 and json.loads(dados)["modelo"]["id"] == "viagem"
    assert pedir(srv, "/api/mural/pegar", "POST", {"codigo": "AAAAAAAAAAA9"})[0].status == 404

    r, _ = pedir(srv, "/api/mural/compartilhar?id=viagem")
    assert r.status == 303 and r.getheader("Location").startswith(f"{mu.endereco()}/publicar#m=")
    assert pedir(srv, "/api/mural/compartilhar?id=drop-cedo")[0].status == 404


def test_post_de_outro_site_e_recusado(falso, srv):
    """Uma página qualquer aberta no navegador consegue mandar POST para 127.0.0.1 (o Host
    chega como IP). O navegador põe Origin e Sec-Fetch-Site: só passa o do próprio editor."""
    _no_mural(falso, "AAAAAAAAAAA1", MODELO)
    corpo = {"codigo": "AAAAAAAAAAA1"}
    proprio = f"http://127.0.0.1:{srv}"
    for cab in ({"Origin": "https://site-qualquer.example"}, {"Origin": "null"},
                {"Origin": f"http://127.0.0.1:{srv + 1}"}, {"Sec-Fetch-Site": "cross-site"}):
        assert pedir(srv, "/api/mural/pegar", "POST", corpo, cab)[0].status == 403, cab
    assert not mg.pasta().is_dir() or not list(mg.pasta().glob("*.json"))
    assert pedir(srv, "/api/mural/pegar", "POST", corpo, {"Origin": proprio, "Sec-Fetch-Site": "same-origin"})[0].status == 200
    assert pedir(srv, "/api/mural/pegar", "POST", corpo)[0].status == 200  # fora do navegador (agente, curl)


def test_rotas_sem_mural(monkeypatch, srv):
    monkeypatch.delenv("CUTMIND_MURAL", raising=False)
    assert json.loads(pedir(srv, "/api/montagens")[1])["mural"] is False
    assert pedir(srv, "/api/mural")[0].status == 502
    assert pedir(srv, "/api/mural/pegar", "POST", {"codigo": "AAAAAAAAAAA1"})[0].status == 502
