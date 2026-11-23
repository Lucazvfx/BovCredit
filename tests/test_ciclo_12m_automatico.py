"""Ciclo 12m calculado junto com a classificação, com o ciclo do modelo como padrão.

Não toca nas fórmulas do 12m (cobertas em test_ciclo_pecuario*.py): prova a COLA
em /api/classificar — padrão vindo do modelo, override explícito recalculando,
tipos mistos e gatilhos de revisão humana sem fluxo automático — e a renderização
do resultado sem ação manual prévia.
"""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

import app as app_mod
import database as db
from app import app

ROOT = Path(__file__).parents[1]
CRIA = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]


def _cli():
    db.init_db()
    email = f'c12-{uuid.uuid4().hex[:8]}@example.com'
    db.criar_usuario(email, 'C12', 'senha123')
    u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def _post(**extra):
    p = {'valores': CRIA, 'preco': 330, 'credito_valor': sum(CRIA) * 1200,
         'prazo_meses': 36, 'juros_aa': 0.125}
    p.update(extra)
    r = _cli().post('/api/classificar', json=p)
    assert r.status_code == 200
    return r.get_json()


def _forcar(monkeypatch, **campos):
    """Mantém a classificação real, só sobrescreve campos do resultado."""
    real = app_mod.classificar

    def falso(*a, **k):
        return {**real(*a, **k), **campos}
    monkeypatch.setattr(app_mod, 'classificar', falso)


# (a) classificação já devolve o 12m do ciclo descoberto pelo modelo
def test_classificacao_devolve_12m_do_ciclo_do_modelo():
    d = _post()
    c = d['parecer']['ciclo_pecuario']
    assert d['tipo'] == 'CRIA'
    assert c['disponivel'] is True and len(c['meses']) == 12
    assert c['sistema'] == 'cria'
    assert c['ciclo_classificado'] == 'CRIA' and c['sistema_origem'] == 'modelo'
    json.dumps(c)


def test_12m_automatico_e_identico_ao_explicito_com_o_mesmo_sistema():
    auto = _post()['parecer']['ciclo_pecuario']
    expl = _post(sistema_produtivo='cria')['parecer']['ciclo_pecuario']
    for k in ('meses', 'vale_caixa', 'dscr_anual', 'receita_anual'):
        assert auto[k] == expl[k]


def test_12m_automatico_nao_muda_o_veredito():
    auto = _post()['parecer']['conclusao']
    # O fluxo é informativo: o veredito coincide com o do override explícito.
    expl = _post(sistema_produtivo='cria')['parecer']['conclusao']
    for k in ('recomendacao', 'dscr', 'dscr_minimo', 'ano_critico'):
        assert auto.get(k) == expl.get(k)


@pytest.mark.parametrize('tipo, sistema', [
    ('RECRIA', 'recria'), ('ENGORDA', 'engorda'),
    ('CICLO_COMPLETO', 'ciclo_completo')])
def test_cada_tipo_puro_usa_o_perfil_correspondente(monkeypatch, tipo, sistema):
    _forcar(monkeypatch, tipo=tipo, classificacao=tipo)
    c = _post()['parecer']['ciclo_pecuario']
    assert c['sistema'] == sistema and c['ciclo_classificado'] == tipo


@pytest.mark.parametrize('tipo', ['CRIA_RECRIA', 'RECRIA_ENGORDA'])
def test_tipo_misto_nao_inventa_perfil(monkeypatch, tipo):
    _forcar(monkeypatch, tipo=tipo, classificacao=tipo)
    c = _post()['parecer']['ciclo_pecuario']
    assert c['disponivel'] is False
    assert 'escolha' in c['motivo'] and c['ciclo_classificado'] == tipo
    assert c['sistema_origem'] is None


def test_tipo_misto_com_override_explicito_calcula(monkeypatch):
    _forcar(monkeypatch, tipo='CRIA_RECRIA', classificacao='CRIA_RECRIA')
    c = _post(sistema_produtivo='recria')['parecer']['ciclo_pecuario']
    assert c['disponivel'] is True and c['sistema'] == 'recria'
    assert c['ciclo_classificado'] == 'CRIA_RECRIA'


