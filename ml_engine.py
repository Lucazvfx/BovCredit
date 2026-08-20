"""
Fluxo de caixa — Motor de Machine Learning
Classifica tipo de exploração bovina e simula cenários financeiros.
Versão melhorada com dataset CSV grande, ensemble estável e parâmetros atualizados para Rondônia 2026.
"""
import os
import csv as _csv
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, cross_validate
import joblib
import logging
import warnings
from sklearn import __version__ as _sklearn_version

_log = logging.getLogger(__name__)
warnings.filterwarnings('ignore')
from services.base_reprodutiva import base_reprodutiva
from services.pesos_rebanho import arrobas_categorias
from services.benchmarks_nacionais import DESFRUTE_MODALIDADE as _FAIXAS_DESFRUTE
from services.parametros_zootecnicos import (
    NATALIDADE_PCT, DESMAME_PCT,
    PESO_BOI_ARR, PESO_VACA_ARR, PESO_BEZERRA_ARR, PESO_GARROTE_ARR,
    MORTALIDADE_ADULTO_PCT, MORTALIDADE_BEZERRA_PCT, PESO_JOVEM_F_ARR,
    TROCA_ARROBAS_BOI_MAGRO, TROCA_ARROBAS_BEZERRO,
    taxa_desmama_efetiva, natalidade_de_prenhez,
)
from services.nivel_tecnologico import GMD_PADRAO_SEM_NIVEL as _GMD_PADRAO_SEM_NIVEL

# ── Reposição 1:1 precificada ────────────────────────────────────────────────
# Recria e engorda vendem o lote e repõem comprando animais magros. O material
# de treinamento define a regra operacional: "1 animal vendido = 1 animal
# reposto". Sem precificar essa compra, o resultado de uma engorda fica ~3,9×
# superestimado — o modelo vendia o peso total de saída pagando só a manutenção.
#
# Reversível: REPOSICAO_PRECIFICADA=0 volta ao comportamento anterior
# (compra aparece no balanço de animais, mas não custa nada).
_REPOSICAO_PRECIFICADA = os.environ.get('REPOSICAO_PRECIFICADA', '1') != '0'

# Na cria, o excedente da coorte 0–12m sobre a produção própria foi comprado.
# `1` mantém a estrutura do rebanho comprando essa diferença todo ano (estoque
# estável, custo de compra no caixa); `0` (default) assume que o produtor para
# de comprar e o rebanho converge para a produção própria. Ver _simular_cria.
_REPOR_COMPRA_DESMAMA = os.environ.get('REPOR_COMPRA_DESMAMA', '0') == '1'

# Razão bezerra/adulto para derivar mort_bezerra quando só mort_adulto é informada
_RAZAO_MORT_BEZERRA = MORTALIDADE_BEZERRA_PCT / MORTALIDADE_ADULTO_PCT  # 3.5

# Participação mínima de matrizes para um rebanho poder ser chamado de CRIA.
# Cria é produzir bezerro, e bezerro vem de vaca: sem base reprodutiva o
# rebanho pode ser predominantemente fêmea e ainda assim não ser cria — é o
# caso da recria de fêmeas, que compra fêmea jovem para engordar ou para virar
# matriz depois.
#
# O valor já era usado em `indice_ciclo`; virou constante nomeada quando passou
# a valer também na guarda de classificação, para não haver dois limiares
# soltos que alguém pudesse mudar só de um lado.
P_MATRIZES_CRIA = 0.18

# Razão mínima entre fêmeas ACIMA de 36 meses e fêmeas de 25–36 meses para o
# rebanho poder ser chamado de cria.
#
# `matrizes` no classificador soma as duas faixas (va[6] + va[8]), o que é
# defensável — fêmea de 25–36m já está em idade de cobertura. Mas a soma
# esconde a forma da pirâmide, e é a forma que distingue cria de recria de
# fêmeas:
#
#   vaca de cria vive de oito a dez anos e SE ACUMULA acima dos 36 meses
#   fêmea de recria é vendida ANTES de parir, e a faixa acima de 36m fica vazia
#
# Medido em rebanhos reais e sintéticos (fac_F ÷ f25_F):
#
#   Recria B de fêmeas (753 cab)                0,02   ← 209 fêmeas 25–36m, 5 acima
#   ficha real de recria, 700 cabeças           1,31
#   cria do teste de conservação                1,89
#   cria sintética de 1.705 cabeças             5,00
#
# A separação é de duas ordens de grandeza. 0,50 fica no meio do vazio: bem
# acima do caso truncado e bem abaixo da menor cria observada.
RAZAO_MATRIZ_MADURA_CRIA = 0.50

# Fração dos machos de 13–24m que atinge o peso de saída dentro do ano e é
# vendida ("venda conforme peso"). Calibrado na ficha real de recria de 700
# cabeças: 195 de 234 machos dessa faixa. É UMA amostra — o número merece
# recalibração quando houver mais fichas; a estrutura, não.
_FRAC_VENDA_RECRIA_M = float(os.environ.get('FRAC_VENDA_RECRIA_M', '0.83'))

# ── A fronteira entre recria e engorda ───────────────────────────────────────
#
# O memorial §16 configurava recria de 10@ a 18@ (300 → 540 kg vivo) e engorda
# de 300 a 520 kg. As duas COMEÇAVAM no mesmo peso e terminavam a uma arroba de
# distância: eram a mesma fase com dois nomes, e a recria vendia o animal como
# se o tivesse terminado.
#
# O argumento que dispensa fonte externa é definicional. Compre Rural, e é a
# definição corrente: "recria ocorre da desmama até o início da reprodução nas
# fêmeas ou até o INÍCIO DA FASE DE ENGORDA nos machos". A saída da recria É a
# entrada da engorda — não pode haver sobreposição.
#
# Os números escolhidos, com as fontes:
#
#   entrada da recria = desmama.  Rehagro dá 6–8@; a Embrapa mediu 177 kg
#     (macho) e 162 kg (fêmea) à desmama, que a 50% de rendimento são 5,4–5,9@.
#     6,5@ (195 kg vivo) fica no encontro dos dois.
#
#   saída da recria.  Rehagro dá 13–14@ explicitamente em arroba; Premix dá
#     360–450 kg vivo, que são 12–15@. 13,5@ (405 kg) é o centro dos dois.
#
#   entrada da engorda = saída da recria, por definição. Sobe de 300 para
#     405 kg. A saída da engorda (520 kg) fica como está — é realista e
#     nenhuma fonte a contesta.
#
# IMPACTO MEDIDO, ficha real de recria de 700 cabeças: a receita do ano 1 cai
# de R$ 1.662.671 para R$ 1.247.003 (−25%) e o resultado vira de +R$ 248.719
# para −R$ 77.174. É correção grande e vai na direção de NEGAR, ao contrário
# dos outros defeitos conhecidos, que todos erravam a favor de aprovar.
#
# CONFLITO DE FONTE, declarado: o 10@/18@ vem do memorial §16, material do
# próprio projeto — não é chute. Contra ele há cinco fontes externas e a
# incoerência interna. A ficha real de 700 cabeças validou o VOLUME de vendas
# (304 contra 315), nunca a receita, então a suíte não cobre esta escolha.
#
# Reversível: PESO_RECRIA_MEMORIAL=1 volta ao par 10@/18@ e à engorda a 300 kg.
_PESO_MEMORIAL = os.environ.get('PESO_RECRIA_MEMORIAL', '0') == '1'
_PESO_ENTRADA_RECRIA_ARR = 10.0 if _PESO_MEMORIAL else 6.5
_PESO_SAIDA_RECRIA_ARR   = 18.0 if _PESO_MEMORIAL else 13.5
_PESO_ENTRADA_ENGORDA_KG = 300.0 if _PESO_MEMORIAL else 405.0

# ==================================================================
# CONSTANTES GLOBAIS
# ==================================================================
_MODEL_PATH = os.path.join(os.path.dirname(__file__), 'gestao_model.pkl')
_CSV_PATH = os.path.join(os.path.dirname(__file__), 'dataset_sintetico_bovino.csv')
# Modalidades pecuárias. A ordem define o rótulo numérico no dataset e NÃO
# pode ser reordenada — os rótulos 0–3 já existem no CSV histórico.
# As duas últimas vieram do material "Análise de Crédito na Pecuária Bovina",
# que trabalha com 5 modalidades + o sistema misto cria/recria:
#   RECRIA_ENGORDA — compra magro e termina (desfrute 60–85%)
#   CRIA_RECRIA    — base de cria + compra de desmama (sistema misto)
TIPOS = ['CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO',
         'RECRIA_ENGORDA', 'CRIA_RECRIA']

# Nomes legíveis das 40 features geradas por extrair_features()
# Ordem exata: norm[0-9] | p_agregados[10-13] | por_cat[14-19] |
#              sinais[20-27] | flags[28-34] | producao[35-39]
FEATURE_NAMES = [
    # 0-9: proporção de cada faixa etária / total
    'Fêmeas 0-5m / total',        'Machos 0-5m / total',
    'Fêmeas 5-13m / total',       'Machos 5-13m / total',
    'Fêmeas 13-25m / total',      'Machos 13-25m / total',
    'Futuras matrizes 25-36m',    'Garrotes 25-36m',
    'Matrizes adultas / total',   'Bois adultos / total',
    # 10-13: grupos agregados
    'Fêmeas jovens % total',      'Machos jovens % total',
    'Matrizes % total',           'Bois % total',
    # 14-19: por categoria / total
    'Bezerras 0-5m / total',      'Bezerros 0-5m / total',
    'Bezerros (0-24m) / total',   'Novilhas recria / total',
    'Garrotes recria / total',    'Jovens recria / total',
    # 20-27: sinais escalados e razões
    'Intensidade matrizes (×5)',  'Intensidade bois (×5)',
    'Intensidade mac. jovens (×5)','Intensidade bezerros (×5)',
    'Razão touro:matriz',         'Razão matriz:touro',
    'Razão macho:fêmea jovem',    'Razão fêmea jovem:matriz',
    # 28-34: flags binárias de composição
    'Flag matrizes >8%',          'Flag bois adultos >10%',
    'Flag machos recria >12%',    'Flag bezerros >20%',
    'Flag perfil engorda',        'Flag perfil cria',
    'Score ciclo completo',
    # 35-39: indicadores de produção
    'Produção esperada / total',  'Eficiência reprodutiva',
    'Transição garrote→adulto',   'Intensidade de engorda',
    'Intensidade de cria',
    # 40-41: sinal de compra de desmama (discrimina cria pura de cria+recria)
    'Coorte 0-12m / produção própria', 'Coorte 0-12m % total',
]

# Parâmetros padrão por ciclo de produção
# (branch 9318087 — útil para simular_cenario com defaults por ciclo)
PARAMS_POR_CICLO = {
    'CRIA': {
        'prop_boi': 30.0,       # 1 touro : 30 matrizes
        'renov_boi_pct': 20.0,
        'desc_mat_pct': 10.0,   # 8–15% descarte (slide ref); conservador 10%
        'venda_bez_pct': 75.0,  # retém 25%, vende 75% (slide ref)
        'nat_pct': NATALIDADE_PCT,
    },
    'RECRIA': {
        'prop_boi': 0.0,
        'renov_boi_pct': 0.0,
        'desc_mat_pct': 0.0,
        'venda_bez_pct': 100.0,
        'nat_pct': 0.0,
    },
    'ENGORDA': {
        'prop_boi': 0.0,
        'renov_boi_pct': 0.0,
        'desc_mat_pct': 0.0,
        'venda_bez_pct': 100.0,
        'nat_pct': 0.0,
    },
    'CICLO_COMPLETO': {
        'prop_boi': 30.0,
        'renov_boi_pct': 20.0,
        'desc_mat_pct': 10.0,   # alinhado com CRIA (8–15%; conservador 10%)
        'venda_bez_pct': 75.0,  # alinhado com CRIA (retém 25%, vende 75%)
        'nat_pct': NATALIDADE_PCT,
    },
    # Compra magro + terminação. Retenção "muito baixa", sem base reprodutiva.
    'RECRIA_ENGORDA': {
        'prop_boi': 0.0,
        'renov_boi_pct': 0.0,
        'desc_mat_pct': 0.0,
        'venda_bez_pct': 100.0,
        'nat_pct': 0.0,
    },
    # Base de cria + compra de desmama para recria. Mantém matrizes e produção
    # própria, mas o giro de jovens é maior que o de uma cria pura.
    'CRIA_RECRIA': {
        'prop_boi': 30.0,
        'renov_boi_pct': 20.0,
        'desc_mat_pct': 10.0,
        'venda_bez_pct': 60.0,  # retém mais para recriar do que a cria pura
        'nat_pct': NATALIDADE_PCT,
    },
}

# ==================================================================
# 1. CARREGAMENTO DO DATASET (apenas CSV)
# ==================================================================
def _carregar_dataset_csv(path: str = _CSV_PATH):
    """Carrega dataset CSV e retorna (X_list, y_list)."""
    X, y = [], []
    if not os.path.exists(path):
        return X, y
    with open(path, newline='', encoding='utf-8') as f:
        reader = _csv.DictReader(f)
        for row in reader:
            try:
                v = [
                    float(row['f00F']), float(row['f00M']),
                    float(row['f05F']), float(row['f05M']),
                    float(row['f13F']), float(row['f13M']),
                    float(row['f25F']), float(row['f25M']),
                    float(row['facF']), float(row['facM']),
                ]
                label = int(row['rotulo'])
                if label not in range(len(TIPOS)):
                    continue
                X.append(v)
                y.append(label)
            except (KeyError, ValueError):
                continue
    return X, y

# ==================================================================
# 2. FEATURE ENGINEERING
# ==================================================================
def extrair_features(
    v: list,
    taxa_natalidade: float = 0.75,
    bois_vendidos: float = None,
    bezerros_vendidos: float = None,
) -> np.ndarray:
    v = np.array(v, dtype=float)
    total = v.sum() or 1.0

    norm = v / total

    femeas_024  = v[0] + v[2] + v[4]
    machos_024  = v[1] + v[3] + v[5]
    # Plantel adulto, não base reprodutiva: aqui a pergunta é "que fração
    # deste rebanho é fêmea adulta", e para isso a de 30 meses conta como a de
    # 40. É de propósito que este número difere do que projeta bezerro — ver
    # services/base_reprodutiva.py. Mexer nele desloca as features e invalida
    # gestao_model.pkl, que foi treinado com a soma.
    matrizes    = base_reprodutiva(v).plantel_adulto
    bois        = v[7] + v[9]
    bois_25_36  = v[7]
    bezerros_0_24 = femeas_024 + machos_024

    p_femeas_024 = femeas_024 / total
    p_machos_024 = machos_024 / total
    p_matrizes   = matrizes   / total
    p_bois       = bois       / total

    bezerros_f = v[0] / total
    bezerros_m = v[1] / total
    bezerros   = (v[0] + v[1]) / total
    recria_f   = v[4] / total
    recria_m   = v[5] / total
    recria     = (v[4] + v[5]) / total

    ratio_boi_mat = bois / max(matrizes, 1)
    ratio_mat_boi = matrizes / max(bois, 1)
    ratio_mac_fem = machos_024 / max(femeas_024, 1)
    ratio_fem_mat = femeas_024 / max(matrizes, 1)

    ciclo_score = float(
        (bezerros > 0.05) and
        (recria_f > 0.03) and
        (p_matrizes > 0.05) and
        (p_machos_024 > 0.05)
    )

    has_matrizes   = 1.0 if p_matrizes   > 0.08 else 0.0
    has_bois_adult = 1.0 if p_bois       > 0.10 else 0.0
    has_mac_recria = 1.0 if recria_m     > 0.12 else 0.0
    big_bezerros   = 1.0 if bezerros     > 0.20 else 0.0
    engorda_sig    = 1.0 if (p_bois > 0.20 and p_matrizes < 0.15) else 0.0
    cria_sig       = 1.0 if (p_matrizes > 0.20 and bezerros > 0.15) else 0.0

    _bois_v = bois_vendidos if bois_vendidos is not None else float(bois_25_36)
    _bez_v  = bezerros_vendidos if bezerros_vendidos is not None else (bezerros_0_24 * 0.3)

    producao_esperada      = matrizes * taxa_natalidade
    eficiencia_reprodutiva = min(bezerros_0_24 / max(producao_esperada, 1), 3.0)
    taxa_transicao         = min(bois_25_36 / max(bezerros_0_24, 1), 3.0)
    intensidade_engorda    = _bois_v / total
    intensidade_cria       = _bez_v  / total

    # Sinal de COMPRA de desmama: a coorte de 0–12 meses observada contra a
    # produção biologicamente possível do próprio rebanho. Acima de ~1,15 o
    # excedente só pode ter vindo de compra — é o que separa uma cria pura de
    # um sistema misto cria+recria (material de treinamento, caso real do PA).
    coorte_0_12   = v[0] + v[1] + v[2] + v[3]
    razao_compra  = min(coorte_0_12 / max(producao_esperada, 1.0), 4.0)
    p_coorte_0_12 = coorte_0_12 / total

    features = np.concatenate([
        norm,
        [p_femeas_024, p_machos_024, p_matrizes, p_bois],
        [bezerros_f, bezerros_m, bezerros, recria_f, recria_m, recria],
        [min(p_matrizes*5, 2.0), min(p_bois*5, 2.0),
         min(p_machos_024*5, 2.0), min(bezerros*5, 2.0),
         min(ratio_boi_mat, 3.0), min(ratio_mat_boi/5, 2.0),
         min(ratio_mac_fem, 3.0), min(ratio_fem_mat, 3.0)],
        [has_matrizes, has_bois_adult, has_mac_recria,
         big_bezerros, engorda_sig, cria_sig, ciclo_score],
        [producao_esperada / max(total, 1),
         eficiencia_reprodutiva,
         taxa_transicao,
         intensidade_engorda,
         intensidade_cria],
        [razao_compra, p_coorte_0_12],
    ])
    return features

