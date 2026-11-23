const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = process.argv[2];
const srv = http.createServer((q, r) => {
  let f = path.join(root, q.url.split('?')[0] === '/' ? 'index.html' : q.url.split('?')[0]);
  if (!fs.existsSync(f)) { r.writeHead(404); return r.end(); }
  const t = f.endsWith('.css') ? 'text/css' : f.endsWith('.js') ? 'text/javascript' : f.endsWith('.html') ? 'text/html' : 'application/octet-stream';
  r.writeHead(200, { 'content-type': t }); r.end(fs.readFileSync(f));
}).listen(0);
// Verificação de layout da carteira (executada por tests/test_carteira_historico.py).
// Uso: node carteira_layout.js <dir com index.html + static/> <dir de screenshots>
const longo = 'Fazenda Santa Maria do Rio Grande do Norte Agropecuária e Participações Ltda — Gleba 12';
const completo = { dscr_minimo: 1.05, rating_faixa: 'B', rating_score: 72, prazo_meses: 60, credito_valor: 900000,
  ruptura: { preco_minimo: 248.5, preco_base: 300, folga_pct: 17.2, em_ruptura: false },
  vale_caixa: { tem_vale: true, valor: 85000, mes: 'out', meses_deficit: 3, quebra_com_dscr_ok: true },
  ressalvas_total: 2, ressalvas: ['DSCR mínimo 1,05 no ano 3 e outra frase bem longa para forçar quebra de linha na tela estreita sem estourar', 'b'], erros_consistencia: 0 };
const carteira = [
  { fazenda_id: 1, nome: longo, proprietario: 'A', municipio: 'Município com nome bem extenso', estado: 'MT', recomendacao: 'ressalva', dscr: 1.1, parecer_em: '2026-11-01 10:00:00', resumo: completo },
  { fazenda_id: 2, nome: 'Antigo', municipio: 'X', estado: 'RO', recomendacao: 'aprovar', dscr: 1.4, parecer_em: '2026-01-01', resumo: { dscr_minimo: null, ruptura: null, vale_caixa: null, ressalvas_total: 0, ressalvas: [] } },
  { fazenda_id: 3, nome: 'Sem parecer', municipio: null, estado: null, recomendacao: null, dscr: null, parecer_em: null, resumo: null },
  { fazenda_id: 4, nome: 'Em ruptura <b>x</b>', recomendacao: 'negar', dscr: 0.8, parecer_em: '2026-10-01', resumo: { ...completo, ruptura: { preco_minimo: 320, preco_base: 300, folga_pct: null, em_ruptura: true }, vale_caixa: { tem_vale: false } } },
];
(async () => {
  const b = await chromium.launch(); const port = srv.address().port; let fail = 0;
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }])
    for (const tema of ['light', 'dark']) {
      const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
      const errs = []; pg.on('pageerror', e => errs.push(String(e)));
      await pg.route('**/api/**', r => r.fulfill({ status: 200, contentType: 'application/json',
        body: r.request().url().endsWith('/api/carteira') ? JSON.stringify({ carteira }) : '{}' }));
      await pg.goto(`http://localhost:${port}/`, { waitUntil: 'load' });
      await pg.evaluate(t => document.documentElement.setAttribute('data-theme', t), tema);
      await pg.evaluate(() => showTab('historico'));
      await pg.waitForSelector('.ork-cart-item');
      const info = await pg.evaluate(() => {
        const dock = document.querySelector('.od-dock'); const r = dock && dock.getBoundingClientRect();
        const txt = document.getElementById('panel-historico').innerText;
        return { itens: document.querySelectorAll('.ork-cart-item').length,
          sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
          traco: (txt.match(/—/g) || []).length, xss: !!document.querySelector('#cart-lista b'),
          undef: /\bundefined\b|\bNaN\b|\bnull\b/.test(txt),
          dock: r ? { l: r.left, r: r.right, vw: innerWidth } : null };
      });
      await pg.fill('#cart-busca', 'antigo');
      const filtrado = await pg.evaluate(() => document.querySelectorAll('.ork-cart-item').length);
      await pg.fill('#cart-busca', '');
      await pg.click('#cart-filtros [data-f="sem"]');
      const sem = await pg.evaluate(() => document.querySelectorAll('.ork-cart-item').length);
      const sw2 = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const ok = info.itens === 4 && info.sw <= info.cw && sw2 <= 0 && info.traco >= 6 && !info.xss && !info.undef && filtrado === 1 && sem === 1 && errs.length === 0 && (!info.dock || (info.dock.l >= 0 && info.dock.r <= info.dock.vw));
      if (!ok) fail++;
      console.log(vp.width, tema, ok ? 'OK' : 'FAIL', JSON.stringify({ ...info, filtrado, sem, sw2, errs }));
      await pg.click('#cart-filtros [data-f=""]');
      await pg.screenshot({ path: `${process.argv[3]}/carteira-${vp.width}-${tema}.png`, fullPage: false });
      await ctx.close();
    }
  await b.close(); srv.close(); process.exit(fail ? 1 : 0);
})();
