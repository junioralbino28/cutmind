<h1><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/preview/cutmind-logo-white.png">
  <img src="assets/preview/cutmind-logo.png" alt="CutMind" height="44">
</picture></h1>

Edição de vídeo por conversa, no Claude Code e no Codex. Você coloca o vídeo
bruto numa pasta, abre o agente ali e pede a edição: ele transcreve, escolhe as
melhores tomadas, corta pela fala, legenda, anima e entrega o arquivo final.

Vertical (Reels, TikTok, Shorts) e horizontal (YouTube). A transcrição roda na
sua máquina.

> Em construção.

## Editar pelo celular

O mesmo editor abre no navegador do celular, no jeito do CapCut: linha do tempo
com o dedo, estilo de legenda visto sobre o seu próprio vídeo, envio de vídeo da
galeria e baixar o final. Peça ao agente "abre o editor no celular" e escaneie o
QR que aparece no botão **Abrir no celular** do editor do computador. Pela rede,
só entra quem abriu pelo link ou QR, que levam um código deste computador.

## Instalar

Peça ao seu agente (Claude Code ou Codex): **"instala o CutMind pra mim:
https://github.com/junioralbino28/cutmind"**. Ele roda o instalador, instala o que
faltar (uv, ffmpeg, Node.js) e confere se tudo funciona. O passo a passo dele está
em [install.md](install.md).

À mão, é um comando só:

    uv run https://raw.githubusercontent.com/junioralbino28/cutmind/main/cutmind_install.py

Já baixou esta pasta? De dentro dela:

    uv run --no-project cutmind_install.py --source .

Precisa do [`uv`](https://docs.astral.sh/uv/) e do `ffmpeg`. O Node.js (Fase 2) o instalador põe sozinho quando falta: pelo winget no Windows e pelo Homebrew no Mac. No Linux ele mostra o comando.
