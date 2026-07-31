"""
Trilha de auditoria de acesso: quem viu o quê, quando, de onde.

Sem isto, uma instituição não consegue responder à própria auditoria interna
sobre quem consultou dado de crédito de qual cliente — e essa pergunta aparece
na área de compras antes de qualquer discussão sobre modelo. É o item que
barra a venda para banco, não a acurácia.

Não confundir com a `consistencia_rebanho`, que audita o REBANHO declarado.
Esta audita o USO do sistema.

TRÊS REGRAS

1. **Append-only.** Não há update nem delete. Uma trilha que pode ser editada
   não é trilha — é anotação.

2. **Nunca derruba a operação.** Falha ao registrar vira log de erro no
   servidor, jamais erro para o usuário. Um parecer não pode falhar porque a
   auditoria caiu; e um sistema que falha assim acaba com a auditoria
   desligada na primeira sexta-feira ruim.

3. **Registra a referência, não o conteúdo.** O que importa é *que* fulano
   acessou o parecer 412 da fazenda 7 às 14h32, não o rebanho inteiro
   duplicado numa segunda tabela — que só multiplicaria a superfície de
   vazamento do dado que se quer proteger.

Módulo puro na definição dos eventos; a escrita fica em `database.py`.
"""
from __future__ import annotations

# ── Catálogo de eventos ─────────────────────────────────────────────────────
# Nomeados pelo que o auditor procura, não pela rota que os gerou.
LOGIN            = 'login'
LOGIN_FALHOU     = 'login_falhou'
LOGOUT           = 'logout'
PARECER_GERADO   = 'parecer_gerado'
PARECER_PDF      = 'parecer_pdf'
HISTORICO_LIDO   = 'historico_lido'
PARECERES_LIDOS  = 'pareceres_lidos'
CICLO_CONFIRMADO = 'ciclo_confirmado'
DOC_LIDO         = 'documento_lido'
ADMIN_ACAO       = 'admin_acao'
WHATSAPP_VINCULO = 'whatsapp_vinculo'
WHATSAPP_CONSULTA = 'whatsapp_consulta'
LGPD_EXPORTACAO   = 'lgpd_exportacao'
LGPD_ANONIMIZACAO = 'lgpd_anonimizacao'
LGPD_PURGA        = 'lgpd_purga_auditoria'
<<<<<<< HEAD
LOGIN_2FA_FALHOU  = 'login_2fa_falhou'
LOGIN_2FA_BACKUP  = 'login_2fa_backup'
DOIS_FATORES_ATIVADO    = '2fa_ativado'
DOIS_FATORES_DESATIVADO = '2fa_desativado'
=======
>>>>>>> origin/main

EVENTOS = {
    LOGIN:             'Entrou no sistema',
    LOGIN_FALHOU:      'Tentativa de login recusada',
    LOGOUT:            'Saiu do sistema',
    PARECER_GERADO:    'Gerou parecer de crédito',
    PARECER_PDF:       'Baixou PDF do parecer',
    HISTORICO_LIDO:    'Consultou histórico da fazenda',
    PARECERES_LIDOS:   'Consultou pareceres da fazenda',
    CICLO_CONFIRMADO:  'Confirmou ou corrigiu a classificação',
    DOC_LIDO:          'Enviou documento para leitura',
    ADMIN_ACAO:        'Ação administrativa',
    WHATSAPP_VINCULO:  'Vinculou número de WhatsApp',
    WHATSAPP_CONSULTA: 'Consultou parecer pelo WhatsApp',
    LGPD_EXPORTACAO:   'Exportou dados de um titular (LGPD Art. 18, V)',
    LGPD_ANONIMIZACAO: 'Anonimizou um titular (LGPD Art. 18)',
    LGPD_PURGA:        'Purgou a trilha além do prazo de retenção',
<<<<<<< HEAD
    LOGIN_2FA_FALHOU:  'Segundo fator recusado',
    LOGIN_2FA_BACKUP:  'Entrou usando código de recuperação',
    DOIS_FATORES_ATIVADO:    'Ativou o segundo fator',
    DOIS_FATORES_DESATIVADO: 'Desativou o segundo fator',
=======
>>>>>>> origin/main
}

# Eventos que tocam dado de crédito de um cliente identificado. É esta lista
# que a auditoria interna do banco pede primeiro.
SENSIVEIS = frozenset({
    PARECER_GERADO, PARECER_PDF, HISTORICO_LIDO, PARECERES_LIDOS,
    DOC_LIDO, WHATSAPP_CONSULTA, LGPD_EXPORTACAO,
})


def rotulo(evento: str) -> str:
    return EVENTOS.get(evento, evento)


def e_sensivel(evento: str) -> bool:
    return evento in SENSIVEIS


def ip_da_requisicao(request) -> str:
    """
    IP de origem atrás de proxy.

    Railway e qualquer PaaS ficam na frente da app, então `remote_addr` é o do
    balanceador. O primeiro endereço do X-Forwarded-For é o cliente — e é o que
    a auditoria precisa. Truncado: o header é controlado pelo cliente e uma
    cadeia longa não pode virar linha gigante no banco.
    """
    xff = (request.headers.get('X-Forwarded-For') or '').split(',')
    if xff and xff[0].strip():
        return xff[0].strip()[:64]
    return (request.remote_addr or '')[:64]
