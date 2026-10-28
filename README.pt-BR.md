<h1><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/preview/cutmind-logo-white.png">
  <img src="assets/preview/cutmind-logo.png" alt="CutMind" height="44">
</picture></h1>

[English](README.md) · Português

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
só entra quem abriu pelo link ou QR, que levam um código deste computador. Fora de
casa, no Wi-Fi ou no 4G, o agente abre um link https pela Cloudflare
(`https://….trycloudflare.com`), sem configurar nada no celular, com um código só dele.

## Editar só pela conversa

Ajuste pequeno no editor sai de graça. O Salvar aplica na hora e o Baixar monta o
vídeo final, tudo sem o agente. Pela conversa, cada pedido põe o agente para
trabalhar, e isso gasta o seu limite do Claude ou do Codex. Dá para editar só
conversando, e fica mais barato assim:

- junte vários pedidos numa mensagem só, um por linha;
- diga o tempo ("de 0:12 a 0:15"), e o agente acha o trecho na hora;
- peça o resultado que você quer, não o jeito de fazer.

Pedidos que funcionam bem:

- "Tira de 0:12 a 0:15, é a parte em que eu leio o roteiro."
- "Corta o respiro em 0:41."
- "Sobe o texto do começo e deixa ele maior."
- "Legenda maior."
- "Abaixa o volume de 1:02 a 1:10."
- "Põe um preto e branco no vídeo todo."

No editor, o que você faz à mão não gasta nada. As marcações (tecla M) e os pedidos
escritos esperam o botão **Pronto, Claude segue**, que acorda o agente uma vez só,
com tudo junto.

## Instalar

Peça ao seu agente (Claude Code ou Codex): **"instala o CutMind pra mim, na pasta
geral de skills, para usar em todos os projetos: https://github.com/junioralbino28/cutmind"**.
Ele roda o instalador, instala o que faltar (uv, ffmpeg, Node.js) e confere se tudo
funciona. O passo a passo dele está em [install.md](install.md).

A instalação é do seu agente, não de um projeto: abra a conversa da instalação em
qualquer pasta. O CutMind vai para a pasta geral de skills (`~/.claude/skills/cutmind`
no Claude Code) e aparece em toda conversa nova. Para editar, abra depois uma conversa
nova DENTRO da pasta dos vídeos: o kit cria ali a pasta `edit/` daquele projeto.

Recebeu o kit num zip? Extraia e peça: **"instala o CutMind a partir da pasta
<onde você extraiu>, na pasta geral de skills"**.

À mão, é um comando só:

    uv run https://raw.githubusercontent.com/junioralbino28/cutmind/main/cutmind_install.py

Já baixou esta pasta? De dentro dela:

    uv run --no-project cutmind_install.py --source .

Precisa do [`uv`](https://docs.astral.sh/uv/) e do `ffmpeg`. O Node.js (Fase 2) o instalador põe sozinho quando falta: pelo winget no Windows e pelo Homebrew no Mac. No Linux ele mostra o comando.

## Atualizações

Quando sai versão nova, o editor avisa sozinho num cartão embaixo da barra de cima.
Um clique em **Atualizar** baixa, confere e instala, e você continua onde estava. Se
a versão mexe no editor por dentro, o botão vira **Atualizar e reiniciar**, e o editor
fecha e abre de novo em menos de um minuto. Com o vídeo sendo montado ou o Claude
trabalhando, a atualização espera eles terminarem. Se algo der errado no meio, o
CutMind volta sozinho para a versão de antes.

Quando a versão nova traz instruções novas para o agente, o editor avisa para começar
uma conversa nova, porque é nela que o Claude lê as instruções. Com o editor fechado,
peça ao agente **"atualiza o CutMind"**.

A procura pergunta ao GitHub ao abrir o editor e a cada 6 horas, e não manda nada seu.
Para desligar, no computador, abra o botão **?** do editor e tire **Procurar atualizações**.
