"""Quem o login social pode deixar entrar — e quem ele não pode criar.

O Google prova *quem é você*. Não decide *se você pode entrar*: isso continua
sendo do sistema. A distinção não é filosófica — sem ela, qualquer pessoa com
conta Google entraria numa ferramenta de análise de crédito.

Três portas, nesta ordem:

1. **Já vinculou antes** — o `provedor_id` bate. Entra.
2. **E-mail já cadastrado pelo admin** — entra e o vínculo é criado. É o
   caminho de quem já usava senha e passou a usar o botão.
3. **Domínio liberado** — a conta é criada na hora. Só para os domínios
   listados em `DOMINIOS_PERMITIDOS`; qualquer outro e-mail é recusado.

## Por que o e-mail sozinho não basta

O Google emite `email_verified`. Sem conferir isso, um provedor de identidade
mal configurado poderia afirmar um e-mail que o dono nunca provou controlar —
e o domínio liberado viraria porta aberta.

Contas Workspace trazem também `hd` (hosted domain), que é a afirmação forte:
"esta conta pertence a este domínio corporativo". Quando `hd` vem, é ele que
manda. Quando não vem — conta pessoal com e-mail no domínio —, cai no sufixo
do e-mail, que exige controle da caixa para ter sido criada.

## O que NÃO se decide aqui

Ser admin continua saindo de `ADMIN_EMAILS`, e a empresa continua vindo de
`empresa_membros`. Uma conta criada por domínio entra sem empresa nenhuma e
não enxerga dado de ninguém até um admin vinculá-la — degradação proposital,
não esquecimento.
"""
from __future__ import annotations

from dataclasses import dataclass

# Motivos de recusa, para a tela dizer o que fazer em vez de "acesso negado".
NAO_VERIFICADO = 'nao_verificado'
FORA_DO_DOMINIO = 'fora_do_dominio'
SEM_EMAIL = 'sem_email'

# O que fazer com quem passou.
ENTRAR = 'entrar'
VINCULAR = 'vincular'
CRIAR = 'criar'


@dataclass(frozen=True)
class Decisao:
    acao: str | None          # ENTRAR, VINCULAR, CRIAR — ou None se recusado
    motivo: str | None = None  # preenchido só na recusa

    @property
    def permitido(self) -> bool:
        return self.acao is not None


def normalizar_dominios(bruto: str | None) -> tuple[str, ...]:
    """Lê DOMINIOS_PERMITIDOS: "a.com.br, @b.com" → ('a.com.br', 'b.com')."""
    if not bruto:
        return ()
    itens = (d.strip().lower().lstrip('@') for d in bruto.split(','))
    return tuple(d for d in itens if d)


def dominio_do_email(email: str) -> str:
    return email.rsplit('@', 1)[-1].lower() if '@' in email else ''


def decidir(*, email: str, email_verificado: bool, hosted_domain: str | None,
            dominios_permitidos: tuple[str, ...],
            ja_vinculado: bool, ja_cadastrado: bool) -> Decisao:
    """Resolve o acesso a partir do que o provedor afirmou.

    Pura de propósito: a regra que decide quem entra num sistema de crédito
    tem de ser testável sem rede e sem provedor no ar.
    """
    email = (email or '').strip().lower()
    if not email or '@' not in email:
        return Decisao(None, SEM_EMAIL)

    # Vínculo existente vale mesmo que o domínio tenha saído da lista depois:
    # tirar alguém de dentro é ato de administração, não efeito colateral de
    # uma variável de ambiente.
    if ja_vinculado:
        return Decisao(ENTRAR)

    if not email_verificado:
        return Decisao(None, NAO_VERIFICADO)

    if ja_cadastrado:
        return Decisao(VINCULAR)

    # Daqui para baixo é criação de conta — o único caminho que decide sozinho
    # que alguém novo pode usar o sistema. Sem lista, ninguém entra.
    if not dominios_permitidos:
        return Decisao(None, FORA_DO_DOMINIO)

    # `hd` é a afirmação forte do Workspace e vence o sufixo do e-mail.
    dominio = (hosted_domain or '').strip().lower() or dominio_do_email(email)
    if dominio not in dominios_permitidos:
        return Decisao(None, FORA_DO_DOMINIO)

    return Decisao(CRIAR)


MENSAGENS = {
    SEM_EMAIL: 'A conta não informou um e-mail. Entre com e-mail e senha.',
    NAO_VERIFICADO: ('Este e-mail ainda não foi verificado no provedor. '
                     'Confirme-o e tente de novo.'),
    FORA_DO_DOMINIO: ('Esta conta não tem acesso à plataforma. '
                      'Peça a um administrador para cadastrar seu e-mail.'),
}


def mensagem(motivo: str | None) -> str:
    return MENSAGENS.get(motivo or '', 'Não foi possível entrar com essa conta.')