# ==================================================================
# 3. MODELO BASE (ensemble fixo e estável)
# ==================================================================
def _build_model():
    """
    Cria pipeline com ensemble RandomForest + GradientBoosting.
    XGBoost e LightGBM são adicionados automaticamente se instalados.
    """
    prod = bool(os.environ.get('DATABASE_URL'))

    estimators = []

    rf = RandomForestClassifier(
        n_estimators=100 if prod else 300,
        max_depth=10 if prod else 12,
        min_samples_leaf=2,
        random_state=42, n_jobs=1, class_weight='balanced'
    )
    estimators.append(('rf', rf))

    gb = GradientBoostingClassifier(
        n_estimators=80 if prod else 200,
        learning_rate=0.05, max_depth=4,
        subsample=0.8, random_state=42
    )
    estimators.append(('gb', gb))

    try:
        from xgboost import XGBClassifier
        xgb = XGBClassifier(
            n_estimators=100 if prod else 250,
            max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, use_label_encoder=False,
            eval_metric='mlogloss'
        )
        estimators.append(('xgb', xgb))
        print("[ML] XGBoost adicionado ao ensemble.")
    except ImportError:
        print("[ML] XGBoost não instalado – continuando sem ele.")

    try:
        from lightgbm import LGBMClassifier
        lgb = LGBMClassifier(
            n_estimators=100 if prod else 250,
            max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=42, verbose=-1
        )
        estimators.append(('lgb', lgb))
        print("[ML] LightGBM adicionado ao ensemble.")
    except ImportError:
        print("[ML] LightGBM não instalado – continuando sem ele.")

    ensemble = VotingClassifier(estimators=estimators, voting='soft')
    return Pipeline([('scaler', StandardScaler()), ('model', ensemble)])

# ==================================================================
# 4. TREINAMENTO E PERSISTÊNCIA
# ==================================================================
_pipeline = None

def treinar_modelo():
    """Treina o ensemble com o dataset CSV grande e salva no disco."""
    global _pipeline
    X_csv, y_csv = _carregar_dataset_csv()
    if not X_csv:
        raise RuntimeError("Dataset CSV não encontrado. Execute dataset.py primeiro.")

    X = np.array([extrair_features(v) for v in X_csv])
    y = np.array(y_csv)

    print(f"Treinando com {len(X)} amostras e {X.shape[1]} features.")

    # Um único passe de validação cruzada para as duas métricas. Antes eram
    # dois cross_val_score, que treinavam o mesmo ensemble duas vezes — 6
    # ajustes onde 3 bastam, ~10 minutos jogados fora a cada retreino.
    _cv = cross_validate(_build_model(), X, y, cv=3,
                         scoring=('accuracy', 'f1_macro'))
    cv_acc = _cv['test_accuracy']
    cv_f1  = _cv['test_f1_macro']

    _pipeline = _build_model()
    _pipeline.fit(X, y)
    result = {
        'accuracy_mean': round(float(cv_acc.mean()), 4),
        'accuracy_std':  round(float(cv_acc.std()),  4),
        'f1_macro_mean': round(float(cv_f1.mean()),  4),
        'f1_macro_std':  round(float(cv_f1.std()),   4),
        'n_samples':     len(X),
        'n_features':    X.shape[1],
        'n_csv':         len(X_csv),
    }
    salvar_modelo(result)
    return result

