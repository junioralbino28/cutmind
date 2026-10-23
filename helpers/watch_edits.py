#!/usr/bin/env python3
"""Emit one event per save from the preview UI.

Three files, all written by the UI and none able to reach the chat on its own:
  - preview_edits.json — timeline adjustments and correction markers
  - preview_style.json — the Fase 1 → Fase 2 gate: editing style, caption style,
    edit elements
  - preview_upload.json — vídeos que o usuário mandou pelo botão Enviar (o
    servidor grava o arquivo na pasta dos vídeos e lista aqui)

Run this under the Monitor tool so every save notifies the session automatically:

    Monitor(command="python3 <skill>/helpers/watch_edits.py '<edit>'",
            description="marcações do preview", persistent=True)

Each stdout line is one notification. Stays quiet while nothing changes.

Where the Monitor expires (Claude Code 2.1.309 caps it at 30 min and has no `persistent`),
run it with `--uma-vez` as a background task instead (Bash `run_in_background`): it waits
as long as the session lives, prints the first save (or what is already pending) and exits,
which notifies the session. Apply it, delete the file, and start it again.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def digest(p: Path) -> str:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_edits.json ilegível ({e.__class__.__name__}) — peça ao usuário para salvar de novo"

    parts: list[str] = []
    notes = d.get("notes") or []
    for i, n in enumerate(notes, 1):
        start, end = n.get("start", 0), n.get("end", 0)
        fase = n.get("phase", 1)
        if n.get("geral"):  # a caixa "O que você quer mudar?": pedido sem trecho, a agulha só situa
            parts.append(f'  {i}. PEDIDO (agulha em {fmt(start)}, fase {fase}) {n.get("text", "").strip()}')
        else:
            parts.append(f'  {i}. [{fmt(start)} → {fmt(end)}] (fase {fase}) {n.get("text", "").strip()}')

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
                     "quadro 1080x1920; null = o lugar padrão do componente) e os textos, e refaça só a "
                     "janela de cada um (references/shortform.md):")
        for c in cenas:
            oque = ["DESLIGAR" if c.get("desligada") else "ligado"]
            t = c.get("texto")
            if t:
                oque.append(f'bloco em x={t.get("x")} y={t.get("y")}')
            for k, v in (c.get("textos") or {}).items():
                oque.append(f'{k}="{" / ".join(v) if isinstance(v, list) else v}"')
            est = c.get("estilo") or {}
            if est:  # fonte (família do catálogo), cor, tamanho (×), contorno (px) e a cor dele
                oque.append("estilo " + ", ".join(f"{k}={v}" for k, v in est.items()))
            parts.append(f'  · #{c.get("ref")} {c.get("tipo")} [{fmt(c.get("start", 0))} → {fmt(c.get("end", 0))}]: '
                         + "; ".join(oque))
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
    if not head:
        head.append("ajustes salvos")

    out = [f"AJUSTES DO PREVIEW ({d.get('savedAt', '')}) — {', '.join(head)}. Aplique-os."]
    out += parts
    return "\n".join(out)


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


def efeitos_linhas(e: dict) -> list[str]:
    out = ["  efeitos.json (gravado pelo editor), tempos do cut.mp4:"]
    for it in e.get("itens") or []:
        if it.get("tipo") == "filtro":
            ini, dur = float(it.get("inicio", 0)), float(it.get("duracao", 0))
            forca = (f", intensidade {round(float(it['intensidade']) * 100)}%"
                     if it.get("intensidade") is not None else "")
            out.append(f'  · filtro "{it.get("pacote")}" de {fmt(ini)} a {fmt(ini + dur)}{forca}')
        elif it.get("tipo") == "ajuste":
            ini, dur = float(it.get("inicio", 0)), float(it.get("duracao", 0))
            vals = ", ".join(f"{k} {int(v):+d}" for k, v in (it.get("ajustes") or {}).items())
            out.append(f"  · ajuste de {fmt(ini)} a {fmt(ini + dur)}: {vals}")
        else:
            out.append(f'  · transição "{it.get("pacote")}" no corte de {fmt(float(it.get("corte", 0)))} '
                       f'({float(it.get("duracao", 0)):.1f} s)')
    out.append("  Efeitos → efeitos_render.py antes do render final (references/shortform.md, \"Efeitos\").")
    return out


def style_digest(p: Path) -> str:
    """The gate choice: what Fase 2 should be built as."""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_style.json ilegível ({e.__class__.__name__}) — peça ao usuário para salvar de novo"

    els = d.get("elementNames") or [
        k for k, v in (d.get("elements") or {}).items() if v
    ]
    head = (
        "TROCA DE ESTILO NO PREVIEW ({}) — REFAÇA a Fase 2 assim:"
        if d.get("rerender")
        else "ESTILO ESCOLHIDO NO PREVIEW ({}) — monte a Fase 2 assim:"
    ).format(d.get("savedAt", ""))
    out = [
        head,
        f'  · tipo de edição: {d.get("editName") or d.get("edit")}',
        f'  · headline: {d.get("headlineName") or d.get("headline")}',
        f'  · legenda: {d.get("captionsName") or d.get("captions")}',
    ]
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


def fmt(t: float) -> str:
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:05.2f}"


def main() -> int:
    uma_vez = "--uma-vez" in sys.argv[1:]  # sai no primeiro aviso: tarefa em segundo plano, sem prazo
    args = [a for a in sys.argv[1:] if a != "--uma-vez"]
    root = Path(args[0] if args else ".").expanduser().resolve()
    watched = {
        root / "preview_edits.json": digest,
        root / "preview_style.json": style_digest,
        root / "preview_upload.json": upload_digest,
    }
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
