"""
Assistente de crédito: o que ele responde, o que ele recusa.

O chat existente responde sobre O PARECER ABERTO. Falta a metade que um
assistente de crédito precisa ter: a pergunta conceitual, feita sem parecer
nenhum na tela — "o que é deságio", "como vocês calculam desfrute", "por que
carência muda a parcela".

DUAS DECISÕES QUE DEFINEM ESTE MÓDULO

1. Conceito se responde a partir da NOSSA metodologia, não do modelo.

   Um modelo de linguagem explica "deságio" em geral. Nós explicamos o
   deságio QUE O PARECER USA — 25% em boi, 35% em matriz — porque é a nossa
   conta que produz o número que o comitê vai ler. Uma explicação que não
   bate com o cálculo é pior que nenhuma.

   Por isso os textos são montados a partir das CONSTANTES VIVAS do código.
   Mudar a política muda a explicação no mesmo commit; elas não podem
   divergir porque não são duas coisas.

2. Normativo se RECUSA, e a recusa é determinística.

   Taxa de Pronaf, prazo de Moderfrota, exigência do MCR: um modelo responde
   com confiança e erra. Num produto que vai a banco, resposta errada sobre
   norma é pior que resposta nenhuma — quem cita taxa errada numa proposta
   perde o cliente e a credibilidade junto.

   A recusa NÃO é delegada ao modelo via prompt. Prompt é pedido, não garantia:
   basta a pergunta vir enviesada para o modelo responder assim mesmo. Aqui a
   pergunta é classificada ANTES de qualquer chamada, e normativa não chega ao
   modelo.

O que este módulo NÃO faz é decidir se a pergunta é sobre o parecer — isso
continua com quem tem o parecer em mão.
"""
from __future__ import annotations

import re
import unicodedata


def _sem_acento(t: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', t or '')
                   if unicodedata.category(c) != 'Mn').lower()


# ── O que não temos fonte para responder ────────────────────────────────────
#
# Assuntos em que a resposta depende de norma, tabela oficial ou condição
# contratada — e o sistema não carrega nenhuma dessas. Errar aqui não é
# impreciso, é dar informação falsa sobre obrigação legal ou custo de dinheiro.
_SEM_FONTE = [
    (r'\bpronaf\b',                       'linhas do Pronaf'),
    (r'\bpronamp\b',                      'linhas do Pronamp'),
    (r'\bmoderfrota\b',                   'Moderfrota'),
    (r'\binovagro\b',                     'Inovagro'),
    (r'\bpca\b',                          'PCA'),
    (r'\bplano safra\b',                  'Plano Safra'),
    (r'\bmcr\b|manual de credito rural',  'o MCR do Banco Central'),
    (r'\bresolu(c|ç)(a|ã)o\s*\d',         'resoluções do CMN'),
    (r'\bselic\b',                        'a Selic'),
    (r'\btaxa\b.*\b(juros|ano|a\.a)\b|\b(juros|taxa)\b.*\b(pronaf|pronamp|banco|linha)\b',
                                          'taxas de juros de linhas oficiais'),
    (r'\b(qual|quanto).*\b(taxa|juros)\b','taxas de juros'),
    (r'\bsubven(c|ç)(a|ã)o\b',            'subvenção equalizada'),
    (r'\blimite\b.*\b(pronaf|pronamp|linha|banco)\b', 'limites de linhas oficiais'),
]

RECUSA = (
    'Não tenho fonte para {assunto} e não vou chutar — informação errada sobre '
    'condição de crédito custa caro numa proposta. Consulte o MCR do Banco '
    'Central ou o gerente da instituição.\n\n'
    'Posso ajudar com a metodologia do parecer: DSCR, garantia e deságio, '
    'endividamento, desfrute, custo por arroba e classificação do rebanho.'
)


def assunto_sem_fonte(pergunta: str) -> str | None:
    """Assunto normativo detectado na pergunta, ou None.

    Determinístico e antes do modelo: a garantia não pode depender de o
    modelo obedecer a uma instrução de prompt.
    """
    t = _sem_acento(pergunta)
    for padrao, assunto in _SEM_FONTE:
        if re.search(padrao, t):
            return assunto
    return None


# ── O que sabemos, porque é o que calculamos ────────────────────────────────

def _pct(v) -> str:
    return f'{float(v) * 100:.0f}%' if float(v) <= 1 else f'{float(v):.0f}%'


