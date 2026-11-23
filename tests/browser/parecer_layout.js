const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = process.argv[2];
const srv = http.createServer((q, r) => {
  let f = path.join(root, q.url.split('?')[0] === '/' ? 'index.html' : q.url.split('?')[0]);
  if (!fs.existsSync(f)) { r.writeHead(404); return r.end(); }
  const t = f.endsWith('.css') ? 'text/css' : f.endsWith('.js') ? 'text/javascript' : f.endsWith('.html') ? 'text/html' : 'application/octet-stream';
  r.writeHead(200, { 'content-type': t }); r.end(fs.readFileSync(f));
}).listen(0);
// Verificação de layout do parecer (executada por tests/test_parecer_hierarquia_ui.py).
// Uso: node parecer_layout.js <dir com index.html + static/> <dir de screenshots>
const data = {
  tipo: 'CRIA', valores: [1,2,3], confianca: 90,
  parecer: {
    conclusao: { recomendacao: 'ressalva', nivel_recomendacao_label: 'APROVAR COM RESSALVA', dscr: 1.15, dscr_minimo: 1.05, dscr_ano1: 1.3, ano_critico: 3, anos_avaliados: 5, capacidade_maxima: 250000, parcela_mensal: 9000, justificativa: 'DSCR mínimo 1,05 no ano 3.', memoria: [{passo:'Passo', valor:'1', detalhe:'d'}] },
    rating: { faixa: 'BB', score: 61, rotulo: 'Moderado' },
    estresse_pecuario: { disponivel: true, avisos: ['Aviso de estresse A'], ponto_ruptura_arroba: { ressalva: { status:'ok', preco_minimo: 250, preco_base: 300, em_ruptura: false, dscr_alvo: 1, queda_maxima_suportada_pct: 16 } }, cenarios: {}, base: {} },
    proveniencia: { resumo: { total: 2, contagem: { medido: 1, referencia: 1 }, rotulos: {} }, parametros: [ { rotulo: 'Natalidade', valor: undefined, origem: 'medido', origem_rotulo: 'Medido', fonte: null }, { rotulo: 'X', valor: '1', origem: 'referencia', origem_rotulo: 'Ref', fonte: 'Embrapa' } ] },
    identificacao: {}, garantia: {},
  },
  sensibilidade: [], projecao_anos: [1,2,3,4,5].map(a => ({ ano: a, rebanho: 100, receita: 5000 * a, custo: 4000 * a, resultado: 1000 * a, margem_pct: 20, dscr: 1.1 })),
  sensibilidade_custo: [], shap_pendente: false,
  shap_explicacao: { fatores: [{ feature: 'f1', importancia_pct: 40, direcao: 'positivo' }], metodo: 'm', conformidade: 'c' },
};
(async () => {
  const b = await chromium.launch(); const port = srv.address().port; let fail = 0;
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }])
    for (const tema of ['light', 'dark']) {
      const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
      const errs = []; pg.on('pageerror', e => errs.push(String(e)));
      await pg.route('**/api/**', r => r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
      await pg.goto(`http://localhost:${port}/`, { waitUntil: 'load' });
      await pg.evaluate(t => document.documentElement.setAttribute('data-theme', t), tema);
      const info = await pg.evaluate(d => {
        const w = document.getElementById('result-wrap');
        w.innerHTML = renderParecer(d) + shapCardHtml(d.shap_explicacao, 'CRIA', '#0a0');
        OrkavynDash.renderParecer(d);
        const folds = [...w.querySelectorAll('details.ork-fold')];
        const dock = document.querySelector('.od-dock');
        const r = dock && dock.getBoundingClientRect();
        return {
          sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
          hero: !!w.querySelector('.od-hero'), kpis: w.querySelectorAll('.od-kpi').length,
          notes: w.querySelector('.od-hero__notes')?.innerText || '',
          folds: folds.map(f => ({ t: f.querySelector('summary').innerText, open: f.open })),
          dock: r ? { l: r.left, r: r.right, vw: innerWidth, vis: getComputedStyle(dock).position } : null,
          undef: /\bundefined\b|\bNaN\b|\bnull\b/.test(w.innerText),
        };
      }, data);
      await pg.evaluate(() => document.querySelectorAll('details.ork-fold').forEach(f => f.open = true));
      const sw2 = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const ok = info.sw <= info.cw && sw2 <= 0 && info.hero && info.kpis === 4 && info.folds.length >= 3 && info.folds.every(f => !f.open) && !info.undef && errs.length === 0 && (!info.dock || (info.dock.l >= 0 && info.dock.r <= info.dock.vw));
      if (!ok) fail++;
      console.log(vp.width, tema, ok ? 'OK' : 'FAIL', JSON.stringify({ ...info, sw2, errs }));
      await pg.screenshot({ path: `${process.argv[3]}/shot-${vp.width}-${tema}.png`, fullPage: false });
      await ctx.close();
    }
  await b.close(); srv.close(); process.exit(fail ? 1 : 0);
})();
