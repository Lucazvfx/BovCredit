"""
Avaliação offline do retreino com casos reais confirmados.

Cobre: seleção estrita (só confirmado e não descartado), métricas com amostra
real pequena/vazia, critério de promoção, escrita explícita do artefato e a
não regressão do motor (o pkl em uso não muda e o app não importa o avaliador).
"""
import hashlib
import os
import uuid
from functools import lru_cache

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import avaliar_retreino as av
import database as db
import ml_engine
from ml_engine import TIPOS

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Modelo e dados pequenos ────────────────────────────────────────────────
def _modelo_pequeno():
    return Pipeline([('scaler', StandardScaler()),
                     ('model', LogisticRegression(max_iter=500))])


@lru_cache(maxsize=1)
def _dados():
    """(X_base, y_base, vetores_reais, y_real) a partir do CSV de treino."""
    X, y = ml_engine._carregar_dataset_csv()
    base, reais = [], []
    vistos = {}
    for v, r in zip(X, y):
        n = vistos.get(r, 0)
        vistos[r] = n + 1
        if n < 60:
            base.append((v, r))
        elif n < 70:
            reais.append((v, r))
    X_base = np.array([ml_engine.extrair_features(v) for v, _ in base])
    y_base = np.array([r for _, r in base])
    return X_base, y_base, [v for v, _ in reais], [r for _, r in reais]


def _itens(n_por_classe=10, corrigir_cada=3):
    _, _, vetores, ys = _dados()
    itens, cont = [], {}
    for v, r in zip(vetores, ys):
        cont[r] = cont.get(r, 0) + 1
        if cont[r] > n_por_classe:
            continue
        k = len(itens)
        errada = TIPOS[(r + 1) % len(TIPOS)] if k % corrigir_cada == 0 else None
        itens.append({'vetor': v, 'y': r, 'tipo': TIPOS[r],
                      'classe_ml': errada or TIPOS[r], 'origem': f'teste({k})'})
    return itens


def _atual():
    X_base, y_base, _, _ = _dados()
    return _modelo_pequeno().fit(X_base, y_base)


def _avaliar(itens, **kw):
    X_base, y_base, _, _ = _dados()
    return av.avaliar_candidato(itens, _atual(), X_base, y_base,
                                build_model=_modelo_pequeno, **kw)


def _sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


# ── Seleção estrita (banco) ────────────────────────────────────────────────
def _vetor_unico():
    base = 1_000_000 + uuid.uuid4().int % 1_000_000
    return [base + i for i in range(10)]


@pytest.fixture(autouse=True, scope='module')
def _limpa_casos_do_teste():
    """O gestao.db local é compartilhado: não deixe lixo no treino."""
    yield
    db._exec('DELETE FROM casos_reais WHERE user_id=900002', commit=True)


def _caso(vetor, classe_ml='CRIA'):
    return db.criar_caso_real(vetor, classe_ml, 70, origem='MANUAL',
                              user_id=900002, empresa_id=900002)


def test_selecao_so_inclui_confirmados_nao_descartados():
    db.init_db()
    v_pend, v_conf, v_conf_desc, v_desc = (_vetor_unico() for _ in range(4))
    _caso(v_pend)
    id_conf = _caso(v_conf, classe_ml='CRIA')
    db.confirmar_caso_real(id_conf, 'ENGORDA')
    id_cd = _caso(v_conf_desc)
    db.confirmar_caso_real(id_cd, 'CRIA')
    db.descartar_caso_real(id_cd, 'ficha ilegível')
    db.descartar_caso_real(_caso(v_desc), 'duplicada')

    itens = db.exportar_treino_detalhado()
    por_vetor = {tuple(float(x) for x in i['vetor']): i for i in itens}
    chave = lambda v: tuple(float(x) for x in v)  # noqa: E731

    assert chave(v_conf) in por_vetor
    for fora in (v_pend, v_conf_desc, v_desc):
        assert chave(fora) not in por_vetor
    item = por_vetor[chave(v_conf)]
    assert item['tipo'] == 'ENGORDA' and item['y'] == TIPOS.index('ENGORDA')
    assert item['classe_ml'] == 'CRIA'          # previsão original preservada
    assert av._corrigido(item)


def test_exportar_treino_e_a_visao_xy_da_selecao_detalhada():
    db.init_db()
    id_ = _caso(_vetor_unico())
    db.confirmar_caso_real(id_, 'RECRIA')
    itens = db.exportar_treino_detalhado()
    X, y = db.exportar_treino()
    assert X == [i['vetor'] for i in itens]
    assert y == [i['y'] for i in itens]


def test_vetor_corrompido_nao_derruba_a_selecao():
    db.init_db()
    rid = db.salvar(valores=[1, 2, 3], class_ml='CRIA', confianca=50)
    db.confirmar(rid, 'CRIA')
    v_ok = _vetor_unico()
    db.confirmar_caso_real(_caso(v_ok), 'CRIA')
    itens = db.exportar_treino_detalhado()
    assert all(len(i['vetor']) == 10 for i in itens)
    assert not any(i['origem'] == f'registro({rid})' for i in itens)
    assert [float(x) for x in v_ok] in [[float(x) for x in i['vetor']]
                                         for i in itens]


