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
from sklearn.model_selection import cross_val_score
import joblib
import warnings
warnings.filterwarnings('ignore')
from services.pesos_rebanho import arrobas_categorias
from services.parametros_zootecnicos import (
    NATALIDADE_PCT, DESMAME_PCT,
    PESO_BOI_ARR, PESO_VACA_ARR, PESO_BEZERRA_ARR, PESO_GARROTE_ARR,
    MORTALIDADE_ADULTO_PCT, MORTALIDADE_BEZERRA_PCT,
)

# Razão bezerra/adulto para derivar mort_bezerra quando só mort_adulto é informada
_RAZAO_MORT_BEZERRA = MORTALIDADE_BEZERRA_PCT / MORTALIDADE_ADULTO_PCT  # 3.5

# ==================================================================
# CONSTANTES GLOBAIS
# ==================================================================
_MODEL_PATH = os.path.join(os.path.dirname(__file__), 'gestao_model.pkl')
_CSV_PATH = os.path.join(os.path.dirname(__file__), 'dataset_sintetico_bovino.csv')
TIPOS = ['CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO']

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
]

# Parâmetros padrão por ciclo de produção
# (branch 9318087 — útil para simular_cenario com defaults por ciclo)
PARAMS_POR_CICLO = {
    'CRIA': {
        'prop_boi': 30.0,       # 1 touro : 30 matrizes (memorial §16)
        'renov_boi_pct': 20.0,
        'desc_mat_pct': 30.0,   # 30% descarte (memorial §16)
        'venda_bez_pct': 60.0,  # 60% da produção (memorial §16)
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
        'desc_mat_pct': 30.0,
        'venda_bez_pct': 60.0,
        'nat_pct': NATALIDADE_PCT,
    }
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
                if label not in (0, 1, 2, 3):
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
    matrizes    = v[6] + v[8]
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

    _pipeline_cv = _build_model()
    cv_acc = cross_val_score(_pipeline_cv, X, y, cv=3, scoring='accuracy')
    cv_f1  = cross_val_score(_pipeline_cv, X, y, cv=3, scoring='f1_macro')

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
    try:
        joblib.dump({'pipeline': _pipeline, 'stats': stats_dict}, _MODEL_PATH)
    except Exception as e:
        print(f'[ML] Aviso: não foi possível salvar o modelo: {e}')

def carregar_modelo() -> dict | None:
    if not os.path.exists(_MODEL_PATH):
        return None
    try:
        data = joblib.load(_MODEL_PATH)
        pipeline = data['pipeline']
        # Validação de estrutura (branch 9318087) — rejeita modelos antigos incompatíveis
        if not hasattr(pipeline.named_steps['model'], 'estimators'):
            print("[ML] Modelo antigo incompatível. Retreinando...")
            return None
        global _pipeline
        _pipeline = pipeline
        return data['stats']
    except Exception as e:
        print(f'[ML] Modelo em disco incompatível, retreinando: {e}')
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
        int(p_matrizes_h > 0.18) +
        int(p_mac_13_24_h > 0.10) +
        int(p_bois_h > 0.12) +   # exige ≥12% de garrote/boi gordo para contar como engorda
        int(p_bez_h > 0.12)
    )

    feat = extrair_features(v, taxa_natalidade, _bois_v, _bez_v).reshape(1, -1)
    probs = _pipeline.predict_proba(feat)[0]
    prob_dict = {TIPOS[i]: round(float(p) * 100, 1) for i, p in enumerate(probs)}

    explicacao = []

    if indice_ciclo >= 4 and intensidade_engorda > 0.05:
        # Exige também intensidade_engorda > 5% confirmada pelo usuário;
        # touros de serviço (sem bois_vendidos informado) não ativam esta regra.
        tipo = 'CICLO_COMPLETO'
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
            tipo = 'CRIA' if probs[0] >= probs[1] else 'RECRIA'
            explicacao.append(
                f"Regra híbrida: intensidade_engorda={intensidade_engorda:.3f} < 0.1 → {ml_tipo} descartado"
            )
            explicacao.append(f"ML sugeria {ml_tipo}; substituído por {tipo}")
        else:
            tipo = ml_tipo
            explicacao.append(
                f"Regra híbrida: intensidade_engorda={intensidade_engorda:.3f} < 0.1 → priorizando cria/recria"
            )
            explicacao.append(f"ML confirmou: {tipo}")
        confianca = round(float(probs[TIPOS.index(tipo)]) * 100, 1)
    else:
        ml_idx = int(probs.argmax())
        ml_tipo = TIPOS[ml_idx]
        confianca = round(float(probs[ml_idx]) * 100, 1)

        # Guarda de segurança: ML votou CICLO_COMPLETO com indice_ciclo fraco.
        # indice_ciclo ≤ 1 significa que a composição do rebanho não tem as
        # 4 características simultâneas; provável fazenda de CRIA bem estruturada
        # com touros de serviço sendo confundida com ciclo completo.
        if ml_tipo == 'CICLO_COMPLETO' and indice_ciclo <= 1:
            alt_idx = int(np.argsort(probs)[-2])  # segunda opção do ML
            tipo = TIPOS[alt_idx] if TIPOS[alt_idx] != 'CICLO_COMPLETO' else (
                'CRIA' if p_matrizes_h > 0.18 else 'RECRIA'
            )
            confianca = round(float(probs[TIPOS.index(tipo)]) * 100, 1)
            explicacao.append(
                f"Guarda CICLO_COMPLETO: indice_ciclo={indice_ciclo}/4 insuficiente "
                f"→ revertido para {tipo}"
            )
        else:
            tipo = ml_tipo
            explicacao.append("Classificação via modelo ML (ensemble RF+GB)")
        explicacao.append(f"Confiança: {confianca}%")

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

    return {
        'classificacao': tipo,
        'tipo': tipo,
        'confianca': confianca,
        'probabilidades': prob_dict,
        'explicacao': explicacao,
        'tipo_secundario':       (misto or {}).get('tipo_secundario'),
        'combinacao':            (misto or {}).get('combinacao', tipo),
        'confianca_secundaria':  (misto or {}).get('confianca_secundaria', 0.0),
    }


