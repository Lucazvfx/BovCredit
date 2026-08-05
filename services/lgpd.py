"""
LGPD como código: inventário, anonimização, portabilidade e retenção.

O que é código aqui e o que não é
---------------------------------
Este módulo cobre as obrigações que se implementam. **Não** cobre as que se
escrevem: base legal de cada tratamento, encarregado (DPO), política de
privacidade, contrato de operador com o cliente. Essas são decisão da empresa,
não do sistema, e nenhuma linha aqui as substitui.

A tensão que o desenho resolve
------------------------------
A trilha de auditoria é **append-only** por decisão explícita (ver
`services/auditoria.py`): uma trilha que se edita não é trilha. Mas o Art. 18
da LGPD dá ao titular o direito à eliminação dos seus dados — e a trilha guarda
e-mail e IP.

Os dois não podem ser atendidos apagando linhas. A resolução é **anonimizar,
não excluir**: o registro do evento permanece (quem auditou continua sabendo
que às 14h32 alguém consultou o parecer 412), mas os campos que identificam a
pessoa viram um pseudônimo estável.

Estável importa: substituir por `NULL` destruiria a capacidade de reconstruir
uma sessão — "o mesmo usuário fez 40 consultas em 3 minutos" é exatamente o que
uma investigação de vazamento precisa ver, e continua visível com pseudônimo.

Sobre o dado de crédito
-----------------------
O rebanho e o parecer de uma fazenda são dados do CLIENTE da consultoria, não
do usuário do sistema. Anonimizar um analista não pode apagar o parecer que ele
emitiu — o documento tem valor probatório para a instituição e prazo próprio de
guarda. Por isso `anonimizar_usuario` mexe em quem OPERA o sistema, e a exclusão
de dado de cliente é operação separada, por fazenda.

Módulo puro — as consultas ficam em `database.py`.
"""
from __future__ import annotations

import hashlib
import os

# ── Art. 37: registro das operações de tratamento ───────────────────────────
# O que se guarda, onde, por quê e por quanto tempo. É o documento que o
# encarregado apresenta, e serve de checklist para quem for mexer no schema:
# tabela nova com dado pessoal e sem entrada aqui é buraco de conformidade.
INVENTARIO = {
    'usuarios': {
        'campos':    ['email', 'nome', 'senha_hash', 'security_answer_hash'],
        'titular':   'usuário do sistema (analista)',
        'finalidade': 'autenticação e identificação do autor do parecer',
        'retencao':  'enquanto a conta existir',
    },
    'auditoria_acessos': {
        'campos':    ['user_email', 'ip'],
        'titular':   'usuário do sistema (analista)',
        'finalidade': 'trilha de auditoria de acesso a dado de crédito',
        'retencao':  'RETENCAO_AUDITORIA_DIAS (default 730)',
    },
    'whatsapp_vinculos': {
        'campos':    ['telefone'],
        'titular':   'usuário do sistema (analista)',
        'finalidade': 'vincular o canal WhatsApp à conta',
        'retencao':  'enquanto o vínculo existir',
    },
    'fazendas': {
        'campos':    ['nome', 'proprietario', 'municipio'],
        'titular':   'cliente da consultoria (produtor)',
        'finalidade': 'identificação do proponente na análise de crédito',
        'retencao':  'definida pela instituição — prazo de guarda do processo',
    },
    'registros': {
        'campos':    ['fazenda', 'municipio'],
        'titular':   'cliente da consultoria (produtor)',
        'finalidade': 'histórico de classificações do rebanho',
        'retencao':  'definida pela instituição',
    },
    # O acervo guarda o DOCUMENTO original — ficha de órgão estadual, que traz
    # nome do produtor, CPF e propriedade. É o registro mais sensível do
    # sistema, e por isso é o que precisa estar declarado com mais precisão:
    # não é metadado de uma leitura, é o papel do cliente inteiro.
    #
    # A finalidade é dupla e as duas são legítimas, mas só a primeira é do
    # titular. A segunda (melhorar o parser) é interesse legítimo do
    # controlador e precisa aparecer escrita — inventário que esconde
    # finalidade secundária é o que a ANPD procura.
    'documentos': {
        'campos':    ['nome_arquivo', 'conteudo (PDF da ficha)', 'parse'],
        'titular':   'cliente da consultoria (produtor)',
        'finalidade': ('comprovação da origem do rebanho declarado no parecer; '
                       'e correção dos leitores de documento a partir dos casos '
                       'em que a leitura automática divergiu'),
        'retencao':  'definida pela instituição — prazo de guarda do processo',
    },
    'pareceres': {
        'campos':    ['parecer (identificação embutida no JSON)'],
        'titular':   'cliente da consultoria (produtor)',
        'finalidade': 'documento de decisão de crédito',
        'retencao':  'definida pela instituição — valor probatório',
    },
}

# Retenção da trilha. Dois anos por padrão: prazo suficiente para investigação
# de incidente sem virar acúmulo indefinido de e-mail e IP. Ajustável, porque
# a instituição pode ter obrigação de guarda mais longa.
RETENCAO_AUDITORIA_DIAS = int(os.environ.get('RETENCAO_AUDITORIA_DIAS', '730'))

# Sal do pseudônimo. Sem ele, o hash de um e-mail seria reversível por
# dicionário — a lista de e-mails plausíveis é curta e pública.
_SAL = os.environ.get('LGPD_SAL') or os.environ.get('SECRET_KEY') or 'orkavyn-agro-intelligence'

PREFIXO_ANONIMO = 'anon:'


def pseudonimo(valor: str) -> str:
    """
    Pseudônimo estável para um identificador.

    Estável de propósito: o mesmo e-mail sempre gera o mesmo pseudônimo, então
    "o mesmo usuário fez 40 consultas em 3 minutos" continua legível na trilha
    depois da anonimização — que é justamente o que uma investigação de
    vazamento precisa ver. Substituir por NULL destruiria isso.

    Irreversível: não há tabela de-para. Quem anonimiza não desfaz.
    """
    if not valor:
        return PREFIXO_ANONIMO + '000000000000'
    h = hashlib.sha256((_SAL + str(valor)).encode()).hexdigest()
    return PREFIXO_ANONIMO + h[:12]


def e_anonimo(valor) -> bool:
    return bool(valor) and str(valor).startswith(PREFIXO_ANONIMO)


def campos_pessoais(tabela: str) -> list:
    return list((INVENTARIO.get(tabela) or {}).get('campos') or [])


def tabelas_com_dado_pessoal() -> list:
    return sorted(INVENTARIO)


def resumo_inventario() -> list:
    """Formato de apresentação — o registro do Art. 37 em linhas."""
    return [
        {'tabela': t, **dados}
        for t, dados in sorted(INVENTARIO.items(),
                               key=lambda kv: kv[1]['titular'])
    ]