# ── Guarda de desequilíbrio ────────────────────────────────────────────────
def test_classe_com_poucos_exemplos_reais_fica_fora():
    itens = _itens(10)
    # CRIA ganha só 2 exemplos reais → abaixo do mínimo
    itens = [i for i in itens if i['tipo'] != 'CRIA'] + \
            [i for i in itens if i['tipo'] == 'CRIA'][:2]
    aceitos, excluidas = av.selecionar_reais(itens)
    assert excluidas == {'CRIA': 2}
    assert all(i['tipo'] != 'CRIA' for i in aceitos)


def test_dedup_por_vetor_e_rotulo_ambiguo_sai():
    v = [10] * 10
    dup = [{'vetor': v, 'y': 0, 'tipo': 'CRIA', 'classe_ml': None, 'origem': 'a'},
           {'vetor': list(v), 'y': 0, 'tipo': 'CRIA', 'classe_ml': None, 'origem': 'b'}]
    aceitos, _ = av.selecionar_reais(dup, min_por_classe=1)
    assert len(aceitos) == 1
    w = [20] * 10
    amb = [{'vetor': w, 'y': 0, 'tipo': 'CRIA', 'classe_ml': None, 'origem': 'c'},
           {'vetor': w, 'y': 1, 'tipo': 'RECRIA', 'classe_ml': None, 'origem': 'd'}]
    assert av.selecionar_reais(amb, min_por_classe=1)[0] == []


# ── Métricas ───────────────────────────────────────────────────────────────
def test_metricas_amostra_vazia():
    m = av.calcular_metricas([], [])
    assert m['n'] == 0 and m['acuracia'] is None and m['matriz_confusao'] is None
    assert av.taxa_acerto_corrigidos([], [], [])['taxa'] is None


def test_metricas_por_ciclo_e_matriz():
    y_true = [0, 0, 1, 1, 2]
    y_pred = [0, 1, 1, 1, 2]
    m = av.calcular_metricas(y_true, y_pred)
    assert m['n'] == 5 and m['acuracia'] == 0.8
    assert len(m['matriz_confusao']) == len(TIPOS)
    assert m['matriz_confusao'][0][1] == 1
    assert set(m['por_ciclo']) == {'CRIA', 'RECRIA', 'ENGORDA'}
    assert m['por_ciclo']['CRIA']['recall'] == 0.5
    assert m['por_ciclo']['RECRIA']['suporte'] == 2


def test_taxa_de_acerto_em_corrigidos():
    r = av.taxa_acerto_corrigidos([0, 1, 2, 3], [0, 0, 2, 3],
                                  [True, True, False, False])
    assert r == {'n': 2, 'acertos': 1, 'taxa': 0.5}


# ── Avaliação comparativa ──────────────────────────────────────────────────
def _nao_treina():
    raise AssertionError('não deveria treinar candidato sem amostra suficiente')


@pytest.mark.parametrize('itens', [[], _itens(1)[:4], None])
def test_amostra_vazia_ou_pequena_nao_avalia_nem_promove(itens, tmp_path):
    itens = itens if itens is not None else _itens(3)   # 18 < MIN_TOTAL_REAIS
    X_base, y_base, _, _ = _dados()
    rel = av.avaliar_candidato(itens, _atual(), X_base, y_base,
                               build_model=_nao_treina)
    assert rel['status'] == 'amostra_insuficiente'
    assert rel['recomendar_promocao'] is False
    assert 'candidato' not in rel
    destino = tmp_path / 'm.pkl'
    with pytest.raises(RuntimeError):
        av.promover([], X_base, y_base, rel, str(destino))
    assert not destino.exists()


def test_avaliacao_cv_cobre_cada_caso_uma_vez():
    itens = _itens(10)
    rel = _avaliar(itens, modo='cv', n_splits=3)
    assert rel['status'] == 'ok'
    assert rel['n_avaliados'] == rel['n_usados'] == len(itens)
    for lado in ('atual', 'candidato'):
        assert rel[lado]['n'] == len(itens)
        assert 0 <= rel[lado]['acuracia'] <= 1
        assert len(rel[lado]['matriz_confusao']) == len(TIPOS)
    assert rel['corrigidos']['atual']['n'] == rel['n_corrigidos'] > 0
    assert set(rel['atipicidade']['por_nivel']) >= {'tipico', 'atipico', 'muito_atipico'}
    assert isinstance(rel['recomendar_promocao'], bool)


def test_avaliacao_holdout_usa_parte_dos_casos():
    itens = _itens(10)
    rel = _avaliar(itens, modo='holdout')
    assert rel['status'] == 'ok' and rel['n_splits'] == 1
    assert 0 < rel['n_avaliados'] < len(itens)


def test_classe_rara_nao_entra_na_avaliacao():
    itens = [i for i in _itens(10) if i['tipo'] != 'CRIA'] + \
            [i for i in _itens(10) if i['tipo'] == 'CRIA'][:2]
    rel = _avaliar(itens)
    assert rel['classes_excluidas'] == {'CRIA': 2}
    assert 'CRIA' not in rel['por_classe']
    assert 'CRIA' not in rel['candidato']['por_ciclo']


