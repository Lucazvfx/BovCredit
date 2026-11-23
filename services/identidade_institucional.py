"""Identidade institucional (white-label leve) da empresa no PDF do parecer.

Dado da pessoa jurídica e nome/registro profissional do responsável técnico
(este último é dado pessoal, informado pela própria empresa, sem vínculo com conta): nome de
exibição, CNPJ e nome/registro do responsável. CPF é recusado (dado pessoal
sem necessidade aqui) e nada disto vem de e-mail ou conta de usuário.
"""
import re
import unicodedata

CAMPOS = ('nome_exibicao', 'cnpj', 'responsavel_nome', 'responsavel_registro')
LIMITES = {'nome_exibicao': 120, 'responsavel_nome': 120, 'responsavel_registro': 40}
_REGISTRO_OK = re.compile(r"^[\w .,/\-]+$", re.UNICODE)


def identidade_vazia() -> dict:
    return {c: '' for c in CAMPOS}


def _limpar_texto(valor) -> str:
    """Remove controle/formatação invisível e normaliza espaços."""
    texto = ''.join(' ' if ch.isspace() else ch for ch in str(valor)
                    if ch.isspace() or unicodedata.category(ch)[0] != 'C')
    return re.sub(r'\s+', ' ', texto).strip()


_CNPJ_BASE = re.compile(r'^[0-9A-Z]{12}[0-9]{2}$')


def cnpj_valido(digitos: str) -> bool:
    """CNPJ numérico ou alfanumérico (IN RFB 2.229/2024); valor do caractere = ASCII - 48."""
    if not _CNPJ_BASE.match(digitos or '') or len(set(digitos)) == 1:
        return False
    for tam in (12, 13):
        pesos = ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if tam == 12
                 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        soma = sum((ord(d) - 48) * p for d, p in zip(digitos[:tam], pesos))
        dv = 11 - soma % 11
        if int(digitos[tam]) != (0 if dv >= 10 else dv):
            return False
    return True


def formatar_cnpj(digitos: str) -> str:
    d = digitos or ''
    if not _CNPJ_BASE.match(d):
        return ''
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'


def validar_identidade(payload) -> tuple[dict | None, str | None]:
    """(dados normalizados, None) ou (None, mensagem). Campo vazio = limpar."""
    if not isinstance(payload, dict):
        return None, 'Corpo inválido.'
    dados = identidade_vazia()
    for campo, limite in LIMITES.items():
        bruto = payload.get(campo)
        if bruto is None:
            continue
        if not isinstance(bruto, str):
            return None, f'Campo inválido: {campo}.'
        if len(bruto) > limite * 4:
            return None, f'{campo} excede {limite} caracteres.'
        texto = _limpar_texto(bruto)
        if len(texto) > limite:
            return None, f'{campo} excede {limite} caracteres.'
        if any(ch in texto for ch in '<>'):
            return None, f'{campo} contém caracteres não permitidos.'
        dados[campo] = texto
    if dados['responsavel_registro'] and not _REGISTRO_OK.match(dados['responsavel_registro']):
        return None, 'Registro do responsável contém caracteres não permitidos.'
    cnpj = payload.get('cnpj')
    if cnpj is not None:
        if not isinstance(cnpj, str) or len(cnpj) > 30:
            return None, 'CNPJ inválido.'
        digitos = re.sub(r'[^0-9A-Za-z]', '', cnpj).upper()
        if digitos:
            if len(digitos) == 11 and digitos.isdigit():
                return None, 'Informe o CNPJ da empresa; CPF não é aceito.'
            if not cnpj_valido(digitos):
                return None, 'CNPJ inválido.'
            dados['cnpj'] = digitos
    return dados, None


def para_resposta(dados: dict | None) -> dict:
    """Dados persistidos → JSON da API (CNPJ já formatado além do limpo)."""
    base = {**identidade_vazia(), **{k: (dados or {}).get(k) or '' for k in CAMPOS}}
    base['cnpj_formatado'] = formatar_cnpj(base['cnpj'])
    return base


def linhas_pdf(dados: dict | None) -> list[str]:
    """Texto puro (sem escape) das linhas institucionais; [] se nada preenchido."""
    d = dados or {}
    linhas = []
    cnpj = formatar_cnpj(d.get('cnpj') or '')
    if cnpj:
        linhas.append(f'CNPJ {cnpj}')
    resp = (d.get('responsavel_nome') or '').strip()
    reg = (d.get('responsavel_registro') or '').strip()
    if resp:
        linhas.append(f'Responsável técnico: {resp}' + (f' — Registro {reg}' if reg else ''))
    elif reg:
        linhas.append(f'Registro do responsável técnico: {reg}')
    return linhas
