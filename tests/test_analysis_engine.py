from __future__ import annotations

from importlib import import_module

import pytest

from services.qualidade_dados import analisar_qualidade_dados
from services.rating_credito import calcular_rating


def _load(module_name: str):
    try:
        return import_module(module_name)
    except ImportError as exc:  # pragma: no cover - exercised by failing red test
        pytest.fail(str(exc))


def test_quality_wrapper_preserves_legacy_fields_and_adds_status_layers():
    resultado = analisar_qualidade_dados(
        [10, 20, 30],
        {
            'preco_arroba': 320.0,
            'custo_arroba': 118.0,
            'peso_medio_kg': 420.0,
            'taxa_natalidade_pct': 72.0,
            'taxa_mortalidade_pct': 3.0,
            'observacao_interna': 'keep-me',
        },
    )

    assert resultado['campos']['peso_medio_kg']['origem'] == 'usuario'
    assert resultado['campos']['composicao_rebanho']['valor'] == 60
    assert resultado['status'] == 'COMPLETO'
    assert resultado['confidence_score'] > 0
    assert resultado['assumed_fields']
    assert resultado['extra_fields'] == {
        'observacao_interna': [{'source': 'input_data', 'value': 'keep-me'}]
    }


def test_quality_wrapper_normalizes_legacy_aliases_before_analysis():
    resultado = analisar_qualidade_dados(
        [10, 20, 30],
        {
            'preco_arroba': 320.0,
            'custo_arroba': 118.0,
            'peso_medio_kg': 420.0,
            'natalidade_pct': 72.0,
            'mortalidade_pct': 3.0,
        },
    )

    assert resultado['campos']['natalidade_pct']['origem'] == 'usuario'
    assert resultado['campos']['mortalidade_pct']['origem'] == 'usuario'
    assert resultado['status'] == 'COMPLETO'
    assert 'taxa_natalidade_pct' not in resultado['missing_fields']
    assert 'taxa_mortalidade_pct' not in resultado['missing_fields']


def test_analysis_engine_preserves_all_duplicate_unknown_fields_with_sources():
    data_quality = _load('services.analysis_engine.data_quality')

    resultado = data_quality.assess_data_quality(
        {
            'preco_arroba': 320.0,
            'custo_arroba': 118.0,
            'peso_medio_kg': 420.0,
            'taxa_natalidade_pct': 72.0,
            'taxa_mortalidade_pct': 3.0,
            'observacao_interna': 'input-data',
        },
        {
            'values': [10, 20, 30],
            'observacao_interna': 'herd-data',
        },
        {
            'receita_prevista': 180_000.0,
            'observacao_interna': 'production-data',
        },
    )

    assert resultado['extra_fields']['observacao_interna'] == [
        {'source': 'input_data', 'value': 'input-data'},
        {'source': 'herd', 'value': 'herd-data'},
        {'source': 'production', 'value': 'production-data'},
    ]
    assert resultado['provenance']['input_data']['extra_fields']['observacao_interna'] == [
        {'source': 'input_data', 'value': 'input-data'},
        {'source': 'herd', 'value': 'herd-data'},
        {'source': 'production', 'value': 'production-data'},
    ]


def test_quality_levels_cover_complete_partial_and_insufficient():
    data_quality = _load('services.analysis_engine.data_quality')
    assess_data_quality = data_quality.assess_data_quality

    complete = assess_data_quality(
        {
            'preco_arroba': 320.0,
            'custo_arroba': 118.0,
            'peso_medio_kg': 420.0,
            'taxa_natalidade_pct': 72.0,
            'taxa_mortalidade_pct': 3.0,
        },
        {'values': [10, 20, 30]},
        {'receita_prevista': 180_000.0, 'fluxo_caixa_previsto': 25_000.0},
    )
    partial = assess_data_quality(
        {
            'preco_arroba': 320.0,
            'peso_medio_kg': 420.0,
            'taxa_natalidade_pct': 72.0,
        },
        {'values': [10, 20, 30]},
        None,
    )
    insufficient = assess_data_quality(
        {'values': [10, 20, 30]},
        None,
    )

    assert complete['status'] == 'COMPLETO'
    assert partial['status'] == 'PARCIAL'
    assert insufficient['status'] == 'INSUFICIENTE'
    assert complete['confidence_score'] > partial['confidence_score'] > insufficient['confidence_score']
    assert 'custo_arroba' in partial['missing_fields']
    assert {'custo_arroba', 'peso_medio_kg', 'taxa_natalidade_pct'} <= set(insufficient['missing_fields'])


def test_explanation_builder_exposes_required_sections():
    data_quality = _load('services.analysis_engine.data_quality')
    risk_explanation = _load('services.analysis_engine.risk_explanation')

    analysis = data_quality.assess_data_quality(
        {
            'preco_arroba': 320.0,
            'custo_arroba': 118.0,
            'peso_medio_kg': 420.0,
            'taxa_natalidade_pct': 72.0,
            'taxa_mortalidade_pct': 3.0,
        },
        {'values': [10, 20, 30]},
        {'receita_prevista': 180_000.0, 'fluxo_caixa_previsto': 25_000.0},
    )

    explanation = risk_explanation.build_explanation(analysis)

    assert explanation['status'] == 'COMPLETO'
    assert explanation['reasons']
    assert explanation['positive_factors']
    assert explanation['points_of_attention']
    assert explanation['assumptions']
    assert explanation['provenance']
    assert explanation['limitations']


def test_experimental_score_is_bounded_and_explicitly_unvalidated():
    data_quality = _load('services.analysis_engine.data_quality')
    experimental_score = _load('services.analysis_engine.experimental_score')

    quality = data_quality.assess_data_quality(
        {
            'preco_arroba': 320.0,
            'custo_arroba': 118.0,
            'peso_medio_kg': 420.0,
            'taxa_natalidade_pct': 72.0,
            'taxa_mortalidade_pct': 3.0,
        },
        {'values': [10, 20, 30]},
        {'receita_prevista': 180_000.0, 'fluxo_caixa_previsto': 25_000.0},
    )

    score = experimental_score.calculate_experimental_score(
        {
            'payment_capacity': {'dscr': 1.42},
            'resilience': {'stress_dscr': 1.18},
            'productive_efficiency': {'score': 74},
            'herd_structure': {'score': 66},
            'data_quality': quality,
            'sensitivity': {'score': 58},
            'projected_liquidity': {'score': 61},
        }
    )

    assert 0 <= score['score'] <= 1000
    assert score['experimental'] is True
    assert score['validated'] is False
    assert score['autonomous_credit_decision'] is False
    assert set(score['components']) >= {
        'payment_capacity',
        'resilience',
        'productive_efficiency',
        'herd_structure',
        'data_quality',
        'sensitivity',
        'projected_liquidity',
    }
    assert score['limitations']
    assert score['provenance']


def test_legacy_rating_keeps_current_0_to_100_scale():
    rating = calcular_rating(
        dscr=1.42,
        ltv=55,
        consistencia=82,
        confianca='alta',
        documentos_pendentes=0,
        comprometimento_pct=42,
    )

    assert 0 <= rating['score'] <= 100
    assert rating['faixa'] in {'A', 'B', 'C', 'D', 'E'}
    assert 'observacao' in rating
