const { chromium } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = process.argv[2];
const srv = http.createServer((q, r) => {
  let f = path.join(root, q.url.split('?')[0] === '/' ? 'index.html' : q.url.split('?')[0]);
  if (!fs.existsSync(f)) { r.writeHead(404); return r.end(); }
  const t = f.endsWith('.css') ? 'text/css' : f.endsWith('.js') ? 'text/javascript' : f.endsWith('.html') ? 'text/html' : 'application/octet-stream';
  r.writeHead(200, { 'content-type': t }); r.end(fs.readFileSync(f));
}).listen(0);
// Verificação de layout de papéis e propostas (executada por tests/test_papeis_propostas.py).
// Uso: node alcada_layout.js <dir com index.html + static/> <dir de screenshots>
const longo = 'CT-2026-0001-REFERENCIA-MUITO-LONGA-SEM-ESPACOS-PARA-FORCAR-QUEBRA-NA-TELA-ESTREITA-0000000000';
const prop = (id, st, alc, pode) => ({ id, referencia: id === 1 ? longo : 'CT-' + id, valor_pretendido: 800000 + id,
  prazo_meses: 60, status_alcada: alc, status: st, motivos_texto: ['Valor acima da alçada do analista.'],
  criado_por_nome: 'Analista com nome bastante extenso para testar quebra', criado_em: '2026-11-20 10:00:00',
  parecer_decisor: st === 'em_analise' ? null : 'Parecer longo '.repeat(20), decidido_por_nome: st === 'em_analise' ? null : 'Aprovador',
  decidido_em: st === 'em_analise' ? null : '2026-11-21 09:00:00', pode_decidir: pode });
const politica = { alcada_analista: 500000, alcada_comite: 3000000, prazo_max_meses: 60, margem_capacidade_pct: 100, comite_se_revisao_humana: true, padrao: true };
const membros = [1, 2, 3].map(i => ({ user_id: i, nome: 'Membro ' + i + ' com nome extenso', email: 'membro.com.email.bem.longo.' + i + '@consultoria-exemplo.com.br', papel: i === 1 ? 'admin' : 'analista' }));
const papeis = [{ id: 'admin', rotulo: 'Administrador' }, { id: 'aprovador', rotulo: 'Aprovador' }, { id: 'analista', rotulo: 'Analista' }];
(async () => {
  const b = await chromium.launch(); const port = srv.address().port; let fail = 0;
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }])
    for (const admin of [true, false]) {
      const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 1 }); const pg = await ctx.newPage();
      const errs = []; pg.on('pageerror', e => errs.push(String(e)));
      await pg.route('**/api/**', r => {
        const u = r.request().url(); let body = {};
        if (u.includes('/api/politica-alcada')) body = { politica, pode_editar: admin };
        else if (u.includes('/api/propostas')) body = { meu_papel: admin ? 'admin' : 'analista', propostas: [prop(1, 'em_analise', 'requer_comite', admin), prop(2, 'aprovado', 'fora_alcada', false), prop(3, 'em_analise', 'fora_alcada', false)] };
        else if (u.includes('/api/empresa/papeis')) body = { meu_papel: admin ? 'admin' : 'analista', papeis, membros: admin ? membros : [] };
        r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
      });
      await pg.goto(`http://localhost:${port}/`, { waitUntil: 'load' });
      await pg.evaluate(() => showTab('alcada'));
      await pg.waitForSelector('#prop-lista strong');
      await pg.waitForTimeout(150);
      const info = await pg.evaluate(() => {
        const dock = document.querySelector('.od-dock'); const r = dock && dock.getBoundingClientRect();
        const txt = document.getElementById('panel-alcada').innerText;
        return { props: document.querySelectorAll('#prop-lista strong').length,
          decidir: document.querySelectorAll('#prop-lista [data-act="decidir"]').length,
          equipe: !document.getElementById('eq-card').hidden, selects: document.querySelectorAll('#eq-lista select').length,
          sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
          undef: /\bundefined\b|\bNaN\b|\bnull\b/.test(txt),
          dock: r ? { l: r.left, r: r.right, vw: innerWidth } : null };
      });
      const ok = info.props === 3 && info.decidir === (admin ? 1 : 0) && info.equipe === admin && info.selects === (admin ? 3 : 0)
        && info.sw <= info.cw && !info.undef && errs.length === 0 && (!info.dock || (info.dock.l >= 0 && info.dock.r <= info.dock.vw));
      if (!ok) fail++;
      console.log(vp.width, admin ? 'admin' : 'analista', ok ? 'OK' : 'FAIL', JSON.stringify({ ...info, errs }));
      await pg.screenshot({ path: `${process.argv[3]}/alcada-${vp.width}-${admin ? 'admin' : 'analista'}.png`, fullPage: true });
      await ctx.close();
    }
  await b.close(); srv.close(); process.exit(fail ? 1 : 0);
})();