def _conceitos() -> dict:
    """Explicações montadas a partir das constantes vivas.

    Importadas aqui dentro para o módulo não criar ciclo com quem o usa.
    """
    from services.parecer_credito import (
        DSCR_APROVAR, DSCR_RESSALVA, COE_DIVERGENCIA_AVISO)
    from services.garantia import DESAGIO_PADRAO, LTV_APROVAR, LTV_RESSALVA
    from services.endividamento import COMPROMETIMENTO_ALERTA
    from services.parametros_zootecnicos import (
        DESFRUTE_PCT, NATALIDADE_PCT, DESMAME_PCT)
    from services.benchmarks_nacionais import DESFRUTE_AFASTAMENTO_ALERTA

    desagio = ' · '.join(f'{k} {_pct(v)}' for k, v in DESAGIO_PADRAO.items())
    desfrute = ' · '.join(f'{k} {float(v):.0f}%' for k, v in DESFRUTE_PCT.items())

    return {
        'dscr': (
            'DSCR é a cobertura do serviço da dívida: quanto de caixa a operação '
            f'gera para cada real de parcela. Aprovamos a partir de '
            f'{float(DSCR_APROVAR):.2f} e damos ressalva a partir de '
            f'{float(DSCR_RESSALVA):.2f}.\n\n'
            'O ponto que diferencia: avaliamos TODOS os anos do prazo, não só o '
            'primeiro. O ano 1 costuma liquidar o estoque de animais prontos que '
            'está na ficha; os seguintes vendem só a produção corrente. Já vimos '
            'um ciclo completo com 6,08 no ano 1 e −0,53 no ano 2, com o parecer '
            'aprovando 36 meses. A recomendação segue o ano crítico.'
        ),
        'garantia': (
            'Rebanho em penhor não se realiza pela cotação do dia: entre a '
            'inadimplência e o caixa há apreensão, transporte, risco sanitário e '
            f'venda forçada. Por isso cada categoria leva um deságio — {desagio}.\n\n'
            f'O LTV é medido sobre o valor de EXECUÇÃO, não o de mercado: até '
            f'{_pct(LTV_APROVAR)} é folgado, até {_pct(LTV_RESSALVA)} é ajustado, '
            f'acima disso é insuficiente.'
        ),
        'endividamento': (
            'Somamos a parcela do crédito em análise às dívidas já existentes, '
            'porque a decisão é sobre a situação DEPOIS da operação, não antes. '
            f'O alerta dispara em {_pct(COMPROMETIMENTO_ALERTA)} da geração de caixa.\n\n'
            'Endividamento declarado como zero dispara aviso para conferir o SCR '
            'do Banco Central: zero pode ser verdade ou omissão, e o parecer não '
            'trata os dois igual.'
        ),
        'desfrute': (
            'Desfrute é o que o rebanho entrega em relação ao que ele é. '
            f'Referência por modalidade: {desfrute}.\n\n'
            'Calculamos de duas formas. A simplificada (vendas ÷ rebanho) é a que '
            'se compara com as faixas do setor. A completa desconta compras e a '
            'variação de estoque — e é a única que distingue vender a PRODUÇÃO de '
            'vender o PLANTEL. Quando as duas se afastam mais de '
            f'{DESFRUTE_AFASTAMENTO_ALERTA:.0f} pontos, o parecer avisa: a venda '
            'veio do rebanho, e rebanho vendido não se repete no ano seguinte.'
        ),
        'custo': (
            'O custo entra em R$ por cabeça/mês, que é como o setor mede, e é '
            'convertido para R$/@ pelo peso médio DO REBANHO DECLARADO — não por '
            'uma constante.\n\n'
            'O custo resultante é comparado com a referência Campo Futuro/CNA da '
            f'praça. Divergência acima de {COE_DIVERGENCIA_AVISO:.0f}% aparece no '
            'parecer como aviso: se o custo estiver superestimado, a geração de '
            'caixa e o DSCR estão subestimados na mesma proporção. É para o '
            'analista conferir antes de aceitar uma recusa.'
        ),
        'carencia': (
            'Carência não é de graça. Durante ela o saldo devedor rende juros, e '
            'quem amortiza depois amortiza um saldo maior.\n\n'
            'Num crédito de R$ 1 milhão em 36 meses com 12 de carência a 12,5% '
            'a.a., o principal vai a R$ 1.125.000 e a parcela sai R$ 52.872 — não '
            'R$ 46.997, que é o que dá ignorando a capitalização. A memória de '
            'cálculo mostra essa linha.'
        ),
        'classificacao': (
            'A modalidade sai de um ensemble de quatro modelos sobre 42 variáveis '
            'derivadas das 10 contagens por faixa e sexo, com regras determinísticas '
            'por cima. O parecer diz qual das duas decidiu.\n\n'
            'Uma regra que vale conhecer: cria exige base reprodutiva, não '
            'predominância feminina. Rebanho quase todo fêmea mas com a faixa '
            'acima de 36 meses vazia é recria de fêmeas — elas saem antes de '
            'parir. A primeira parição é aos 36,3 meses (Embrapa), então fêmea de '
            '25–36m ainda não é matriz.'
        ),
        'proveniencia': (
            'Cada número do parecer diz de onde veio: MEDIDO (série apurada por '
            'terceiro, com fonte), REFERÊNCIA (bibliografia, não apurada nesta '
            'fazenda), POLÍTICA (escolha da instituição, ajustável) ou DECLARADO '
            '(informado, não verificado).\n\n'
            'Serve para o comitê saber o que se discute e o que se cita. Política '
            'se discute; medição se cita.'
        ),
        'natalidade': (
            f'Projetamos com natalidade de {float(NATALIDADE_PCT):.0f}% e desmame '
            f'de {float(DESMAME_PCT):.0f}%, que são referência de mercado — '
            'conservadoras de propósito.\n\n'
            'A Embrapa apurou 87,5% de prenhez em rebanho experimental, acima de '
            'fazenda comercial. Esse número aparece no parecer como medição de '
            'terceiro, mas NÃO substitui a projeção: usá-lo inflaria a receita de '
            'todo parecer de cria.'
        ),
    }


