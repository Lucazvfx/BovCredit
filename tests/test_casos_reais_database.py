import uuid

import database as db


def _caso_pendente():
    return db.criar_caso_real(
        valores=[10, 8, 5, 4, 12, 9, 20, 6, 30, 3],
        classificacao_ml='CICLO_COMPLETO',
        confianca=82.5,
        origem='PDF',
        arquivo=f'{uuid.uuid4()}.pdf',
        estado='TO_DECLARACAO',
        modelo='TO_DECLARACAO',
        fazenda='Fazenda Teste',
        municipio='Palmas',
        user_id=900001,
        empresa_id=900001,
    )


def test_caso_real_nasce_pendente_e_valida_vetor():
    db.init_db()
    caso_id = _caso_pendente()

    casos = db.listar_casos_reais(user_id=900001, empresa_id=900001)
    caso = next(item for item in casos if item['id'] == caso_id)

    assert caso['status'] == 'PENDENTE'
    assert caso['classificacao_ml'] == 'CICLO_COMPLETO'
    assert caso['classificacao_humana'] is None
    assert caso['valores'] == [10, 8, 5, 4, 12, 9, 20, 6, 30, 3]


def test_confirmacao_e_idempotente_e_entra_no_resumo():
    db.init_db()
    caso_id = _caso_pendente()

    primeiro = db.confirmar_caso_real(caso_id, 'CRIA', observacao='Revisado pelo analista')
    segundo = db.confirmar_caso_real(caso_id, 'CRIA', observacao='Revisado pelo analista')
    resumo = db.resumo_casos_reais(user_id=900001, empresa_id=900001)

    assert primeiro['status'] == 'CONFIRMADO'
    assert segundo['status'] == 'CONFIRMADO'
    assert segundo['classificacao_humana'] == 'CRIA'
    assert resumo['confirmados'] >= 1


def test_nao_aceita_vetor_invalido_ou_classificacao_invalida():
    db.init_db()

    try:
        db.criar_caso_real([1, 2], 'CRIA', 70)
    except ValueError as exc:
        assert 'dez' in str(exc).lower()
    else:
        raise AssertionError('vetor inválido foi aceito')

    try:
        db.criar_caso_real([1] * 10, 'NAO_EXISTE', 70)
    except ValueError as exc:
        assert 'classifica' in str(exc).lower()
    else:
        raise AssertionError('classificação inválida foi aceita')

