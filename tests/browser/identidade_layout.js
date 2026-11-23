const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = process.argv[2];
const srv = http.createServer((q, r) => {
  let f = path.join(root, q.url.split('?')[0] === '/' ? 'index.html' : q.url.split('?')[0]);
  if (!fs.existsSync(f)) { r.writeHead(404); return r.end(); }
  const t = f.endsWith('.css') ? 'text/css' : f.endsWith('.js') ? 'text/javascript' : f.endsWith('.html') ? 'text/html' : 'application/octet-stream';
  r.writeHead(200, { 'content-type': t }); r.end(fs.readFileSync(f));
}).listen(0);
// Verificação de layout do painel de identidade institucional (tests/test_identidade_institucional.py).
// Uso: node identidade_layout.js <dir com index.html + static/>
const longo = 'Nome-de-exibicao-muito-longo-sem-espacos-para-forcar-quebra-na-tela-estreita-0123456789-0123456789';
(async () => {
  const b = await chromium.launch(); const port = srv.address().port; let fail = 0;
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }])
    for (const admin of [true, false]) {
      const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
      const errs = []; pg.on('pageerror', e => errs.push(String(e)));
      await pg.route('**/api/**', r => {
        const u = r.request().url(); let body = {};
        if (u.includes('/api/empresa/identidade')) body = { pode_editar: admin, identidade: { nome_exibicao: longo, cnpj: '11222333000181', cnpj_formatado: '11.222.333/0001-81', responsavel_nome: 'Responsável Técnico com Nome Bastante Extenso', responsavel_registro: 'CRMV-MT 1234' } };
        else if (u.includes('/api/empresa/perfil')) body = { nome_consultoria: 'Consultoria', logo_base64: '' };
        r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
      });
      await pg.goto(`http://localhost:${port}/`, { waitUntil: 'load' });
      await pg.evaluate(() => abrirMarcaModal());
      await pg.waitForFunction(() => document.getElementById('marca-cnpj').value !== '');
      const info = await pg.evaluate(() => {
        const card = document.querySelector('#marca-modal-overlay .card').getBoundingClientRect();
        return { sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
          cnpj: document.getElementById('marca-cnpj').value,
          travado: document.getElementById('marca-cnpj').disabled,
          nomeTravado: document.getElementById('marca-nome').disabled, salvarTravado: document.getElementById('marca-salvar').disabled,
          cardL: card.left, cardR: card.right, cardB: card.bottom, vw: innerWidth, vh: innerHeight,
          inputsFora: [...document.querySelectorAll('#marca-identidade input')].filter(i => i.getBoundingClientRect().right > card.right + 1).length };
      });
      const ok = info.sw <= info.cw && info.cnpj === '11.222.333/0001-81' && info.travado === !admin && info.nomeTravado === !admin && info.salvarTravado === !admin
        && info.cardL >= 0 && info.cardR <= info.vw && info.cardB <= info.vh + 1 && info.inputsFora === 0 && errs.length === 0;
      console.log(ok ? ' OK ' : ' FALHA ', vp.width + 'x' + vp.height, admin ? 'admin' : 'analista', JSON.stringify(info), errs.join('|'));
      if (!ok) fail = 1;
      await ctx.close();
    }
  await b.close(); srv.close(); process.exit(fail);
})();