# Sinônimos que o analista de fato usa, não o nome interno da chave.
_GATILHOS = {
    'dscr':           (r'\bdscr\b', r'cobertura.*d(i|í)vida', r'capacidade de pagamento'),
    'garantia':       (r'\bgarantia', r'\bdesagio\b|\bdesagios\b', r'\bltv\b', r'penhor', r'execu(c|ç)(a|ã)o'),
    'endividamento':  (r'endividament', r'comprometiment', r'\bscr\b', r'd(i|í)vida.*existente'),
    'desfrute':       (r'desfrute', r'liquida(c|ç)(a|ã)o.*plantel'),
    'custo':          (r'\bcusto', r'\bcoe\b', r'campo futuro', r'r\$.*arroba|arroba.*custo'),
    'carencia':       (r'car(e|ê)ncia', r'capitaliza'),
    'classificacao':  (r'classifica', r'modalidade', r'\bciclo\b.*(qual|como)', r'\bshap\b',
                       r'\bcria\b.*(que|como|por que)', r'recria.*engorda'),
    'proveniencia':   (r'proveni(e|ê)ncia', r'de onde vem|de onde veio', r'\bfonte\b.*(numero|número|dado)'),
    'natalidade':     (r'natalidade', r'desmame', r'prenhez'),
}


# Perguntas que pedem o VALOR, não o conceito.
#
# "Qual o DSCR?" e "o que é DSCR?" citam a mesma palavra e querem coisas
# opostas: a primeira quer o número DESTE parecer, a segunda quer a definição.
# Responder a definição a quem pediu o número é o pior dos dois erros — o
# analista já sabe o que é DSCR, ele quer saber quanto deu.
#
# Na dúvida o assistente CEDE: quem tem o parecer em mão responde melhor uma
# pergunta conceitual do que este módulo responderia uma pergunta de valor.
_PEDE_VALOR = (
    r'\bqual\b', r'\bquanto\b', r'\bquantos\b', r'\bqual e\b',
    r'\bmeu\b|\bminha\b|\bdesse\b|\bdeste\b|\bdessa\b|\bdesta\b',
    r'\bdeu\b|\bficou\b|\bsaiu\b',
    r'\bdo parecer\b|\bda fazenda\b|\bdesse rebanho\b',
)

# Formas que são inequivocamente pedido de EXPLICAÇÃO, mesmo com "qual" junto
# ("qual a diferença entre recria e engorda", "qual o critério de deságio").
_PEDE_EXPLICACAO = (
    r'\bo que (e|significa)\b', r'\bcomo (voces|vc|se|e|funciona|calcula)',
    r'\bpor que\b|\bporque\b', r'\bexplica', r'\bdiferenca\b',
    r'\bcriterio\b', r'\bmetodologia\b', r'\bde onde vem\b|\bde onde veio\b',
)


def pede_valor(pergunta: str) -> bool:
    """A pergunta quer o número deste parecer, não a definição."""
    t = _sem_acento(pergunta)
    if any(re.search(p, t) for p in _PEDE_EXPLICACAO):
        return False
    return any(re.search(p, t) for p in _PEDE_VALOR)


def conceito_da_pergunta(pergunta: str) -> str | None:
    """Chave do conceito que a pergunta pede, ou None.

    Devolve None quando a pergunta é por VALOR: aí quem tem o parecer responde.
    """
    if pede_valor(pergunta):
        return None
    t = _sem_acento(pergunta)
    for chave, padroes in _GATILHOS.items():
        if any(re.search(p, t) for p in padroes):
            return chave
    return None


def explicar(chave: str) -> str | None:
    return _conceitos().get(chave)


def responder(pergunta: str) -> dict | None:
    """Resposta do assistente para uma pergunta, sem chamar modelo nenhum.

    Devolve `{tipo, texto}` quando sabe responder ou sabe que deve recusar;
    None quando a pergunta não é dessas — aí segue para quem tem o parecer.

    A ordem importa: a recusa vem ANTES do conceito. "Qual a taxa de juros do
    Pronaf para quem tem DSCR bom?" cita DSCR e casaria com o conceito, mas o
    que está sendo perguntado é a taxa.
    """
    assunto = assunto_sem_fonte(pergunta)
    if assunto:
        return {'tipo': 'sem_fonte', 'texto': RECUSA.format(assunto=assunto)}
    chave = conceito_da_pergunta(pergunta)
    if chave:
        return {'tipo': 'conceito', 'chave': chave, 'texto': explicar(chave)}
    return None
