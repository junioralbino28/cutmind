# Free soundtracks — where to point the user

The kit does not host music. When the user wants a soundtrack and doesn't want an
AI one (Treblo), relay the list below in their language. For Reels, TikTok and
Shorts, first offer to deliver **without a soundtrack**: they pick the music inside
the app when posting, and the video must not carry another one under it.

The phone editor shows the same sites (Áudio → Trilhas, `TRILHAS_GRATIS` in
`assets/preview/celular.js`). `tests/test_trilhas_gratis.py` fails if a link there
is missing here — change both together.

## Texto para o usuário

**Para rede social, dá para não pôr trilha.** No Instagram, no TikTok e no YouTube
Shorts a música entra na hora de postar, no próprio app. Nesse caso o vídeo sai daqui
sem trilha, para não tocar duas músicas juntas.

- No Instagram, conta comercial vê só a [Sound Collection da Meta](https://www.facebook.com/business/help/880459498798521),
  músicas liberadas para empresa (dá até para usar em anúncio).
- No TikTok, conta empresa vê só a [Biblioteca de Música Comercial](https://ads.tiktok.com/resources/help/article/how-to-use-the-commercial-music-library),
  e essas músicas valem só dentro do TikTok.

**Para a música ficar no vídeo**, baixe de graça num destes sites e traga pelo editor
(Áudio → Do celular) ou mande o arquivo aqui na conversa.

Sem precisar dar crédito:
- [Pixabay Música](https://pixabay.com/music/)
- [Mixkit](https://mixkit.co/free-stock-music/)
- [StreamBeats](https://www.streambeats.com/)
- [Holizna](https://holiznacc0.bandcamp.com/), lo-fi e hip hop em domínio público
- [OpenGameArt](https://opengameart.org/art-search-advanced?keys=&field_art_type_tid%5B%5D=12&field_art_licenses_tid%5B%5D=4), só as músicas em domínio público (CC0); a maioria é de jogo

Grátis, com crédito na descrição do post:
- [Biblioteca de áudio do YouTube](https://studio.youtube.com/), no YouTube Studio; só algumas pedem crédito
- [Uppbeat](https://uppbeat.io/)
- [Incompetech](https://incompetech.com/music/royalty-free/music.html), do Kevin MacLeod
- [Free To Use](https://freetouse.com/music)

Se o YouTube reivindicar uma música grátis, conteste com o link da página onde você
baixou. Acontece com algumas faixas da Pixabay.

## What the agent does with the answer

- **No soundtrack:** leave `soundtrack.enabled: false` and add no music layer. Say in
  one line that the music goes in when posting.
- **A file of theirs:** if it came through the phone (Áudio → Do celular) it is
  already an audio layer in `camadas.json`; otherwise copy it to `public/trilha.mp3`
  and follow Phase 3 in `references/shortform.md` (volume, fades, loudnorm). Never
  both for the same music.
- **Credit:** when the site asks for it, write the credit line for the post
  description at the end of the delivery.
