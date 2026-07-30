"""
Treina o classificador de ciclo bovino usando as faixas de referência
do arquivo Excel (Referências_ciclos.xlsx).

Uso:
    python treinar_ciclos.py
    python treinar_ciclos.py --xlsx caminho/arquivo.xlsx --n 3000
"""
import argparse
import csv
import os
import shutil
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TIPOS = ['CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO']

# ── Faixas de referência extraídas do Excel ───────────────────────────────────
# Mapeamento: indicador do Excel → constraints na composição do rebanho
# Fonte: Referências_ciclos.xlsx (Principais Características + abas por ciclo)
#
# CRIA     → desfrute 18-30%, retenção novilhas 20-35%, descarte 8-15%,
#             taxa prenhez 70-85%, natalidade 65-80%, ciclo longo
# RECRIA   → desfrute 35-55%, retenção fêmeas 0-10%, giro 12-18 meses,
#             compra magros alta, sem matrizes
# ENGORDA  → desfrute 80-120%, retenção ~zero, confinamento 90-150 dias,
#             alta dependência grãos, bois dominam
# RECRIA/ENGORDA → desfrute 60-85%, compra muito alta, retenção muito baixa
#             (mapeado para ENGORDA com perfil intermediário)
# CICLO_COMPLETO → desfrute 20-40%, retenção novilhas 15-25%, descarte 8-12%,
#             receita bezerro + boi gordo, fluxo mais equilibrado

REF: dict[str, dict] = {
    'CRIA': {
        # proporção do rebanho total
        'pct_matrizes_adultas': (0.35, 0.55),   # matrizes dominam
        'pct_futuras_matrizes': (0.12, 0.28),   # novilhas retenção 20-35%
        'pct_bezerros':         (0.18, 0.32),   # alta produção (natalidade 65-80%)
        'pct_recria_M':         (0.04, 0.16),   # poucos machos em recria
        'pct_bois_adultos':     (0.01, 0.04),   # só touros de serviço (~1:30)
        # desfrute alvo (validação)
        'desfrute_range':       (0.18, 0.30),
    },
    'RECRIA': {
        'pct_matrizes_adultas': (0.00, 0.04),   # sem matrizes
        'pct_futuras_matrizes': (0.00, 0.08),   # fêmeas jovens 0-10% (ref Excel)
        'pct_bezerros':         (0.00, 0.07),   # sem produção própria
        'pct_recria_M':         (0.50, 0.72),   # machos em crescimento dominam
        'pct_bois_adultos':     (0.00, 0.04),   # sem bois para abate
        'desfrute_range':       (0.35, 0.55),
    },
    'ENGORDA': {
        # inclui perfil puro (confinamento) e perfil recria-engorda do Excel
        'pct_matrizes_adultas': (0.00, 0.02),   # praticamente zero (ref Excel)
        'pct_futuras_matrizes': (0.00, 0.03),   # quase nada
        'pct_bezerros':         (0.00, 0.05),   # sem cria
        'pct_recria_M':         (0.10, 0.35),   # garrotes em acabamento / compra
        'pct_bois_adultos':     (0.50, 0.80),   # bois para abate dominam
        'desfrute_range':       (0.60, 1.20),   # recria-engorda 60-85% / engorda 80-120%
    },
    'CICLO_COMPLETO': {
        'pct_matrizes_adultas': (0.18, 0.32),   # matrizes presentes
        'pct_futuras_matrizes': (0.10, 0.22),   # novilhas reposição 15-25%
        'pct_bezerros':         (0.10, 0.22),   # produção própria
        'pct_recria_M':         (0.09, 0.20),   # recria integrada
        'pct_bois_adultos':     (0.08, 0.22),   # terminação presente
        'desfrute_range':       (0.20, 0.40),
    },
}


