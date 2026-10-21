/* CutMind — catálogo de estilos e amostras, um arquivo só para os dois editores.
 *
 * O editor de PC (app.js) e o de celular (celular.js) carregam este arquivo antes
 * do próprio script e pegam daqui o que precisam:
 *
 *   const { STYLE_CATALOG, CAP_BUILDERS, ... } = CutMindEstilos;
 *
 * Duas cópias divergem, e uma amostra que mente sobre o estilo é pior que nenhuma.
 * Mudou o visual de uma legenda ou headline no template (Main.tsx, StackedCaptions,
 * ScatterCaptions, SimpleCaptions)? Muda aqui, e os dois editores acompanham.
 *
 * As amostras de legenda aceitam um texto próprio: o editor de celular passa as
 * palavras ditas no trecho do vídeo que está na tela. Sem texto, cada uma usa a
 * frase padrão — e desenha exatamente o que desenhava antes.
 */
(function () {
  'use strict';

  const el = (tag, cls, parent) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (parent) parent.appendChild(e);
    return e;
  };

  /* ---------- style catalog (the Fase 1 → Fase 2 gate) ----------
   * The one place that knows which looks CutMind can build. It is APP-level, not
   * session-level: a new editing style or caption style is a new entry here plus
   * its implementation in the track reference — never a per-session UI.
   * The user's pick ships to <edit>/preview_style.json; the skill reads it once,
   * at the gate, and builds Fase 2 from it.
   */
  const STYLE_CATALOG = {
    edits: [
      {
        // First on purpose: defaultStyle() takes edits[0], so this is also the
        // default for every new project — a clean full-frame cut, with inserts as
        // something the user opts into.
        id: 'limpa',
        name: 'Limpa',
        mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
          <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
          <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
          <circle cx="33" cy="48" r="13" fill="rgba(255,255,255,.16)"/>
          <path d="M12 115a21 21 0 0142 0z" fill="rgba(255,255,255,.16)"/>
          <rect x="14" y="14" width="38" height="4.4" rx="2.2" fill="rgba(255,255,255,.5)"/>
          <rect x="20" y="21.5" width="26" height="4.4" rx="2.2" fill="rgba(255,255,255,.3)"/>
          <rect x="12" y="74" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
          <rect x="16" y="78.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
          <rect x="30" y="78.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
          <rect x="40" y="78.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        </svg>`,
      },
      {
        id: 'split',
        name: 'Tela dividida',
        mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
          <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
          <rect x="3" y="3" width="60" height="36" rx="5" fill="rgba(255,119,19,.16)"/>
          <circle cx="17" cy="15" r="3.6" fill="rgba(255,119,19,.6)"/>
          <path d="M6 36l11-11a2 2 0 013 0l7 7 5-4a2 2 0 013 0l11 8" fill="none" stroke="rgba(255,119,19,.6)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M3 40.5h60" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>
          <rect x="3" y="42" width="60" height="73" rx="5" fill="rgba(255,255,255,.05)"/>
          <circle cx="33" cy="70" r="12" fill="rgba(255,255,255,.16)"/>
          <path d="M15 115a18 18 0 0136 0z" fill="rgba(255,255,255,.16)"/>
          <rect x="12" y="35" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
          <rect x="16" y="39.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
          <rect x="30" y="39.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
          <rect x="40" y="39.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        </svg>`,
      },
      {
        id: 'split2',
        name: 'Tela dividida 2',
        mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
          <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
          <rect x="3" y="3" width="60" height="65" rx="5" fill="rgba(255,255,255,.05)"/>
          <circle cx="33" cy="24" r="11" fill="rgba(255,255,255,.16)"/>
          <path d="M16 68a17 17 0 0134 0z" fill="rgba(255,255,255,.16)"/>
          <path d="M3 69.5h60" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>
          <rect x="3" y="71" width="60" height="44" rx="5" fill="rgba(255,119,19,.16)"/>
          <circle cx="17" cy="83" r="3.6" fill="rgba(255,119,19,.6)"/>
          <path d="M6 111l11-11a2 2 0 013 0l7 7 5-4a2 2 0 013 0l11 8" fill="none" stroke="rgba(255,119,19,.6)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <rect x="12" y="58" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
          <rect x="16" y="62.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
          <rect x="30" y="62.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
          <rect x="40" y="62.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        </svg>`,
      },
    ],
    // No names on purpose: the sample headline IS the label. Ids and geometry
    // mirror HL_STYLES in the template's Main.tsx — keep the two in step.
    headlines: [
      {id: 'outline', name: 'Contorno', hl: 'outline'},
      {id: 'card', name: 'Cartão', hl: 'card'},
      {id: 'realce', name: 'Realce', hl: 'realce'},
      {id: 'misto', name: 'Misto', hl: 'misto'},
      // Last on purpose: defaultStyle() takes headlines[0]. `hlbox` only so the
      // card matches the height of its siblings in this row.
      {id: 'none', name: 'Nenhum', none: true, hlbox: true},
    ],
    // `multiline`: more than one line on screen at once (the phone editor's
    // "Uma linha / Várias linhas" filter reads it).
    captions: [
      {id: 'karaoke', name: 'Karaokê', demo: 'karaoke'},
      {id: 'stacked', name: 'Empilhado', demo: 'stacked', multiline: true},
      {id: 'scatter', name: 'Disperso', demo: 'scatter', multiline: true},
      {id: 'simples', name: 'Simples', stat: 'simples'},
      {id: 'serifada', name: 'Serifada', stat: 'serifada'},
      {id: 'classica', name: 'Clássica', stat: 'classica', multiline: true},
      {id: 'none', name: 'Nenhum', none: true},
    ],
    elements: [
      {
        id: 'tracking',
        name: 'Movimento de tracking',
        def: false,
        icon: '<svg viewBox="0 0 16 16"><path d="M2 5.6V3.4A1.4 1.4 0 013.4 2h2.2M10.4 2h2.2A1.4 1.4 0 0114 3.4v2.2M14 10.4v2.2a1.4 1.4 0 01-1.4 1.4h-2.2M5.6 14H3.4A1.4 1.4 0 012 12.6v-2.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="8" r="2.1"/></svg>',
      },
      {
        id: 'zoomAuto',
        name: 'Automação de zoom in',
        def: true,
        icon: '<svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M10.6 10.6L14 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" fill="none"/><path d="M7 5.1v3.8M5.1 7h3.8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/></svg>',
      },
      {
        id: 'zoomCuts',
        name: 'Zoom in e out nos cortes',
        def: true,
        icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.4" width="6" height="9.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="9.6" y="1.9" width="5.2" height="12.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8.4 8h.7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
      },
      {
        id: 'flashCut',
        name: 'Flash na transição',
        def: false,
        icon: '<svg viewBox="0 0 16 16"><path d="M3 13.2L13 3.2" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" fill="none"/><path d="M6.6 14L9.4 11.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/><path d="M6.6 4.8L3.8 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/></svg>',
      },
      {
        id: 'musicAI',
        name: 'Trilha sonora com IA',
        // OFF by default, unlike the other two defaults-on. Those are free; this
        // is the only element in the catalog that needs an account. Pre-ticked, it
        // walked every first-time user into a signup they never asked for, at the
        // exact moment they expected a finished video. The checkbox is still right
        // there and says what it does — that is discovery enough.
        def: false,
        icon: '<svg viewBox="0 0 16 16"><path d="M12.6 1.6L6.9 3a.7.7 0 00-.55.68v5.6a2 2 0 101.35 1.9V5.9l4.4-1.05v2.9a2 2 0 101.35 1.9V2.3a.7.7 0 00-.85-.7z"/><path d="M2.4 2.2l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6z"/></svg>',
      },
    ],
  };

  /* Which styles actually paint the accent. Kept as data because the honest UI
   * note depends on it: with `karaoke` + `outline` picked, nothing on screen uses
   * the colour, and saying so beats letting the user wonder why the previews did
   * not move. Mirrors the template — update both together. */
  const ACCENT_USERS = {headlines: ['realce', 'misto'], captions: ['stacked']};
  const ACCENT_DEFAULT = '#ff5200';

  /* ---------- caption previews: the template's animation, not an impression ----
   * Every number here is lifted from the render (Main.tsx Karaoke/Word and
   * StackedCaptions.tsx STACK_MIXED) and scaled by boxWidth/1080, so the preview
   * shows the real proportions, the real faces and the real motion. If the
   * template's caption look changes, change it HERE too — a preview that lies
   * about the style is worse than no preview.
   */
  const CAP_TEXT = 'É assim que sua legenda irá aparecer';
  const FPS_REF = 30; // the template's reference fps for frame-based timings
  const wordsOf = (text) => String(text || '').trim().split(/\s+/).filter(Boolean);

  // cubic-bezier solver — the stacked style eases on bezier(.16,1,.3,1)
  function bez(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const fx = (t) => ((ax * t + bx) * t + cx) * t;
    const dfx = (t) => (3 * ax * t + 2 * bx) * t + cx;
    return (x) => {
      let t = x;
      for (let i = 0; i < 6; i++) {
        const e = fx(t) - x;
        if (Math.abs(e) < 1e-4) break;
        const d = dfx(t);
        if (Math.abs(d) < 1e-6) break;
        t -= e / d;
      }
      return ((ay * t + by) * t + cy) * t;
    };
  }
  const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3); // Easing.out(Easing.cubic)
  const easeStack = bez(0.16, 1, 0.3, 1);
  const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

  // Karaoke: lines of ≤3 words (captions.maxWords), Poppins 900 white, each word
  // rises 34px and fades in over 7 frames; the line is replaced by the next one.
  // `still`: the phrase as it stands once every word is in, on one line, no loop —
  // the phone editor's "Posição das frases" drags it, it is not there to be watched.
  function buildKaraokeDemo(host, text = CAP_TEXT, still = false) {
    const s = host.clientWidth / 1080;
    host.innerHTML = '';
    const wrap = el('div', 'cap-demo', host);
    const words = wordsOf(text);
    const lines = [];
    const per = still ? Math.max(1, words.length) : 3;
    for (let i = 0; i < words.length; i += per) lines.push(words.slice(i, i + per));

    const STEP = 0.26, ENTER = 7 / FPS_REF, HOLD = 0.6;
    const rise = 34 * s;
    const built = [];
    let t = 0;
    for (const ln of lines) {
      const box = el('div', 'kar-line', wrap);
      box.style.fontSize = `${61 * s}px`;
      const spans = ln.map((w) => {
        const sp = el('span', '', box);
        sp.textContent = w;
        sp.style.marginRight = `${18 * s}px`;
        return sp;
      });
      const start = t;
      t = start + (ln.length - 1) * STEP + ENTER + HOLD;
      built.push({ box, spans, start, end: t });
    }
    if (still) return null;
    const cycle = t + 0.3;

    return (now) => {
      const p = now % cycle;
      for (const L of built) {
        const on = p >= L.start && p < L.end;
        L.box.style.display = on ? '' : 'none';
        if (!on) continue;
        L.spans.forEach((sp, j) => {
          const e = easeOutCubic(clamp01((p - (L.start + j * STEP)) / ENTER));
          sp.style.opacity = e;
          sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
        });
      }
    };
  }

  // Stacked: one cue, lines cycling the STACK_MIXED styles (bold-italic gradient →
  // regular small → Playfair italic orange). Words rise 46px with a blur that
  // resolves; the cue leaves with the blur_up exit.
  const STK_LINES = [
    { words: ['É', 'assim'], style: 0 },
    { words: ['que', 'sua', 'legenda'], style: 1 },
    { words: ['irá', 'aparecer'], style: 2 },
  ];
  // A cue from the director itself (caption_style.py, served by the preview at
  // /gen/frases): its own lines, line styles and sizes, as StackedCaptions sizes
  // them — fitFont at 1080 wide times FONT_SCALE 0.8, then the per-style tweaks.
  const stkFit = (t, base, factor) => {
    const n = Math.max(1, String(t).trim().length);
    return (n * base * factor > 1125 ? Math.floor(1125 / (n * factor)) : base) * 0.8;
  };
  function cueLines(cue) {
    if (cue.preset !== 'STACK_MIXED') {
      const w = cue.lines[0][0];
      const big = cue.preset === 'SOLO_BIG';
      return [{ words: [w], style: big ? 0 : 3, size: stkFit(w, big ? 150 : 118, 0.6) }];
    }
    return cue.lines.map((ws, li) => {
      const style = (cue.lineStyles || [])[li] ?? li % 4;
      let size = stkFit(ws.join(' '), 86, 0.58);
      if (style === 1) size *= 0.72;
      if (style === 2) size *= 0.95;
      if ((cue.lineEmph || [])[li]) size *= 1.12;
      if ((cue.lineBoost || [])[li]) size *= 1.35;
      return { words: ws, style, size: Math.round(size) };
    });
  }
  // Texto próprio: as mesmas linhas de 2, 3 e 2 palavras, girando os três estilos.
  function stackedLines(text) {
    if (text == null) return STK_LINES;
    const words = wordsOf(text);
    const sizes = [2, 3, 2];
    const lines = [];
    for (let i = 0, k = 0; i < words.length; k++) {
      const n = sizes[k % sizes.length];
      lines.push({ words: words.slice(i, i + n), style: k % 3 });
      i += n;
    }
    return lines;
  }
  function buildStackedDemo(host, text, still = false, dirCue = null) {
    const s = host.clientWidth / 1080;
    host.innerHTML = '';
    const wrap = el('div', 'cap-demo', host);
    const cue = el('div', 'stk-cue', wrap);

    const STEP = 0.2, ENTER = 8 / FPS_REF, HOLD = 0.8, EXIT = 7 / FPS_REF;
    const rise = 46 * s, blurIn = 5 * s, upY = 55 * s, cueBlur = 14 * s;
    const shadow = `drop-shadow(0 ${(5 * s).toFixed(2)}px ${(9 * s).toFixed(2)}px rgba(0,0,0,0.5))`;
    const all = [];
    let idx = 0;
    for (const L of dirCue ? cueLines(dirCue) : stackedLines(text)) {
      const row = el('div', 'stk-line', cue);
      let size = L.size || 69;
      if (!L.size && L.style === 1) size = Math.round(size * 0.72);
      if (!L.size && L.style === 2) size = Math.round(size * 0.95);
      row.style.fontSize = `${size * s}px`;
      L.words.forEach((w, i) => {
        // the face/gradient belongs to the WORD, like the template's `...ls` spread
        const sp = el('span', `s${L.style}`, row);
        sp.textContent = w + (i < L.words.length - 1 ? ' ' : '');
        all.push({ sp, start: idx * STEP });
        idx++;
      });
    }
    if (still) {
      for (const w of all) w.sp.style.filter = shadow;
      return null;
    }
    const exitStart = (idx - 1) * STEP + ENTER + HOLD;
    // short gap after the exit: side by side with the karaoke card, a preview that
    // sits blank for half a second reads as broken rather than as a cue boundary
    const cycle = exitStart + EXIT + 0.15;

    return (now) => {
      const p = now % cycle;
      const ex = clamp01((p - exitStart) / EXIT);
      cue.style.opacity = 1 - ex;
      cue.style.translate = `0px ${(-upY * ex).toFixed(2)}px`;
      cue.style.filter = ex > 0.02 ? `blur(${(cueBlur * ex).toFixed(2)}px)` : '';
      for (const w of all) {
        const e = easeStack(clamp01((p - w.start) / ENTER));
        const eb = (1 - e) * blurIn;
        w.sp.style.opacity = e;
        w.sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
        w.sp.style.filter = `${eb > 0.06 ? `blur(${eb.toFixed(2)}px) ` : ''}${shadow}`;
      }
    };
  }

  /* ---------- headline previews: the template's own hook styles ----------------
   * Same contract as the caption demos — these render what `HookInner` renders,
   * scaled from 1080-wide. The two-line break and the size fit run the SAME
   * algorithm as the template (balance by measured width, then fit to safeW), so
   * the preview shows the real break at the real size, not an approximation.
   * HL_STYLES exists on both sides; change one, change the other.
   */
  const HEADLINE_TEXT = 'É assim que vai ficar a sua headline';
  const HL_MIN = 28;
  const HL_STYLES = {
    outline: { weights: [800, 800], cap: 51, safeW: 900, lh: 1.02 },
    card: { weights: [900, 900], cap: 46, safeW: 820, lh: 1.06 },
    realce: { weights: [900, 900], cap: 48, safeW: 830, lh: 1.04 },
    misto: { weights: [400, 900], cap: 55, safeW: 900, lh: 0.98 },
  };

  // Measured in RENDER units (1080-wide), scaled to the box only at the end — the
  // template's letterSpacing is -1px at 1080, which is NOT proportional once the
  // preview shrinks it, so measuring in preview px would break the fit.
  let hlMeter = null;
  function measureType(text, size, weight, family, tracking) {
    if (!text) return 0;
    if (!hlMeter) {
      hlMeter = document.createElement('span');
      hlMeter.style.cssText =
        'position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre;';
      document.body.appendChild(hlMeter);
    }
    hlMeter.style.fontFamily = family || "'Poppins',sans-serif";
    hlMeter.style.letterSpacing = `${tracking == null ? -1 : tracking}px`;
    hlMeter.style.fontSize = `${size}px`;
    hlMeter.style.fontWeight = String(weight);
    hlMeter.textContent = text;
    return hlMeter.offsetWidth;
  }
  const hlWidth = (text, size, weight) => measureType(text, size, weight);

  // Balance by MEASURED width, not word count: "É assim que vai" and "ficar a sua
  // headline" are 4 and 3 words but nearly the same width — counting words breaks
  // the line in the wrong place.
  function hlTwoLines(text, weights) {
    const words = text.trim().split(/\s+/).filter(Boolean);
    if (words.length < 2) return [words[0] || '', ''];
    let best = [words[0], words.slice(1).join(' ')];
    let bestDiff = Infinity;
    for (let i = 1; i < words.length; i++) {
      const a = words.slice(0, i).join(' ');
      const b = words.slice(i).join(' ');
      const d = Math.abs(hlWidth(a, 100, weights[0]) - hlWidth(b, 100, weights[1]));
      if (d < bestDiff) { bestDiff = d; best = [a, b]; }
    }
    return best;
  }

  function hlFit(lines, S) {
    const widest = (size) =>
      Math.max(hlWidth(lines[0], size, S.weights[0]), hlWidth(lines[1], size, S.weights[1]));
    let size = Math.floor((S.safeW / Math.max(1, widest(100))) * 100);
    size = Math.floor((S.safeW / Math.max(1, widest(size))) * size);
    return Math.max(HL_MIN, Math.min(size, S.cap));
  }

  function buildHeadlineDemo(host, styleId, text = HEADLINE_TEXT) {
    const s = host.clientWidth / 1080;
    const S = HL_STYLES[styleId];
    host.innerHTML = '';
    const wrap = el('div', 'cap-demo', host);
    const raw = styleId === 'card' ? text.toUpperCase() : text;
    const lines = hlTwoLines(raw, S.weights);
    const size = hlFit(lines, S) * s;
    const box = el('div', `hl-demo hl-${styleId}`, wrap);
    box.style.lineHeight = String(S.lh);
    box.style.letterSpacing = `${-1 * s}px`;

    if (styleId === 'realce') {
      for (const l of lines) {
        if (!l) continue;
        const b = el('div', 'hl-block', box);
        b.style.fontSize = `${size}px`;
        b.style.borderRadius = `${12 * s}px`;
        b.textContent = l;
      }
      return;
    }
    if (styleId === 'card') {
      box.style.borderRadius = `${24 * s}px`;
      box.style.padding = `${28 * s}px ${46 * s}px`;
    }
    if (styleId === 'outline') {
      box.style.webkitTextStroke = `${7 * s}px #000`;
    }
    lines.forEach((l, i) => {
      if (!l) return;
      const d = el('div', '', box);
      d.style.fontSize = `${size}px`;
      d.style.fontWeight = String(S.weights[i]);
      // var(), not a literal — an inline colour would beat the accent variable and
      // this preview would keep painting orange while the others followed the pick
      if (styleId === 'misto') d.style.color = i === 1 ? 'var(--hl-accent)' : '#fff';
      d.textContent = l;
    });
  }

  // Scatter ("disperso"): serif, lowercase, one word at a time, off-white with a
  // slight darkening toward the baseline. Ordinary words FADE only — no movement;
  // the one highlighted word resolves out of a blur and dissolves back into it.
  // Mirrors ScatterCaptions.tsx: same line rules, same SPREAD, same hash.
  const SCAT = { base: 58, hiScale: 1.62, gap: 12, spread: 0.45, safeW: 820 };
  const scatHash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

  // `gi`: the cue's index in the video — the template hashes line breaks and offsets
  // off it, so a real phrase breaks where the render breaks it (the cards use 1).
  function buildScatterDemo(host, text = CAP_TEXT, still = false, gi = 1) {
    const s = host.clientWidth / 1080;
    host.innerHTML = '';
    const wrap = el('div', 'cap-demo', host);
    const cue = el('div', 'scat-cue', wrap);

    const words = wordsOf(text.toLowerCase());
    // highlight = longest word of the cue, and only if it carries weight (>6)
    let hiIdx = -1, hiLen = 6;
    words.forEach((w, i) => { if (w.length > hiLen) { hiLen = w.length; hiIdx = i; } });

    // ragged lines of 3–4 words; the highlighted word takes a line of its own
    const lines = [];
    let line = [];
    words.forEach((w, i) => {
      if (i === hiIdx) {
        if (line.length) lines.push(line);
        lines.push([{ w, i, hi: true }]);
        line = [];
        return;
      }
      line.push({ w, i, hi: false });
      if (line.length >= (scatHash(gi * 31 + i) > 0.5 ? 4 : 3)) { lines.push(line); line = []; }
    });
    if (line.length) lines.push(line);

    const STEP = 0.22, ENTER = 7 / FPS_REF, HI_ENTER = 10 / FPS_REF, HOLD = 0.9, EXIT = 8 / FPS_REF;
    const all = [];
    lines.forEach((ln, li) => {
      const row = el('div', 'scat-line', cue);
      row.style.gap = `${SCAT.gap * s}px`;
      let w = 0;
      for (const it of ln) {
        const sp = el('span', it.hi ? 'hi' : '', row);
        sp.textContent = it.w;
        sp.style.fontSize = `${(it.hi ? SCAT.base * SCAT.hiScale : SCAT.base) * s}px`;
        all.push({ sp, start: it.i * STEP, hi: it.hi });
        w += sp.offsetWidth + SCAT.gap * s;
      }
      const room = Math.max(0, (SCAT.safeW * s - w) / 2) * SCAT.spread;
      row.style.translate = `${((scatHash(gi * 17 + li * 5 + 3) * 2 - 1) * room).toFixed(1)}px 0px`;
    });
    if (still) return null; // every word in, the highlighted one already sharp

    const exitStart = (words.length - 1) * STEP + ENTER + HOLD;
    const cycle = exitStart + EXIT + 0.35;
    const blurIn = 26 * s, blurOut = 30 * s;

    return (now) => {
      const p = now % cycle;
      const out = clamp01((p - exitStart) / EXIT);
      for (const w of all) {
        const t = easeOutCubic(clamp01((p - w.start) / (w.hi ? HI_ENTER : ENTER)));
        w.sp.style.opacity = t * (1 - out);
        if (w.hi) {
          const b = (1 - t) * blurIn + out * blurOut;
          w.sp.style.filter = b > 0.1 ? `blur(${b.toFixed(2)}px)` : '';
        }
      }
    };
  }

  /* ---------- the three STATIC caption styles ---------------------------------
   * No animation, so no entry in capAnims — built once and left alone. Mirrors
   * SIMPLE_VARIANTS in SimpleCaptions.tsx, including the rule that matters most:
   * lines are grouped by MEASURED WIDTH, capped at maxWords. That is why a long
   * word ends up alone and short ones ride together.
   */
  const STATIC_VARIANTS = {
    simples: {family: "'Poppins',sans-serif", weight: 600, size: 66, maxWords: 3, lines: 1, sx: 0.9, sy: 0.9, tracking: -3, maxW: 860},
    serifada: {family: "'Libre Baskerville',serif", weight: 700, size: 67, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 860},
    classica: {family: "'Inter',sans-serif", weight: 500, size: 42, maxWords: 14, lines: 2, sx: 1, sy: 1, tracking: 0, maxW: 840},
  };
  const ORPHAN_PT = /^(o|a|os|as|e|é|de|do|da|em|no|na|um|uma|que|se|ao|à|por|com)$/i;

  function buildStaticDemo(host, id, text = CAP_TEXT) {
    const V = STATIC_VARIANTS[id];
    const s = host.clientWidth / 1080;
    host.innerHTML = '';
    const wrap = el('div', 'cap-demo', host);
    const words = wordsOf(text);
    const wOf = (ws) => measureType(ws.join(' '), V.size, V.weight, V.family, V.tracking) * V.sx;

    // the WHOLE sentence, cut into cues exactly as the render would
    const cues = [];
    let cur = [];
    for (const w of words) {
      const trial = [...cur, w];
      if (cur.length && (trial.length > V.maxWords || wOf(trial) > V.maxW * V.lines)) {
        cues.push(cur);
        cur = [w];
      } else {
        cur = trial;
      }
    }
    if (cur.length) cues.push(cur);

    const boxes = cues.map((cue) => {
      let lines = [cue];
      if (V.lines === 2 && cue.length > 1) {
        let best = 1, bestScore = Infinity;
        for (let i = 1; i < cue.length; i++) {
          const score = Math.abs(wOf(cue.slice(0, i)) - wOf(cue.slice(i))) + (ORPHAN_PT.test(cue[i - 1]) ? 200 : 0);
          if (score < bestScore) { bestScore = score; best = i; }
        }
        lines = [cue.slice(0, best), cue.slice(best)];
      }
      const box = el('div', 'stat-demo', wrap);
      box.style.fontFamily = V.family;
      box.style.fontWeight = String(V.weight);
      box.style.fontSize = `${V.size * s}px`;
      box.style.letterSpacing = `${V.tracking * s}px`;
      box.style.transform = V.sx === 1 && V.sy === 1 ? '' : `scale(${V.sx}, ${V.sy})`;
      for (const ln of lines) el('div', '', box).textContent = ln.join(' ');
      return box;
    });

    // A style with no animation still has a RHYTHM — the cues replacing each other
    // is what the viewer sees. So the card plays the whole sentence, cue by cue,
    // on hard cuts. A single-cue style (the two-line "classica" fits the sentence
    // whole) has nothing to step through and stays still.
    if (boxes.length < 2) return null;
    const HOLD = 0.95;
    const cycle = boxes.length * HOLD;
    return (now) => {
      const i = Math.floor((now % cycle) / HOLD);
      boxes.forEach((b, k) => { b.style.display = k === i ? '' : 'none'; });
    };
  }

  /* ---------- the phrases of a real video: the template's own cue rules --------
   * `words`: [{text, start, end}] in seconds (transcripts/cut.json — the words of
   * captions.json). Returns [{gi, start, end, text}], `end` being when the next
   * phrase takes over, exactly where each component switches cue:
   *   karaoke  Main.tsx buildLines        — maxWords, or punctuation
   *   scatter  ScatterCaptions buildCues  — 6 words, punctuation, or a 400ms gap
   *   static   SimpleCaptions buildCues   — measured width, maxWords, punctuation, 450ms gap
   * Stacked is not here: its director (caption_style.py) is served by the preview.
   */
  const capClean = (t) => String(t).replace(/[.,!?…]+$/, '');
  const capBreak = (t) => /[.,!?…]$/.test(t);
  function capPhrases(id, words, opts = {}) {
    const groups = [];
    let cur = [];
    if (id === 'karaoke') {
      const max = opts.maxWords || 3;
      for (const w of words) {
        cur.push(w);
        if (cur.length >= max || capBreak(w.text)) { groups.push(cur); cur = []; }
      }
    } else if (id === 'scatter') {
      words.forEach((w, i) => {
        cur.push(w);
        const nx = words[i + 1];
        if (cur.length >= 6 || capBreak(w.text) || (nx ? nx.start - w.end : Infinity) > 0.4) { groups.push(cur); cur = []; }
      });
    } else if (STATIC_VARIANTS[id]) {
      const V = STATIC_VARIANTS[id];
      const wOf = (ws) => measureType(ws.map((x) => capClean(x.text)).join(' '), V.size, V.weight, V.family, V.tracking) * V.sx;
      words.forEach((w, i) => {
        const trial = [...cur, w];
        if (cur.length && (trial.length > V.maxWords || wOf(trial) > V.maxW * V.lines)) { groups.push(cur); cur = [w]; } else cur = trial;
        const nx = words[i + 1];
        if (cur.length && (capBreak(w.text) || (nx ? nx.start - w.end : 0) > 0.45)) { groups.push(cur); cur = []; }
      });
    } else {
      return [];
    }
    if (cur.length) groups.push(cur);
    return groups.map((g, gi) => ({
      gi,
      start: g[0].start,
      end: groups[gi + 1] ? groups[gi + 1][0].start : g[g.length - 1].end + 1,
      text: g.map((w) => capClean(w.text)).join(' '),
    }));
  }

  const CAP_BUILDERS = { karaoke: buildKaraokeDemo, stacked: buildStackedDemo, scatter: buildScatterDemo };

  window.CutMindEstilos = Object.freeze({
    STYLE_CATALOG, ACCENT_USERS, ACCENT_DEFAULT,
    CAP_TEXT, FPS_REF, HEADLINE_TEXT, HL_MIN, HL_STYLES, SCAT, STATIC_VARIANTS, ORPHAN_PT,
    bez, easeOutCubic, easeStack, clamp01,
    measureType, hlTwoLines, hlFit,
    buildKaraokeDemo, buildStackedDemo, buildHeadlineDemo, buildScatterDemo, buildStaticDemo,
    CAP_BUILDERS, capPhrases,
  });
})();
