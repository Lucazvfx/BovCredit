const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
// Verificação da tela de Resultado (executada por tests/test_resultado_refatorado.py).
// Uso: node resultado_layout.js <dir com index.html + static/> <dir de screenshots> <payload COM crédito.json> <payload SEM crédito.json>
const [root, shots, comPath, semPath] = process.argv.slice(2);
const payloads = { com: JSON.parse(fs.readFileSync(comPath, 'utf8')), sem: JSON.parse(fs.readFileSync(semPath, 'utf8')) };
const srv = http.createServer((q, r) => {
  const u = q.url.split('?')[0];
  const f = path.join(root, u === '/' ? 'index.html' : u);
  if (!fs.existsSync(f)) { r.writeHead(404); return r.end(); }
  const t = f.endsWith('.css') ? 'text/css' : f.endsWith('.js') ? 'text/javascript' : f.endsWith('.html') ? 'text/html' : 'application/octet-stream';
  r.writeHead(200, { 'content-type': t }); r.end(fs.readFileSync(f));
}).listen(0);

(async () => {
  const b = await chromium.launch(); const port = srv.address().port; let fail = 0;
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }])
    for (const caso of ['com', 'sem']) {
      const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
      const errs = []; pg.on('pageerror', e => errs.push(String(e)));
      await pg.route('**/api/**', r => r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
      await pg.goto(`http://localhost:${port}/`, { waitUntil: 'load' });
      const info = await pg.evaluate(d => {
        document.getElementById('f_faz').value = 'Fazenda Santa Cruz';
        document.getElementById('f_mun').value = 'Juara - MT';
        showTab('resultado');
        renderResult(d);
        const w = document.getElementById('result-wrap');
        const tabs = [...w.querySelectorAll('.rt-tab')].map(t => t.id.replace('rt-tab-', ''));
        const visiveis = () => [...w.querySelectorAll('.rt-panel')].filter(p => !p.hidden).map(p => p.id.replace('rt-panel-', ''));
        const porAba = {};
        for (const id of tabs) {
          rtAtivar(id);
          w.querySelectorAll('details').forEach(x => { x.open = true; });
          porAba[id] = { visiveis: visiveis(), overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
        }
        rtAtivar(tabs[0]);
        const kpis = w.querySelector('.ork-exec__kpis');
        const dock = document.querySelector('.od-dock');
        const alvo = [...w.querySelectorAll('.btn-sm')].pop();
        // o contêiner de rolagem do app é o <body>, não a janela
        const ir = { top: 1e9, behavior: 'instant' }; document.body.scrollTo(ir); window.scrollTo(ir);
        const rb = alvo && alvo.getBoundingClientRect(), rd = dock && dock.getBoundingClientRect();
        return {
          tabs, porAba,
          resumo: !!w.querySelector('.ork-exec'),
          nKpis: kpis ? kpis.children.length : 0,
          colsKpis: kpis ? getComputedStyle(kpis).gridTemplateColumns.split(' ').length : 0,
          kpisTexto: kpis ? kpis.innerText : '',
          heroVazios: w.querySelectorAll('.od-kpi--empty').length,
          heroFiguras: w.querySelectorAll('.od-hero__figures').length,
          texto: w.textContent,
          ctaImpeditivo: !!w.querySelector('.ork-exec__alert button'),
          gaveta: !!w.querySelector('dialog#dlg-memoria'),
          folga: rb && rd ? Math.round(rd.top - rb.bottom) : null,
          padBottom: parseFloat(getComputedStyle(document.querySelector('.ork-workspace')).paddingBottom),
          dockH: rd ? rd.height : 0,
          sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
        };
      }, payloads[caso]);
      const conf = String(payloads[caso].confianca);
      const confFmt = Number(conf).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%';
      const checks = {
        quatroAbas: JSON.stringify(info.tabs) === JSON.stringify(['checklist', 'financeiro', 'rebanho', 'risco']),
        umPainelPorVez: Object.values(info.porAba).every(a => a.visiveis.length === 1),
        semOverflow: info.sw <= info.cw && Object.values(info.porAba).every(a => a.overflow <= 0),
        resumo: info.resumo && info.nKpis >= 1 && info.nKpis <= 4 && info.colsKpis === 2,
        confiancaCerta: info.texto.includes(confFmt) && !/\d{4,}(,\d+)?\s?%/.test(info.texto) && !/\d{1,3}(\.\d{3})+(,\d+)?\s?%/.test(info.texto),
        semUndefined: !/\bundefined\b|\bNaN\b/.test(info.texto),
        semErros: errs.length === 0,
        // o dock flutuante não pode cobrir a última ação da tela
        dockLivre: info.folga === null || info.folga >= 0,
        // a proveniência dos parâmetros não depende de crédito: a gaveta existe nos dois casos
        gaveta: info.gaveta,
        folgaDock: info.padBottom >= info.dockH + 16,
        // sem crédito ativo: nada de card vazio com "—" nem KPI de crédito
        semCardVazio: caso === 'com' || (info.heroVazios === 0 && info.heroFiguras === 0 && !info.kpisTexto.includes('Crédito máx') && !info.kpisTexto.includes('—')),
      };
      const ok = Object.values(checks).every(Boolean);
      if (!ok) fail++;
      console.log(vp.width, caso, ok ? 'OK' : 'FAIL', JSON.stringify(ok ? { folga: info.folga, nKpis: info.nKpis } : { checks, folga: info.folga, errs, sw: info.sw, cw: info.cw, porAba: info.porAba }));
      await pg.evaluate(() => { const t = { top: 0, behavior: 'instant' }; document.body.scrollTo(t); window.scrollTo(t); });
      await pg.screenshot({ path: `${shots}/res-${vp.width}-${caso}.png`, fullPage: false });
      await ctx.close();
    }
  await b.close(); srv.close(); process.exit(fail ? 1 : 0);
})();