def retrain_com_dados(X_extra: list, y_extra: list) -> dict:
    """
    Retreina o ensemble combinando o CSV original + dados confirmados.
    Mantém a mesma arquitetura do pipeline.
    """
    global _pipeline
    X_csv, y_csv = _carregar_dataset_csv()
    X_base = [extrair_features(v) for v in X_csv]
    y_base = list(y_csv)

    if X_extra:
        X_all = np.array(X_base + [extrair_features(v) for v in X_extra])
        y_all = np.array(y_base + list(y_extra))
    else:
        X_all = np.array(X_base)
        y_all = np.array(y_base)

    if _pipeline is None:
        _pipeline = _build_model()
    _pipeline.fit(X_all, y_all)

    n_classes = len(set(y_all))
    cv = min(5, max(2, len(X_all) // max(n_classes, 1)))
    scores = cross_val_score(_pipeline, X_all, y_all, cv=cv, scoring='accuracy')
    result = {
        'accuracy_mean': round(float(scores.mean()), 4),
        'accuracy_std':  round(float(scores.std()),  4),
        'n_samples':     int(len(X_all)),
        'n_features':    int(X_all.shape[1]),
        'n_confirmados': int(len(X_extra)),
        'n_csv':         len(X_csv),
    }
    salvar_modelo(result)
    return result

def salvar_modelo(stats_dict: dict):
    """
    Persiste o pipeline treinado.

    compress=3 reduz o arquivo em ~75% (56 MB → 14 MB no ensemble de 6 classes)
    sem alterar uma vírgula do modelo e sem custo de carga — o tempo de load
    permanece em ~0,3s. Importa porque o .pkl é versionado no git e lido no
    boot, dentro do timeout do gunicorn.
    """
    try:
        joblib.dump({'pipeline': _pipeline, 'stats': stats_dict},
                    _MODEL_PATH, compress=3)
    except Exception as e:
        print(f'[ML] Aviso: não foi possível salvar o modelo: {e}')

def carregar_modelo() -> dict | None:
    """
    Carrega o modelo do disco. Devolve None se não der, e o app aborta o boot.

    Falhar aqui derruba a aplicação — o app não retreina no boot (ver app.py).
    O motivo precisa aparecer no log com o traceback: a mensagem curta
    ("cannot unpickle") não diz qual versão de biblioteca divergiu, e é
    justamente essa a causa quase sempre.
    """
    if not os.path.exists(_MODEL_PATH):
        _log.error('[ML] %s não existe — regenere com `python '
                   'treinar_ciclos.py`.', _MODEL_PATH)
        return None
    try:
        data = joblib.load(_MODEL_PATH)
        pipeline = data['pipeline']
        # Validação de estrutura (branch 9318087) — rejeita modelos antigos incompatíveis
        if not hasattr(pipeline.named_steps['model'], 'estimators'):
            _log.error('[ML] Modelo em disco tem estrutura antiga (sem '
                       'estimators) — regenere com `python '
                       'treinar_ciclos.py`.')
            return None
        global _pipeline
        _pipeline = pipeline
        return data['stats']
    except Exception:
        _log.error(
            '[ML] Falha ao ler %s — o app não vai subir. Quase '
            'sempre é divergência de versão: o pickle foi gravado com '
            'scikit-learn %s / numpy %s. Confira se requirements.txt está '
            'fixado e se a imagem usa o mesmo Python de runtime.txt, '
            'regenere com `python treinar_ciclos.py` e commite o artefato.',
            _MODEL_PATH, _sklearn_version, np.__version__, exc_info=True)
        return None

# ==================================================================
# 5. CLASSIFICAÇÃO (com regras híbridas corrigidas)
# ==================================================================
def classificar(
    v: list,
    taxa_natalidade: float = 0.75,
    bois_vendidos: float = None,
    bezerros_vendidos: float = None,
) -> dict:
    if _pipeline is None:
        raise RuntimeError("Modelo não treinado.")

    va = np.array(v, dtype=float)
    total = va.sum() or 1.0
    matrizes = va[6] + va[8]
    bois_25_36 = va[7]
    bezerros_0_24 = va[0] + va[1] + va[2] + va[3] + va[4] + va[5]

    # Bois_v para features ML: usa garrotes como proxy quando não informado
    _bois_v = bois_vendidos if bois_vendidos is not None else float(bois_25_36)
    _bez_v = bezerros_vendidos if bezerros_vendidos is not None else (bezerros_0_24 * 0.3)

    producao_esperada = matrizes * taxa_natalidade

    # Para a regra híbrida: só conta vendas reais confirmadas.
    # Garrotes de reprodução não são vendas de engorda — usar 0 como default
    # evita falsos positivos de CICLO_COMPLETO em fazendas CRIA com touros.
    _bois_v_regra = bois_vendidos if bois_vendidos is not None else 0.0
    intensidade_engorda = _bois_v_regra / total
    intensidade_cria = _bez_v / total

    p_matrizes_h = matrizes / total
    p_mac_13_24_h = (va[3] + va[5]) / total
    p_bois_h = (va[7] + va[9]) / total
    p_bez_h = bezerros_0_24 / total

    indice_ciclo = (
        int(p_matrizes_h > P_MATRIZES_CRIA) +
        int(p_mac_13_24_h > 0.10) +
        int(p_bois_h > 0.10) +   # threshold 10% (antes 12%) — captura terminação típica
        int(p_bez_h > 0.12)
    )

    # Flag: confinamento/engorda puro — sem matrizes, poucas fêmeas, machos dominam
    _p_fem_total = (va[0] + va[2] + va[4] + va[6] + va[8]) / total
    _engorda_puro = (p_matrizes_h < 0.02 and _p_fem_total < 0.10 and va[7] / total > 0.08)

    feat = extrair_features(v, taxa_natalidade, _bois_v, _bez_v).reshape(1, -1)
    probs = _pipeline.predict_proba(feat)[0]
    prob_dict = {TIPOS[i]: round(float(p) * 100, 1) for i, p in enumerate(probs)}
    tipo_modelo = TIPOS[int(probs.argmax())]

    # Sem vendas declaradas, só aceitamos CICLO_COMPLETO diretamente quando a
    # própria pirâmide etária sustenta uma base madura de matrizes. Isso evita
    # transformar uma recria de fêmeas jovens em ciclo completo só porque há
    # muitos animais nas faixas intermediárias.
    _razao_madura_ficha = (float(va[8]) / float(va[6])) if va[6] > 0 else float('inf')
    _ciclo_completo_inferido = bool(
        bois_vendidos is None
        and tipo_modelo == 'CICLO_COMPLETO'
        and _razao_madura_ficha >= 1.0
    )

    explicacao = []

    # Rastreio de proveniência da decisão — a explicação
    # apresentada precisa corresponder ao processo que efetivamente decidiu).
    origem_decisao = 'ml'
    regra_aplicada = None

    if _ciclo_completo_inferido:
        # Ausência de vendas na ficha significa dado desconhecido, não venda
        # zero. A composição e o modelo continuam sendo a melhor inferência
        # disponível; o resultado financeiro será marcado como limitado.
        tipo = tipo_modelo
        origem_decisao = 'ml'
        regra_aplicada = None
        confianca = round(float(probs[int(probs.argmax())]) * 100, 1)
        explicacao.append(
            'Classificação automática pela composição da ficha e pelo modelo ML; '
            'vendas de bois não informadas (não tratadas como zero).'
        )
        explicacao.append(f'ML confirmou: {tipo}')
    elif _engorda_puro:
        tipo = 'ENGORDA'
        origem_decisao = 'regra'
        regra_aplicada = 'engorda_pura'
        confianca = max(prob_dict.get('ENGORDA', 0.0), 75.0)
        explicacao.append(
            f"Flag engorda_puro: p_matrizes={p_matrizes_h:.1%}, p_fem={_p_fem_total:.1%}, "
            f"mac_25_36={va[7]/total:.1%} → confinamento sem matrizes → ENGORDA"
        )
    elif indice_ciclo >= 4 and intensidade_engorda > 0.05:
        # Exige intensidade_engorda > 5% confirmada pelo usuário;
        # touros de serviço (sem bois_vendidos informado) não ativam esta regra.
        tipo = 'CICLO_COMPLETO'
        origem_decisao = 'regra'
        regra_aplicada = 'indice_ciclo_completo'
        confianca = max(prob_dict.get('CICLO_COMPLETO', 0.0), 85.0)
        explicacao.append(f"Regra híbrida ativada: indice_ciclo={indice_ciclo}/4 + engorda={intensidade_engorda:.1%} → ciclo_completo")
        explicacao.append(
            f"p_matrizes={p_matrizes_h:.2%}, p_mac_13_24={p_mac_13_24_h:.2%}, "
            f"p_bois={p_bois_h:.2%}, p_bez={p_bez_h:.2%}"
        )
    elif intensidade_engorda < 0.1:
        ml_idx = int(probs.argmax())
        ml_tipo = TIPOS[ml_idx]
        if ml_tipo in ('ENGORDA', 'CICLO_COMPLETO'):
            # Rescue CICLO_COMPLETO: ML acertou o tipo mas sem bois_vendidos.
            # Aceita quando há evidência estrutural forte (matrizes + bois + bezerros ≥ 3/4 critérios).
            if (ml_tipo == 'CICLO_COMPLETO' and indice_ciclo >= 3
                    and p_bois_h > 0.08 and p_matrizes_h > 0.20 and p_bez_h > 0.20):
                tipo = 'CICLO_COMPLETO'
                origem_decisao = 'regra'
                regra_aplicada = 'rescue_ciclo_completo'
                confianca = max(prob_dict.get('CICLO_COMPLETO', 0.0), 80.0)
                explicacao.append(
                    f"Rescue ciclo_completo: indice_ciclo={indice_ciclo}/4, "
                    f"p_bois={p_bois_h:.1%}>8%, p_mat={p_matrizes_h:.1%}>20%, "
                    f"p_bez={p_bez_h:.1%}>20% → CICLO_COMPLETO (sem bois_vendidos)"
                )
            # Rescue ENGORDA: bois dominam o rebanho (>45%) → aceita voto ML mesmo sem bois_vendidos
            elif ml_tipo in ('ENGORDA', 'RECRIA_ENGORDA') and p_bois_h > 0.45:
                # Preserva a distinção do ML entre confinamento puro e
                # recria/engorda — a regra confirma a terminação, não o tipo.
                tipo = ml_tipo
                origem_decisao = 'regra'
                regra_aplicada = 'rescue_engorda'
                confianca = max(prob_dict.get(ml_tipo, 0.0), 80.0)
                explicacao.append(
                    f"Rescue engorda: p_bois={p_bois_h:.1%}>45% confirma terminação → ENGORDA (sem bois_vendidos)"
                )
            else:
                # Sem venda de boi confirmada, o rebanho é de base reprodutiva
                # ou de recria. Escolhe entre essas por probabilidade, incluindo
                # o sistema misto — antes o CRIA_RECRIA era forçado para CRIA.
                _cands = ('CRIA', 'RECRIA', 'CRIA_RECRIA')
                tipo = max(_cands, key=lambda t: probs[TIPOS.index(t)])
                origem_decisao = 'regra'
                regra_aplicada = 'descarte_engorda_sem_venda'
                explicacao.append(
                    f"Regra híbrida: intensidade_engorda={intensidade_engorda:.3f} < 0.1 → {ml_tipo} descartado"
                )
                explicacao.append(f"ML sugeria {ml_tipo}; substituído por {tipo}")
        else:
            tipo = ml_tipo
            # Rescue: ML classificou CRIA mas estrutura do rebanho indica CICLO_COMPLETO
            # (matrizes + bois + bezerros ≥ 3/4 critérios, mesmo sem bois_vendidos)
            if (tipo == 'CRIA' and indice_ciclo >= 3
                    and p_bois_h > 0.08 and p_matrizes_h > 0.20 and p_bez_h > 0.20):
                tipo = 'CICLO_COMPLETO'
                origem_decisao = 'regra'
                regra_aplicada = 'rescue_ciclo_completo_ml_cria'
                confianca = max(prob_dict.get('CICLO_COMPLETO', 0.0), 80.0)
                explicacao.append(
                    f"Rescue ciclo_completo: ML=CRIA, indice_ciclo={indice_ciclo}/4, "
                    f"p_bois={p_bois_h:.1%}>8%, p_mat={p_matrizes_h:.1%}>20%, "
                    f"p_bez={p_bez_h:.1%}>20% → CICLO_COMPLETO"
                )
            else:
                explicacao.append(
                    f"Regra híbrida: intensidade_engorda={intensidade_engorda:.3f} < 0.1 → priorizando cria/recria"
                )
                explicacao.append(f"ML confirmou: {tipo}")
        if tipo != 'CICLO_COMPLETO':
            confianca = round(float(probs[TIPOS.index(tipo)]) * 100, 1)
    else:
        ml_idx = int(probs.argmax())
        ml_tipo = TIPOS[ml_idx]
        confianca = round(float(probs[ml_idx]) * 100, 1)

        # Guarda de segurança: ML votou CICLO_COMPLETO com indice_ciclo fraco.
        if ml_tipo == 'CICLO_COMPLETO' and indice_ciclo <= 1:
            alt_idx = int(np.argsort(probs)[-2])
            tipo = TIPOS[alt_idx] if TIPOS[alt_idx] != 'CICLO_COMPLETO' else (
                'CRIA' if p_matrizes_h >= P_MATRIZES_CRIA else 'RECRIA'
            )
            confianca = round(float(probs[TIPOS.index(tipo)]) * 100, 1)
            origem_decisao = 'regra'
            regra_aplicada = 'guarda_ciclo_completo'
            explicacao.append(
                f"Guarda CICLO_COMPLETO: indice_ciclo={indice_ciclo}/4 insuficiente "
                f"→ revertido para {tipo}"
            )
        else:
            tipo = ml_tipo
            explicacao.append("Classificação via modelo ML (ensemble RF+GB)")
        explicacao.append(f"Confiança: {confianca}%")

    # ── Cria sem vaca não é cria ────────────────────────────────────────────
    # Guarda única, depois de TODAS as regras, porque há mais de um caminho que
    # chega em CRIA e nenhum deles perguntava se havia base reprodutiva. Duas
    # regras diferentes (`guarda_ciclo_completo` e `descarte_engorda_sem_venda`)
    # escolhiam CRIA por probabilidade e seguiam adiante.
    #
    # Caso real que motivou isto — Recria B, 753 cabeças,
    # reportado por analista em campo: rebanho quase todo fêmea, com 150 de
    # 0–12m, 374 de 13–24m, 209 de 25–36m e apenas CINCO acima de 36 meses.
    # Saía CRIA, e cinco matrizes não parem 700 cabeças.
    #
    # `matrizes` soma 25–36m e >36m, o que é defensável (aos 25 meses a fêmea
    # já cobre) mas esconde a FORMA da pirâmide — e é a forma que distingue:
    #
    #   vaca de cria vive de 8 a 10 anos e SE ACUMULA acima dos 36 meses
    #   fêmea de recria é vendida ANTES de parir, e essa faixa fica vazia
    #
        # Medido (fêmeas >36m ÷ fêmeas 25–36m): Recria B 0,02 · ficha real de
    # recria 1,31 · cria de teste 1,89 · cria sintética 5,00. Duas ordens de
    # grandeza de separação.
    #
    # A escolha dos 36 meses como corte não é arbitrária: a Embrapa Gado de
    # Corte apurou IDADE MÉDIA À PRIMEIRA PARIÇÃO DE 36,3 MESES em 468
    # matrizes Nelore no Brasil Central, criadas a pasto. Ou seja, a fêmea da
    # faixa de 25–36m ainda NÃO PARIU — contá-la como matriz projeta bezerro
    # que ainda não existe. Ver IDADE_PRIMEIRA_PARICAO_MESES em
    # services/parametros_zootecnicos.py, com a fonte registrada.
    _f25_F, _fac_F = float(va[6]), float(va[8])
    _razao_madura = (_fac_F / _f25_F) if _f25_F > 0 else float('inf')
    if tipo in ('CRIA', 'CRIA_RECRIA') and (
            p_matrizes_h < P_MATRIZES_CRIA
            or _razao_madura < RAZAO_MATRIZ_MADURA_CRIA):
        _antes = tipo
        tipo = 'RECRIA'
        confianca = round(float(probs[TIPOS.index(tipo)]) * 100, 1)
        origem_decisao = 'regra'
        regra_aplicada = 'cria_sem_base_reprodutiva'
        explicacao.append(
            f"{_antes} descartado: matrizes são {p_matrizes_h:.1%} do rebanho e "
            f"há {_fac_F:.0f} fêmeas acima de 36m para {_f25_F:.0f} de 25–36m "
            f"(razão {_razao_madura:.2f}, mínimo {RAZAO_MATRIZ_MADURA_CRIA:.2f}). "
            f"Sem vaca que fique, é recria de fêmeas — não cria."
        )

    explicacao.append(
        f"Variáveis chave — matrizes={matrizes:.0f}, bois_25_36={bois_25_36:.0f}, "
        f"bezerros_0_24={bezerros_0_24:.0f}"
    )
    explicacao.append(
        f"intensidade_engorda={intensidade_engorda:.3f}, "
        f"intensidade_cria={intensidade_cria:.3f}, indice_ciclo={indice_ciclo}"
    )

    misto = _detectar_ciclo_misto(
        tipo_principal=tipo,
        prob_dict=prob_dict,
        p_matrizes=p_matrizes_h,
        p_mac_recria=p_mac_13_24_h,
        p_bois=p_bois_h,
        p_bez=p_bez_h,
        intensidade_engorda=intensidade_engorda,
    )
    if misto:
        explicacao.append(
            f"Ciclo misto detectado: {misto['combinacao']} "
            f"(secundário {misto['tipo_secundario']} = {misto['confianca_secundaria']}%)"
        )

    # Probabilidade real do modelo para a classe final — nunca inflada.
    # Quando a decisão veio de regra determinística, este é o número que
    # mostra o que o ML de fato pensava.
    confianca_ml = round(float(probs[TIPOS.index(tipo)]) * 100, 1)

    if origem_decisao == 'regra':
        explicacao.append(
            f"⚠ Decisão tomada por REGRA DETERMINÍSTICA ({regra_aplicada}), "
            f"não pelo modelo ML. Probabilidade do ML para {tipo}: {confianca_ml}%."
        )

    try:
        atipicidade = calcular_atipicidade(v)
    except Exception:
        atipicidade = None

    # Uma ficha de saldo informa composição, mas não prova que houve venda de
    # animais para abate. Quando o modelo sugere CICLO_COMPLETO e a regra
    # conservadora o rebaixa por falta dessa informação, expor a limitação é
    # mais honesto do que apresentar RECRIA como conclusão definitiva.
    classificacao_limitada = bois_vendidos is None
    dados_faltantes = ['bois_vendidos'] if bois_vendidos is None else []
    revisao_humana = classificacao_limitada
    if classificacao_limitada:
        explicacao.append(
            'Classificação limitada: o modelo sugere CICLO_COMPLETO, mas a '
            'ficha não informa vendas de bois; confirmar com o analista.'
        )

    return {
        'classificacao': tipo,
        'tipo': tipo,
        'confianca': confianca,
        'probabilidades': prob_dict,
        'explicacao': explicacao,
        'tipo_secundario':       (misto or {}).get('tipo_secundario'),
        'combinacao':            (misto or {}).get('combinacao', tipo),
        'confianca_secundaria':  (misto or {}).get('confianca_secundaria', 0.0),
        # ── Proveniência e qualidade da decisão ──────────────────────────────
        'origem_decisao':  origem_decisao,   # 'regra' | 'ml'
        'regra_aplicada':  regra_aplicada,   # None quando origem_decisao == 'ml'
        'confianca_ml':    confianca_ml,     # probabilidade real do modelo
        'atipicidade':     atipicidade,      # distância à distribuição de treino
        'tipo_modelo':     tipo_modelo,
        'classificacao_limitada': classificacao_limitada,
        'dados_faltantes': dados_faltantes,
        'revisao_humana':  revisao_humana,
    }


# ==================================================================
# 5a. ATIPICIDADE — o rebanho se parece com o conjunto de treino?
# ==================================================================
# O modelo foi treinado majoritariamente com amostras sintéticas geradas a
# partir de faixas de referência. Uma probabilidade alta só é significativa
# se o rebanho analisado estiver dentro da região coberta pelo treino.
# Esta métrica mede a distância (z-score euclidiano) até o centro dessa
# distribuição e a compara com os percentis observados no próprio treino.
_ATIP_STATS = None


def _stats_treino() -> dict | None:
    """Estatísticas da distribuição de features do treino (lazy + cache)."""
    global _ATIP_STATS
    if _ATIP_STATS is not None:
        return _ATIP_STATS
    X_csv, _ = _carregar_dataset_csv()
    if not X_csv:
        return None
    F = np.array([extrair_features(v) for v in X_csv], dtype=float)
    mu = F.mean(axis=0)
    sd = F.std(axis=0)
    sd[sd < 1e-9] = 1e-9
    dist = np.linalg.norm((F - mu) / sd, axis=1)
    _ATIP_STATS = {
        'mu': mu,
        'sd': sd,
        'p50': float(np.percentile(dist, 50)),
        'p95': float(np.percentile(dist, 95)),
        'p99': float(np.percentile(dist, 99)),
        'n':   int(len(dist)),
    }
    return _ATIP_STATS


def calcular_atipicidade(v: list) -> dict | None:
    """
    Mede o quão atípico é o rebanho frente ao conjunto de treino.

    Retorna nível 'tipico' | 'atipico' | 'muito_atipico'. Em rebanhos
    atípicos a probabilidade do modelo perde significado estatístico e o
    caso deve ir para revisão humana.
    """
    s = _stats_treino()
    if s is None:
        return None
    f = np.array(extrair_features(v), dtype=float)
    d = float(np.linalg.norm((f - s['mu']) / s['sd']))
    if d <= s['p95']:
        nivel, msg = 'tipico', 'Rebanho dentro do padrão do conjunto de treino.'
    elif d <= s['p99']:
        nivel, msg = 'atipico', ('Composição incomum frente ao treino — '
                                 'confira os dados e considere revisão manual.')
    else:
        nivel, msg = 'muito_atipico', ('Composição muito distante do conjunto de treino — '
                                       'a confiança do modelo não é estatisticamente '
                                       'significativa. Revisão humana recomendada.')
    return {
        'distancia':   round(d, 2),
        'nivel':       nivel,
        'mensagem':    msg,
        'limiar_p95':  round(s['p95'], 2),
        'limiar_p99':  round(s['p99'], 2),
    }


# ==================================================================
# 5a-bis. FEATURES REDUNDANTES — agrupamento para o SHAP
# ==================================================================
# extrair_features() produz 40 colunas, mas várias são a MESMA informação
# escrita de outro jeito (ex.: 'Machos 0-5m / total' e 'Bezerros 0-5m / total'
# têm correlação 1,0000). O SHAP reparte a importância entre as cópias, o que
# dilui a explicação regulatória: uma única variável aparece como duas linhas
# com metade do peso cada.
#
# A correção aqui é de APRESENTAÇÃO, não de modelagem: o modelo continua
# recebendo as 40 colunas (nada é retreinado), mas a explicação soma as
# contribuições dentro de cada grupo e mostra uma linha por informação real.
#
# Reversível: defina SHAP_AGRUPAR_REDUNDANTES=0 no ambiente para voltar ao
# comportamento anterior (40 linhas, com duplicatas).
_SHAP_AGRUPAR = os.environ.get('SHAP_AGRUPAR_REDUNDANTES', '1') != '0'
_CORR_REDUNDANTE = 0.995
_GRUPOS_RED = None


def _grupos_redundantes() -> list[list[int]]:
    """
    Agrupa índices de features com correlação absoluta > 0.995 no conjunto de
    treino (union-find). Calculado uma vez e cacheado.

    Retorna lista de grupos; features sem par aparecem como grupo unitário.
    """
    global _GRUPOS_RED
    if _GRUPOS_RED is not None:
        return _GRUPOS_RED

    X_csv, _ = _carregar_dataset_csv()
    n_feat = len(FEATURE_NAMES)
    if not X_csv:
        _GRUPOS_RED = [[i] for i in range(n_feat)]
        return _GRUPOS_RED

    F = np.array([extrair_features(v) for v in X_csv], dtype=float)
    sd = F.std(axis=0)
    sd[sd < 1e-9] = 1e-9
    C = np.nan_to_num(np.corrcoef(((F - F.mean(axis=0)) / sd).T))

    pai = list(range(n_feat))

    def _find(a: int) -> int:
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a

    for i in range(n_feat):
        for j in range(i + 1, n_feat):
            if abs(C[i, j]) > _CORR_REDUNDANTE:
                pai[_find(i)] = _find(j)

    agrup: dict[int, list[int]] = {}
    for i in range(n_feat):
        agrup.setdefault(_find(i), []).append(i)

    _GRUPOS_RED = list(agrup.values())
    return _GRUPOS_RED


# ==================================================================
# 5b. SHAP — explicabilidade técnica e governança do modelo
# ==================================================================
def explicar_shap(
    v: list,
    tipo_classificado: str,
    top_n: int = 8,
    origem_decisao: str = 'ml',
    regra_aplicada: str | None = None,
) -> dict:
    """
    Retorna os principais fatores que explicam a classificação via SHAP.

    Apoio à governança: explicação técnica do modelo para revisão humana.
    Isto não constitui, isoladamente, conformidade regulatória.

    IMPORTANTE: quando `origem_decisao == 'regra'`, a classificação final foi
    determinada por uma regra determinística e NÃO pelo modelo. Nesse caso o
    resultado é marcado com `decisao_por_regra=True` e os fatores SHAP devem
    ser lidos como contexto do modelo, não como justificativa da decisão —
    apresentá-los como causa seria descolar a explicação do processo real.

    Para cada estimador do ensemble (RF, GB, XGB, LGB) calcula SHAP values
    via TreeExplainer e devolve a média ponderada. Os valores representam a
    contribuição de cada característica do rebanho para a probabilidade da
    classe classificada (positivo = aumenta, negativo = reduz).

    Retorna dict vazio se shap não estiver instalado ou se o cálculo falhar.
    """
    if _pipeline is None:
        return {}
    try:
        import shap as _shap
    except ImportError:
        return {'erro': 'shap não instalado — execute: pip install shap'}

    scaler = _pipeline.named_steps['scaler']
    voting = _pipeline.named_steps['model']

    feat = extrair_features(v).reshape(1, -1)
    feat_scaled = scaler.transform(feat)

    if tipo_classificado not in TIPOS:
        return {}
    classe_idx = TIPOS.index(tipo_classificado)

    contribs = []
    # VotingClassifier.estimators_ é uma LISTA de estimadores já treinados
    # (sem nomes) — os pares (nome, est) ficam em .estimators / .named_estimators_.
    # Desempacotar como tupla aqui lançava ValueError e o SHAP nunca era gerado.
    for est in voting.estimators_:
        try:
            exp = _shap.TreeExplainer(est)
            sv = exp.shap_values(feat_scaled)
            # RF / GB multi-classe: list[n_classes][1, n_features]
            if isinstance(sv, list):
                if len(sv) > classe_idx:
                    arr = np.asarray(sv[classe_idx])
                    contribs.append(arr.flatten())
            elif isinstance(sv, np.ndarray):
                if sv.ndim == 3:
                    # XGB: (1, n_features, n_classes)
                    contribs.append(sv[0, :, classe_idx])
                elif sv.ndim == 2:
                    contribs.append(sv[0])
        except Exception:
            continue

    if not contribs:
        return {}

    media = np.mean(contribs, axis=0)

    # Soma as contribuições de features que são a mesma informação, para que
    # uma variável não apareça repartida em duas linhas com metade do peso.
    if _SHAP_AGRUPAR:
        grupos = _grupos_redundantes()
        itens = []
        for g in grupos:
            soma = float(sum(media[i] for i in g))
            nome = FEATURE_NAMES[g[0]]
            itens.append({
                'idx': g[0],
                'shap': soma,
                'feature': nome,
                'equivalentes': [FEATURE_NAMES[i] for i in g[1:]],
            })
    else:
        itens = [{'idx': i, 'shap': float(media[i]),
                  'feature': FEATURE_NAMES[i], 'equivalentes': []}
                 for i in range(len(media))]

    total_abs = float(sum(abs(it['shap']) for it in itens)) or 1.0

    fatores = sorted(
        [
            {
                'feature':         it['feature'],
                'shap':            round(it['shap'], 4),
                'importancia_pct': round(abs(it['shap']) / total_abs * 100, 1),
                'direcao':         'positivo' if it['shap'] > 0 else 'negativo',
                'equivalentes':    it['equivalentes'],
            }
            for it in itens
            if abs(it['shap']) > 1e-6
        ],
        key=lambda x: abs(x['shap']),
        reverse=True,
    )[:top_n]

    por_regra = origem_decisao == 'regra'
    return {
        'classe':        tipo_classificado,
        'fatores':       fatores,
        'n_estimadores': len(contribs),
        'metodo':        ('SHAP TreeExplainer — média do ensemble'
                          + (' · features equivalentes agrupadas' if _SHAP_AGRUPAR else '')),
        'conformidade':  'Apoio à governança e revisão humana; não certifica conformidade regulatória',
        'agrupamento_redundantes': _SHAP_AGRUPAR,
        'decisao_por_regra': por_regra,
        'regra_aplicada':    regra_aplicada,
        'aviso': (
            f'A classificação final foi determinada pela regra determinística '
            f'"{regra_aplicada}", não pelo modelo. Os fatores abaixo descrevem '
            f'o comportamento do modelo para este rebanho e servem como contexto, '
            f'não como justificativa da decisão.'
        ) if por_regra else None,
    }


# ==================================================================
# 5c. CICLOS MISTOS (pós-processamento)
# ==================================================================
# Pares de ciclo que fazem sentido coexistir numa mesma propriedade.
# RECRIA_ENGORDA e CRIA_RECRIA ficam de fora de propósito: já SÃO combinações
# de fases, e tratá-las como "principal + secundário" duplicaria a leitura.
_PARES_VALIDOS = {
    ('CRIA',    'RECRIA'),
    ('RECRIA',  'CRIA'),
    ('RECRIA',  'ENGORDA'),
    ('ENGORDA', 'RECRIA'),
    ('CRIA',    'ENGORDA'),
    ('ENGORDA', 'CRIA'),
}

_MISTO_PROB_MIN = 25.0
_MISTO_GAP_MAX  = 50.0


def _detectar_ciclo_misto(
    tipo_principal: str,
    prob_dict: dict,
    p_matrizes: float,
    p_mac_recria: float,
    p_bois: float,
    p_bez: float,
    intensidade_engorda: float,
) -> dict | None:
    if tipo_principal == 'CICLO_COMPLETO':
        return None

    candidatos = [
        (t, p) for t, p in prob_dict.items()
        if t != tipo_principal and t != 'CICLO_COMPLETO'
    ]
    if not candidatos:
        return None
    secundario, prob_sec = max(candidatos, key=lambda x: x[1])

    if prob_sec < _MISTO_PROB_MIN:
        return None
    if (prob_dict[tipo_principal] - prob_sec) > _MISTO_GAP_MAX:
        return None
    if (tipo_principal, secundario) not in _PARES_VALIDOS:
        return None

    if not _composicao_suporta(tipo_principal, secundario,
                                p_matrizes, p_mac_recria, p_bois,
                                p_bez, intensidade_engorda):
        return None

    par_ord = '+'.join(sorted([tipo_principal, secundario]))
    return {
        'tipo_secundario': secundario,
        'combinacao': par_ord,
        'confianca_secundaria': round(float(prob_sec), 1),
    }


def _composicao_suporta(principal, secundario,
                         p_matrizes, p_mac_recria, p_bois,
                         p_bez, intensidade_engorda) -> bool:
    par = frozenset([principal, secundario])

    if par == frozenset(['CRIA', 'RECRIA']):
        return p_matrizes > 0.10 and p_mac_recria > 0.05

    if par == frozenset(['RECRIA', 'ENGORDA']):
        return p_mac_recria > 0.05 and (p_bois > 0.05 or intensidade_engorda > 0.05)

    if par == frozenset(['CRIA', 'ENGORDA']):
        return p_matrizes > 0.10 and p_bois > 0.05 and p_mac_recria < 0.15

    return False

# ==================================================================
# 6. INDICADORES ZOOTÉCNICOS
# ==================================================================
def calcular_indicadores(v: list) -> dict:
    from services.livestock_engine import calculate_herd_indicators

    indicators = calculate_herd_indicators(v)
    return {
        'total':           indicators['total_animals'],
        'total_femeas':    indicators['total_females'],
        'total_machos':    indicators['total_males'],
        'femeas_024':      indicators['females_0_24_months'],
        'machos_024':      indicators['males_0_24_months'],
        'matrizes':        indicators['matrices'],
        'bois':            indicators['bois'],
        'fem_adultas':     indicators['adult_females'],
        'mac_adultos':     indicators['adult_males'],
        'cria':            indicators['cria'],
        'recria':          indicators['recria'],
        'adultos':         indicators['adults'],
        'pct_cria':        indicators['pct_cria'],
        'pct_recria':      indicators['pct_recria'],
        'pct_adultos':     indicators['pct_adults'],
        'pct_matrizes':    indicators['pct_matrices'],
        'pct_mac_adultos': indicators['pct_adult_males'],
        'ratio_fm':        indicators['female_male_ratio'],
        'bezerros_est':    indicators['estimated_calves'],
    }

# ==================================================================
# 7. SIMULAÇÕES FINANCEIRAS (PARÂMETROS ATUALIZADOS)
# ==================================================================
def calcular_ano(
    matrizes, c0_femeas, c1_femeas, c0_machos, c1_machos, bois,
    nat_pct, desc_mat_pct, prop_boi, renov_boi_pct,
    venda_bez_pct, mort_pct, preco_arroba, custo_arroba,
    peso_boi: float = PESO_BOI_ARR, peso_vaca: float = PESO_VACA_ARR,
    peso_bezerra: float = PESO_BEZERRA_ARR, peso_garrote: float = PESO_GARROTE_ARR,
    preco_boi_arr: float = None, preco_vaca_arr: float = None,
    preco_bezerra_cab: float = None, preco_bezerro_cab: float = None,
    mort_adulto_pct: float = None,   # fração; default = mort_pct
    mort_bezerra_pct: float = None,  # fração; default = mort_pct × 3.5 (EMBRAPA)
    # Fêmeas de 25–36 meses ("prestes") — coorte que amadurece dentro do ano
    # e entra na base reprodutiva. Estado corrente, não injeção de uma vez:
    # do ano 2 em diante ela é alimentada por c1_femeas do ano anterior (ver
    # o loop de simular_cenario), não mais zerada.
    prestes_matrizes: float = 0.0,
) -> dict:
    """
    Coortes reais, não um pool 0–24m misturado.

    c0 (0–12m) → c1 (13–24m) → prestes_matrizes (25–36m) → matriz. Cada ano
    avança uma etapa. Antes, `femeas_024`/`machos_024` eram um único número
    cobrindo dois anos de idade, e QUALQUER fêmea retida — tivesse ela um mês
    ou vinte e três — virava matriz reprodutiva no ano seguinte via
    `fem_repor`. Uma novilha de 30 meses ainda não pariu (idade média à
    primeira parição: 36,3 meses, Embrapa, 468 matrizes Nelore); uma bezerra
    de três, muito menos. Numa cria de 190 fêmeas jovens recém-nascidas isso
    promovia ~38 delas a matriz no ano 1.

    Machos seguem o mesmo princípio: só quem já estava em c1 (13–24m) no
    início do ano gradua para o pipeline de terminação — não mais metade de
    um pool misturado, gradue o animal tivesse nascido ontem ou há dois anos.

    Pesos: bezerra vendida (bez_vend) é do desmame, mais leve (peso_bezerra=
    6.0@). Macho jovem excedente (machos_024_vend, sempre 0 — ver abaixo) seria
    garrote, mais pesado (peso_garrote=10.67@). Pesos GEP Araguaia 24/25.
    """

    bezerros = matrizes * nat_pct
    nascidos_f = bezerros * 0.5
    nascidos_m = bezerros * 0.5
    bois_nec  = max(round(matrizes / max(prop_boi, 1)), 1)
    renovacao = round(bois_nec * renov_boi_pct)

    _mort_adulto  = mort_adulto_pct  if mort_adulto_pct  is not None else mort_pct
    _mort_bezerra = mort_bezerra_pct if mort_bezerra_pct is not None else min(mort_pct * _RAZAO_MORT_BEZERRA, 0.25)

    def _mortes(n, taxa):
        """Arredonda mortalidade mas garante mínimo 1 quando n > 0 e taxa > 0."""
        if n <= 0 or taxa <= 0:
            return 0
        return max(1, round(n * taxa))

    def _sobrevive(n, taxa):
        """Como _mortes, mas devolve quem fica — para encadear coortes."""
        return max(n - _mortes(n, taxa), 0.0) if n > 0 else 0.0

    # ── Venda na desmama ──────────────────────────────────────────────────────
    # `venda_bez_pct` incide sobre a bezerra recém-nascida/desmamada — mesma
    # convenção de production_engine/cria.py —, não sobre um pool de dois anos.
    bez_vend = round(nascidos_f * venda_bez_pct)
    reter_f0 = max(nascidos_f - bez_vend, 0.0)

    # ── Pipeline de terminação ───────────────────────────────────────────────
    # Num ciclo completo o macho jovem NÃO é vendido: ele envelhece até a
    # terminação. É isso que torna o ciclo "completo". Todo c1_machos — quem
    # já estava em 13–24m no início do ano — completa 25 meses dentro deste
    # ano e entra no estoque de terminação.
    #
    # Antes (histórico) o modelo vendia todos os machos de 0–24m como garrote
    # E liquidava os bois adultos no mesmo ano, sem repor. Resultado: o ano 1
    # vendia o estoque inteiro e o ano 2 não tinha o que vender — as vendas
    # caíam 55% e o DSCR ia de 6,56 para −2,25, enquanto o parecer aprovava
    # olhando só o ano 1. A correção por coortes preserva essa garantia: o
    # pipeline nunca esvazia, porque c1 é reposto por c0 todo ano.
    graduados = _sobrevive(c1_machos, _mort_adulto)
    bois_disp = bois + graduados                 # prontos ou em terminação
    bois_vendidos   = max(bois_disp - bois_nec, 0)
    # Garrote (0–24m) não é vendido: só o boi formado, via bois_vendidos acima.
    machos_024_vend = 0.0

    desc_mat = round(matrizes * desc_mat_pct)
    # A coorte prestes_matrizes (25–36m) cruza os 36 meses dentro do ano e
    # entra no plantel sem passar pela regra de venda: cruzar os 36 meses é
    # calendário, não decisão de manejo. Submetê-la a `venda_bez_pct`
    # liquidaria fêmeas prestes a parir.
    prestes_sobrevivente = _sobrevive(prestes_matrizes, _mort_adulto)
    aumento  = prestes_sobrevivente - desc_mat
    vendidos = bois_vendidos + desc_mat + bez_vend + machos_024_vend

    mortes_mat      = _mortes(matrizes, _mort_adulto)
    mortes_bois_tot = _mortes(bois, _mort_adulto)
    # Perdas em cada transição de coorte: prestes→matriz, c1→(terminação ou
    # prestes), c0→c1, e recém-nascidos retidos→c0.
    mortes_prestes  = _mortes(prestes_matrizes, _mort_adulto)
    mortes_c1_f     = _mortes(c1_femeas, _mort_adulto)
    mortes_c1_m     = _mortes(c1_machos, _mort_adulto)
    mortes_c0_f     = _mortes(c0_femeas, _mort_bezerra)
    mortes_c0_m     = _mortes(c0_machos, _mort_bezerra)
    mortes_nasc     = _mortes(reter_f0, _mort_bezerra) + _mortes(nascidos_m, _mort_bezerra)
    mortes = (mortes_mat + mortes_bois_tot + mortes_prestes + mortes_c1_f
              + mortes_c1_m + mortes_c0_f + mortes_c0_m + mortes_nasc)

    mat_prox     = max(matrizes + aumento - mortes_mat, 0)
    bois_prox    = max(bois_nec, 1)
    prestes_prox = _sobrevive(c1_femeas, _mort_adulto)      # c1 → prestes (25–36m)
    c1_femeas_prox = _sobrevive(c0_femeas, _mort_bezerra)   # c0 → c1
    c0_femeas_prox = _sobrevive(reter_f0, _mort_bezerra)    # nascidas retidas → c0
    c1_machos_prox = _sobrevive(c0_machos, _mort_bezerra)   # c0 → c1
    c0_machos_prox = _sobrevive(nascidos_m, _mort_bezerra)  # nascidos → c0

    # Somas para compatibilidade com quem só quer "jovem fêmea"/"jovem macho"
    # totais (arrobas_categorias, valorização) — a distinção por coorte
    # importa para a simulação, não para essas consumidoras externas.
    femeas_024_prx = round(c0_femeas_prox + c1_femeas_prox)
    machos_024_prx = round(c0_machos_prox + c1_machos_prox)
    total_prox = (mat_prox + prestes_prox + femeas_024_prx
                  + machos_024_prx + bois_prox)
    # Receita por categoria: boi/vaca em R$/@ (× peso), bezerra/bezerro em
    # R$/cabeça (direto). Sem preço da categoria → cai no preço da arroba único.
    p_boi  = preco_boi_arr  if preco_boi_arr  is not None else preco_arroba
    p_vaca = preco_vaca_arr if preco_vaca_arr is not None else preco_arroba
    receita = bois_vendidos * peso_boi * p_boi + desc_mat * peso_vaca * p_vaca
    receita += (bez_vend * preco_bezerra_cab if preco_bezerra_cab is not None
                else bez_vend * peso_bezerra * preco_arroba)
    receita += (machos_024_vend * preco_bezerro_cab if preco_bezerro_cab is not None
                else machos_024_vend * peso_garrote * preco_arroba)
    arrobas_rebanho = arrobas_categorias(
        matrizes=mat_prox, bois=bois_prox,
        jovens_f=femeas_024_prx, jovens_m=machos_024_prx,
        peso_vaca=peso_vaca, peso_boi=peso_boi,
        peso_bezerra=peso_bezerra, peso_garrote=peso_garrote)
    custo_tot = arrobas_rebanho * custo_arroba
    resultado = receita - custo_tot
    return {
        'bezerros_produzidos': int(bezerros),
        'bois_necessarios':    bois_nec,
        'bois_excedentes':     int(max(bois_disp - bois_nec, 0)),
        'machos_graduados':    int(graduados),
        'renovacao_bois':      renovacao,
        'bois_vendidos':       int(bois_vendidos),
        'descarte_matrizes':   desc_mat,
        'bezerras_vendidas':   bez_vend,
        'machos_024_vendidos': int(machos_024_vend),
        'total_vendido':       int(vendidos),
        'aumento_matrizes':    int(aumento),
        'mortes':              mortes,
        'matrizes_prox':       int(mat_prox),
        'bois_prox':           bois_prox,
        'prestes_matrizes_prox': prestes_prox,
        'c0_femeas_prox':      c0_femeas_prox,
        'c1_femeas_prox':      c1_femeas_prox,
        'c0_machos_prox':      c0_machos_prox,
        'c1_machos_prox':      c1_machos_prox,
        'femeas_024_prox':     int(femeas_024_prx),
        'machos_024_prox':     int(machos_024_prx),
        'total_prox':          int(total_prox),
        'receita':             round(receita, 2),
        'custo':               round(custo_tot, 2),
        'resultado':           round(resultado, 2),
    }

# ==================================================================
# 8. CENÁRIOS ECONÔMICOS
# ==================================================================
CENARIOS = {
    'otimista': {
        'nome': 'Otimista — Melhoria Tecnológica',
        'desc': 'IATF, suplementação, genética melhorada. Alta produtividade.',
        'emoji': '🚀',
        'mods': {'nat': 1.08, 'mort': 0.70, 'desc': 0.90, 'preco': 1.05}
    },
    'crescimento': {
        'nome': 'Crescimento Gradual',
        'desc': 'Expansão sustentável com reinvestimento de resultados.',
        'emoji': '📈',
        'mods': {'nat': 1.03, 'mort': 0.90, 'desc': 0.95, 'preco': 1.02}
    },
    'provavel': {
        'nome': 'Provável — Premissas neutras',
        'desc': 'Mantém as premissas informadas sem melhora ou piora de cenário.',
        'emoji': '📊',
        'mods': {'nat': 1.00, 'mort': 1.00, 'desc': 1.00, 'preco': 1.00}
    },
    'especulativo': {
        'nome': 'Especulativo — Alta Venda',
        'desc': 'Maximiza venda aproveitando preço favorável.',
        'emoji': '💰',
        'mods': {'nat': 1.00, 'mort': 1.00, 'desc': 1.20, 'preco': 1.10}
    },
    'conservador': {
        'nome': 'Conservador — Manutenção',
        'desc': 'Estabilidade mínima em cenário de baixa de preços.',
        'emoji': '🛡️',
        'mods': {'nat': 0.95, 'mort': 1.10, 'desc': 0.80, 'preco': 0.95}
    },
}

def _montar_resultado(cenario, sc, anos_proj, total_ini, ciclo):
    return {
        'cenario': cenario,
        'nome': sc['nome'],
        'emoji': sc['emoji'],
        'ciclo': ciclo,
        'anos': anos_proj,
        'acumulado': {
            'receita':   round(sum(a['receita']   for a in anos_proj), 2),
            'custo':     round(sum(a['custo']     for a in anos_proj), 2),
            'resultado': round(sum(a['resultado'] for a in anos_proj), 2),
        },
        'delta_rebanho': anos_proj[-1]['total'] - int(total_ini),
    }

def _simular_cria(
    v, cenario, nat_pct, mort_pct, desmama_pct, venda_bez_pct,
    preco_arroba_bezerro, custo_arroba, anos,
    peso_matriz=PESO_VACA_ARR, peso_bezerra=PESO_BEZERRA_ARR, preco_vaca_arr=None,
    desc_mat_pct=15.0,
):
    va  = np.array(v, dtype=float)
    sc  = CENARIOS.get(cenario, CENARIOS['crescimento'])
    m   = sc['mods']

    nat      = min((nat_pct / 100) * m['nat'], 0.95)
    mort     = (mort_pct / 100) * m['mort']
    # Taxa de bezerra pré-desmame é maior que a adulta (EMBRAPA: ~3.5× a adulta)
    mort_bez = min(mort * _RAZAO_MORT_BEZERRA, 0.25)
    # ── A cadeia reprodutiva, sem descontar a mesma perda três vezes ─────────
    #
    # Era: `desmamados = nascidos × desmama × (1 − mort_bez)`, com desmama
    # default de 82%. Vieira et al. (2005) mede a cadeia inteira num só rebanho
    # por quatro safras e mostra que `desmama = natalidade × (1 − mort_bez)` —
    # a identidade fecha com erro de 0,4 ponto. A desmama É o fim da cadeia.
    # Multiplicá-la pelos nascidos e ainda descontar a mortalidade descontava a
    # perda três vezes: 70% × 82% × 93% = 53,4 bezerros por 100 matrizes,
    # contra 77,2 medidos — e abaixo até do Pantanal extensivo (58,0).
    #
    # Ver a derivação e a tabela em services/parametros_zootecnicos.py.
    taxa_desmama = taxa_desmama_efetiva(
        natalidade_pct=nat * 100.0,
        mortalidade_bezerro_pct=mort_bez * 100.0,
        desmama_declarada_pct=desmama_pct)
    venda_bz = (venda_bez_pct / 100)
    preco_bz = (preco_arroba_bezerro * m['preco']) * peso_bezerra   # R$/cabeça derivado de R$/@
    # Preço da vaca descartada: usa preco_vaca_arr se informado, senão usa o mesmo preco/@ do bezerro
    _preco_vaca_cab = ((preco_vaca_arr if preco_vaca_arr is not None else preco_arroba_bezerro)
                       * m['preco']) * peso_matriz

    # Rebanho rastreado por COORTE, seguindo a metodologia do material de
    # treinamento: o que se comercializa no ano é o ESTOQUE DECLARADO, não os
    # bezerros que ainda vão nascer. Os nascidos deste ano viram o estoque de
    # 0–12 meses do ano seguinte.
    #
    # Modelar como "nascem e vendem no mesmo ano" subestimava a receita pela
    # metade em qualquer rebanho com estoque jovem relevante, e o custo era
    # cobrado sobre o rebanho inteiro — daí o caixa negativo.
    bez_F     = float(va[0] + va[2])   # fêmeas 0–12m
    bez_M     = float(va[1] + va[3])   # machos 0–12m
    mac_R     = float(va[5] + va[7])   # machos 13–36m (sem função na cria)

    # ── Quem pare e quem ainda vai parir ─────────────────────────────────────
    #
    # Era `matrizes = va[6] + va[8]` e `nov_F = va[4]`. A faixa de 25–36 meses
    # entrava inteira na BASE REPRODUTIVA, e isso contradiz o que este mesmo
    # arquivo já afirma na guarda de classificação, com fonte:
    #
    #     "a fêmea da faixa de 25–36m ainda NÃO PARIU — contá-la como matriz
    #      projeta bezerro que ainda não existe"
    #
    # A Embrapa Gado de Corte apurou 36,3 meses de idade média à primeira
    # parição em 468 matrizes Nelore; no Pantanal extensivo são 40,0. Uma fêmea
    # de 30 meses não tem bezerro ao pé.
    #
    # QUANTO CUSTAVA, medido numa cria de 1.775 cabeças:
    #
    #     base reprodutiva ..... 750 contra 600 reais
    #     nascidos por ano ..... 525 contra 420
    #     105 bezerros por ano que a fazenda não produz
    #
    # É o mesmo defeito que a checagem de consistência tinha na superfície — a
    # mesma fêmea contada como plantel a repor E como reposição — só que uma
    # camada abaixo, no motor.
    #
    # POR QUE ELA VAI PARA A REPOSIÇÃO E NÃO SOME: ela é exatamente o estoque
    # de reposição. Em até um ano cruza os 36 meses e vira matriz de fato, e é
    # isso que `promovidas` representa. O rebanho não perde a fêmea — ela muda
    # de papel, do lado que produz para o lado que ainda vai produzir.
    #
    # DIREÇÃO DO ERRO CORRIGIDO: para baixo. A projeção passa a nascer menos
    # bezerro, o resultado cai e o DSCR cai junto — o lado de reprovar. É o
    # sentido seguro num produto de crédito, e aqui é também o sentido certo.
    matrizes  = float(va[8])           # já pariram: acima de 36 meses
    nov_F     = float(va[4])           # reposição jovem: 13–24 meses
    # Coorte que ENVELHECE para dentro da base reprodutiva. Ver `_prestes` no
    # laço: ela não disputa a regra de manutenção, porque cruzar os 36 meses
    # não é decisão de manejo — é o calendário.
    prestes_F = float(va[6])           # 25–36 meses
    bois      = float(va[9])           # touros de serviço
    total_ini = float(va.sum())

    # ── Promoção de novilhas: mira a MANUTENÇÃO do plantel ───────────────────
    #
    # Era `promovidas = nov_F × min(max(desc_mat_pct/100, 0.20), 0.35)` — uma
    # fração das novilhas DISPONÍVEIS, vinda do material de treinamento como
    # faixa de retenção de 20–35%.
    #
    # O problema não era a faixa: era o denominador. Aplicada sobre as novilhas
    # e não sobre as matrizes, com poucas novilhas na base, ela produzia:
    #
    #     promovidas = 100 novilhas × 0,20 ....... 20 cabeças
    #     descarte   = 750 matrizes × 0,10 ....... 75 cabeças
    #     reposição efetiva ...................... 2,7% das matrizes
    #
    # A base reprodutiva perdia ~50 cabeças por ano POR CONSTRUÇÃO, o plantel
    # caía 45% em cinco anos, a receita caía junto e o DSCR dos anos 2+ desabava.
    # Medido: nem retendo 100% das bezerras o rebanho parava de encolher.
    #
    # QUAL É O NÚMERO DE UMA CRIA DE VERDADE
    #
    # O painel da Embrapa Pantanal (CT 126, Tabela 4) publica taxa de reposição
    # de descendentes sobre matrizes de 14,00% ao ano — e o próprio documento a
    # confirma por outro caminho: idade da primeira cria 40 meses e vida total
    # da vaca 12,08 anos dão 8,75 anos de vida produtiva, ou 11,4%/ano só para
    # manter o plantel. Dois números independentes da mesma tabela.
    #
    # Que é reposição PRÓPRIA, e não compra, decide-se pela composição do custo
    # no mesmo painel: aquisição de animais é 6% do COE. Repor 14% de 2.500
    # vacas comprando seriam 350 matrizes/ano, o que não cabe em 6%.
    #
    # POR QUE MIRAR MANUTENÇÃO E NÃO OS 14%
    #
    # Os 14% são daquele sistema — primeira cria aos 40 meses, 0,30 UA/ha. Uma
    # fazenda que emprenha novilha aos 24 meses repõe mais rápido, e transportar
    # o número inteiro repetiria o erro de tratar medição de um sistema como
    # constante nacional. Pior: 14% contra 10% de descarte projeta plantel
    # CRESCENDO 4% ao ano, e projetar crescimento de rebanho infla receita
    # futura — a direção perigosa num produto de crédito.
    #
    # Então a regra é: promover o necessário para repor o descarte, limitado
    # pelas novilhas que a ficha tem. O 14% do painel entra como evidência de
    # que uma cria viável opera nesse patamar, não como meta.
    #
    # A propriedade que mais importa: quando o plantel encolher no parecer, vai
    # ser porque a ficha NÃO TEM NOVILHA — razão real, que o analista vê na
    # composição — e não por causa de uma constante.

    anos_proj = []
    for yr in range(1, anos + 1):
        nascidos   = matrizes * nat
        desmamados = matrizes * taxa_desmama

        # ── Comercialização ─────────────────────────────────────────────────
        # A base de venda é o estoque de 0–12m declarado, mas nunca abaixo do
        # que as matrizes entregam no ano: uma ficha sem bezerros (rebanho
        # recém-formado ou declaração parcial) ainda comercializa os
        # desmamados do próprio ano. O que for vendido além do estoque sai da
        # safra corrente e é descontado do inventário de fechamento.
        _desm_M = desmamados * 0.5
        _desm_F = desmamados * 0.5
        disp_M  = max(bez_M, _desm_M)
        disp_F  = max(bez_F, _desm_F)
        _antecip_M = max(disp_M - bez_M, 0.0)     # veio dos nascidos do ano
        _antecip_F = max(disp_F - bez_F, 0.0)

        vende_bez_M = disp_M                      # todo macho desmamado sai
        vende_bez_F = disp_F * venda_bz           # parte das bezerras
        retem_bez_F = disp_F - vende_bez_F
        descarte_mat = round(matrizes * (desc_mat_pct / 100))
        # Repõe o descarte E as matrizes que morrem — repor só o descarte
        # deixava o plantel caindo pela mortalidade (3% ao ano, 15% em cinco).
        # Se não houver novilha bastante, promove o que tem.
        # ── Duas promoções, com regras diferentes ────────────────────────────
        #
        # A coorte de 25–36m cruza os 36 meses dentro do ano. Isso não é decisão
        # de manejo, é calendário — ela entra na base reprodutiva inteira.
        #
        # POR QUE ELA NÃO PODE ENTRAR NA REGRA DE MANUTENÇÃO: medido, dava um
        # salto de venda no ano 1. Com 150 fêmeas de 25–36m e apenas 78 baixas
        # a repor, a regra promovia 78 e mandava 172 para a venda — o ano 1 de
        # uma cria passava de 785 para 955 cabeças vendidas e o resultado subia
        # 46%. É a ilusão do ano 1 outra vez, agora liquidando a fêmea que está
        # prestes a parir.
        #
        # Também não é "projetar crescimento de rebanho", que é a coisa perigosa
        # que o comentário acima adverte: estas fêmeas JÁ ESTÃO na ficha. Contar
        # que elas amadureçam é descrever o declarado, não extrapolar.
        #
        # A regra de manutenção continua valendo para a coorte de 13–24m, que é
        # onde o produtor de fato escolhe entre reter e vender.
        _baixas_mat = float(descarte_mat) + matrizes * mort
        _falta      = max(_baixas_mat - prestes_F, 0.0)
        promovidas  = prestes_F + min(nov_F, _falta)
        vende_nov_F = max(nov_F - min(nov_F, _falta), 0.0)   # excedente jovem
        vende_mac_R = mac_R                       # machos de recria saem

        machos_vend  = vende_bez_M + vende_mac_R
        femeas_vend  = vende_bez_F
        femeas_exced = vende_nov_F
        vez_vendidos = machos_vend + femeas_vend + femeas_exced

        # ── Receita por categoria ───────────────────────────────────────────
        _preco_novilha_cab = ((preco_vaca_arr if preco_vaca_arr is not None
                               else preco_arroba_bezerro) * m['preco']) * PESO_JOVEM_F_ARR
        _preco_garrote_cab = (preco_arroba_bezerro * m['preco']) * PESO_GARROTE_ARR
        receita = (
            (vende_bez_M + vende_bez_F) * preco_bz
            + vende_mac_R * _preco_garrote_cab
            + femeas_exced * _preco_novilha_cab
            + descarte_mat * _preco_vaca_cab
        )

        # ── Custo sobre o rebanho mantido no ano ────────────────────────────
        _touros = bois if bois > 0 else (max(round(matrizes / 30.0), 1) if matrizes > 0 else 0)
        # `prestes_F` estava de fora e a coorte pastava de graça no modelo — o
        # teste de custo por arroba pegou. Ela come como novilha adulta: peso de
        # fêmea jovem, não de matriz, porque ainda não pariu nem amamenta.
        custo_manutencao = (matrizes * peso_matriz
                            + (bez_F + bez_M) * peso_bezerra
                            + (nov_F + prestes_F + mac_R) * PESO_JOVEM_F_ARR
                            + _touros * PESO_BOI_ARR) * custo_arroba

        # ── Compra de desmama ───────────────────────────────────────────────
        # Coorte de 0–12m acima do que as matrizes entregam só pode ter sido
        # comprada. `services.consistencia_rebanho.estimar_compra_animais` já
        # detectava e sinalizava isso, mas o fluxo de caixa nunca debitava nada
        # — e o modelo, ao projetar o ano seguinte só com produção própria,
        # assumia em silêncio que o produtor PARA de comprar.
        #
        # Essa suposição não é neutra: é ela que faz o rebanho encolher e
        # produz a variação de estoque negativa. As duas leituras são legítimas
        # e dão pareceres diferentes:
        #
        #   não repõe (default) — rebanho converge para a produção própria;
        #       sem custo de compra, mas o estoque perde valor
        #   repõe               — mantém a estrutura declarada; estoque estável,
        #       ao custo de comprar a diferença todo ano
        #
        # O default mantém o comportamento histórico. O que muda é que a
        # suposição passa a ser declarada, em vez de implícita.
        compra_desmama = max((bez_F + bez_M) - nascidos, 0.0)
        custo_compra   = (compra_desmama * preco_bz
                          if (_REPOR_COMPRA_DESMAMA and _REPOSICAO_PRECIFICADA)
                          else 0.0)

        custo     = custo_manutencao + custo_compra
        resultado = receita - custo

        # ── Estado no fim do ano (balanço fechado) ──────────────────────────
        mortes = round((matrizes + nov_F + prestes_F + mac_R + bois) * mort
                       + (nascidos - desmamados))
        # `mortes` acima já contabiliza a mortalidade das matrizes, mas o
        # fechamento não a descontava: as matrizes mortas continuavam no
        # plantel, e o balanço fechava com mais animais do que entrou. Todas as
        # outras categorias (nov_F, bois) já aplicavam a perda.
        matrizes_prox = max(matrizes * (1 - mort) + promovidas - descarte_mat,
                            matrizes * 0.7)
        nov_F_prox    = max(retem_bez_F - retem_bez_F * mort, 0.0)
        # A coorte de 25–36m declarada existe UMA vez: no ano 1 ela cruza os 36
        # meses e vira base reprodutiva. Do ano 2 em diante quem alimenta a
        # promoção é a regra de manutenção sobre as bezerras retidas, que é o
        # ponto em que o produtor de fato escolhe entre reter e vender.
        prestes_F     = 0.0
        # A safra do ano forma o estoque de 0–12m seguinte, menos o que já foi
        # antecipado para venda.
        bez_F_prox    = max(_desm_F - _antecip_F, 0.0)
        bez_M_prox    = max(_desm_M - _antecip_M, 0.0)
        if _REPOR_COMPRA_DESMAMA and compra_desmama > 0:
            # A compra recompõe a coorte jovem na proporção declarada, então a
            # estrutura do rebanho se mantém em vez de convergir para a
            # produção própria.
            _frac_f_jov = (bez_F / (bez_F + bez_M)) if (bez_F + bez_M) > 0 else 0.5
            bez_F_prox += compra_desmama * _frac_f_jov
            bez_M_prox += compra_desmama * (1 - _frac_f_jov)
        mac_R_prox    = 0.0
        bois_prox     = max(bois - bois * mort, 0.0)
        total_prox    = int(matrizes_prox + nov_F_prox + bez_F_prox
                            + bez_M_prox + mac_R_prox + bois_prox)

        anos_proj.append({
            'ano': yr,
            'total': total_prox,
            'matrizes': int(matrizes_prox),
            'bezerros': int(nascidos),
            'vendidos': int(vez_vendidos),
            'bois_vendidos': int(machos_vend),
            'matrizes_descartadas': descarte_mat,
            'bezerras_vendidas': int(femeas_vend),
            'machos_vendidos': int(machos_vend),
            'femeas_excedentes': int(femeas_exced),
            'aumento_matrizes': int(promovidas - descarte_mat),
            'receita': round(receita, 2),
            'custo': round(custo, 2),
            'custo_manutencao': round(custo_manutencao, 2),
            'custo_compra_desmama': round(custo_compra, 2),
            'compra_desmama_estimada': int(round(compra_desmama)),
            'repoe_compra_desmama': bool(_REPOR_COMPRA_DESMAMA),
            'resultado': round(resultado, 2),
            'bois_fim':     int(bois_prox),
            'jovens_f_fim': int(nov_F_prox + bez_F_prox),
            'jovens_m_fim': int(bez_M_prox + mac_R_prox),
            'compras':      0,
            'mortes':       int(mortes),
        })
        matrizes = matrizes_prox
        nov_F    = nov_F_prox
        bez_F    = bez_F_prox
        bez_M    = bez_M_prox
        mac_R    = mac_R_prox
        bois     = bois_prox

    result = _montar_resultado(cenario, sc, anos_proj, total_ini, 'CRIA')
    ano1 = anos_proj[0]
    # Na cria a receita é por bezerro/bezerra vendido, não por arroba.
    # Multiplicar as cabeças pelo peso e rotular como R$/arroba misturava
    # unidades e subestimava o preço mínimo por animal.
    units = float(max(ano1['vendidos'], 1))
    result.update({
        'preco_breakeven':         round(ano1['custo'] / units, 2),
        'preco_breakeven_unidade': 'R$/cabeça',
        'preco_usado':             preco_bz,
        'slider_units':            units,
        'slider_custo_ano1':       ano1['custo'],
        'margem_atual_pct':        round(ano1['resultado'] / max(ano1['custo'], 1) * 100, 1),
        'margem_atual_rs':         round(ano1['resultado'], 2),
    })
    return result

def _simular_recria(
    v, cenario, mort_pct, preco_arroba, peso_entrada_arr, peso_saida_arr,
    meses_recria, custo_arroba, anos, preco_reposicao_cab=None,
    reposicao_pct=100.0,
):
    """
    Recria por coortes etárias.

    O modelo anterior tratava 5–25 meses como um pool único e vendia 100% dele
    todo ano — inclusive os de 5–12 meses, que acabaram de entrar, e ainda os
    precificava pelo peso de SAÍDA da recria. Ao mesmo tempo, tudo fora dessa
    faixa (25–36m e >36m) caía num balde que não era vendido em ano nenhum.

    Contra a ficha real de 700 cabeças (INDICADORES: desfrute-base 45%, giro
    12–18 meses, reposição 1:1) isso projetava 443 vendas — desfrute 63%,
    acima da própria faixa de referência 35–55% — contra as 315 da ficha.
    Receita superestimada em ~41%, e o DSCR junto.

    Agora saem os animais já terminados (25m+, integralmente) e a parcela dos
    machos de 13–24m que atingiu o peso. Fêmeas de 13–24m e todo o 0–12m ficam
    para evoluir — é o que a ficha chama de "permanência / evolução".

    Receita = animais_sai × peso_saida_arr × preço (memorial §6). Aplicar o
    peso de saída a todos passa a ser legítimo: só sai quem o atingiu.
    """
    va  = np.array(v, dtype=float)
    sc  = CENARIOS.get(cenario, CENARIOS['crescimento'])
    m   = sc['mods']

    mort  = (mort_pct / 100) * m['mort']
    preco = preco_arroba * m['preco']
    ganho_arr = max(peso_saida_arr - peso_entrada_arr, 0.0)
    _repos_frac = min(max(float(reposicao_pct), 0.0), 100.0)

    c0_f, c0_m = float(va[0] + va[2]), float(va[1] + va[3])   # 0–12 meses
    c1_f, c1_m = float(va[4]), float(va[5])                    # 13–24 meses
    c2_f, c2_m = float(va[6]), float(va[7])                    # 25–36 meses
    c3_f, c3_m = float(va[8]), float(va[9])                    # acima de 36
    total_ini = float(va.sum())

    anos_proj = []
    for yr in range(1, anos + 1):
        plantel_ini = c0_f + c0_m + c1_f + c1_m + c2_f + c2_m + c3_f + c3_m
        mortes = plantel_ini * mort

        s = 1.0 - mort
        c0_f, c0_m = c0_f * s, c0_m * s
        c1_f, c1_m = c1_f * s, c1_m * s
        c2_f, c2_m = c2_f * s, c2_m * s
        c3_f, c3_m = c3_f * s, c3_m * s

        # Saídas
        vend_c1_m   = c1_m * _FRAC_VENDA_RECRIA_M
        machos_sai  = c3_m + c2_m + vend_c1_m
        femeas_sai  = c3_f + c2_f
        animais_sai = machos_sai + femeas_sai

        receita = animais_sai * peso_saida_arr * preco
        peso_medio = (peso_entrada_arr + peso_saida_arr) / 2.0
        custo_manutencao = plantel_ini * peso_medio * custo_arroba * (meses_recria / 12.0)

        # Envelhecimento de quem ficou: 25m+ zerou (saiu tudo), 13–24 sobe para
        # 25–36, 0–12 sobe para 13–24.
        n3_f = n3_m = 0.0
        n2_f, n2_m = c1_f, c1_m - vend_c1_m
        n1_f, n1_m = c0_f, c0_m

        # Reposição por compra, entrando como jovem e macho: a recria compra
        # bezerro desmamado, não boi magro, e a relação de troca é outra
        # (≈9,26@ contra 12,4@).
        #
        # Era 1:1 fixo — `compras = animais_sai` —, número que veio da ficha de
        # 700 cabeças (venda 315 → compra 315) e virou lei do motor. A ficha de
        # estoque não comprova reposição: não diz se o produtor recompra o
        # lote, reduz a escala ou traz os animais da própria cria. Agora é
        # premissa declarável, com o default no comportamento antigo.
        compras = animais_sai * (_repos_frac / 100.0)
        n0_f, n0_m = 0.0, compras

        # O MESMO animal precisa ser comprado e valorado pelo mesmo preço.
        #
        # O sistema precificava um bezerro desmamado de três formas: a compra
        # pela relação de troca (9,26@ = R$ 2.963 com boi a R$ 320), o estoque
        # de fechamento pelo peso da bezerra (6,00@ = R$ 1.920) e a cotação da
        # interface (6,67@ × 1,05 = R$ 2.241). Nenhuma está errada em si — a
        # relação de troca tem fonte de mercado e o peso é peso — mas usar
        # bases diferentes nas duas pontas cria ou destrói valor no papel a
        # cada reposição, sem que nada tenha acontecido na fazenda.
        #
        # Medido num caso real de 753 cabeças: R$ 1.043 por cabeça reposta,
        # R$ 215.942 no ano 1, o bastante para inverter o sinal do resultado.
        #
        # Quando há cotação de bezerro do dia, ela vale para as duas pontas. A
        # relação de troca fica como fallback — é referência de mercado, não
        # cotação da praça, e só entra quando não há cotação.
        _p_repo = (preco_reposicao_cab * m['preco'] if preco_reposicao_cab
                   else TROCA_ARROBAS_BEZERRO * preco)
        custo_reposicao = (compras * _p_repo
                           if _REPOSICAO_PRECIFICADA else 0.0)
        custo     = custo_manutencao + custo_reposicao
        resultado = receita - custo

        total_fim = n0_f + n0_m + n1_f + n1_m + n2_f + n2_m + n3_f + n3_m
        anos_proj.append({
            'ano': yr,
            'total': int(round(total_fim)),
            'matrizes': int(round(n3_f + n2_f)),
            'bezerros': 0,
            'vendidos': int(round(animais_sai)),
            'bois_vendidos': int(round(animais_sai)),
            'matrizes_descartadas': 0,
            'bezerras_vendidas': 0,
            'machos_vendidos': int(round(machos_sai)),
            'femeas_vendidas': int(round(femeas_sai)),
            'aumento_matrizes': 0,
            'ganho_arrobas_por_animal': round(ganho_arr, 2),
            'receita': round(receita, 2),
            'custo': round(custo, 2),
            'custo_manutencao': round(custo_manutencao, 2),
            'custo_reposicao':  round(custo_reposicao, 2),
            'resultado': round(resultado, 2),
            'bois_fim': int(round(n3_m + n2_m)),
            'jovens_f_fim': int(round(n0_f + n1_f)),
            'jovens_m_fim': int(round(n0_m + n1_m)),
            'compras':      int(round(compras)),
            'reposicao_pct': _repos_frac,
            'mortes':       int(round(mortes)),
        })
        c0_f, c0_m = n0_f, n0_m
        c1_f, c1_m = n1_f, n1_m
        c2_f, c2_m = n2_f, n2_m
        c3_f, c3_m = n3_f, n3_m


    result = _montar_resultado(cenario, sc, anos_proj, total_ini, 'RECRIA')
    ano1  = anos_proj[0]
    # Breakeven: R$/arroba total na saída (memorial §6)
    units = float(max(ano1['vendidos'], 1)) * peso_saida_arr
    result.update({
        'preco_breakeven':         round(ano1['custo'] / max(units, 1), 2),
        'preco_breakeven_unidade': 'R$/arroba',
        'preco_usado':             preco,
        'slider_units':            round(units, 2),
        'slider_custo_ano1':       ano1['custo'],
        'margem_atual_pct':        round(ano1['resultado'] / max(ano1['custo'], 1) * 100, 1),
        'margem_atual_rs':         round(ano1['resultado'], 2),
    })
    return result

def _simular_engorda(
    v, cenario, mort_pct, preco_arroba, peso_entrada_kg, peso_saida_kg,
    rendimento_carcaca, custo_arroba, dias_engorda, anos,
):
    """
    Receita calculada sobre o PESO TOTAL NA SAÍDA — arrobas de carcaça
    (memorial §7 e §12). O comprador paga pelo peso do animal abatido,
    não apenas pelo ganho obtido no confinamento.

    arrobas_por_boi = peso_saida_kg × rendimento% / 15
    Receita         = bois_abatidos × arrobas_por_boi × preco
    Breakeven       = custo_ano1    / (bois_abatidos  × arrobas_por_boi)  [R$/arroba]
    """
    va  = np.array(v, dtype=float)
    sc  = CENARIOS.get(cenario, CENARIOS['crescimento'])
    m   = sc['mods']

    mort  = (mort_pct / 100) * m['mort']
    preco = preco_arroba * m['preco']
    rend  = rendimento_carcaca / 100

    arrobas_saida = (peso_saida_kg * rend) / 15.0
    ganho_arrobas = max(arrobas_saida - (peso_entrada_kg * rend) / 15.0, 0.0)

    # Bois em engorda = machos adultos (v[7]+v[9])
    bois      = float(va[7] + va[9])
    # Demais categorias declaradas: fora do lote de confinamento, mas seguem
    # no plantel — sem contá-las o fechamento acusa perda de animais inexistente.
    #
    # va[8] (fêmeas acima de 36 meses) ficava de FORA das duas listas e sumia
    # do modelo inteiro: numa ficha de recria/engorda com 60 matrizes o
    # fechamento perdia exatamente essas 60 cabeças, e a variação de estoque
    # registrava uma perda patrimonial que nunca aconteceu.
    outros_f  = float(va[0] + va[2] + va[4] + va[6] + va[8])
    outros_m  = float(va[1] + va[3] + va[5])
    total_ini = float(va.sum())
    # ── Giros por ano: fracionário, não truncado ─────────────────────────────
    #
    # Era `max(1, int(365/dias))`. A truncagem inteira jogava fora produção
    # real: a engorda não zera em 31 de dezembro, e o lote a meio caminho na
    # virada continua no pasto — o nosso próprio modelo o carrega no inventário
    # de fechamento. Numa projeção de cinco anos, a média correta de giros é a
    # fracionária.
    #
    # O tamanho do estrago aparecia ao ligar o GMD ao nível tecnológico:
    #
    #     extensivo   0,45 kg/dia   256 dias   1,43 giros → truncado a 1  (−30%)
    #     médio       0,65          177        2,06       → truncado a 2  (−3%)
    #     intensivo   0,85          135        2,70       → truncado a 2  (−26%)
    #
    # Médio e intensivo colapsavam no mesmo número, e o nível deixava de
    # distinguir justamente onde deveria. Pior: o custo é cobrado por
    # `dias_engorda/365`, então truncar os giros truncava a despesa junto e o
    # modelo subcobrava — o erro não era conservador, era só ruído.
    lotes_ano = 365.0 / max(float(dias_engorda), 30.0)

    anos_proj = []
    for yr in range(1, anos + 1):
        bois_no_ano   = bois * lotes_ano
        mortes        = bois_no_ano * mort
        bois_abatidos = bois_no_ano - mortes

        # Receita = arrobas totais de carcaça na saída (memorial §7)
        receita   = bois_abatidos * arrobas_saida * preco
        arrobas_media = (arrobas_saida + (peso_entrada_kg * rend) / 15.0) / 2.0
        custo_manutencao = bois_no_ano * arrobas_media * custo_arroba * (dias_engorda / 365.0)

        bois_prox = bois * (1 + min(0.05, 0.04 * m['nat']))
        # O confinamento gira `lotes_ano` lotes: vende bois_abatidos e repõe
        # comprando magros. A compra é explicitada para o balanço de animais
        # fechar; o CUSTO dela ainda NÃO entra no resultado (ver README/parecer).
        compras = max(bois_prox + bois_abatidos + mortes - bois, 0.0)
        outros_f_prox = max(outros_f - outros_f * mort, 0.0)
        outros_m_prox = max(outros_m - outros_m * mort, 0.0)
        # Reposição 1:1 — cada animal vendido é reposto por um boi magro
        # comprado. Preço derivado da relação de troca sobre o boi gordo.
        custo_reposicao = (compras * TROCA_ARROBAS_BOI_MAGRO * preco
                           if _REPOSICAO_PRECIFICADA else 0.0)
        custo     = custo_manutencao + custo_reposicao
        resultado = receita - custo

        anos_proj.append({
            'ano': yr,
            'total': int(bois_prox + outros_f_prox + outros_m_prox),
            'compras': int(compras),
            'mortes': int(mortes + (outros_f + outros_m) * mort),
            'matrizes': 0,
            'bezerros': 0,
            'vendidos': int(bois_abatidos),
            'bois_vendidos': int(bois_abatidos),
            'matrizes_descartadas': 0,
            'bezerras_vendidas': 0,
            'machos_vendidos': int(bois_abatidos),
            'aumento_matrizes': 0,
            'arrobas_por_boi': round(arrobas_saida, 2),
            'arrobas_ganho_por_boi': round(ganho_arrobas, 2),
            'lotes_por_ano': round(lotes_ano, 2),
            'ganho_peso_kg': round(peso_saida_kg - peso_entrada_kg, 1),
            'receita': round(receita, 2),
            'custo': round(custo, 2),
            'custo_manutencao': round(custo_manutencao, 2),
            'custo_reposicao':  round(custo_reposicao, 2),
            'resultado': round(resultado, 2),
            'bois_fim': int(bois_prox),
            'jovens_f_fim': int(outros_f_prox),
            'jovens_m_fim': int(outros_m_prox),
        })
        bois     = bois_prox
        outros_f = outros_f_prox
        outros_m = outros_m_prox

    result = _montar_resultado(cenario, sc, anos_proj, total_ini, 'ENGORDA')
    ano1  = anos_proj[0]
    # Breakeven: R$/arroba total na saída (memorial §7)
    units = float(max(ano1['vendidos'], 1)) * arrobas_saida
    result.update({
        'preco_breakeven':         round(ano1['custo'] / max(units, 1), 2),
        'preco_breakeven_unidade': 'R$/arroba',
        'preco_usado':             preco,
        'slider_units':            round(units, 2),
        'slider_custo_ano1':       ano1['custo'],
        'margem_atual_pct':        round(ano1['resultado'] / max(ano1['custo'], 1) * 100, 1),
        'margem_atual_rs':         round(ano1['resultado'], 2),
    })
    return result

def simular_cenario(
    v: list,
    cenario:        str   = 'crescimento',
    nat_pct:        float = None,
    mort_pct:       float = 3.0,        # memorial §16: 3%
    desc_pct:       float = None,
    preco_arroba:   float = 320.0,      # memorial §16: R$320
    custo_arroba:   float = 57.0,       # R$/@ ano (default de formulário)
    custo_arroba_cria:    float = None,  # se informado, substitui custo_arroba p/ cria
    custo_arroba_recria:  float = None,  # se informado, substitui custo_arroba p/ recria
    custo_arroba_engorda: float = None,  # se informado, substitui custo_arroba p/ engorda
    peso_arroba:    float = PESO_BEZERRA_ARR,  # bezerra desmame GEP (6.00@)
    peso_garrote:   float = PESO_GARROTE_ARR,  # garrote macho jovem GEP (10.67@)
    prop_boi:       float = None,
    renov_boi_pct:  float = None,
    venda_bez_pct:  float = None,
    anos:           int   = 5,
    ciclo:              str   = 'CICLO_COMPLETO',
    preco_bezerro:      float = 1800.0, # memorial §16: R$1.800
    preco_arroba_bezerro: float = None, # R$/@ do bezerro; default = preco_arroba
    # None → derivada da cadeia (natalidade × sobrevivência), que é a definição.
    # Um número aqui é DECLARAÇÃO do analista sobre aquela fazenda, e vence.
    # Era DESMAME_PCT (82%) por default, e esse 82% entrava como FATOR sobre os
    # nascidos — ver a correção da cadeia em _simular_cria.
    desmama_pct:        float = None,
    peso_entrada_arr:   float = _PESO_ENTRADA_RECRIA_ARR,
    peso_saida_arr:     float = _PESO_SAIDA_RECRIA_ARR,
    meses_recria:       int   = 12,
    peso_entrada_kg:    float = _PESO_ENTRADA_ENGORDA_KG,
    peso_saida_kg:      float = 520.0,  # memorial §16: 520kg
    rendimento_carcaca: float = 52.0,
    ganho_peso_kg_dia:  float = None,   # GMD; default = meio da faixa adequado
    dias_engorda:       int   = None,   # None → derivado do ganho e do GMD
    peso_boi:           float = PESO_BOI_ARR,   # GEP Araguaia (20.53@)
    peso_vaca:          float = PESO_VACA_ARR,  # GEP Araguaia (15.33@)
    preco_boi_arr:      float = None,   # R$/@ boi do dia (senão usa preco_arroba)
    preco_vaca_arr:     float = None,   # R$/@ vaca do dia
    preco_bezerra_cab:  float = None,   # R$/cabeça bezerra do dia
    preco_bezerro_cab:  float = None,   # R$/cabeça bezerro do dia
    reposicao_pct:      float = 100.0,  # RECRIA: % do lote que sai e é recomprado
) -> dict:
    # ── Duração da engorda: derivada, não fixa ───────────────────────────────
    #
    # `dias_engorda` era 90 fixo. Com entrada de 405 kg e saída de 520, isso
    # implica ganho de 1,28 kg/dia — ACIMA do 1,10 medido em semiconfinamento
    # (estudo de campo em Theobroma/RO, 100 nelores, pesagem em jejum a cada
    # 20 dias), e o perfil de custo da ENGORDA descreve pasto com suplementação,
    # não confinamento.
    #
    # O efeito era grande porque `lotes_ano = int(365/dias)`: 90 dias dá QUATRO
    # giros por ano sobre o mesmo lote. Medido numa engorda de 736 cabeças,
    # isso projetava desfrute de 273% contra a faixa de referência de 80–120%,
    # e DSCR de 6,14 — o erro corria a favor de APROVAR, que é o lado caro.
    #
    # Agora a duração sai do ganho de peso dividido pelo GMD. O GMD default é o
    # meio da faixa "adequado" do nosso próprio benchmark de engorda a pasto
    # (700–1000 g/dia), e o analista pode informar o dele. Quem passa a mandar
    # é a zootecnia, não uma constante.
    if dias_engorda is None:
        # 0,85 era o default aqui também — ver GMD_PADRAO_SEM_NIVEL, que
        # explica por que supor precoce de quem não declarou nada é a
        # suposição mais otimista possível.
        _gmd = max(float(ganho_peso_kg_dia or _GMD_PADRAO_SEM_NIVEL), 0.20)
        _ganho_kg = max(float(peso_saida_kg) - float(peso_entrada_kg), 1.0)
        dias_engorda = int(round(_ganho_kg / _gmd))

    # Preenche defaults a partir de PARAMS_POR_CICLO quando não passados explicitamente
    ciclo_params = PARAMS_POR_CICLO.get(ciclo, PARAMS_POR_CICLO['CICLO_COMPLETO'])
    if prop_boi      is None: prop_boi      = ciclo_params['prop_boi']
    if renov_boi_pct is None: renov_boi_pct = ciclo_params['renov_boi_pct']
    if desc_pct      is None: desc_pct      = ciclo_params['desc_mat_pct']
    if venda_bez_pct is None: venda_bez_pct = ciclo_params['venda_bez_pct']
    if nat_pct       is None: nat_pct       = ciclo_params.get('nat_pct', 75.0)
    if preco_arroba_bezerro is None: preco_arroba_bezerro = preco_arroba

    _custo_cria    = custo_arroba_cria    if custo_arroba_cria    is not None else custo_arroba
    _custo_recria  = custo_arroba_recria  if custo_arroba_recria  is not None else custo_arroba
    _custo_engorda = custo_arroba_engorda if custo_arroba_engorda is not None else custo_arroba

    # CRIA_RECRIA usa o motor de cria: mantém matrizes e produção própria. A
    # compra de desmama já é captada pelo balanço de animais (a coorte 0–12m
    # declarada entra no vetor) e precificada pela reposição.
    if ciclo in ('CRIA', 'CRIA_RECRIA'):
        return _simular_cria(
            v, cenario, nat_pct, mort_pct, desmama_pct, venda_bez_pct,
            preco_arroba_bezerro, _custo_cria, anos,
            peso_matriz=peso_vaca, peso_bezerra=peso_arroba,
            preco_vaca_arr=preco_vaca_arr,
            desc_mat_pct=desc_pct,
        )
    # RECRIA_ENGORDA termina o animal comprado magro — mesmo motor da engorda,
    # cujo custo já inclui a reposição 1:1.
    if ciclo == 'RECRIA_ENGORDA':
        return _simular_engorda(
            v, cenario, mort_pct, preco_arroba, peso_entrada_kg, peso_saida_kg,
            rendimento_carcaca, _custo_engorda, dias_engorda, anos,
        )
    if ciclo == 'RECRIA':
        # A cotação de bezerro do dia, quando existe, é a mesma dos dois lados
        # — compra e estoque. Ver o comentário em _simular_recria.
        return _simular_recria(
            v, cenario, mort_pct, preco_arroba, peso_entrada_arr, peso_saida_arr,
            meses_recria, _custo_recria, anos,
            preco_reposicao_cab=preco_bezerro_cab,
            reposicao_pct=reposicao_pct,
        )
    if ciclo == 'ENGORDA':
        return _simular_engorda(
            v, cenario, mort_pct, preco_arroba, peso_entrada_kg, peso_saida_kg,
            rendimento_carcaca, _custo_engorda, dias_engorda, anos,
        )

    # CICLO_COMPLETO
    va  = np.array(v, dtype=float)
    sc  = CENARIOS.get(cenario, CENARIOS['crescimento'])
    m   = sc['mods']

    nat  = min((nat_pct  / 100) * m['nat'],  0.95)
    mort = (mort_pct / 100) * m['mort']
    desc = min((desc_pct / 100) * m['desc'], 0.99)

    # Coortes reais, não um pool 0–24m misturado — ver calcular_ano. c0 é
    # 0–12m (as duas sub-faixas mais jovens do vetor), c1 é 13–24m.
    c0_femeas = float(va[0]+va[2])
    c1_femeas = float(va[4])
    c0_machos = float(va[1]+va[3])
    c1_machos = float(va[5])
    # Base reprodutiva = só quem já pariu (acima de 36 meses). A faixa de
    # 25–36m entra como coorte que AMADURECE — mesma correção de _simular_cria,
    # e pela mesma fonte: idade média à primeira parição de 36,3 meses
    # (Embrapa, 468 matrizes Nelore) e 40,0 no Pantanal extensivo.
    matrizes   = float(va[8])
    prestes_F  = float(va[6])
    bois       = float(va[7]+va[9])
    total_ini  = float(va.sum())

    # Custo médio PONDERADO por cabeças em cada fase — não simples média aritmética.
    # Exemplo: 150 cab em CRIA (R$40/@) + 50 cab em ENGORDA (R$120/@)
    # → ponderado = R$60/@ vs. média simples = R$80/@ (erro de 33%).
    _n_cria    = matrizes + c0_femeas + c1_femeas  # matrizes + fêmeas em crescimento
    _n_recria  = c0_machos + c1_machos             # machos em fase de recria
    _n_engorda = bois                              # garrotes e bois adultos

    _pesos_fase = [
        (_custo_cria,    custo_arroba_cria,    _n_cria),
        (_custo_recria,  custo_arroba_recria,  _n_recria),
        (_custo_engorda, custo_arroba_engorda, _n_engorda),
    ]
    _fases_w = [(c, n) for c, orig, n in _pesos_fase if orig is not None and n > 0]
    if _fases_w:
        _total_n_fases = sum(n for _, n in _fases_w)
        _custo_completo = sum(c * n for c, n in _fases_w) / _total_n_fases
    else:
        _custo_completo = custo_arroba

    anos_proj = []
    for yr in range(1, anos + 1):
        r = calcular_ano(
            prestes_matrizes=prestes_F,
            matrizes=matrizes,
            c0_femeas=c0_femeas, c1_femeas=c1_femeas,
            c0_machos=c0_machos, c1_machos=c1_machos,
            bois=bois,
            nat_pct=nat, desc_mat_pct=desc,
            prop_boi=prop_boi, renov_boi_pct=renov_boi_pct/100,
            venda_bez_pct=venda_bez_pct/100,
            mort_pct=mort,
            preco_arroba=preco_arroba * m['preco'],
            custo_arroba=_custo_completo,
            peso_boi=peso_boi,
            peso_vaca=peso_vaca,
            peso_bezerra=peso_arroba,
            peso_garrote=peso_garrote,
            preco_boi_arr=(preco_boi_arr * m['preco']) if preco_boi_arr is not None else None,
            preco_vaca_arr=(preco_vaca_arr * m['preco']) if preco_vaca_arr is not None else None,
            preco_bezerra_cab=(preco_bezerra_cab * m['preco']) if preco_bezerra_cab is not None else None,
            preco_bezerro_cab=(preco_bezerro_cab * m['preco']) if preco_bezerro_cab is not None else None,
        )
        anos_proj.append({
            'ano':      yr,
            'total':    r['total_prox'],
            'matrizes': r['matrizes_prox'],
            'bezerros': r['bezerros_produzidos'],
            'vendidos': r['total_vendido'],
            'bois_vendidos':        r['bois_vendidos'],
            'matrizes_descartadas': r['descarte_matrizes'],
            'bezerras_vendidas':    r['bezerras_vendidas'],
            'machos_vendidos':      r['machos_024_vendidos'],
            'aumento_matrizes':     r['aumento_matrizes'],
            'mortes':    r['mortes'],
            'receita':   r['receita'],
            'custo':     r['custo'],
            'resultado': r['resultado'],
            'bois_fim':      r['bois_prox'],
            'jovens_f_fim':  r['femeas_024_prox'],
            'jovens_m_fim':  r['machos_024_prox'],
            # Fêmeas de 25–36m ("prestes") que ainda não pariram — estado
            # contínuo agora (ver calcular_ano), não mais absorvido dentro de
            # `matrizes` no mesmo ano. Fica de fora de `matrizes` de propósito:
            # inflar a contagem exibida ao analista repetiria o defeito que
            # base_reprodutiva.py corrigiu na classificação, só que na tela.
            'prestes_matrizes_fim': round(r['prestes_matrizes_prox']),
        })
        matrizes  = float(r['matrizes_prox'])
        # A coorte "prestes" (25–36m) agora é estado corrente, não injeção de
        # uma vez: do ano 2 em diante ela vem de c1_femeas do ano anterior —
        # quem tinha 13–24m no início do ano e completou 25 dentro dele —, não
        # mais zerada. Zerar aqui era o que fazia QUALQUER fêmea jovem retida
        # virar matriz em um ano só, pulando as duas etapas intermediárias.
        prestes_F = float(r['prestes_matrizes_prox'])
        bois      = float(r['bois_prox'])
        c0_femeas = float(r['c0_femeas_prox'])
        c1_femeas = float(r['c1_femeas_prox'])
        c0_machos = float(r['c0_machos_prox'])
        c1_machos = float(r['c1_machos_prox'])

    result = _montar_resultado(cenario, sc, anos_proj, total_ini, 'CICLO_COMPLETO')
    ano1 = anos_proj[0]
    preco_adj = preco_arroba * m['preco']
    bv   = float(ano1.get('bois_vendidos', 0))
    dv   = float(ano1.get('matrizes_descartadas', 0))
    bezv = float(ano1.get('bezerras_vendidas', 0))
    garv = float(ano1.get('machos_vendidos', 0))
    peso_medio = (
        bv   * peso_boi    +
        dv   * peso_vaca   +
        bezv * peso_arroba +
        garv * peso_garrote
    ) / max(ano1['vendidos'], 1)
    units = float(max(ano1['vendidos'], 1)) * peso_medio
    result.update({
        'preco_breakeven':         round(ano1['custo'] / max(units, 1), 2),
        'preco_breakeven_unidade': 'R$/arroba',
        'preco_usado':             preco_adj,
        'slider_units':            round(units, 2),
        'slider_custo_ano1':       ano1['custo'],
        'margem_atual_pct':        round(ano1['resultado'] / max(ano1['custo'], 1) * 100, 1),
        'margem_atual_rs':         round(ano1['resultado'], 2),
    })
    return result

# ==================================================================
# 9. BENCHMARKS REGIONAIS (RONDÔNIA 2026)
# ==================================================================
BENCHMARKS_RO = {
    'natalidade': {
        'label': 'Taxa de Natalidade',
        'unidade': '%',
        # memorial §3: Abaixo<65, Médio 65–78, Bom 78–88, Excelente>=88
        'faixas': {'abaixo': 65.0, 'medio': 78.0, 'bom': 88.0},
        'inverso': False,
        'ciclos': ['CRIA', 'CICLO_COMPLETO', 'CRIA_RECRIA'],
    },
    'mortalidade': {
        'label': 'Mortalidade Geral',
        'unidade': '%',
        # memorial §3: Excelente<=1,5, Bom 1,5–3, Médio 3–5, Abaixo>5
        'faixas': {'abaixo': 5.0, 'medio': 3.0, 'bom': 1.5},
        'inverso': True,
        'ciclos': ['CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO',
                   'RECRIA_ENGORDA', 'CRIA_RECRIA'],
    },
    'desmama': {
        'label': 'Taxa de Desmama',
        'unidade': '%',
        # memorial §3: Abaixo<70, Médio 70–82, Bom 82–90, Excelente>=90
        'faixas': {'abaixo': 70.0, 'medio': 82.0, 'bom': 90.0},
        'inverso': False,
        'ciclos': ['CRIA', 'CICLO_COMPLETO', 'CRIA_RECRIA'],
    },
    'relacao_fm': {
        'label': 'Relação Fêmeas/Macho Adulto',
        'unidade': ':1',
        # memorial §3: Abaixo<1,8, Médio 1,8–2,2, Bom 2,2–2,8, Excelente>=2,8
        'faixas': {'abaixo': 1.8, 'medio': 2.2, 'bom': 2.8},
        'inverso': False,
        'ciclos': ['CRIA', 'CICLO_COMPLETO', 'CRIA_RECRIA'],
    },
    'pct_matrizes': {
        'label': '% Matrizes no Rebanho',
        'unidade': '%',
        # memorial §3: Abaixo<28, Médio 28–35, Bom 35–42, Excelente>=42
        'faixas': {'abaixo': 28.0, 'medio': 35.0, 'bom': 42.0},
        'inverso': False,
        'ciclos': ['CRIA', 'CICLO_COMPLETO', 'CRIA_RECRIA'],
    },
    'ganho_peso_arr': {
        'label': 'Ganho de Peso (@/mês)',
        'unidade': '@/mês',
        # memorial §3: Abaixo<0,5, Médio 0,5–0,7, Bom 0,7–0,9, Excelente>=0,9
        'faixas': {'abaixo': 0.5, 'medio': 0.7, 'bom': 0.9},
        'inverso': False,
        'ciclos': ['RECRIA'],
    },
    'rend_carcaca': {
        'label': 'Rendimento de Carcaça',
        'unidade': '%',
        # memorial §3: Abaixo<50, Médio 50–52, Bom 52–54, Excelente>=54
        'faixas': {'abaixo': 50.0, 'medio': 52.0, 'bom': 54.0},
        'inverso': False,
        'ciclos': ['ENGORDA', 'CICLO_COMPLETO'],
    },
    'desfrute': {
        'label': 'Desfrute do Rebanho',
        'unidade': '%',
        # Fontes: GEP Araguaia + Scot Consultoria (jul/2026).
        # Scot Consultoria: CRIA bom >35%, CICLO_COMPLETO bom >45%,
        # RECRIA/ENGORDA bom >55%/100%. Média nacional: 18,9%.
        # Desfrute = Total vendido no ano / Rebanho total × 100.
        'faixas_por_ciclo': {
            'CRIA':            {'abaixo': 18.0, 'medio': 25.0, 'bom': 35.0},
            'RECRIA':          {'abaixo': 35.0, 'medio': 45.0, 'bom': 55.0},
            'ENGORDA':         {'abaixo': 80.0, 'medio': 100.0, 'bom': 120.0},
            'CICLO_COMPLETO':  {'abaixo': 20.0, 'medio': 32.0, 'bom': 45.0},
            'RECRIA_ENGORDA':  {'abaixo': 60.0, 'medio': 72.0, 'bom': 85.0},
            'CRIA_RECRIA':     {'abaixo': 25.0, 'medio': 32.0, 'bom': 40.0},
        },
        'inverso': False,
        # Desfrute não é "quanto maior melhor". O material de treinamento é
        # explícito: "desfrute muito baixo pode indicar excesso de retenção e
        # baixo retorno financeiro; desfrute muito alto pode aumentar riscos
        # sanitários, de mercado e de custo" — IDEAL É EQUILÍBRIO.
        #
        # Sem isso, uma projeção que vendia 291% do rebanho era rotulada
        # "excelente" e passava sem alarme, inflando o DSCR.
        #
        # CRIA e CICLO_COMPLETO subiram em julho/2026 (30→35 e 40→45) para
        # acompanhar DESFRUTE_MODALIDADE em benchmarks_nacionais.py — ver lá o
        # porquê e o conflito de fontes. Os dois precisam andar juntos: são o
        # mesmo limiar lido por caminhos diferentes.
        # TERCEIRA cópia das mesmas faixas — havia esta, a de
        # DESFRUTE_MODALIDADE e a de DESFRUTE_PCT. Ao corrigir as faixas contra
        # os 19 painéis do Campo Futuro 2022, as três divergiram e os testes
        # apontaram. Agora todas derivam de DESFRUTE_MODALIDADE.
        'teto_por_ciclo': {
            **{mod: hi for mod, (_lo, hi) in _FAIXAS_DESFRUTE.items()},
            'CRIA_RECRIA': _FAIXAS_DESFRUTE['CRIA'][1],
        },
    },
}

def comparar_cenarios(v: list, ciclo: str, parametros: dict | None = None) -> dict:
    """Compara quatro cenários mantendo o mesmo estoque inicial e ciclo."""
    parametros_base = dict(parametros or {})
    parametros_base.pop('cenario', None)
    parametros_base.pop('ciclo', None)
    total_inicial = int(sum(float(x or 0) for x in (v or [])))
    mapa = (
        ('base_estimado', 'crescimento'),
        ('conservador', 'conservador'),
        ('provavel', 'provavel'),
        ('otimista', 'otimista'),
    )
    cenarios = []
    for identificador, subjacente in mapa:
        resultado = simular_cenario(
            list(v), subjacente, ciclo=ciclo, **parametros_base)
        anos = []
        for ano in resultado.get('anos', []):
            item = dict(ano)
            item['total_inicial'] = total_inicial
            anos.append(item)
        dscrs = [float(a['dscr']) for a in anos if a.get('dscr') is not None]
        ano_critico = None
        if anos:
            ano_critico = min(anos, key=lambda a: float(a.get('resultado', 0)))['ano']
        cenarios.append({
            'id': identificador,
            'cenario_subjacente': subjacente,
            'nome': resultado.get('nome'),
            'emoji': resultado.get('emoji'),
            'ciclo': ciclo,
            'premissas': dict(CENARIOS[subjacente]['mods']),
            'anos': anos,
            'acumulado': resultado.get('acumulado', {}),
            'ano_critico': ano_critico,
            'dscr_minimo': min(dscrs) if dscrs else None,
            'capacidade_pagamento': None,
        })
    return {
        'premissas_comuns': {
            'total_inicial': total_inicial,
            'ciclo': ciclo,
        },
        'cenarios': cenarios,
    }


def _classificar_faixa(valor: float, faixas: dict, inverso: bool = False) -> tuple:
    t_a, t_m, t_b = faixas['abaixo'], faixas['medio'], faixas['bom']
    if not inverso:
        if valor >= t_b:
            return 'excelente', None, 0.0
        elif valor >= t_m:
            return 'bom', 'excelente', round(t_b - valor, 2)
        elif valor >= t_a:
            return 'medio', 'bom', round(t_m - valor, 2)
        else:
            return 'abaixo', 'medio', round(t_a - valor, 2)
    else:
        if valor <= t_b:
            return 'excelente', None, 0.0
        elif valor <= t_m:
            return 'bom', 'excelente', round(valor - t_b, 2)
        elif valor <= t_a:
            return 'medio', 'bom', round(valor - t_m, 2)
        else:
            return 'abaixo', 'medio', round(valor - t_a, 2)

def avaliar_benchmarks(ciclo: str, indicadores: dict) -> list:
    resultado = []
    for key, cfg in BENCHMARKS_RO.items():
        ciclos_validos = cfg.get('ciclos') or list(cfg.get('faixas_por_ciclo', {}).keys())
        if ciclo not in ciclos_validos:
            continue
        valor = indicadores.get(key)
        if valor is None:
            continue
        faixas = cfg.get('faixas') or cfg.get('faixas_por_ciclo', {}).get(ciclo)
        if not faixas:
            continue
        faixa, proximo, falta = _classificar_faixa(
            float(valor), faixas, cfg.get('inverso', False)
        )
        item = {
            'key': key,
            'label': cfg['label'],
            'valor': round(float(valor), 2),
            'unidade': cfg['unidade'],
            'faixa': faixa,
            'proximo_nivel': proximo,
            'falta': falta,
        }
        # Indicadores com teto: acima da faixa não é excelência, é sinal de
        # atenção. Vale para o desfrute, onde giro excessivo eleva risco
        # sanitário, de mercado e de custo.
        _teto = (cfg.get('teto_por_ciclo') or {}).get(ciclo)
        if _teto is not None and float(valor) > _teto:
            item['faixa'] = 'acima'
            item['proximo_nivel'] = None
            item['falta'] = round(float(valor) - _teto, 2)
            item['alerta'] = (
                f'{cfg["label"]} de {float(valor):.1f}{cfg["unidade"]} supera o teto '
                f'de referência da modalidade ({_teto:.0f}{cfg["unidade"]}). '
                f'Giro acima do normal — confira se a projeção de vendas é '
                f'sustentável e se há compra de animais não declarada.'
            )
        resultado.append(item)
    return resultado

# Defaults regionais (Rondônia, médias) usados quando o usuário não informa
# o indicador manualmente. Não incluem 'desfrute' de propósito: a faixa
# típica varia demais entre modalidades (18% na CRIA a 120% na ENGORDA) e
# um valor sintético aqui distorceria a leitura — só entra se o usuário
# informar 'desfrute_pct' (memorial: mesma lógica do §14, evitar default
# que mascare a ausência de dado real).
_DEFAULTS_BENCHMARK = {
    'mortalidade':    3.0,   # médio — 5% colocava todo produtor sem dado na faixa "abaixo"
    'desmama':        72.0,
    'rend_carcaca':   52.0,
    'ganho_peso_arr': 0.55,
    'natalidade':     75.0,  # tecnificada (BeefPoint/EMBRAPA: 76% referência; nacional: 55%)
}


def _to_float_ou_default(valor, default: float) -> float:
    if valor is None:
        return default
    try:
        return float(valor)
    except (TypeError, ValueError):
        return default


def extrair_indicadores_benchmark(v: list, data: dict) -> dict:
    """
    Monta o dicionário de indicadores usado por avaliar_benchmarks(),
    combinando o que o usuário informou (campos opcionais no payload de
    /api/classificar) com defaults regionais e com indicadores derivados
    diretamente do rebanho (pct_matrizes, relacao_fm).

    Campos aceitos no payload (todos opcionais, aceitam string numérica):
      taxa_natalidade    -> natalidade (%)     [já usado em classificar()]
      mortalidade_pct    -> mortalidade (%)
      desmama_pct        -> desmama (%)
      rend_carcaca_pct   -> rend_carcaca (%)
      ganho_peso_kg_dia  -> ganho_peso_arr
      desfrute_pct       -> desfrute (%) — sem default, ver nota acima
    """
    ind = calcular_indicadores(v)

    taxa_natalidade = data.get('taxa_natalidade')
    if taxa_natalidade is not None:
        natalidade = _to_float_ou_default(taxa_natalidade, 0.75) * 100
    else:
        natalidade = _DEFAULTS_BENCHMARK['natalidade']

    resultado = {
        'natalidade':     round(natalidade, 2),
        'mortalidade':    _to_float_ou_default(data.get('mortalidade_pct'),  _DEFAULTS_BENCHMARK['mortalidade']),
        'desmama':        _to_float_ou_default(data.get('desmama_pct'),      _DEFAULTS_BENCHMARK['desmama']),
        'rend_carcaca':   _to_float_ou_default(data.get('rend_carcaca_pct'), _DEFAULTS_BENCHMARK['rend_carcaca']),
        'ganho_peso_arr': _to_float_ou_default(data.get('ganho_peso_kg_dia'), _DEFAULTS_BENCHMARK['ganho_peso_arr']),
        'pct_matrizes':   ind['pct_matrizes'],
        'relacao_fm':     ind['ratio_fm'],
    }
    if data.get('desfrute_pct') is not None:
        desfrute = _to_float_ou_default(data.get('desfrute_pct'), None)
        if desfrute is not None:
            resultado['desfrute'] = desfrute
    return resultado


def calcular_breakeven_simples(v: list, ciclo: str) -> dict:
    """
    Estimativa rápida do breakeven usando custo_arroba=R$57/@ padrão.

    CRIA:    custo_rebanho / (matrizes × 0,75 × 0,80 × 0,60)   → R$/cabeça
    RECRIA:  custo_total / (animais × 14@)                      → R$/arroba
    ENGORDA: custo_total / (bois × saída_carcaça@)              → R$/arroba
    CICLO:   custo_rebanho / (total × 0,30 × 16@)               → R$/arroba
    """
    va = np.array(v, dtype=float)
    custo_arroba = 57.0

    if ciclo == 'CRIA':
        matrizes  = float(va[6] + va[8])
        total     = float(va.sum()) or 1.0
        arrobas = arrobas_categorias(
            matrizes=float(va[6] + va[8]), bois=float(va[7] + va[9]),
            jovens_f=float(va[0] + va[2] + va[4]), jovens_m=float(va[1] + va[3] + va[5]))
        custo = arrobas * custo_arroba
        # nat=75%, desmama=80%, venda=60% (memorial §9)
        bezerros  = matrizes * 0.75 * 0.80 * 0.60
        if bezerros <= 0:
            return {}
        return {'preco_breakeven': round(custo / bezerros, 2), 'unidade': 'R$/cabeça'}

    if ciclo == 'RECRIA':
        # Usa pesos padrão de recria (entrada=8@, saída=14@, 12 meses)
        _peso_entrada_r, _peso_saida_r, _meses_r = 8.0, 14.0, 12
        _animais_r = float(va[2] + va[3] + va[4] + va[5])
        _peso_medio_r = (_peso_entrada_r + _peso_saida_r) / 2.0
        _custo_total_r = _animais_r * _peso_medio_r * custo_arroba * (_meses_r / 12.0)
        _arrobas_r = _animais_r * _peso_saida_r
        be = round(_custo_total_r / max(_arrobas_r, 1), 2)
        return {'preco_breakeven': be, 'unidade': 'R$/arroba'}

    if ciclo == 'ENGORDA':
        # Usa pesos padrão de engorda (entrada=350kg, saída=500kg, rend=54%, 120 dias)
        _peso_entrada_e = 350.0 / 15.0               # @ entrada
        _peso_saida_e   = (500.0 * 0.54) / 15.0      # @ carcaça saída
        _animais_e = float(va[7] + va[9])
        _peso_medio_e = (_peso_entrada_e + _peso_saida_e) / 2.0
        _custo_total_e = _animais_e * _peso_medio_e * custo_arroba * (120 / 365.0)
        _arrobas_e = _animais_e * _peso_saida_e
        be = round(_custo_total_e / max(_arrobas_e, 1), 2)
        return {'preco_breakeven': be, 'unidade': 'R$/arroba'}

    # CICLO_COMPLETO: 30% do rebanho × 16@ médias (memorial §9)
    total = float(va.sum()) or 1.0
    arrobas = arrobas_categorias(
        matrizes=float(va[6] + va[8]), bois=float(va[7] + va[9]),
        jovens_f=float(va[0] + va[2] + va[4]), jovens_m=float(va[1] + va[3] + va[5]))
    custo = arrobas * custo_arroba
    units = total * 0.30 * 16.0
    return {'preco_breakeven': round(custo / max(units, 1), 2), 'unidade': 'R$/arroba'}