# ==================================================================
# 5b. SHAP — Explicabilidade (CMN 4.966/2021 / Marco Legal IA)
# ==================================================================
def explicar_shap(
    v: list,
    tipo_classificado: str,
    top_n: int = 8,
) -> dict:
    """
    Retorna os principais fatores que explicam a classificação via SHAP.

    Conformidade: CMN 4.966/2021 (modelos internos de risco) e
    PL 2.338/2023 — Marco Legal da IA (sistemas de alto risco).

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
    for _, est in voting.estimators_:
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
    total_abs = float(np.abs(media).sum()) or 1.0

    fatores = sorted(
        [
            {
                'feature':    FEATURE_NAMES[i],
                'shap':       round(float(media[i]), 4),
                'importancia_pct': round(abs(float(media[i])) / total_abs * 100, 1),
                'direcao':    'positivo' if media[i] > 0 else 'negativo',
            }
            for i in range(len(media))
            if abs(media[i]) > 1e-6
        ],
        key=lambda x: abs(x['shap']),
        reverse=True,
    )[:top_n]

    return {
        'classe':        tipo_classificado,
        'fatores':       fatores,
        'n_estimadores': len(contribs),
        'metodo':        'SHAP TreeExplainer — média do ensemble',
        'conformidade':  'CMN 4.966/2021 · Marco Legal IA (Lei 2.338/2023)',
    }


# ==================================================================
# 5c. CICLOS MISTOS (pós-processamento)
# ==================================================================
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
    v = np.array(v, dtype=float)
    total      = v.sum() or 1
    femeas_024 = v[0]+v[2]+v[4]
    machos_024 = v[1]+v[3]+v[5]
    matrizes   = v[6]+v[8]
    bois       = v[7]+v[9]
    tot_fem    = femeas_024 + matrizes
    tot_mac    = machos_024 + bois
    cria       = v[0]+v[1]+v[2]+v[3]
    recria     = v[4]+v[5]

    return {
        'total':           int(total),
        'total_femeas':    int(tot_fem),
        'total_machos':    int(tot_mac),
        'femeas_024':      int(femeas_024),
        'machos_024':      int(machos_024),
        'matrizes':        int(matrizes),
        'bois':            int(bois),
        'fem_adultas':     int(matrizes),
        'mac_adultos':     int(bois),
        'cria':            int(cria),
        'recria':          int(recria),
        'adultos':         int(matrizes+bois),
        'pct_cria':        round(cria/total*100, 1),
        'pct_recria':      round(recria/total*100, 1),
        'pct_adultos':     round((matrizes+bois)/total*100, 1),
        'pct_matrizes':    round(matrizes/total*100, 1),
        'pct_mac_adultos': round(bois/total*100, 1),
        'ratio_fm':        round(tot_fem/max(tot_mac, 1), 2),
        'bezerros_est':    int(matrizes * NATALIDADE_PCT / 100),
    }

# ==================================================================
# 7. SIMULAÇÕES FINANCEIRAS (PARÂMETROS ATUALIZADOS)
# ==================================================================
def calcular_ano(
    matrizes, femeas_024, machos_024, bois,
    nat_pct, desc_mat_pct, prop_boi, renov_boi_pct,
    venda_bez_pct, mort_pct, preco_arroba, custo_arroba,
    peso_boi: float = PESO_BOI_ARR, peso_vaca: float = PESO_VACA_ARR,
    peso_bezerra: float = PESO_BEZERRA_ARR, peso_garrote: float = PESO_GARROTE_ARR,
    preco_boi_arr: float = None, preco_vaca_arr: float = None,
    preco_bezerra_cab: float = None, preco_bezerro_cab: float = None,
    mort_adulto_pct: float = None,   # fração; default = mort_pct
    mort_bezerra_pct: float = None,  # fração; default = mort_pct × 3.5 (EMBRAPA)
) -> dict:
    """
    Pesos diferenciados na faixa jovem (0-25 meses):
    'femeas_024'/'machos_024' agrupam 3 sub-faixas etárias. Bezerras
    vendidas (bez_vend) tendem a ser do desmame, mais leves (peso_bezerra=6.0@).
    Machos jovens excedentes (machos_024_vend) são predominantemente
    garrotes próximos dos 25 meses — mais pesados (peso_garrote=10.67@).
    Todos os pesos seguem GEP Araguaia safra 24/25 via parametros_zootecnicos.
    """

    bezerros = matrizes * nat_pct
    bois_nec   = max(round(matrizes / max(prop_boi, 1)), 1)
    bois_exc   = max(bois - bois_nec, 0)
    renovacao       = round(bois_nec * renov_boi_pct)
    machos_024_vend = max(machos_024 - renovacao, 0)
    bois_vendidos   = bois_exc + renovacao
    desc_mat = round(matrizes * desc_mat_pct)
    bez_vend  = round(femeas_024 * venda_bez_pct)
    fem_repor = femeas_024 - bez_vend
    aumento  = fem_repor - desc_mat
    vendidos = bois_vendidos + desc_mat + bez_vend + machos_024_vend
    # Mortalidade diferenciada por categoria (EMBRAPA: bezerros 5–10%, adultos 1.5–2.5%)
    _mort_adulto  = mort_adulto_pct  if mort_adulto_pct  is not None else mort_pct
    _mort_bezerra = mort_bezerra_pct if mort_bezerra_pct is not None else min(mort_pct * _RAZAO_MORT_BEZERRA, 0.25)

    def _mortes(n, taxa):
        """Arredonda mortalidade mas garante mínimo 1 quando n > 0 e taxa > 0."""
        if n <= 0 or taxa <= 0:
            return 0
        return max(1, round(n * taxa))

    mortes_mat      = _mortes(matrizes, _mort_adulto)
    mortes_bois_tot = _mortes(bois, _mort_adulto)
    mortes_jovens   = _mortes(femeas_024 + machos_024, _mort_adulto)
    mortes_bezerros = _mortes(bezerros, _mort_bezerra)
    mortes          = mortes_mat + mortes_bois_tot + mortes_jovens + mortes_bezerros

    mat_prox       = max(matrizes + aumento - mortes_mat, 0)
    bois_prox      = max(bois_nec, 1)
    femeas_024_prx = round(bezerros * 0.5 * (1 - _mort_bezerra))
    machos_024_prx = round(bezerros * 0.5 * (1 - _mort_bezerra))
    total_prox     = mat_prox + femeas_024_prx + machos_024_prx + bois_prox
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
        'bois_excedentes':     int(bois_exc),
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
    desmama  = (desmama_pct / 100)
    venda_bz = (venda_bez_pct / 100)
    preco_bz = (preco_arroba_bezerro * m['preco']) * peso_bezerra   # R$/cabeça derivado de R$/@
    # Preço da vaca descartada: usa preco_vaca_arr se informado, senão usa o mesmo preco/@ do bezerro
    _preco_vaca_cab = ((preco_vaca_arr if preco_vaca_arr is not None else preco_arroba_bezerro)
                       * m['preco']) * peso_matriz

    matrizes    = float(va[6] + va[8])
    fem_recria  = float(va[0] + va[2] + va[4])
    total_ini   = float(va.sum())

    anos_proj = []
    for yr in range(1, anos + 1):
        nascidos      = matrizes * nat
        desmamados    = nascidos * desmama * (1 - mort_bez)  # mortalidade pré-desmame de bezerros
        vez_vendidos  = desmamados * venda_bz
        machos_vend   = vez_vendidos * 0.5
        femeas_vend   = vez_vendidos * 0.5
        bezerras_ret  = (desmamados - vez_vendidos) * 0.5

        descarte_mat  = round(matrizes * (desc_mat_pct / 100))
        matrizes_prox = max(matrizes + bezerras_ret - descarte_mat, matrizes * 0.7)
        total_prox    = int(matrizes_prox + bezerras_ret)
        mortes        = round((matrizes + fem_recria) * mort)  # adultos: taxa adulta

        # Receita: bezerros vendidos + descarte de matrizes (ambos geram caixa na cria)
        receita   = vez_vendidos * preco_bz + descarte_mat * _preco_vaca_cab
        # Custo inclui touros de serviço (1:30 matrizes, pesam como bois)
        _touros_cria = max(round(matrizes / 30.0), 1) if matrizes > 0 else 0
        custo     = (matrizes * peso_matriz + fem_recria * peso_bezerra + _touros_cria * PESO_BOI_ARR) * custo_arroba
        resultado = receita - custo

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
            'aumento_matrizes': int(bezerras_ret - descarte_mat),
            'receita': round(receita, 2),
            'custo': round(custo, 2),
            'resultado': round(resultado, 2),
            # Composição do rebanho no fim do ano — usada pelo fluxo GEP
            'bois_fim': 0,
            'jovens_f_fim': int(bezerras_ret),
            'jovens_m_fim': 0,
        })
        matrizes   = matrizes_prox
        fem_recria = bezerras_ret

    result = _montar_resultado(cenario, sc, anos_proj, total_ini, 'CRIA')
    ano1 = anos_proj[0]
    units = float(max(ano1['vendidos'], 1)) * peso_bezerra
    result.update({
        'preco_breakeven':         round(ano1['custo'] / max(units, 1), 2),
        'preco_breakeven_unidade': 'R$/arroba',
        'preco_usado':             preco_bz,
        'slider_units':            units,
        'slider_custo_ano1':       ano1['custo'],
        'margem_atual_pct':        round(ano1['resultado'] / max(ano1['custo'], 1) * 100, 1),
        'margem_atual_rs':         round(ano1['resultado'], 2),
    })
    return result

def _simular_recria(
    v, cenario, mort_pct, preco_arroba, peso_entrada_arr, peso_saida_arr,
    meses_recria, custo_arroba, anos,
):
    """
    Receita calculada sobre o PESO TOTAL NA SAÍDA (memorial §6 e §12):
    O comprador paga pelo peso vivo do animal ao sair, não apenas pelo ganho.
    ganho_arr é mantido apenas como informação auxiliar no retorno.

    Receita   = animais_sai × peso_saida_arr × preco
    Breakeven = custo_ano1  / (animais_sai × peso_saida_arr)   [R$/arroba]
    """
    va  = np.array(v, dtype=float)
    sc  = CENARIOS.get(cenario, CENARIOS['crescimento'])
    m   = sc['mods']

    mort  = (mort_pct / 100) * m['mort']
    preco = preco_arroba * m['preco']
    ganho_arr = max(peso_saida_arr - peso_entrada_arr, 0.0)

    # Animais em recria = machos e fêmeas 5–25 meses
    animais   = float(va[2] + va[3] + va[4] + va[5])
    total_ini = float(va.sum())

    anos_proj = []
    for yr in range(1, anos + 1):
        mortes       = animais * mort
        animais_sai  = animais - mortes

        # Receita = peso total na saída (memorial §6)
        receita   = animais_sai * peso_saida_arr * preco
        peso_medio = (peso_entrada_arr + peso_saida_arr) / 2.0
        custo      = animais * peso_medio * custo_arroba * (meses_recria / 12.0)
        resultado = receita - custo

        animais_prox = animais * (1 + min(0.05, 0.04 * m['nat']))

        anos_proj.append({
            'ano': yr,
            'total': int(animais_prox),
            'matrizes': 0,
            'bezerros': 0,
            'vendidos': int(animais_sai),
            'bois_vendidos': int(animais_sai),
            'matrizes_descartadas': 0,
            'bezerras_vendidas': 0,
            'machos_vendidos': int(animais_sai),
            'aumento_matrizes': 0,
            'ganho_arrobas_por_animal': round(ganho_arr, 2),
            'receita': round(receita, 2),
            'custo': round(custo, 2),
            'resultado': round(resultado, 2),
            'bois_fim': 0,
            'jovens_f_fim': 0,
            'jovens_m_fim': int(animais_prox),
        })
        animais = animais_prox

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
    total_ini = float(va.sum())
    lotes_ano = max(1, int(365 / max(dias_engorda, 30)))

    anos_proj = []
    for yr in range(1, anos + 1):
        bois_no_ano   = bois * lotes_ano
        mortes        = bois_no_ano * mort
        bois_abatidos = bois_no_ano - mortes

        # Receita = arrobas totais de carcaça na saída (memorial §7)
        receita   = bois_abatidos * arrobas_saida * preco
        arrobas_media = (arrobas_saida + (peso_entrada_kg * rend) / 15.0) / 2.0
        custo         = bois_no_ano * arrobas_media * custo_arroba * (dias_engorda / 365.0)
        resultado = receita - custo

        bois_prox = bois * (1 + min(0.05, 0.04 * m['nat']))

        anos_proj.append({
            'ano': yr,
            'total': int(bois_prox),
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
            'lotes_por_ano': lotes_ano,
            'ganho_peso_kg': round(peso_saida_kg - peso_entrada_kg, 1),
            'receita': round(receita, 2),
            'custo': round(custo, 2),
            'resultado': round(resultado, 2),
            'bois_fim': int(bois_prox),
            'jovens_f_fim': 0,
            'jovens_m_fim': 0,
        })
        bois = bois_prox

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
    desmama_pct:        float = DESMAME_PCT,  # benchmark desmame (82%)
    peso_entrada_arr:   float = 10.0,   # memorial §16: 10@
    peso_saida_arr:     float = 18.0,   # memorial §16: 18@
    meses_recria:       int   = 12,
    peso_entrada_kg:    float = 300.0,  # memorial §16: 300kg
    peso_saida_kg:      float = 520.0,  # memorial §16: 520kg
    rendimento_carcaca: float = 52.0,
    dias_engorda:       int   = 90,
    peso_boi:           float = PESO_BOI_ARR,   # GEP Araguaia (20.53@)
    peso_vaca:          float = PESO_VACA_ARR,  # GEP Araguaia (15.33@)
    preco_boi_arr:      float = None,   # R$/@ boi do dia (senão usa preco_arroba)
    preco_vaca_arr:     float = None,   # R$/@ vaca do dia
    preco_bezerra_cab:  float = None,   # R$/cabeça bezerra do dia
    preco_bezerro_cab:  float = None,   # R$/cabeça bezerro do dia
) -> dict:
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

    if ciclo == 'CRIA':
        return _simular_cria(
            v, cenario, nat_pct, mort_pct, desmama_pct, venda_bez_pct,
            preco_arroba_bezerro, _custo_cria, anos,
            peso_matriz=peso_vaca, peso_bezerra=peso_arroba,
            preco_vaca_arr=preco_vaca_arr,
            desc_mat_pct=desc_pct,
        )
    if ciclo == 'RECRIA':
        return _simular_recria(
            v, cenario, mort_pct, preco_arroba, peso_entrada_arr, peso_saida_arr,
            meses_recria, _custo_recria, anos,
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

    femeas_024 = float(va[0]+va[2]+va[4])
    machos_024 = float(va[1]+va[3]+va[5])
    matrizes   = float(va[6]+va[8])
    bois       = float(va[7]+va[9])
    total_ini  = float(va.sum())

    # Custo médio PONDERADO por cabeças em cada fase — não simples média aritmética.
    # Exemplo: 150 cab em CRIA (R$40/@) + 50 cab em ENGORDA (R$120/@)
    # → ponderado = R$60/@ vs. média simples = R$80/@ (erro de 33%).
    _n_cria    = matrizes + femeas_024  # matrizes + fêmeas em crescimento
    _n_recria  = machos_024             # machos em fase de recria
    _n_engorda = bois                   # garrotes e bois adultos

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
            matrizes=matrizes, femeas_024=femeas_024,
            machos_024=machos_024, bois=bois,
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
            'receita':   r['receita'],
            'custo':     r['custo'],
            'resultado': r['resultado'],
            'bois_fim':      r['bois_prox'],
            'jovens_f_fim':  r['femeas_024_prox'],
            'jovens_m_fim':  r['machos_024_prox'],
        })
        matrizes   = float(r['matrizes_prox'])
        bois       = float(r['bois_prox'])
        femeas_024 = float(r['femeas_024_prox'])
        machos_024 = float(r['machos_024_prox'])

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
        'ciclos': ['CRIA', 'CICLO_COMPLETO'],
    },
    'mortalidade': {
        'label': 'Mortalidade Geral',
        'unidade': '%',
        # memorial §3: Excelente<=1,5, Bom 1,5–3, Médio 3–5, Abaixo>5
        'faixas': {'abaixo': 5.0, 'medio': 3.0, 'bom': 1.5},
        'inverso': True,
        'ciclos': ['CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO'],
    },
    'desmama': {
        'label': 'Taxa de Desmama',
        'unidade': '%',
        # memorial §3: Abaixo<70, Médio 70–82, Bom 82–90, Excelente>=90
        'faixas': {'abaixo': 70.0, 'medio': 82.0, 'bom': 90.0},
        'inverso': False,
        'ciclos': ['CRIA', 'CICLO_COMPLETO'],
    },
    'relacao_fm': {
        'label': 'Relação Fêmeas/Macho Adulto',
        'unidade': ':1',
        # memorial §3: Abaixo<1,8, Médio 1,8–2,2, Bom 2,2–2,8, Excelente>=2,8
        'faixas': {'abaixo': 1.8, 'medio': 2.2, 'bom': 2.8},
        'inverso': False,
        'ciclos': ['CRIA', 'CICLO_COMPLETO'],
    },
    'pct_matrizes': {
        'label': '% Matrizes no Rebanho',
        'unidade': '%',
        # memorial §3: Abaixo<28, Médio 28–35, Bom 35–42, Excelente>=42
        'faixas': {'abaixo': 28.0, 'medio': 35.0, 'bom': 42.0},
        'inverso': False,
        'ciclos': ['CRIA', 'CICLO_COMPLETO'],
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
        },
        'inverso': False,
    },
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
        resultado.append({
            'key': key,
            'label': cfg['label'],
            'valor': round(float(valor), 2),
            'unidade': cfg['unidade'],
            'faixa': faixa,
            'proximo_nivel': proximo,
            'falta': falta,
        })
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
    Estimativa rápida do breakeven — parâmetros fixos do memorial §9.

    CRIA:    (total × R$850) / (matrizes × 0,75 × 0,80 × 0,60)   → R$/cabeça
    RECRIA:  (12 × R$80)     / 14@                                → R$68,57/@
    ENGORDA: (90 × R$12)     / (520×0,52/15)                      → R$59,90/@
    CICLO:   (total × R$850) / (total × 0,30 × 16@)               → R$/arroba
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