def _parse_xlsx(xlsx_path: str) -> dict:
    """
    Lê o Excel e extrai as faixas de referência numéricas por ciclo.
    Retorna dict com validação das faixas do REF acima.
    """
    try:
        xl = pd.ExcelFile(xlsx_path)
    except Exception as e:
        print(f"  [aviso] Não foi possível ler o Excel: {e}")
        return {}

    resumo = {}
    # Aba principal
    df_main = pd.read_excel(xlsx_path, sheet_name='Principais Características', header=None)
    # Linhas 2-6 têm dados (ver estrutura do arquivo)
    ciclo_map = {
        2: 'CRIA',
        3: 'RECRIA',
        4: 'CICLO_COMPLETO',  # Recria/Engorda → mapeado para ENGORDA em TIPOS
        5: 'ENGORDA',
        6: 'CICLO_COMPLETO',
    }
    for row_idx, ciclo in ciclo_map.items():
        try:
            row = df_main.iloc[row_idx]
            resumo.setdefault(ciclo, {})['modalidade'] = str(row.iloc[0]).strip()
            resumo[ciclo]['desfrute_raw'] = str(row.iloc[2]).strip()
            resumo[ciclo]['retencao_raw'] = str(row.iloc[3]).strip()
        except Exception:
            continue

    # Abas específicas de cada ciclo
    _faixas_abas = {
        'Cria ':           'CRIA',
        'Recria':          'RECRIA',
        'Recria -Engorda': 'ENGORDA',
        'Engorda':         'ENGORDA',
        'Ciclo Completo':  'CICLO_COMPLETO',
    }
    for aba, ciclo in _faixas_abas.items():
        if aba not in xl.sheet_names:
            continue
        df = pd.read_excel(xlsx_path, sheet_name=aba, header=None)
        for _, row in df.iterrows():
            indicador = str(row.iloc[0]).strip().lower()
            referencia = str(row.iloc[1]).strip() if len(row) > 1 else ''
            if not referencia or referencia == 'nan':
                continue
            resumo.setdefault(ciclo, {})[indicador] = referencia

    return resumo


def _gerar_amostra(ciclo: str, rng: np.random.Generator) -> np.ndarray:
    """
    Gera um vetor de 10 contagens compatível com as referências do ciclo.

    Índices do vetor (igual ao _carregar_dataset_csv):
      0=f00F(bezerras 0-5m), 1=f00M(bezerros 0-5m),
      2=f05F(fêmeas 5-13m), 3=f05M(machos 5-13m),
      4=f13F(fêmeas 13-25m), 5=f13M(machos 13-25m),
      6=f25F(futuras matrizes 25-36m), 7=f25M(garrotes 25-36m),
      8=facF(matrizes adultas), 9=facM(bois adultos)
    """
    ref = REF[ciclo]

    # Amostra proporções dentro dos ranges calibrados pelo Excel
    p_mat_ad  = rng.uniform(*ref['pct_matrizes_adultas'])
    p_fut_mat = rng.uniform(*ref['pct_futuras_matrizes'])
    p_bez     = rng.uniform(*ref['pct_bezerros'])
    p_rec_M   = rng.uniform(*ref['pct_recria_M'])
    p_bois_ad = rng.uniform(*ref['pct_bois_adultos'])

    # Garante que as proporções somem ≤ 0.95 (5% de folga para ruído)
    soma = p_mat_ad + p_fut_mat + p_bez + p_rec_M + p_bois_ad
    if soma > 0.92:
        fator = 0.92 / soma
        p_mat_ad, p_fut_mat, p_bez, p_rec_M, p_bois_ad = (
            p_mat_ad * fator, p_fut_mat * fator, p_bez * fator,
            p_rec_M * fator, p_bois_ad * fator,
        )

    # Distribui bezerros M/F com pequena variação (~50/50)
    split_bez = rng.uniform(0.44, 0.56)
    f00F = p_bez * split_bez
    f00M = p_bez * (1 - split_bez)

    # Fêmeas jovens (5-25m): além das futuras matrizes, há fêmeas em crescimento
    p_fem_jov_extra = rng.uniform(0.0, 0.08)

    # Subdivisão da recria F entre 5-13m e 13-25m
    split_recF_05 = rng.uniform(0.35, 0.65)
    p_rec_F_total = p_fut_mat * rng.uniform(0.3, 0.7) + p_fem_jov_extra
    f05F = p_rec_F_total * split_recF_05
    f13F = p_rec_F_total * (1 - split_recF_05)

    # Subdivisão da recria M entre 5-13m e 13-25m
    split_recM_05 = rng.uniform(0.30, 0.60)
    f05M = p_rec_M * split_recM_05
    f13M = p_rec_M * (1 - split_recM_05)

    # Futuras matrizes (25-36m): parte das fêmeas jovens mais velhas
    f25F = p_fut_mat * rng.uniform(0.40, 0.70)

    # Garrotes (25-36m): parte dos bois adultos em acabamento
    garrote_frac = rng.uniform(0.15, 0.45)
    f25M = p_bois_ad * garrote_frac
    facM = max(p_bois_ad - f25M, 0.0)

    facF = max(p_mat_ad - f25F * 0.3, 0.0)

    # Monta vetor de proporções e converte para contagens
    props = np.array([f00F, f00M, f05F, f05M, f13F, f13M, f25F, f25M, facF, facM])
    props = np.maximum(props, 0.0)
    total_herd = rng.integers(150, 1500)
    counts = np.round(props * total_herd).astype(float)

    # Ruído gaussiano de ±4% do total para robustez
    ruido = rng.normal(0, 0.04 * float(counts.sum() or 1), size=10)
    counts = np.maximum(counts + ruido, 0.0)

    return counts


