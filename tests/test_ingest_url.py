"""Baixar por link (ingest_url.py) para uma pasta com acento. O yt-dlp é outro processo Python: no Windows, com a
saída redirecionada, ele escreve no código de página do sistema, e o `-X utf8` do helper não passa para ele. Lido
como UTF-8, o caminho quebrava no "Ç" de "EDIÇÃO" (o vídeo baixava e o script caía no fim, achado em 28/10)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import ingest_url as iu  # noqa: E402

# faz o papel do yt-dlp: imprime o caminho do arquivo que "baixou", na codificação que o próprio processo escolher
FALSO = ("import sys; from pathlib import Path\n"
         "a = sys.argv[1:]\n"
         "print(Path(a[a.index('-o') + 1]).parent / 'Edicao_de_teste.mp4')\n")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="precisa do ffmpeg")
def test_pasta_com_acento_nao_derruba_o_fim_do_download(tmp_path, monkeypatch, capsys):
    destino = tmp_path / "EDIÇÃO DE VIDEOS"
    destino.mkdir()
    video = destino / "Edicao_de_teste.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.5", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(video)], check=True)
    (destino / "Edicao_de_teste.info.json").write_bytes(json.dumps(
        {"title": "Edição de teste", "uploader": "Canal", "webpage_url": "https://exemplo.invalid/v"}).encode("utf-8"))
    for var in ("PYTHONUTF8", "PYTHONIOENCODING"):       # como no computador de quem usa
        monkeypatch.delenv(var, raising=False)
    de_verdade = subprocess.run

    def run(cmd, *args, **kw):
        if cmd and cmd[0] == "yt-dlp":
            cmd = [sys.executable, "-c", FALSO, *cmd[1:]]
        return de_verdade(cmd, *args, **kw)

    monkeypatch.setattr(iu.subprocess, "run", run)
    monkeypatch.setattr(iu.shutil, "which", lambda nome: nome)
    monkeypatch.setattr(sys, "argv", ["ingest_url.py", "https://exemplo.invalid/v", "--dest", str(destino)])
    iu.main()
    resumo = json.loads(capsys.readouterr().out)
    assert resumo["path"] == str(video) and resumo["title"] == "Edição de teste"
    assert resumo["width"] == 64 and resumo["duration_s"] > 0
