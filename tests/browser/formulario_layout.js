const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = process.argv[2];
const srv = http.createServer((q, r) => {
  let f = path.join(root, q.url.split('?')[0] === '/' ? 'index.html' : q.url.split('?')[0]);
  if (!fs.existsSync(f)) { r.writeHead(404); return r.end(); }
  const t = f.endsWith('.css') ? 'text/css' : f.endsWith('.js') ? 'text/javascript' : f.endsWith('.html') ? 'text/html' : 'application/octet-stream';
  r.writeHead(200, { 'content-type': t }); r.end(fs.readFileSync(f));
}).listen(0);
// Formulário e navegação (executado por tests/test_ux_formulario_navegacao.py).
// Uso: node formulario_layout.js <dir com index.html + static/> <dir de screenshots>
(async () => {
  const b = await chromium.launch(); const port = srv.address().port; let fail = 0;
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }])
    for (const tema of ['light', 'dark']) {
      const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
      const errs = []; pg.on('pageerror', e => errs.push(String(e)));
      await pg.route('**/api/**', r => r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }));
      await pg.goto(`http://localhost:${port}/`, { waitUntil: 'load' });
      await pg.evaluate(t => document.documentElement.setAttribute('data-theme', t), tema);
      const over = () => pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      const checks = {}; const overflows = [await over()];

      // Blocos opcionais nascem recolhidos e abrem pelo botão (aria-expanded).
      checks.recolhidos = await pg.evaluate(() => ['od-b2', 'od-b3'].every(id =>
        document.getElementById(id + '-body').hidden &&
        document.querySelector('#' + id + ' .od-block__toggle').getAttribute('aria-expanded') === 'false'));
      await pg.click('#od-b3 .od-block__toggle');
      checks.abriu = await pg.evaluate(() => !document.getElementById('od-b3-body').hidden);

      // Estresse: preenchimento parcial mostra o que falta; completo limpa.
      await pg.fill('#preco_arroba_base', '320');
      checks.parcial = await pg.evaluate(() => ({
        status: !document.getElementById('od-estresse-status').hidden,
        faltam: document.querySelectorAll('#od-b3 .od-field--missing').length,
        chip: document.querySelector('#od-b3 .od-block__status').textContent,
      }));
      await pg.fill('#custo_reposicao_anual', '180000'); await pg.fill('#custo_suplementacao_anual', '60000');
      checks.completo = await pg.evaluate(() => ({
        status: document.getElementById('od-estresse-status').hidden,
        faltam: document.querySelectorAll('#od-b3 .od-field--missing').length,
        chip: document.querySelector('#od-b3 .od-block__status').textContent,
      }));
      overflows.push(await over());

      // Erro de validação em bloco recolhido abre o bloco antes de focar.
      await pg.click('#od-b3 .od-block__toggle');
      await pg.evaluate(() => OrkavynDash.revelarCampo('preco_arroba_base'));
      checks.revelou = await pg.evaluate(() => !document.getElementById('od-b3-body').hidden &&
        document.querySelector('#od-b3 .od-block__toggle').getAttribute('aria-expanded') === 'true');

      // Menu "Mais opções ▾": itens secundários só dentro dele; cabe na viewport.
      checks.foraDoMenu = await pg.evaluate(() => {
        const sec = [...document.querySelectorAll('.ork-section-herd button')].filter(x => /Template|Baixar Ficha|Instruções/.test(x.textContent));
        return sec.length === 3 && sec.every(x => x.closest('.od-more__menu'));
      });
      await pg.click('#od-more-faixa > summary');
      const menu = await pg.evaluate(() => { const r = document.querySelector('#od-more-faixa .od-more__menu').getBoundingClientRect();
        return { l: r.left, r: r.right, vw: innerWidth, w: r.width }; });
      checks.menuNaTela = menu.l >= 0 && menu.r <= menu.vw && menu.w > 0;
      overflows.push(await over());
      await pg.keyboard.press('Escape');
      checks.menuFechou = await pg.evaluate(() => !document.getElementById('od-more-faixa').open);

      // Aviso GEP some quando o desembolso do produtor é informado.
      checks.gep = await pg.evaluate(() => {
        const a = document.getElementById('aviso-gep-padrao'); const c = document.getElementById('c-desemb');
        const antes = a.hidden; c.value = '95'; c.dispatchEvent(new Event('input', { bubbles: true }));
        const depois = a.hidden; c.value = ''; c.dispatchEvent(new Event('input', { bubbles: true }));
        return { antes, depois, volta: !a.hidden };
      });

      // Rótulos iguais entre dock (desktop/mobile) e abas legadas.
      checks.rotulos = await pg.evaluate(() => {
        const dock = [...document.querySelectorAll('.od-dock > .od-dock__item[data-ork-nav] span')].map(x => x.textContent.trim());
        const leg = [...document.querySelectorAll('.tab-btn')].map(x => x.textContent.trim());
        return { dock, ok: ['Nova análise', 'Resultado', 'Cenários', 'Histórico'].every((t, i) => dock[i] === t && leg[i] === t) };
      });

      // Saudação sem identificador bruto (sem '@').
      checks.saudacao = await pg.evaluate(() => document.getElementById('od-cover-title').textContent.trim());

      // Dock nunca cobre o fim da página; tabela de faixas sem overflow.
      await pg.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      checks.dock = await pg.evaluate(() => {
        const dock = document.querySelector('.od-dock').getBoundingClientRect();
        const ws = document.querySelector('.ork-workspace');
        const pb = parseFloat(getComputedStyle(ws).paddingBottom);
        const panel = document.getElementById('panel-entrada').getBoundingClientRect();
        return { pb, dockH: dock.height, folga: pb >= dock.height + 16, conteudoAcimaDoDock: panel.bottom <= dock.top + 1 };
      });
      checks.tabela = await pg.evaluate(() => {
        const t = document.querySelector('.itbl'); const r = t.getBoundingClientRect();
        const row = t.querySelector('tbody tr'); const inp = row.querySelector('input').getBoundingClientRect();
        return { cards: getComputedStyle(row).display === 'grid', cabe: r.right <= innerWidth + 1 && inp.right <= innerWidth + 1, vw: innerWidth };
      });
      overflows.push(await over());

      const mobile = vp.width < 600;
      const ok = overflows.every(o => o <= 0) && errs.length === 0 &&
        checks.recolhidos && checks.abriu && checks.parcial.status && checks.parcial.faltam === 2 && /Incompleto 1\/3/.test(checks.parcial.chip) &&
        checks.completo.status && checks.completo.faltam === 0 && checks.completo.chip === 'Completo' && checks.revelou &&
        checks.foraDoMenu && checks.menuNaTela && checks.menuFechou &&
        !checks.gep.antes && checks.gep.depois && checks.gep.volta && checks.rotulos.ok && !checks.saudacao.includes('@') &&
        checks.dock.folga && checks.dock.conteudoAcimaDoDock && checks.tabela.cabe && checks.tabela.cards === mobile;
      if (!ok) fail++;
      console.log(vp.width, tema, ok ? 'OK' : 'FAIL', JSON.stringify({ overflows, checks, errs }));
      await pg.screenshot({ path: `${process.argv[3]}/form-${vp.width}-${tema}.png`, fullPage: false });
      await ctx.close();
    }
  await b.close(); srv.close(); process.exit(fail ? 1 : 0);
})();
