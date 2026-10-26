#!/usr/bin/env python3
"""Os modelos de montagem (o painel Modelos de montagem do editor): os lugares na batida, os
textos trocáveis e as transições, guardados com nome para usar com outra música e outras mídias.

Os da pessoa ficam em `~/.cutmind/montagens/<id>.json` (a pasta de `CUTMIND_HOME`), fora de
qualquer projeto; os que vêm com o kit, em `assets/montagens/` e na biblioteca de pacotes (tipo
`montagem`, o modelo escrito no catálogo e um vídeo de exemplo como prévia), só para ler. Um modelo
da pessoa com o id de um do kit vale no lugar dele; um de `assets/montagens/` vale no lugar de um da
biblioteca. O formato é o do `montagem.py` (a conferência é a dele), gravado com os lugares iguais
seguidos juntos em `repetir`:

    {"versao": 1, "id": "drop-cedo", "nome": "Drop cedo", "criado": <epoch>, "comeca": "forte",
     "drop_na_vaga": 3, "golpe": true,
     "vagas": [{"batidas": 4, "repetir": 2}, {"batidas": 1, "repetir": 32}],
     "textos": [{"nome": "Título", "texto": "SEU TÍTULO", "vaga": 1, "batidas": 8, "x": 540,
                 "y": 760, "estilo": {...}}],
     "transicoes": [{"vaga": 3, "pacote": "t-zoom-central", "duracao": 0.4}]}

    python montagens.py listar
    python montagens.py mostrar <id>
    python montagens.py salvar <arquivo.json>
    python montagens.py apagar <id>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import modelos  # mesma pasta deste arquivo
import montagem as mt  # mesma pasta deste arquivo
import pacotes as pk  # mesma pasta deste arquivo
import projetos as pj  # mesma pasta deste arquivo

VERSAO = 1
MAX_MODELOS = 200
MAX_BYTES = 20_000
KIT = Path(__file__).resolve().parents[1] / "assets" / "montagens"


class MontagemInvalida(ValueError):
    pass


def pasta() -> Path:
    return pj.casa() / "montagens"


def normalize(obj: object) -> dict:
    """O modelo como ele é gravado; recusa (MontagemInvalida) o que não for do formato."""
    if not isinstance(obj, dict):
        raise MontagemInvalida("o modelo não é um objeto")
    try:
        nome = modelos._nome(obj.get("nome"))
        ident = modelos.id_do_nome(nome)
        m = mt.carregar_modelo({**obj, "id": ident, "nome": nome})
    except (mt.ErroMontagem, modelos.ModeloInvalido) as e:
        raise MontagemInvalida(str(e)) from None
    vagas: list[dict] = []
    for v in m["vagas"]:  # os iguais seguidos voltam a ser um lugar com `repetir`
        chave = {"batidas": v["batidas"], **({"movimento": v["movimento"]} if v.get("movimento") else {})}
        if vagas and {k: x for k, x in vagas[-1].items() if k != "repetir"} == chave:
            vagas[-1]["repetir"] = vagas[-1].get("repetir", 1) + 1
        else:
            vagas.append(dict(chave))
    out = {"versao": VERSAO, "id": ident, "nome": nome, **_nome_en(obj),
           "criado": float(obj["criado"]) if isinstance(obj.get("criado"), (int, float)) else time.time(),
           "comeca": m["comeca"], "drop_na_vaga": m["drop_na_vaga"], "golpe": m["golpe"], "formato": m["formato"],
           "vagas": vagas,
           "textos": m["textos"], "transicoes": m["transicoes"]}
    if len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        raise MontagemInvalida(f"o modelo passa de {MAX_BYTES // 1000} KB")
    return out


def _nome_en(obj: dict) -> dict:
    """O nome na tela em inglês, que só os modelos do kit e da biblioteca trazem; inválido, fica sem."""
    try:
        return {"nome_en": modelos._nome(obj["nome_en"])} if obj.get("nome_en") is not None else {}
    except modelos.ModeloInvalido:
        return {}


def resumo(m: dict) -> dict:
    """O que o cartão do painel mostra: o ritmo (as batidas de cada lugar), os textos e o drop."""
    ritmo = [v["batidas"] for v in m["vagas"] for _ in range(v.get("repetir", 1))]
    return {"id": m["id"], "nome": m["nome"], "nomeEn": m.get("nome_en"), "doKit": bool(m.get("doKit")), "criado": m["criado"],
            "lugares": len(ritmo), "batidas": sum(ritmo), "ritmo": ritmo, "drop_na_vaga": m["drop_na_vaga"],
            "formato": m.get("formato") or mt.FORMATO_PADRAO,
            "textos": [{"nome": t["nome"], "vaga": t["vaga"], "batidas": t["batidas"]} for t in m["textos"]],
            "transicoes": len(m["transicoes"]),
            "previa": m.get("pacote") if m.get("previa") else None}  # o pacote do vídeo de exemplo


def _ler(p: Path, do_kit: bool = False) -> dict | None:
    try:
        m = normalize(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None
    if m["id"] != p.stem:  # o arquivo é do id que ele diz ser: nunca outro nome por cima
        return None
    return {**m, "doKit": True} if do_kit else m


def _da_pessoa() -> dict[str, dict]:
    p = pasta()
    return {m["id"]: m for m in (_ler(x) for x in sorted(p.glob("*.json"))) if m} if p.is_dir() else {}


def _do_kit() -> dict[str, dict]:
    kit = {m["id"]: m for m in (_ler(x, True) for x in sorted(KIT.glob("*.json"))) if m} if KIT.is_dir() else {}
    return {**_da_biblioteca(), **kit}


def _da_biblioteca() -> dict[str, dict]:
    """Os da biblioteca de pacotes: o modelo vem escrito no catálogo e passa pela mesma conferência;
    o vídeo de exemplo é a prévia do pacote, baixada só quando a pessoa pede para ver."""
    try:
        cat = pk.Pacotes.do_ambiente().cat
    except (pk.PacoteErro, OSError):
        return {}
    out: dict[str, dict] = {}
    for p in cat["pacotes"]:
        if p["tipo"] != "montagem":
            continue
        try:
            m = normalize({**p["modelo"], "nome": p["nome"][:modelos.NOME_MAX], "criado": 0,
                           **({"nome_en": p["nome_en"][:modelos.NOME_MAX]} if p.get("nome_en") else {})})
        except MontagemInvalida:
            continue  # um modelo que o kit recusaria não aparece
        out[m["id"]] = {**m, "doKit": True, "pacote": p["id"], "previa": "previa" in p}
    return out


def listar() -> list[dict]:
    """Os modelos válidos: os da pessoa primeiro (o mais novo antes), depois os do kit."""
    pessoa = _da_pessoa()
    kit = [m for k, m in _do_kit().items() if k not in pessoa]
    return sorted(pessoa.values(), key=lambda m: m["criado"], reverse=True) + sorted(kit, key=lambda m: m["nome"])


def obter(mid: object) -> dict | None:
    if not isinstance(mid, str) or not modelos._ID.fullmatch(mid):
        return None
    return _ler(pasta() / f"{mid}.json") or _ler(KIT / f"{mid}.json", True) or _da_biblioteca().get(mid)


def salvar(obj: dict) -> dict:
    """Grava (ou troca, se o nome já existe entre os da pessoa) e devolve o modelo gravado."""
    m = normalize(obj)
    antigo = _ler(pasta() / f"{m['id']}.json")
    if antigo:
        m["criado"] = antigo["criado"]  # trocar o conteúdo não muda o lugar na lista
    elif len(_da_pessoa()) >= MAX_MODELOS:
        raise MontagemInvalida(f"já são {MAX_MODELOS} modelos de montagem: apague um antes")
    p = pasta()
    p.mkdir(parents=True, exist_ok=True)
    tmp = p / f"{m['id']}.json.tmp"
    tmp.write_bytes(json.dumps(m, ensure_ascii=False, indent=2).encode("utf-8"))
    tmp.replace(p / f"{m['id']}.json")
    return m


def apagar(mid: object) -> bool:
    """Apaga um modelo da pessoa. Os do kit não se apagam."""
    if not isinstance(mid, str) or not modelos._ID.fullmatch(mid) or not _ler(pasta() / f"{mid}.json"):
        return False
    (pasta() / f"{mid}.json").unlink()
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar")
    for c in ("mostrar", "apagar"):
        sub.add_parser(c).add_argument("id")
    sub.add_parser("salvar").add_argument("arquivo", type=Path)
    a = ap.parse_args()
    if a.cmd == "listar":
        for m in listar():
            r = resumo(m)
            print(f"{r['id']}  {r['nome']}  · {r['lugares']} lugares, {r['batidas']} batidas"
                  + (f", {len(r['textos'])} texto(s)" if r["textos"] else "")
                  + (f", {r['transicoes']} transição(ões)" if r["transicoes"] else "") + ("  (do kit)" if r["doKit"] else ""))
    elif a.cmd == "mostrar":
        m = obter(a.id)
        print(json.dumps(m, ensure_ascii=False, indent=2) if m else "não existe")
    elif a.cmd == "salvar":
        try:
            m = salvar(json.loads(a.arquivo.read_text(encoding="utf-8")))
        except (OSError, ValueError) as e:  # MontagemInvalida e JSON quebrado são ValueError
            print(f"recusado: {e}")
            return 1
        print(f"salvo: {m['id']}  {m['nome']}")
    else:
        print("apagado" if apagar(a.id) else "não existe (ou é do kit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