def test_modo_invalido():
    with pytest.raises(ValueError):
        _avaliar(_itens(10), modo='x')


# ── Critério de promoção ───────────────────────────────────────────────────
def _aval(f1_a=0.80, f1_c=0.85, acc_a=0.80, acc_c=0.85, rec_a=0.8, rec_c=0.8,
          corr_a=0.5, corr_c=0.6):
    return {
        'status': 'ok',
        'atual': {'f1_macro': f1_a, 'acuracia': acc_a,
                  'por_ciclo': {'CRIA': {'recall': rec_a}}},
        'candidato': {'f1_macro': f1_c, 'acuracia': acc_c,
                      'por_ciclo': {'CRIA': {'recall': rec_c}}},
        'corrigidos': {'atual': {'n': 4, 'taxa': corr_a},
                       'candidato': {'n': 4, 'taxa': corr_c}},
    }


def test_decisao_aprova_ganho_claro():
    assert av.decidir_promocao(_aval()) == (True, [])


@pytest.mark.parametrize('kw,motivo', [
    ({'f1_c': 0.805}, 'ganho_de_f1_insuficiente'),
    ({'f1_c': 0.90, 'acc_c': 0.70}, 'acuracia_regrediu'),
    ({'corr_c': 0.4}, 'pior_nos_casos_corrigidos'),
    ({'rec_c': 0.5}, 'recall_caiu_CRIA'),
])
def test_decisao_recusa_regressao(kw, motivo):
    ok, motivos = av.decidir_promocao(_aval(**kw))
    assert ok is False and motivo in motivos


def test_decisao_recusa_sem_avaliacao_ok():
    assert av.decidir_promocao({'status': 'amostra_insuficiente'})[0] is False


# ── Promoção explícita ─────────────────────────────────────────────────────
def test_promover_grava_com_backup_e_nao_toca_o_pipeline_global(tmp_path):
    X_base, y_base, _, _ = _dados()
    destino = tmp_path / 'modelo.pkl'
    destino.write_bytes(b'antigo')
    global_antes = ml_engine._pipeline
    aval = {'recomendar_promocao': True, 'motivos': [], 'modo': 'cv',
            'n_avaliados': 1, 'atual': {}, 'candidato': {}}
    stats = av.promover(_itens(10), X_base, y_base, aval, str(destino),
                        build_model=_modelo_pequeno)
    assert (tmp_path / 'modelo.pkl.bak').read_bytes() == b'antigo'
    pipeline = av.carregar_pipeline_atual(str(destino))
    assert pipeline.predict(X_base[:3]).shape == (3,)
    assert stats['n_confirmados'] == 60
    assert ml_engine._pipeline is global_antes
    # O boot do app (app.py) lê estas chaves do pkl em uso: têm de existir.
    atuais = ml_engine.carregar_modelo()
    ml_engine._pipeline = global_antes   # carregar_modelo reatribui o global
    assert {'accuracy_mean', 'accuracy_std', 'f1_macro_mean', 'f1_macro_std',
            'n_samples', 'n_features', 'n_csv'} <= set(atuais) & set(stats)
    assert (os.stat(destino).st_mode & 0o777) == 0o644
    assert not [p for p in tmp_path.iterdir() if p.suffix == '.tmp']


def test_promover_recusa_sem_aprovacao(tmp_path):
    X_base, y_base, _, _ = _dados()
    destino = tmp_path / 'modelo.pkl'
    destino.write_bytes(b'antigo')
    with pytest.raises(RuntimeError):
        av.promover(_itens(10), X_base, y_base,
                    {'recomendar_promocao': False, 'motivos': ['x']},
                    str(destino), build_model=_modelo_pequeno)
    assert destino.read_bytes() == b'antigo'


# ── Não regressão do motor ─────────────────────────────────────────────────
def test_avaliar_nao_altera_o_artefato_em_uso():
    pkl = ml_engine._MODEL_PATH
    antes = _sha(pkl)
    _avaliar(_itens(10))
    assert _sha(pkl) == antes


def test_motor_classifica_com_o_pkl_versionado():
    assert ml_engine.carregar_modelo() is not None
    r = ml_engine.classificar([80, 80, 50, 50, 60, 60, 90, 40, 220, 60],
                              bois_vendidos=10)
    assert r['tipo'] in TIPOS
    assert 'revisao_humana' in r and 'atipicidade' in r
    n = ml_engine._pipeline.named_steps['scaler'].n_features_in_
    assert n == len(ml_engine.extrair_features([1] * 10))
    assert TIPOS == ['CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO',
                     'RECRIA_ENGORDA', 'CRIA_RECRIA']


@pytest.mark.parametrize('arq', ['app.py', 'ml_engine.py', 'gunicorn.conf.py'])
def test_avaliador_nao_e_carregado_pelo_app_nem_pelo_boot(arq):
    with open(os.path.join(RAIZ, arq), encoding='utf-8') as f:
        assert 'avaliar_retreino' not in f.read()
