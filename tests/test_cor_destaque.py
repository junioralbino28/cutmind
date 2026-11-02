"""A cor de destaque do painel Estilo chega ao vídeo: nenhum laranja fixo no template.

Edição real de 01/11: legenda Empilhado com destaque azul saiu laranja no render, com a prévia do painel em azul. O mesmo
defeito estava nos estilos `realce` e `misto` do gancho, que nem liam `hook.accent`.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "assets" / "shortform" / "src"
LARANJA = re.compile(r"#ff5200", re.I)
COMENTARIO = re.compile(r"^\s*(//|\*|/\*)")


def _usos():
    out = []
    for p in sorted(SRC.rglob("*.ts*")):
        for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if LARANJA.search(linha) and not COMENTARIO.match(linha):
                out.append((p.relative_to(SRC).as_posix(), n, linha.strip()))
    return out


def test_o_laranja_so_existe_como_reserva_depois_da_cor_escolhida():
    usos = _usos()
    assert len(usos) >= 4, usos  # o detector tem de achar os lugares que conhecemos
    for arq, n, linha in usos:
        assert re.search(r"\baccent\s*\|\|\s*'#ff5200'", linha), f"{arq}:{n} pinta laranja fixo: {linha}"


def test_o_detector_pega_o_laranja_fixo():
    assert not re.search(r"\baccent\s*\|\|\s*'#ff5200'", "const ORANGE = '#ff5200';")
    assert not re.search(r"\baccent\s*\|\|\s*'#ff5200'", "background: E.cor || '#ff5200',")


def test_quem_pinta_o_destaque_usa_a_cor_escolhida():
    empilhado = (SRC / "StackedCaptions.tsx").read_text(encoding="utf-8")
    assert "color: ACCENT" in empilhado and "ORANGE" not in empilhado
    main = (SRC / "Main.tsx").read_text(encoding="utf-8")
    assert main.count("E.cor || H.accent ||") == 2  # o bloco do realce e a 2ª linha do misto


def test_o_editor_espelha_a_mesma_cor():
    js = (RAIZ / "assets" / "preview" / "celular.js").read_text(encoding="utf-8")
    assert "cor: () => corDestaque()" in js  # parede
    assert "['misto', 'realce'].includes(c.style) ? corDestaque()" in js
