#!/usr/bin/env python3
"""Emit one event each time the editor asks for the agent.

Three files, all written by the editor and none able to reach the chat on its own:
  - pronto.json — the user pressed "Pronto, Claude segue" (or sent the request box): the
    written requests and markers, plus what the editor already applied by itself
  - preview_style.json — the Fase 1 → Fase 2 gate: editing style, caption style,
    edit elements
  - preview_upload.json — vídeos que o usuário mandou pelo botão Enviar (o
    servidor grava o arquivo na pasta dos vídeos e lista aqui)

The Salvar does NOT wake the agent any more: the editor's server applies takes, layers,
effects, speed and the Phase 2 data by itself (aplicar_corte.py, editdata_aplicar.py) and
the Baixar builds the final video (gerar.py). A preview_edits.json is from an editor older
than that; the Pronto carries it along (`legado`).

Run this under the Monitor tool so every request notifies the session automatically:

    Monitor(command="python3 <skill>/helpers/watch_edits.py '<edit>'",
            description="pedidos do editor", persistent=True)

Each stdout line is one notification. Stays quiet while nothing changes.

Where the Monitor expires (Claude Code 2.1.309 caps it at 30 min and has no `persistent`),
run it with `--uma-vez` as a background task instead (Bash `run_in_background`): it waits
as long as the session lives, prints the first request (or what is already pending) and
exits, which notifies the session. Apply it, delete the file, and start it again.

It also watches `~/.cutmind/aberto.json` (projetos.py): when the user opens ANOTHER project
in the editor's Projetos screen (or creates a new one), it says which and where. With
`--uma-vez` it exits on that too: from then on the work is in that folder, so restart the
watcher there. Without it, it follows the new folder by itself.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import modelos as md  # mesma pasta deste arquivo
import projetos as pj  # mesma pasta deste arquivo


def linhas_pedidos(notes: list[dict]) -> list[str]:
    """Uma linha por marcação (trecho do vídeo) ou pedido escrito (a caixa "O que você quer mudar?")."""
    out = []
    for i, n in enumerate(notes, 1):
        start, end = n.get("start", 0), n.get("end", 0)
        fase = n.get("phase", 1)
        if n.get("geral"):  # a caixa "O que você quer mudar?": pedido sem trecho, a agulha só situa
            out.append(f'  {i}. PEDIDO (agulha em {fmt(start)}, fase {fase}) {n.get("text", "").strip()}')
        else:
            out.append(f'  {i}. [{fmt(start)} → {fmt(end)}] (fase {fase}) {n.get("text", "").strip()}')
    return out


def pronto_digest(p: Path) -> str:
    """O Pronto do editor: o que ele já aplicou sozinho (não refazer) e os pedidos, uma vez só."""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"pronto.json ilegível ({e.__class__.__name__}) — peça ao usuário para apertar Pronto de novo"
    pedidos = d.get("pedidos") or []
    fase = d.get("fase") or 1
    out = [f"PRONTO DO EDITOR ({d.get('quando', '')}) — fase {fase}, {_plural(len(pedidos), 'pedido', 'pedidos')}."]
    feitos = [str(f.get("oque", "")).strip() for f in d.get("feitos") or [] if isinstance(f, dict)]
    if feitos:
        out.append("  Já aplicado pelo editor, NÃO refaça: " + "; ".join(x for x in feitos if x) + ".")
    if pedidos:
        out.append("  Pedidos:")
        out += ["  " + x for x in linhas_pedidos(pedidos)]
    elif fase == 1:
        out.append("  Sem pedido na fase 1 = o corte está aprovado: siga para o Estilo (awaitingStyle).")
    else:
        out.append("  Sem pedido: a pessoa terminou o que queria à mão. O Baixar do editor já gera o vídeo final "
                   "com isso; pergunte se falta algo.")
    if d.get("legado") and (p.parent / "preview_edits.json").exists():
        out.append("  Há um preview_edits.json de um editor anterior: aplique-o como antes e apague:")
        out += ["  " + x for x in digest(p.parent / "preview_edits.json").splitlines()]
    out.append("  Ao começar, rode helpers/agente.py trabalhando <edit> (o editor segura o Salvar do corte e o "
               "Gerar); ao terminar, helpers/agente.py livre <edit> e apague pronto.json e ajustes_feitos.json.")
    return "\n".join(out)


def digest(p: Path) -> str:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_edits.json ilegível ({e.__class__.__name__}) — peça ao usuário para salvar de novo"

    parts: list[str] = []
    notes = d.get("notes") or []
    parts += linhas_pedidos(notes)

    edl = d.get("edl") or {}
    n_ch = len(edl.get("changes") or [])
    n_rm = len(edl.get("removed") or [])
    ops = edl.get("ops") or {}
    ed = d.get("editData") or {}

    head = []
    pedidos = sum(1 for n in notes if n.get("geral"))
    if pedidos:
        head.append(_plural(pedidos, "pedido escrito", "pedidos escritos"))
    if len(notes) - pedidos:
        head.append(f"{len(notes) - pedidos} marcação(ões)")
    if n_ch:
        head.append(f"{n_ch} take(s) reajustado(s)")
    if n_rm:
        head.append(f"{n_rm} take(s) removido(s)")
    if ops.get("divisoes"):
        head.append(f"{ops['divisoes']} divisão(ões)")
    if ops.get("copias"):
        head.append(f"{ops['copias']} take(s) duplicado(s)")
    if ops.get("ordemMudou"):
        head.append("ordem dos takes mudou")
    if ops.get("volume"):
        head.append(f"volume mudado em {ops['volume']} take(s)")
    if ops.get("velocidade"):
        head.append(f"velocidade mudada em {ops['velocidade']} take(s)")
    if ops.get("curva"):
        head.append(f"curva de velocidade em {ops['curva']} take(s)")
    if ops:  # editor que divide, copia e move: a lista inteira é a referência
        parts.append("  edl.ranges é a lista inteira, na ordem nova — monte o edl.json por ela (SKILL.md).")
    vols = [(i, r) for i, r in enumerate(edl.get("ranges") or [], 1) if r.get("volume") is not None]
    if vols:
        parts.append("  volume por take (vai para o edl.json como está; sem `volume` = 100%; o render.py "
                     "aplica no fim e o final.mp4 sai pelo mixar_final.py):")
        for i, r in vols:
            parts.append(f'  · take {i} ({r.get("beat") or r.get("source", "")}): '
                         f'{round(float(r["volume"]) * 100)}%')
    vels = [(i, r) for i, r in enumerate(edl.get("ranges") or [], 1) if r.get("velocidade") is not None]
    if vels:
        parts.append("  velocidade por take (vai para o edl.json como está; sem `velocidade` = 1×; "
                     "o render.py aplica e o tempo de tudo passa pelo tempo.py):")
        for i, r in vels:
            parts.append(f'  · take {i} ({r.get("beat") or r.get("source", "")}): {float(r["velocidade"]):g}×')
    curvas = [(i, r) for i, r in enumerate(edl.get("ranges") or [], 1) if r.get("curva")]
    if curvas:
        parts.append("  curva de velocidade por take (vai para o edl.json como está, sem `velocidade`; "
                     "x = fração da tomada na gravação, y = velocidade; o render.py aplica pelo tempo.py):")
        for i, r in curvas:
            c = r["curva"]
            parts.append(f'  · take {i} ({r.get("beat") or r.get("source", "")}): '
                         f'curva {c.get("nome") or "personalizada"}, {len(c.get("pontos") or [])} pontos')
    if any(k in ed for k in ("inserts", "splitInserts", "splitVideos", "hook", "behind", "wordAccents", "numeros")):
        head.append("inserts/gancho movidos")
    cenas = ed.get("cenas") or []
    if cenas:
        head.append(_plural(len(cenas), "efeito mudado", "efeitos mudados"))
        parts.append("  efeitos (edit-data.json `cenas[ref]`): grave `desligada`, `texto` (centro do bloco no "
                     "quadro 1080x1920; null = o lugar padrão do componente), os textos e, num Fundo, os "
                     "`campos` (`fundo`, `escurecer`, `desfoque` direto no item); `NOVO` = um efeito criado no "
                     "editor, sem `ref`: acrescente em cenas[]. Rode cenas_edit_data.py <edit> (as posições "
                     "dependem dos textos; o efeito novo ganha o recorte) e refaça só a janela de cada um "
                     "(references/cenas.md):")
        # o Fundo novo desligado nunca entrou no vídeo: não há janela para refazer
        janelas = ",".join(f'{c.get("start", 0):g}-{c.get("end", 0):g}' for c in cenas
                           if not (c.get("nova") and c.get("desligada")))
        if janelas:
            parts.append(f"    depois: render_janelas.py <edit> --janelas {janelas} e mixar_final.py "
                         "<edit> --render <remotion>/out/render.mp4")
        for c in cenas:
            onde = f'{c.get("tipo")} [{fmt(c.get("start", 0))} → {fmt(c.get("end", 0))}]'
            if c.get("nova"):
                if c.get("desligada"):
                    parts.append(f"  · NOVO {onde}: desligado no editor, não acrescente")
                else:
                    item = {"tipo": c.get("tipo"), "start": c.get("start"), "end": c.get("end"), **(c.get("campos") or {})}
                    parts.append(f"  · NOVO {onde}: acrescente em cenas[] {json.dumps(item, ensure_ascii=False)}")
                continue
            oque = ["DESLIGAR" if c.get("desligada") else "ligado"]
            t = c.get("texto")
            if t:
                oque.append(f'bloco em x={t.get("x")} y={t.get("y")}')
            for k, v in (c.get("textos") or {}).items():
                oque.append(f'{k}="{" / ".join(v) if isinstance(v, list) else v}"')
            est = c.get("estilo") or {}
            if est:  # fonte (família do catálogo), cor, tamanho (×), contorno (px) e a cor dele
                oque.append("estilo " + ", ".join(f"{k}={v}" for k, v in est.items()))
            campos = c.get("campos") or {}
            if campos:  # o Fundo: a imagem, o véu e o desfoque
                oque.append(", ".join(f"{k}={v}" for k, v in campos.items()))
            parts.append(f'  · #{c.get("ref")} {onde}: ' + "; ".join(oque))
    destaques = ed.get("destaques") or []
    if destaques:
        head.append(_plural(len(destaques), "texto de destaque mudado", "textos de destaque mudados"))
        parts.append("  gancho e números (edit-data.json `hook` e `numeros[ref]`): grave `texto` (centro do "
                     "bloco no quadro 1080x1920), `estilo` e os textos — no gancho `text` (e tire `lines`), no "
                     "número `prefixo`/`valor` (número)/`sufixo`/`rotulo` — e refaça a janela de cada um:")
        for c in destaques:
            alvo = "gancho" if c.get("alvo") == "hook" else f'número #{c.get("ref")}'
            oque = []
            t = c.get("texto")
            if t:
                oque.append(f'bloco em x={t.get("x")} y={t.get("y")}')
            for k, v in (c.get("textos") or {}).items():
                oque.append(f'{k}="{v}"')
            est = c.get("estilo") or {}
            if est:
                oque.append("estilo " + ", ".join(f"{k}={v}" for k, v in est.items()))
            parts.append(f"  · {alvo}: " + "; ".join(oque))
    leg = ed.get("legenda")
    if leg:
        head.append("legenda mudada")
        oque = [f"estilo {', '.join(f'{k}={v}' for k, v in leg['estilo'].items())}" if leg.get("estilo") else "estilo do desenho (sem `estilo`)",
                "ACOMPANHA a pessoa" if leg.get("acompanhar") else "parada"]
        parts.append("  legenda (edit-data.json `captions`): grave `estilo` (null = tire a chave) e `acompanhar`; "
                     "com acompanhar, rode camadas_edit_data.py (ele faz o rastreio do rosto) e renderize: "
                     + "; ".join(oque))
        tempos = leg.get("tempos") or []
        if tempos:  # pedaços arrastados no tempo, na vista Final
            parts.append(f"  legenda: {_plural(len(tempos), 'pedaço levado', 'pedaços levados')} no tempo → "
                         "legenda_tempos.py <edit> (desloca as palavras no captions.json) e renderize:")
            for t in tempos:
                de, para = t.get("deMs", 0) / 1000, t.get("paraMs", 0) / 1000
                parts.append(f"  · palavras {t.get('palavra')}–{t.get('palavra', 0) + t.get('palavras', 1) - 1}: "
                             f"{fmt(de)} → {fmt(para)} ({para - de:+.2f} s)")
    cam = ed.get("camera") or {}
    if cam.get("zooms"):
        mud = [i for i in (cam.get("mudou") or []) if 0 <= i < len(cam["zooms"])]
        head.append(f"zoom mudado em {_plural(len(mud), 'tomada', 'tomadas')}")
        parts.append("  zoom: `camera.zooms` passa a ser a lista inteira, uma por tomada; refaça as tomadas mudadas: "
                     + ", ".join(f"tomada {i + 1} → {round(float(cam['zooms'][i]) * 100)}%" for i in mud))
    if "camadas" in d:
        head.append(f"camadas: {camadas_resumo(d['camadas'])}")
        parts += camadas_linhas(d["camadas"])
        if edl:
            parts.append("  ⚠ O corte mudou no mesmo Salvar: os tempos das camadas são do corte ANTIGO. "
                         "Leve-os para o corte novo antes de montar (references/shortform.md).")
    if "efeitos" in d:
        head.append(f"efeitos: {efeitos_resumo(d['efeitos'])}")
        parts += efeitos_linhas(d["efeitos"])
        if edl:
            parts.append("  ⚠ O corte mudou no mesmo Salvar: os tempos dos efeitos são do corte ANTIGO. "
                         "Leve-os para o corte novo antes do render (references/shortform.md).")
    if "velocidade" in d:
        head.append(f"velocidade: {velocidade_resumo(d['velocidade'])}")
        parts += velocidade_linhas(d["velocidade"])
        if edl:
            parts.append("  ⚠ O corte mudou no mesmo Salvar: os trechos são do final ANTIGO. Refaça o final, "
                         "leve os trechos para ele (grave a duração nova) e só então acelere.")
    lugares = (d.get("montagem") or {}).get("lugares") or []
    formato = (d.get("montagem") or {}).get("formato")
    if formato:
        head.append(f"montagem: formato {NOMES_FORMATO.get(formato, formato)}")
    if lugares:
        head.append(f"montagem: {_plural(len(lugares), 'lugar mudado', 'lugares mudados')}")
    if lugares or formato:
        parts += montagem_linhas(lugares, bool(ops), formato)
    usar = (d.get("montagem") or {}).get("usar")
    if isinstance(usar, dict):
        head.append(f"MONTAGEM NOVA com o modelo {usar.get('modelo')}")
        parts += usar_linhas(usar)
    if ("camadas" in d or "efeitos" in d) and _eh_montagem(p.parent):
        # numa montagem, o vídeo com texto, imagem ou efeito sai do montagem.py (ele monta o Remotion dela)
        parts.append("  montagem na batida: " + (
            "o montagem.py aplicar acima já leva estas camadas e efeitos (o servidor gravou os dois)."
            if lugares or formato else
            "as camadas e os efeitos já estão gravados; em vez dos passos acima, rode montagem.py render <edit> "
            "(refaz o vídeo, pelo Remotion quando há texto, imagem ou efeito, e confere a batida)."))
    if "melhorar" in d:
        head.append(f"melhorar voz: {melhorar_resumo(d['melhorar'])}")
        parts += melhorar_linhas(d["melhorar"], bool(edl))
    elif edl and voz_aplicada(p.parent):
        parts.append("  ⚠ Melhorar voz está aplicado: o corte refeito volta com o som original. Depois do "
                     "render.py, rode melhorar_voz.py aplicar <edit> (sem números: a última escolha).")
    if not head:
        head.append("ajustes salvos")

    out = [f"AJUSTES DO PREVIEW ({d.get('savedAt', '')}) — {', '.join(head)}. Aplique-os."]
    out += parts
    return "\n".join(out)


def _eh_montagem(edit: Path) -> bool:
    try:
        return "montagem" in json.loads((edit / "edl.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False


NOMES_FORMATO = {"9:16": "em pé (9:16)", "16:9": "deitado (16:9)", "1:1": "quadrado (1:1)"}


def montagem_linhas(lugares: list[dict], tomadas_mudaram: bool, formato: str | None = None) -> list[str]:
    """Os lugares da montagem na batida que o editor mudou (outra mídia, outro trecho do clipe) e o
    formato novo do vídeo."""
    refaz = "refaz a montagem inteira no formato novo" if formato else "refaz só estes lugares"
    linhas = [("  montagem na batida: " + ("primeiro grave no edl.json o volume das tomadas; depois " if tomadas_mudaram else "")
               + f"rode montagem.py aplicar <edit> (lê este Salvar, {refaz}, renderiza e confere):")]
    if formato:
        linhas.append(f"  · formato: {NOMES_FORMATO.get(formato, formato)}; os textos vão para o mesmo lugar do "
                      "quadro novo")
    for x in lugares:
        oque = []
        if x.get("midia"):
            oque.append(f"troca para {Path(str(x['midia'])).name}")
        if x.get("de") is not None:
            oque.append(f"trecho a partir de {float(x['de']):g} s")
        if "enquadre" in x:
            e = x["enquadre"]
            oque.append("enquadramento automático" if not e else
                        f"enquadrado à mão: {float(e['escala']):g}× de caber inteira, centro em "
                        f"{float(e['x']) * 100:.0f}% × {float(e['y']) * 100:.0f}% da tela")
        linhas.append(f"  · lugar {x.get('vaga')}: " + "; ".join(oque))
    return linhas


def usar_linhas(usar: dict) -> list[str]:
    """O Usar do painel Modelos de montagem: a montagem nova que o editor pediu."""
    midias = [Path(str(x)).name for x in usar.get("midias") or []]
    return ["  montagem na batida, NOVA: rode montagem.py montar <edit> (monta com o modelo, a música e as "
            "mídias abaixo, renderiza e confere; o projeto inteiro é refeito):",
            f"  · modelo: {usar.get('modelo')} (montagens.py mostrar {usar.get('modelo')})",
            f"  · música: {Path(str(usar.get('musica'))).name}",
            f"  · {_plural(len(midias), 'foto ou clipe', 'fotos e clipes')}, na ordem: "
            + ", ".join(midias[:12]) + (" …" if len(midias) > 12 else "")] + (
        [f"  · formato: {NOMES_FORMATO.get(usar['formato'], usar['formato'])}"] if usar.get("formato") else [])


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def camadas_resumo(c: dict) -> str:
    fx = c.get("faixas") or []
    n_img = sum(len(f.get("itens") or []) for f in fx if f.get("tipo") == "imagem")
    n_aud = sum(len(f.get("itens") or []) for f in fx if f.get("tipo") == "audio")
    n_txt = sum(len(f.get("itens") or []) for f in fx if f.get("tipo") == "texto")
    if not n_img and not n_aud and not n_txt:
        return "nenhuma"
    return ", ".join(x for x in (n_img and _plural(n_img, "imagem", "imagens"),
                                 n_aud and _plural(n_aud, "áudio", "áudios"),
                                 n_txt and _plural(n_txt, "texto", "textos")) if x)


def camadas_linhas(c: dict) -> list[str]:
    """Uma linha por item, no relógio do cut.mp4; o que está silenciado ou escondido
    aparece para o agente saber que fica FORA do vídeo final."""
    out = ["  camadas.json (gravado pelo editor), tempos do cut.mp4:"]
    for f in c.get("faixas") or []:
        for it in f.get("itens") or []:
            ini, dur = float(it.get("inicio", 0)), float(it.get("duracao", 0))
            nome = str(it.get("arquivo", "")).removeprefix("midia/")
            if f.get("tipo") == "audio":
                bits = [f"volume {round(float(it.get('volume', 1)) * 100)}%"]
                if it.get("corte"):
                    bits.append(f"a partir de {fmt(it['corte'])} do arquivo")
                if it.get("melhorar"):
                    bits.append("melhorar")
                if f.get("mudo"):
                    bits.append("silenciada: fica fora")
                rotulo = f'trilha "{it["trilha"]}" (biblioteca)' if it.get("trilha") else f'áudio "{nome}"'
                out.append(f'  · {rotulo} de {fmt(ini)} a {fmt(ini + dur)}, {", ".join(bits)}')
            elif f.get("tipo") == "texto":
                bits = []
                if it.get("atras"):
                    bits.append("atrás da pessoa")
                if it.get("acompanhar"):
                    bits.append("acompanha a pessoa")
                if it.get("curva"):
                    bits.append(f"curva {float(it['curva']):g}")
                if f.get("oculto"):
                    bits.append("escondido: fica fora")
                linha = " / ".join(str(it.get("texto", "")).split("\n"))
                out.append(f'  · texto "{linha}" de {fmt(ini)} a {fmt(ini + dur)}' + (f", {', '.join(bits)}" if bits else ""))
            else:
                fora = ", escondida: fica fora" if f.get("oculto") else ""
                out.append(f'  · imagem "{nome}" de {fmt(ini)} a {fmt(ini + dur)}{fora}')
    if (c.get("video") or {}).get("mudo"):
        out.append("  · som do vídeo desligado: a voz do corte fica fora do vídeo final")
    out.append("  Imagens e textos → camadas_edit_data.py (inserts[] e textos[]; ele faz o recorte da "
               "pessoa e o rastreio do rosto que faltarem) e renderizar; som → mixar_final.py "
               "(references/shortform.md, \"Camadas\").")
    return out


def efeitos_resumo(e: dict) -> str:
    itens = e.get("itens") or []
    n_f = sum(1 for it in itens if it.get("tipo") == "filtro")
    n_t = sum(1 for it in itens if it.get("tipo") == "transicao")
    n_a = sum(1 for it in itens if it.get("tipo") == "ajuste")
    if not n_f and not n_t and not n_a:
        return "nenhum"
    return ", ".join(x for x in (n_f and _plural(n_f, "filtro", "filtros"),
                                 n_t and _plural(n_t, "transição", "transições"),
                                 n_a and _plural(n_a, "ajuste", "ajustes")) if x)


def _aparencia(it: dict) -> tuple:
    if it.get("tipo") == "ajuste":
        return tuple(sorted((it.get("ajustes") or {}).items()))
    return it.get("pacote"), it.get("intensidade" if it.get("tipo") == "filtro" else "duracao")


def _fim(it: dict) -> float:
    return float(it.get("inicio", 0)) + float(it.get("duracao", 0))


def _linha_efeito(g: list[dict]) -> str:
    it, n = g[0], len(g)
    if it.get("tipo") == "transicao":
        cortes = [fmt(float(x.get("corte", 0))) for x in g]
        dur = f'{float(it.get("duracao", 0)):.1f} s'
        if n == 1:
            return f'  · transição "{it.get("pacote")}" no corte de {cortes[0]} ({dur})'
        onde = ", ".join(cortes) if n <= 4 else f"de {cortes[0]} a {cortes[-1]}"
        return f'  · transição "{it.get("pacote")}" ({dur}) em {n} cortes: {onde}'
    de, ate = fmt(float(it.get("inicio", 0))), fmt(_fim(g[-1]))
    seguidos = f" ({n} trechos seguidos)" if n > 1 else ""
    if it.get("tipo") == "ajuste":
        vals = ", ".join(f"{k} {int(v):+d}" for k, v in (it.get("ajustes") or {}).items())
        return f"  · ajuste de {de} a {ate}: {vals}{seguidos}"
    forca = f", intensidade {round(float(it['intensidade']) * 100)}%" if it.get("intensidade") is not None else ""
    return f'  · filtro "{it.get("pacote")}" de {de} a {ate}{forca}{seguidos}'


def efeitos_linhas(e: dict) -> list[str]:
    """Um efeito por linha, mas o igual e seguido numa linha só: um modelo de estilo põe o mesmo
    filtro e o mesmo ajuste em cada tomada e a mesma transição em cada corte (62 linhas num
    vídeo de 21 tomadas), e o agente não precisa delas, porque o efeitos.json já está gravado."""
    out = ["  efeitos.json (gravado pelo editor), tempos do cut.mp4:"]
    itens = e.get("itens") or []
    for tipo in ("filtro", "ajuste", "transicao"):
        chave = "corte" if tipo == "transicao" else "inicio"
        grupos: list[list[dict]] = []
        for it in sorted((x for x in itens if x.get("tipo") == tipo), key=lambda x: float(x.get(chave, 0))):
            g = grupos[-1] if grupos else None
            # filtro e ajuste só juntam encostados (a sobra do arredondamento é de até 1 ms)
            if g and _aparencia(g[-1]) == _aparencia(it) and (
                    tipo == "transicao" or abs(float(it.get("inicio", 0)) - _fim(g[-1])) <= 2e-3):
                g.append(it)
            else:
                grupos.append([it])
        out += [_linha_efeito(g) for g in grupos]
    out.append("  Efeitos → efeitos_render.py antes do render final (references/shortform.md, \"Efeitos\").")
    return out


def _x(f: float) -> str:
    return f"{float(f):g}".replace(".", ",") + "×"


def melhorar_resumo(m: dict) -> str:
    return "tirar (o som original volta)" if m.get("desligar") else f"Voz {m['voz']}%, Fundo {m['fundo']}%"


def melhorar_linhas(m: dict, corte_mudou: bool) -> list[str]:
    """Melhorar voz, a voz do próprio vídeo (melhorar_voz.py; references/shortform.md, "Melhorar voz")."""
    depois = " Depois do render.py." if corte_mudou else ""
    if m.get("desligar"):
        return [f"  Melhorar voz: tirar → melhorar_voz.py restaurar <edit> (o som original volta ao cut.mp4, "
                f"byte a byte).{depois} Com vídeo final, refaça o som dele (mixar_final.py)."]
    return [f"  Melhorar voz: Voz {m['voz']}% (0 = limpa, 100 = estúdio) e Fundo {m['fundo']}% (o ambiente "
            f"original) → melhorar_voz.py aplicar <edit> --voz {m['voz']} --fundo {m['fundo']}: troca só o som "
            f"do cut.mp4 e prepara antes se o corte mudou.{depois} Com vídeo final, refaça o som dele "
            "(mixar_final.py)."]


def voz_aplicada(edit: Path) -> bool:
    """O cut.mp4 de agora tem a voz melhorada? (o estado do melhorar_voz.py, sem rodar nada)"""
    try:
        e = json.loads((edit / ".melhorar" / "estado.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(isinstance(e, dict) and (e.get("aplicado") or {}).get("hash"))


def velocidade_resumo(v: dict) -> str:
    tr = v.get("trechos") or []
    return _plural(len(tr), "trecho", "trechos") if tr else "tudo na velocidade normal"


def velocidade_linhas(v: dict) -> list[str]:
    """Os trechos do vídeo final que tocam em outro ritmo (tudo junto: imagem, som, legenda)."""
    tr = v.get("trechos") or []
    if not tr:
        return ["  velocidade.json (gravado pelo editor): sem trechos. Rode velocidade_final.py <edit>: "
                "ele tira a entrega acelerada e o final.mp4 volta a ser a entrega."]
    out = ["  velocidade.json (gravado pelo editor), tempos do final.mp4:"]
    for t in tr:
        ini, fim, f = float(t["inicio"]), float(t["fim"]), float(t["fator"])
        out.append(f"  · de {fmt(ini)} a {fmt(fim)} a {_x(f)} ({fim - ini:.2f} s viram {(fim - ini) / f:.2f} s)")
    out.append("  Velocidade → velocidade_final.py <edit> (se o final for refeito neste pedido, depois do "
               "mixar_final.py): ele faz o final-entrega.mp4 e grava `entregaVideo` no state.json "
               "(references/shortform.md, \"Speed of the finished video\").")
    return out


def _sem_mudanca(p: Path, d: dict) -> bool:
    """Uma troca de Estilo que repete o que o vídeo já tem (o Aplicar sem mudar nada, ou um
    modelo igual ao vídeo): refazer a Fase 2 custaria minutos e daria o mesmo vídeo."""
    if not d.get("rerender"):
        return False  # a 1ª escolha sempre monta a Fase 2
    try:
        st = json.loads((p.parent / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    atual = st.get("style") or {}
    if any((atual.get(k) or None) != (d.get(k) or None) for k in ("edit", "headline", "captions", "elements",
                                                                     "captionPositions")):
        return False
    if str(atual.get("accent") or "").lower() != str(d.get("accent") or "").lower() or \
            (atual.get("note") or "").strip() != (d.get("note") or "").strip():
        return False
    leg = d.get("legenda")
    if leg:  # a legenda fina do modelo mora no edit-data
        try:
            cap = json.loads((p.parent / st["editData"]).read_text(encoding="utf-8")).get("captions") or {}
        except (KeyError, TypeError, OSError, json.JSONDecodeError):
            return False
        if (cap.get("estilo") or None) != (leg.get("estilo") or None) or \
                bool(cap.get("acompanhar")) != bool(leg.get("acompanhar")):
            return False
    return True


def style_digest(p: Path) -> str:
    """The gate choice: what Fase 2 should be built as."""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_style.json ilegível ({e.__class__.__name__}) — peça ao usuário para salvar de novo"

    els = d.get("elementNames") or [
        k for k, v in (d.get("elements") or {}).items() if v
    ]
    if _sem_mudanca(p, d):
        head = ("ESTILO APLICADO SEM MUDANÇA NO PREVIEW ({}): é o Estilo que o vídeo já tem, nada a "
                "refazer na Fase 2; apague o preview_style.json. O mesmo Estilo:")
    elif d.get("rerender"):
        head = "TROCA DE ESTILO NO PREVIEW ({}) — REFAÇA a Fase 2 assim:"
    else:
        head = "ESTILO ESCOLHIDO NO PREVIEW ({}) — monte a Fase 2 assim:"
    head = head.format(d.get("savedAt", ""))
    out = [
        head,
        f'  · tipo de edição: {d.get("editName") or d.get("edit")}',
        f'  · headline: {d.get("headlineName") or d.get("headline")}',
        f'  · legenda: {d.get("captionsName") or d.get("captions")}',
    ]
    # modelo de estilo (aba Modelos): o visual inteiro de outro vídeo. Filtro, transição, ajuste
    # e trilha dele o mesmo Aplicar já gravou no efeitos.json e no camadas.json; o que ele leva de
    # fato está no arquivo do modelo
    modelo = d.get("modelo") or {}
    if modelo.get("nome"):
        m = md.obter(str(modelo.get("id") or "")) or {}
        leva = [nome for k, nome in (("filtro", "filtro"), ("transicao", "transição"), ("ajuste", "ajuste"),
                                     ("trilha", "trilha")) if m.get(k)]
        if not m:
            extra = "filtro, transição, ajuste e trilha dele, se tiver, já estão no efeitos.json e no camadas.json"
        elif leva:
            extra = f'{", ".join(leva)} dele já estão no efeitos.json e no camadas.json'
        else:
            extra = "ele não tem filtro, transição, ajuste nem trilha: é só o Estilo"
        out.insert(1, f'  · MODELO "{modelo["nome"]}" aplicado (modelos.py mostrar {modelo.get("id", "?")}); {extra}')
    leg = (d.get("legenda") or {}).get("estilo") or {}
    if leg:
        bits = [f"{k}={v}" for k, v in leg.items()]
        acomp = " · acompanhar" if (d.get("legenda") or {}).get("acompanhar") else ""
        out.append(f'  · legenda fina do modelo: {" ".join(bits)}{acomp} → captions do edit-data '
                   '(como o editData.legenda de um Salvar)')
    # frases arrastadas no celular: o lugar delas vale mais que o do estilo e o da emenda
    pos = d.get("captionPositions") or {}
    n = len(pos.get("phrases") or [])
    if pos.get("all") or n:
        bits = (["todas as frases num lugar escolhido"] if pos.get("all") else []) + \
               ([f"{n} frase(s) com lugar próprio"] if n else [])
        out.append(f'  · posição da legenda: {", ".join(bits)} → caption_positions.py grava '
                   'captions.positions (references/shortform.md)')
    # Only worth reporting when the chosen styles actually paint an accent —
    # naming a colour that nothing uses reads as an instruction to go find a
    # place for it.
    accent = d.get("accent")
    if accent:
        if d.get("accentUsed"):
            name = d.get("accentName") or accent
            label = f"{name} ({accent})" if name.lower() != str(accent).lower() else accent
            out.append(f"  · cor de destaque: {label}")
        else:
            out.append("  · cor de destaque: não se aplica (os estilos escolhidos não usam destaque)")
    out.append(f'  · elementos: {", ".join(els) if els else "nenhum"}')
    # everything NOT chosen is an instruction too — it is what must stay out
    off = [k for k, v in (d.get("elements") or {}).items() if not v]
    if off:
        out.append(f'  · fora: {", ".join(off)}')
    if (d.get("note") or "").strip():
        out.append(f'  · observação do usuário: {d["note"].strip()}')
    return "\n".join(out)


def upload_digest(p: Path) -> str:
    """Vídeos que chegaram pelo botão Enviar do editor (celular ou PC)."""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_upload.json ilegível ({e.__class__.__name__}) — confira a pasta dos vídeos"
    files = d.get("files") or []
    out = [f"VÍDEO ENVIADO PELO EDITOR ({d.get('savedAt', '')}) — "
           f"{len(files)} arquivo(s) em {d.get('folder', '')}:"]
    for f in files:
        out.append(f"  · {f.get('file')} ({(f.get('size') or 0) / 1_000_000:.0f} MB)")
    out.append("  É material novo desta edição: sem corte ainda, é a fonte — siga a Fase 1. "
               "Com corte pronto, pergunte o que fazer com ele. Depois apague preview_upload.json.")
    return "\n".join(out)


def troca_digest(edit: Path) -> str:
    """O usuário abriu outro projeto no editor (tela Projetos), no PC ou no celular."""
    try:
        st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        st = {}
    out = [f"O EDITOR ABRIU OUTRO PROJETO: {st.get('project') or edit.parent.name} — {edit}"]
    if st.get("novo") and not (edit / "edl.json").exists():
        out.append("  · projeto novo, criado pelo editor, ainda sem corte: os vídeos chegam pelo Enviar "
                   "(preview_upload.json); com eles, siga a Fase 1 nessa pasta.")
    else:
        out.append(f"  · fase {st.get('phase')}: {st.get('message') or ''}".rstrip())
    pend = [n for n in ("pronto.json", "preview_style.json", "preview_upload.json", "preview_edits.json")
            if (edit / n).exists()]
    if pend:
        out.append(f"  · pendente lá: {', '.join(pend)}")
    out.append(f"  Daqui em diante o trabalho é nessa pasta: ligue o vigia nela ({edit}).")
    return "\n".join(out)


def _aberto() -> str | None:
    ab = pj.aberto()
    return ab.get("edit") if ab else None


def fmt(t: float) -> str:
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:05.2f}"


def vigiar(pasta: Path) -> dict:
    """O que acorda o agente nesta pasta: o Pronto, a escolha do Estilo e o vídeo enviado."""
    return {
        pasta / "pronto.json": pronto_digest,
        pasta / "preview_style.json": style_digest,
        pasta / "preview_upload.json": upload_digest,
    }


def main() -> int:
    uma_vez = "--uma-vez" in sys.argv[1:]  # sai no primeiro aviso: tarefa em segundo plano, sem prazo
    args = [a for a in sys.argv[1:] if a != "--uma-vez"]
    root = Path(args[0] if args else ".").expanduser().resolve()

    watched = vigiar(root)
    # só a TROCA conta: o projeto que já estava aberto quando o vigia ligou não é aviso
    # (pode ser de outra sessão, com o editor fechado)
    aberto_antes = _aberto()
    # a file already sitting there at startup means it is pending — say so once
    last: dict[Path, float | None] = {}
    pendente = False
    for target, fn in watched.items():
        last[target] = target.stat().st_mtime if target.exists() else None
        if last[target] is not None:
            print(fn(target), flush=True)
            pendente = True
    if uma_vez and pendente:
        return 0

    while True:
        avisou = False
        aberto = _aberto()
        if aberto and aberto != aberto_antes:
            aberto_antes = aberto
            novo = Path(aberto).resolve()
            if novo != root:
                print(troca_digest(novo), flush=True)
                if uma_vez:
                    return 0
                # Monitor: passa a vigiar a pasta nova; o que está pendente lá já foi dito
                root, watched = novo, vigiar(novo)
                last = {t: (t.stat().st_mtime if t.exists() else None) for t in watched}
        for target, fn in watched.items():
            try:
                cur = target.stat().st_mtime if target.exists() else None
            except OSError:
                cur = None
            if cur is not None and cur != last[target]:
                last[target] = cur
                time.sleep(0.15)  # let the atomic replace settle before reading
                print(fn(target), flush=True)
                avisou = True
            elif cur is None:
                last[target] = None  # applied and deleted — re-arm for the next save
        if uma_vez and avisou:
            return 0
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
