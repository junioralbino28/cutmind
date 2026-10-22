/* O relógio do corte nos editores: a MESMA conta do helpers/tempo.py, para a linha do tempo,
 * a prévia e o Salvar baterem com o render. Uma tomada é uma lista de pedaços de velocidade
 * constante [de, até, velocidade] na gravação: sem curva, um pedaço só; com curva, a reta
 * entre os pontos cortada onde a velocidade cresce 4%, cada pedaço com a média exata dele.
 * O teste tests/test_tempo_js.py roda este arquivo no Node e compara com o tempo.py. */
const Tempo = (() => {
  const PASSO = 1.04;

  // a curva (pontos [x, y], x de 0 a 1 na gravação) em pedaços [x0, x1, v] de 0 a 1
  function pedacosDaCurva(pontos) {
    const out = [];
    for (let k = 0; k + 1 < pontos.length; k++) {
      const [xa, ya] = pontos[k], [xb, yb] = pontos[k + 1];
      if (xb <= xa) continue; // degrau
      let xs, vs;
      if (yb === ya) { xs = [xa, xb]; vs = [ya, yb]; }
      else {
        const n = Math.max(1, Math.ceil(Math.abs(Math.log(yb / ya)) / Math.log(PASSO) - 1e-9));
        vs = [];
        for (let i = 0; i < n; i++) vs.push(ya * Math.pow(yb / ya, i / n));
        vs.push(yb);
        xs = vs.map((v) => xa + (v - ya) / (yb - ya) * (xb - xa));
        xs[xs.length - 1] = xb;
      }
      for (let i = 0; i + 1 < xs.length; i++) {
        const a = xs[i], b = xs[i + 1], va = vs[i], vb = vs[i + 1];
        const t = Math.abs(vb - va) < 1e-12 ? (b - a) / va : (b - a) * Math.log(vb / va) / (vb - va);
        const v = (b - a) / t;
        const ult = out[out.length - 1];
        if (ult && ult[2] === v) ult[1] = b; // trecho reto seguido de outro igual
        else out.push([a, b, v]);
      }
    }
    return out;
  }

  // a tomada `start`…`end` da gravação em pedaços; `curva` = {nome, pontos} ou null
  function pedacos(start, end, vel, curva) {
    if (!curva) return [[start, end, vel || 1]];
    const L = end - start;
    const out = pedacosDaCurva(curva.pontos).map(([a, b, v]) => [start + a * L, start + b * L, v]);
    out[out.length - 1][1] = end;
    return out;
  }

  function corteAte(p, at) {
    if (p.length === 1) return (at - p[0][0]) / p[0][2];
    let t = 0;
    for (const [a, b, v] of p) {
      if (at <= b) return t + (at - a) / v;
      t += (b - a) / v;
    }
    const u = p[p.length - 1];
    return t + (at - u[1]) / u[2];
  }

  function gravacaoEm(p, t) {
    if (p.length === 1) return p[0][0] + t * p[0][2];
    let acc = 0;
    for (const [a, b, v] of p) {
      const d = (b - a) / v;
      if (t <= acc + d) return a + (t - acc) * v;
      acc += d;
    }
    const u = p[p.length - 1];
    return u[1] + (t - acc) * u[2];
  }

  const durTrecho = (p, de, ate) => (p.length === 1 ? (ate - de) / p[0][2] : corteAte(p, ate) - corteAte(p, de));

  // a velocidade no ponto `at` da gravação
  function velEm(p, at) {
    for (const [, b, v] of p) if (at < b) return v;
    return p[p.length - 1][2];
  }

  // a curva cortada no ponto `x` (0–1): as duas metades, cada uma de 0 a 1, com as mesmas
  // velocidades nos mesmos pontos da gravação
  function cortarCurva(pontos, x) {
    const vEm = (xx) => {
      for (let k = 0; k + 1 < pontos.length; k++) {
        const [xa, ya] = pontos[k], [xb, yb] = pontos[k + 1];
        if (xx <= xb && xb > xa) return ya + (yb - ya) * (xx - xa) / (xb - xa);
      }
      return pontos[pontos.length - 1][1];
    };
    const meio = [x, vEm(x)];
    const esq = [...pontos.filter(([xx]) => xx < x), meio].map(([xx, y]) => [xx / x, y]);
    const dir = [meio, ...pontos.filter(([xx]) => xx > x)].map(([xx, y]) => [(xx - x) / (1 - x), y]);
    const limpa = (ps) => ps.map(([xx, y]) => [+xx.toFixed(6), +y.toFixed(4)]);
    return [limpa(esq), limpa(dir)];
  }

  return { pedacosDaCurva, pedacos, corteAte, gravacaoEm, durTrecho, velEm, cortarCurva };
})();
if (typeof module !== 'undefined') module.exports = Tempo;
