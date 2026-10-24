"""O karaokê do modelo do Remotion tem tamanho mesmo sem `captions.fontSize` no edit-data.

Um edit-data montado para uma legenda estática (serifada, simples, clássica) não traz
`fontSize`: elas se dimensionam sozinhas. Trocar para o karaokê depois (um modelo de estilo
faz isso) multiplicava `undefined` e a legenda saía no tamanho do navegador, ~16 px num quadro
de 1080 (medido em 23/10). O padrão do código tem de ser o mesmo do edit-data do modelo.
"""
import json
import re
from pathlib import Path

SHORT = Path(__file__).resolve().parents[1] / "assets" / "shortform"


def test_karaoke_sem_fontsize_usa_o_padrao_do_modelo():
    main = (SHORT / "src" / "Main.tsx").read_text(encoding="utf-8")
    m = re.search(r"const K_BASE = Number\(D\.captions\.fontSize\) > 0 \? Number\(D\.captions\.fontSize\) : (\d+);", main)
    assert m, "o padrão do tamanho do karaokê (K_BASE) sumiu do Main.tsx"
    assert "const K_SIZE = K_BASE *" in main
    padrao = json.loads((SHORT / "public" / "edit-data.json").read_text(encoding="utf-8"))["captions"]["fontSize"]
    assert int(m.group(1)) == padrao
