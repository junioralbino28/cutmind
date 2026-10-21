# CutMind

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

## Instalar a partir desta pasta

    python cutmind_install.py --source .

Precisa de `uv` e `ffmpeg` instalados. O Node.js (Fase 2) o instalador põe sozinho quando falta: pelo winget no Windows e pelo Homebrew no Mac. No Linux ele mostra o comando.