@pytest.mark.parametrize('motivo', ['rebanho_zerado', 'rebanho_fora_faixa'])
def test_gatilhos_de_revisao_humana_nao_geram_12m_automatico(monkeypatch, motivo):
    _forcar(monkeypatch, revisao_humana=True, motivos_revisao=[motivo])
    d = _post()
    c = d['parecer']['ciclo_pecuario']
    assert c['disponivel'] is False and 'revisão humana' in c['motivo']
    assert d['revisao_humana'] is True and motivo in d['motivos_revisao']


# (b) override manual recalcula o 12m e mantém o ciclo do modelo visível
def test_override_manual_recalcula_o_12m_e_preserva_o_ciclo_do_modelo():
    padrao = _post()['parecer']['ciclo_pecuario']
    ovr = _post(sistema_produtivo='engorda')['parecer']['ciclo_pecuario']
    assert padrao['sistema'] == 'cria' and ovr['sistema'] == 'engorda'
    assert ovr['sistema_origem'] == 'analista'
    assert ovr['ciclo_classificado'] == padrao['ciclo_classificado'] == 'CRIA'
    assert ovr['meses'] != padrao['meses']


def test_override_com_rebanho_em_revisao_ainda_calcula(monkeypatch):
    _forcar(monkeypatch, revisao_humana=True, motivos_revisao=['rebanho_zerado'])
    c = _post(sistema_produtivo='cria')['parecer']['ciclo_pecuario']
    assert c['sistema_origem'] == 'analista'


# (c) Resultado renderiza o 12m sem ação manual prévia (navegador real)
_RENDER_JS = r"""
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const [, , raiz, jsonPath] = process.argv;
  const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
  // Mesmos estilos da página real (reset/box-sizing vêm de style.css).
  const css = ['style.css', 'orkavyn-fields.css', 'orkavyn-dashboard.css']
    .map((f) => fs.readFileSync(raiz + '/static/' + f, 'utf8')).join('\n');
  const js = fs.readFileSync(raiz + '/static/orkavyn-dashboard.js', 'utf8');
  const browser = await chromium.launch();
  const out = {};
  for (const [nome, w, h] of [['desktop', 1440, 900], ['mobile', 390, 844]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.setContent('<!doctype html><html><head><style>' + css +
      '</style></head><body><div id="result-wrap"><p>legado</p></div></body></html>');
    await page.addScriptTag({ content: js });
    await page.evaluate((d) => window.OrkavynDash.renderParecer(d), data);
    out[nome] = await page.evaluate(() => ({
      kpi: document.querySelector('.od-kpis') ? document.querySelector('.od-kpis').innerText : '',
      aba: !!document.getElementById('od-tab-ciclo'),
      painel: document.getElementById('od-panel-ciclo').innerText,
      linhas: document.querySelectorAll('#od-panel-ciclo tbody tr').length,
      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    }));
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(shutil.which('node') is None or shutil.which('npm') is None,
                    reason='node/npm ausente')
def test_resultado_renderiza_12m_sem_confirmacao_previa(tmp_path):
    data = _post()  # nenhuma ação manual: nada de sistema_produtivo nem confirmar
    (tmp_path / 'data.json').write_text(json.dumps(data), encoding='utf-8')
    (tmp_path / 'render.js').write_text(_RENDER_JS, encoding='utf-8')
    r = subprocess.run(['node', str(tmp_path / 'render.js'), str(ROOT),
                        str(tmp_path / 'data.json')],
                       capture_output=True, text=True, timeout=120,
                       env={**__import__('os').environ,
                            'NODE_PATH': subprocess.run(
                                ['npm', 'root', '-g'], capture_output=True,
                                text=True).stdout.strip()})
    if r.returncode != 0 and 'Cannot find module' in r.stderr:
        pytest.skip('playwright ausente')
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    for viewport in ('desktop', 'mobile'):
        o = out[viewport]
        assert o['aba'] and o['linhas'] == 12, viewport
        assert 'Vale de caixa (12m)' in o['kpi'] and 'Informe o sistema' not in o['kpi']
        assert 'Ciclo classificado' in o['painel'] and 'CRIA' in o['painel']
        assert 'adotado da classificação' in o['painel']
        assert o['overflow'] is False, f'overflow horizontal em {viewport}'