def gerar_dataset(n_por_classe: int = 2500, seed: int = 42) -> tuple[list, list]:
    """Gera dataset com n_por_classe amostras por ciclo."""
    rng = np.random.default_rng(seed)
    X, y = [], []
    for label, ciclo in enumerate(TIPOS):
        for _ in range(n_por_classe):
            X.append(_gerar_amostra(ciclo, rng).tolist())
            y.append(label)
    return X, y


def _carregar_csv_existente(path: str) -> tuple[list, list]:
    X, y = [], []
    if not os.path.exists(path):
        return X, y
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                v = [float(row[c]) for c in
                     ['f00F', 'f00M', 'f05F', 'f05M', 'f13F', 'f13M',
                      'f25F', 'f25M', 'facF', 'facM']]
                label = int(row['rotulo'])
                if label in (0, 1, 2, 3):
                    X.append(v)
                    y.append(label)
            except (KeyError, ValueError):
                continue
    return X, y


def _salvar_csv(path: str, X: list, y: list) -> None:
    cols = ['f00F', 'f00M', 'f05F', 'f05M', 'f13F', 'f13M',
            'f25F', 'f25M', 'facF', 'facM', 'rotulo']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for v, label in zip(X, y):
            writer.writerow([f'{x:.2f}' for x in v] + [label])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--xlsx', default=None, help='Caminho para o arquivo Excel de referências')
    parser.add_argument('--n', type=int, default=2500, help='Amostras por classe (padrão: 2500)')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    print("=" * 65)
    print("  TREINAMENTO — Classificador de Ciclo Bovino")
    print("  Referências: Principais Características (Excel)")
    print("=" * 65)

    # Lê o Excel se fornecido
    xlsx_info = {}
    xlsx_path = args.xlsx
    if xlsx_path and os.path.exists(xlsx_path):
        print(f"\n[0] Lendo referências do Excel: {os.path.basename(xlsx_path)}")
        xlsx_info = _parse_xlsx(xlsx_path)
        for ciclo, dados in xlsx_info.items():
            print(f"    {ciclo}: {len(dados)} indicadores carregados")

    # Importa ml_engine
    from ml_engine import treinar_modelo, _CSV_PATH

    # 1. Gera dataset calibrado pelo Excel
    print(f"\n[1/3] Gerando {args.n * len(TIPOS):,} amostras sintéticas ({args.n:,} por ciclo)...")
    X_novo, y_novo = gerar_dataset(n_por_classe=args.n, seed=args.seed)
    print(f"      Gerado: {len(X_novo):,} amostras")

    # 2. Combina com CSV existente
    X_orig, y_orig = _carregar_csv_existente(_CSV_PATH)
    if X_orig:
        print(f"      CSV original: {len(X_orig):,} amostras (mantidas)")
    X_todos = X_orig + X_novo
    y_todos = y_orig + y_novo

    # Backup + sobrescreve CSV principal
    if os.path.exists(_CSV_PATH):
        shutil.copy2(_CSV_PATH, _CSV_PATH + '.bak')
    _salvar_csv(_CSV_PATH, X_todos, y_todos)

    print(f"\n      Total para treino: {len(X_todos):,} amostras")
    print("      Distribuição:")
    for i, tipo in enumerate(TIPOS):
        n = sum(1 for yi in y_todos if yi == i)
        bar = '█' * (n // 200)
        print(f"        {tipo:<18} {n:>5}  {bar}")

    # 3. Treina
    print("\n[2/3] Treinando ensemble (RF + GB)...")
    stats = treinar_modelo()

    # Remove backup
    bak = _CSV_PATH + '.bak'
    if os.path.exists(bak):
        os.remove(bak)

    print("\n[3/3] Resultado:")
    print(f"      Acurácia CV:  {stats['accuracy_mean']:.1%} ± {stats['accuracy_std']:.1%}")
    print(f"      F1 Macro CV:  {stats['f1_macro_mean']:.1%} ± {stats['f1_macro_std']:.1%}")
    print(f"      Amostras:     {stats['n_samples']:,}")
    print(f"      Features:     {stats['n_features']}")
    print("\n✓ Modelo salvo em gestao_model.pkl")
    print("=" * 65)


if __name__ == '__main__':
    main()
