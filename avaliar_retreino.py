"""
Avaliação offline: modelo atual (gestao_model.pkl) x candidato retreinado com
casos reais confirmados.

Uso:
    python avaliar_retreino.py                  # só avalia e imprime o relatório
    python avaliar_retreino.py --saida r.json   # grava o relatório
    python avaliar_retreino.py --promover       # grava o pkl SE os critérios passarem

Regras que este módulo garante:
- Só entra o que `database.exportar_treino_detalhado()` devolve: caso confirmado
  por humano, não descartado, vetor válido. Nada pendente/descartado chega aqui.
- Classe com poucos exemplos reais (< MIN_POR_CLASSE) fica fora do treino e da
  avaliação: sem amostra, a métrica seria ruído e o exemplo isolado só
  deslocaria a fronteira da classe.
- Sem amostra real suficiente não há métrica nem promoção.
- `gestao_model.pkl` só é sobrescrito com `--promover` explícito E critérios
  aprovados, com backup `.bak` e escrita atômica.
- A promoção é LOCAL: o pkl é versionado no git, então grave aqui, rode a
  suíte e commite o artefato (mesmo fluxo de `treinar_ciclos.py`). Rodar no VPS
  sujaria `/opt/orkavyn` e quebraria o `git checkout --detach` do deploy.
- Casos reais não têm sobrepeso (sem `sample_weight`): com poucas dezenas de
  casos contra ~35 mil linhas sintéticas o candidato muda pouco. O critério é
  deliberadamente conservador e com N pequeno um caso vale vários pontos de
  acurácia — trate o relatório como evidência, não como veredito.
- Não é importado pelo app, não toca em `ml_engine._pipeline` e não é chamado
  no boot: o modelo do `preload_app` e o isolamento do SHAP não mudam.

A comparação é entre os *pipelines de ML puros* (sem as regras determinísticas
de `classificar`), no mesmo conjunto de casos reais. O modelo atual nunca viu
`casos_reais` (nenhum caminho de produção os usa no treino), então a avaliação
dele nesses casos é fora de amostra.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

import joblib
import numpy as np
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_recall_fscore_support)
from sklearn.model_selection import StratifiedKFold, train_test_split

import ml_engine
from ml_engine import TIPOS

MIN_TOTAL_REAIS = 30      # abaixo disso não há métrica confiável
MIN_POR_CLASSE = 5        # classe com menos exemplos reais é excluída
GANHO_MIN_F1 = 0.01       # ganho mínimo de F1 macro para valer a troca
TOL_ACURACIA = 0.01       # queda de acurácia tolerada
TOL_RECALL_CLASSE = 0.15  # queda de recall tolerada por classe
MODOS = ('cv', 'holdout')


# ──────────────────────────────────────────────────────────────────────────
# Seleção
# ──────────────────────────────────────────────────────────────────────────
def selecionar_reais(itens: list, min_por_classe: int = MIN_POR_CLASSE):
    """
    Deduplica por vetor e aplica o guarda de desequilíbrio. Devolve (aceitos, excluidas), com
    `excluidas` = {tipo: n} das classes que ficaram abaixo do mínimo.
    """
    # A mesma ficha confirmada duas vezes (outro usuário, reupload) cairia em
    # treino e teste ao mesmo tempo e inflaria o candidato: dedup por vetor.
    # Vetor com rótulos humanos divergentes é ambíguo e sai por inteiro.
    rotulos = {}
    for i in itens:
        rotulos.setdefault(tuple(float(x) for x in i['vetor']), set()).add(i['y'])
    vistos, unicos = set(), []
    for i in itens:
        chave = tuple(float(x) for x in i['vetor'])
        if chave in vistos or len(rotulos[chave]) > 1:
            continue
        vistos.add(chave)
        unicos.append(i)
    contagem = {}
    for i in unicos:
        contagem[i['tipo']] = contagem.get(i['tipo'], 0) + 1
    excluidas = {t: n for t, n in contagem.items() if n < min_por_classe}
    aceitos = [i for i in unicos if i['tipo'] not in excluidas]
    return aceitos, excluidas


def _corrigido(item) -> bool:
    return item.get('classe_ml') is not None and item['classe_ml'] != item['tipo']


# ──────────────────────────────────────────────────────────────────────────
# Métricas
# ──────────────────────────────────────────────────────────────────────────
def calcular_metricas(y_true, y_pred) -> dict:
    """Acurácia, F1 macro, matriz de confusão e métricas por ciclo."""
    n = len(y_true)
    if n == 0:
        return {'n': 0, 'acuracia': None, 'f1_macro': None,
                'matriz_confusao': None, 'por_ciclo': {}}
    labels = list(range(len(TIPOS)))
    presentes = sorted(set(int(v) for v in y_true))
    prec, rec, f1, sup = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0)
    por_ciclo = {
        TIPOS[k]: {'precisao': round(float(prec[k]), 4),
                   'recall': round(float(rec[k]), 4),
                   'f1': round(float(f1[k]), 4),
                   'suporte': int(sup[k])}
        for k in labels if sup[k] > 0
    }
    return {
        'n': int(n),
        'acuracia': round(float(accuracy_score(y_true, y_pred)), 4),
        # F1 macro só sobre as classes que existem na verdade-terreno.
        'f1_macro': round(float(f1_score(y_true, y_pred, labels=presentes,
                                         average='macro', zero_division=0)), 4),
        'matriz_confusao': confusion_matrix(y_true, y_pred,
                                            labels=labels).tolist(),
        'por_ciclo': por_ciclo,
    }


def taxa_acerto_corrigidos(y_true, y_pred, corrigido) -> dict:
    """Acerto nos casos em que o analista contrariou a previsão original."""
    idx = [k for k, c in enumerate(corrigido) if c]
    if not idx:
        return {'n': 0, 'acertos': 0, 'taxa': None}
    acertos = sum(1 for k in idx if y_true[k] == y_pred[k])
    return {'n': len(idx), 'acertos': acertos,
            'taxa': round(acertos / len(idx), 4)}


def resumo_atipicidade(vetores, corrigido) -> dict:
    """
    Quanto dos casos reais o motor já mandaria para revisão humana por
    atipicidade (`muito_atipico`), e quanto dos corrigidos por humanos foi
    sinalizado. O outro motivo de `revisao_humana` (dados_incompletos) vem da
    ficha, não do vetor, e não é avaliável aqui.
    """
    niveis = {'tipico': 0, 'atipico': 0, 'muito_atipico': 0, 'indisponivel': 0}
    corr_sinalizados = 0
    for v, c in zip(vetores, corrigido):
        try:
            a = ml_engine.calcular_atipicidade(v)
        except Exception:
            a = None
        nivel = (a or {}).get('nivel') or 'indisponivel'
        niveis[nivel] = niveis.get(nivel, 0) + 1
        if c and nivel == 'muito_atipico':
            corr_sinalizados += 1
    n = len(vetores)
    n_corr = sum(1 for c in corrigido if c)
    return {
        'por_nivel': niveis,
        'taxa_revisao_por_atipicidade': (
            round(niveis['muito_atipico'] / n, 4) if n else None),
        'corrigidos': n_corr,
        'corrigidos_sinalizados': corr_sinalizados,
    }


# ──────────────────────────────────────────────────────────────────────────
# Critério de promoção
# ──────────────────────────────────────────────────────────────────────────
def decidir_promocao(avaliacao: dict) -> tuple:
    """(recomendar: bool, motivos: list). Pura: só lê o dict de avaliação."""
    if avaliacao.get('status') != 'ok':
        return False, [avaliacao.get('status') or 'avaliacao_indisponivel']
    atual, cand = avaliacao['atual'], avaliacao['candidato']
    motivos = []
    if cand['f1_macro'] - atual['f1_macro'] < GANHO_MIN_F1:
        motivos.append('ganho_de_f1_insuficiente')
    if cand['acuracia'] < atual['acuracia'] - TOL_ACURACIA:
        motivos.append('acuracia_regrediu')
    ca, cc = avaliacao['corrigidos']['atual'], avaliacao['corrigidos']['candidato']
    if ca['n'] and cc['taxa'] < ca['taxa']:
        motivos.append('pior_nos_casos_corrigidos')
    for tipo, m in cand['por_ciclo'].items():
        ref = atual['por_ciclo'].get(tipo)
        if ref and m['recall'] < ref['recall'] - TOL_RECALL_CLASSE:
            motivos.append(f'recall_caiu_{tipo}')
    return not motivos, motivos


# ──────────────────────────────────────────────────────────────────────────
# Avaliação
# ──────────────────────────────────────────────────────────────────────────
def _splits(y, modo, n_splits, seed):
    y = np.asarray(y)
    if modo == 'holdout':
        idx = np.arange(len(y))
        tr, te = train_test_split(idx, test_size=0.3, stratify=y,
                                  random_state=seed)
        return [(tr, te)]
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return list(skf.split(np.zeros(len(y)), y))


def avaliar_candidato(itens, pipeline_atual, X_base, y_base, *,
                      build_model=None, modo='cv', n_splits=3, seed=42,
                      min_total=MIN_TOTAL_REAIS,
                      min_por_classe=MIN_POR_CLASSE) -> dict:
    """
    Compara `pipeline_atual` com um candidato treinado em base + casos reais.
    `X_base` são features já extraídas. O candidato é retreinado por split só
    com a parte de treino dos casos reais; os dois modelos são pontuados nos
    mesmos casos de teste. Nada é gravado em disco.
    """
    if modo not in MODOS:
        raise ValueError(f'modo inválido: {modo}')
    build_model = build_model or ml_engine._build_model
    aceitos, excluidas = selecionar_reais(itens, min_por_classe)
    contagem = {}
    for i in aceitos:
        contagem[i['tipo']] = contagem.get(i['tipo'], 0) + 1
    out = {
        'modo': modo,
        'n_confirmados': len(itens),
        'n_usados': len(aceitos),
        'por_classe': contagem,
        'classes_excluidas': excluidas,
        'n_corrigidos': sum(1 for i in aceitos if _corrigido(i)),
    }
    if len(aceitos) < min_total or len(contagem) < 2:
        out['status'] = 'amostra_insuficiente'
        out['recomendar_promocao'] = False
        out['motivos'] = ['amostra_insuficiente']
        return out
    out['status'] = 'ok'
    # k-fold nunca com mais folds que a menor classe (stratify exige isso).
    k = max(2, min(n_splits, min(contagem.values())))

    vetores = [i['vetor'] for i in aceitos]
    y = np.array([i['y'] for i in aceitos])
    corrigido = [_corrigido(i) for i in aceitos]
    F = np.array([ml_engine.extrair_features(v) for v in vetores], dtype=float)
    X_base = np.asarray(X_base, dtype=float)
    y_base = np.asarray(y_base)

    pred_atual = np.asarray(pipeline_atual.predict(F))
    pred_cand = np.full(len(y), -1, dtype=int)
    avaliados = []
    for tr, te in _splits(y, modo, k, seed):
        modelo = build_model()
        modelo.fit(np.vstack([X_base, F[tr]]), np.concatenate([y_base, y[tr]]))
        pred_cand[te] = modelo.predict(F[te])
        avaliados.extend(int(j) for j in te)
    ev = sorted(avaliados)
    yt = y[ev]
    pa, pc = pred_atual[ev], pred_cand[ev]
    corr_ev = [corrigido[j] for j in ev]

    out.update({
        'n_avaliados': len(ev),
        'n_splits': 1 if modo == 'holdout' else k,
        # Pipeline de ML puro, features com defaults de extrair_features (como
        # no treino do pkl) — não inclui as regras determinísticas de classificar().
        'features': 'defaults',
        'atual': calcular_metricas(yt, pa),
        'candidato': calcular_metricas(yt, pc),
        'corrigidos': {
            'atual': taxa_acerto_corrigidos(yt, pa, corr_ev),
            'candidato': taxa_acerto_corrigidos(yt, pc, corr_ev),
        },
        'atipicidade': resumo_atipicidade(
            [vetores[j] for j in ev], corr_ev),
    })
    out['recomendar_promocao'], out['motivos'] = decidir_promocao(out)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Promoção explícita
# ──────────────────────────────────────────────────────────────────────────
def promover(aceitos, X_base, y_base, avaliacao, destino, build_model=None):
    """
    Treina o candidato final (base + todos os casos reais aceitos) e grava em
    `destino` no mesmo formato de `ml_engine.salvar_modelo`. Recusa se a
    avaliação não recomendar a promoção. Backup `.bak` + escrita atômica.
    """
    if not avaliacao.get('recomendar_promocao'):
        raise RuntimeError('Promoção recusada: critérios não aprovados '
                           f"({avaliacao.get('motivos')}).")
    build_model = build_model or ml_engine._build_model
    F = np.array([ml_engine.extrair_features(i['vetor']) for i in aceitos],
                 dtype=float)
    y = np.array([i['y'] for i in aceitos])
    X = np.vstack([np.asarray(X_base, dtype=float), F])
    modelo = build_model()
    modelo.fit(X, np.concatenate([np.asarray(y_base), y]))
    # O app lê `stats['accuracy_mean']` e `['n_samples']` no import (preload):
    # as chaves de `treinar_modelo` têm de existir, senão o boot cai. Os valores
    # de acurácia/F1 aqui vêm da avaliação nos casos reais (std não se aplica).
    cand = avaliacao.get('candidato') or {}
    stats = {'accuracy_mean': cand.get('acuracia'), 'accuracy_std': 0.0,
             'f1_macro_mean': cand.get('f1_macro'), 'f1_macro_std': 0.0,
             'n_samples': int(len(X)), 'n_features': int(X.shape[1]),
             'n_csv': int(len(y_base)), 'n_confirmados': int(len(aceitos)),
             'avaliacao_real': {k: avaliacao[k] for k in
                                ('modo', 'n_avaliados', 'atual', 'candidato')
                                if k in avaliacao}}
    if os.path.exists(destino):
        shutil.copy2(destino, destino + '.bak')
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(destino)),
                               suffix='.tmp')
    os.close(fd)
    try:
        joblib.dump({'pipeline': modelo, 'stats': stats}, tmp, compress=3)
        # mkstemp cria 0600; o container roda com outro uid e precisa ler.
        os.chmod(tmp, 0o644)
        os.replace(tmp, destino)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return stats


def carregar_pipeline_atual(path=None):
    """Lê o pkl sem tocar no global `ml_engine._pipeline`."""
    path = path or ml_engine._MODEL_PATH
    return joblib.load(path)['pipeline']


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--modo', choices=MODOS, default='cv')
    ap.add_argument('--folds', type=int, default=3)
    ap.add_argument('--saida', default=None, help='grava o relatório JSON')
    ap.add_argument('--promover', action='store_true',
                    help='sobrescreve gestao_model.pkl se os critérios passarem')
    args = ap.parse_args(argv)

    import database as db
    itens = db.exportar_treino_detalhado()
    # `_build_model` encolhe o ensemble quando DATABASE_URL existe. O pkl em uso
    # foi treinado no tamanho local; já lidos os casos, volte a ele para que a
    # comparação (e o pkl promovido) não mude hiperparâmetros às escondidas.
    os.environ.pop('DATABASE_URL', None)
    X_csv, y_csv = ml_engine._carregar_dataset_csv()
    if not X_csv:
        print('Dataset CSV base não encontrado.', file=sys.stderr)
        return 2
    X_base = [ml_engine.extrair_features(v) for v in X_csv]
    pipeline = carregar_pipeline_atual()
    rel = avaliar_candidato(itens, pipeline, X_base, y_csv,
                            modo=args.modo, n_splits=args.folds)
    texto = json.dumps(rel, ensure_ascii=False, indent=2)
    print(texto)
    if args.saida:
        with open(args.saida, 'w', encoding='utf-8') as f:
            f.write(texto)
    if args.promover:
        aceitos, _ = selecionar_reais(itens)
        try:
            promover(aceitos, X_base, y_csv, rel, ml_engine._MODEL_PATH)
        except RuntimeError as e:
            print(f'✗ {e}', file=sys.stderr)
            return 1
        print('✓ gestao_model.pkl atualizado (backup em .bak).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
