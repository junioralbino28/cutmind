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
        parts.append(f'  {i}. [{fmt(start)} → {fmt(end)}] (fase {fase}) {n.get("text", "").strip()}')

    edl = d.get("edl") or {}
    n_ch = len(edl.get("changes") or [])
    n_rm = len(edl.get("removed") or [])
    ops = edl.get("ops") or {}
    ed = d.get("editData") or {}

    head = []
    if notes:
        head.append(f"{len(notes)} marcação(ões)")
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
    if ops:  # editor que divide, copia e move: a lista inteira é a referência
        parts.append("  edl.ranges é a lista inteira, na ordem nova — monte o edl.json por ela (SKILL.md).")
    if ed:
        head.append("inserts/gancho movidos")
    if "camadas" in d:
        head.append(f"camadas: {camadas_resumo(d['camadas'])}")
        parts += camadas_linhas(d["camadas"])
        if edl:
            parts.append("  ⚠ O corte mudou no mesmo Salvar: os tempos das camadas são do corte ANTIGO. "
                         "Leve-os para o corte novo antes de montar (references/shortform.md).")
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
    if not n_img and not n_aud:
        return "nenhuma"
    return ", ".join(x for x in (n_img and _plural(n_img, "imagem", "imagens"),
                                 n_aud and _plural(n_aud, "áudio", "áudios")) if x)


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
            else:
                fora = ", escondida: fica fora" if f.get("oculto") else ""
                out.append(f'  · imagem "{nome}" de {fmt(ini)} a {fmt(ini + dur)}{fora}')
    if (c.get("video") or {}).get("mudo"):
        out.append("  · som do vídeo desligado: a voz do corte fica fora do vídeo final")
    out.append("  Imagens → camadas_edit_data.py (inserts[]); som → mixar_final.py "
               "(references/shortform.md, \"Camadas\").")
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
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()
    watched = {
        root / "preview_edits.json": digest,
        root / "preview_style.json": style_digest,
        root / "preview_upload.json": upload_digest,
    }
    # a file already sitting there at startup means it is pending — say so once
    last: dict[Path, float | None] = {}
    for target, fn in watched.items():
        last[target] = target.stat().st_mtime if target.exists() else None
        if last[target] is not None:
            print(fn(target), flush=True)

    while True:
        for target, fn in watched.items():
            try:
                cur = target.stat().st_mtime if target.exists() else None
            except OSError:
                cur = None
            if cur is not None and cur != last[target]:
                last[target] = cur
                time.sleep(0.15)  # let the atomic replace settle before reading
                print(fn(target), flush=True)
            elif cur is None:
                last[target] = None  # applied and deleted — re-arm for the next save
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
