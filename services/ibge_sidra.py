"""
Ingestão de séries do IBGE via API SIDRA — a primeira medição do projeto.

Hoje a camada de proveniência responde: 26 parâmetros, **0 medidos**. Tudo é
referência (bibliografia) ou política (escolha da instituição). Este módulo
existe para tirar esse zero do zero.

    desfrute(UF) = cabeças abatidas (tab. 1092) ÷ efetivo do rebanho (tab. 3939)

RESSALVA QUE VAI JUNTO COM O NÚMERO

Abate ÷ efetivo **não é** desfrute exato. Ignora venda viva entre propriedades
e inclui animal abatido em UF diferente da de origem — MT e GO exportam boi em
pé para frigorífico de outro estado, e SP abate mais do que cria. É o proxy
padrão do setor e é citável, mas o parecer precisa dizer o que ele é. Ver
`RESSALVA_DESFRUTE`.

SOBRE O PARSER

A API devolve um array cujo PRIMEIRO elemento é um cabeçalho — as mesmas
chaves das linhas de dado, mas com o nome legível da coluna no lugar do valor.
Este módulo **detecta** o cabeçalho em vez de assumir a posição 0, porque uma
mudança silenciosa de formato viraria um desfrute com valor `'Valor'`.

O campo `V` vem como STRING e nem sempre é número: o IBGE usa marcadores para
ausência de dado, e tratá-los como zero produziria desfrute zerado num estado
inteiro sem ninguém perceber. Ver `_MARCADORES`.

    ESTE MÓDULO NUNCA FOI EXERCITADO CONTRA A API REAL.

O ambiente de desenvolvimento bloqueia saída para o IBGE (403 no proxy), então
o parsing foi escrito a partir da documentação e testado com fixtures. A
primeira execução com rede é a validação de verdade — e `parse_valores`
levanta com o payload recebido quando a forma não bate, justamente para essa
primeira execução falhar alto em vez de gravar lixo.
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

BASE = 'https://apisidra.ibge.gov.br/values'
TIMEOUT = 60

# Tabelas usadas. Números conferidos no SIDRA; os códigos de variável e
# classificação são o que a primeira execução com rede precisa confirmar.
TAB_EFETIVO = '3939'   # PPM — Efetivo dos rebanhos, por tipo de rebanho
TAB_ABATE   = '1092'   # Pesquisa Trimestral do Abate — bovinos por categoria

RESSALVA_DESFRUTE = (
    'Abate ÷ efetivo é proxy de desfrute: ignora venda viva entre propriedades '
    'e inclui animal abatido fora da UF de origem.'
)

# Marcadores do IBGE no campo V. Tratá-los como zero zeraria o desfrute de um
# estado inteiro sem ninguém perceber — por isso viram None, não 0.0.
_MARCADORES = {
    '-':   'zero absoluto',
    '..':  'não se aplica',
    '...': 'dado não disponível',
    'X':   'omitido para não identificar o informante',
    '..X': 'omitido para não identificar o informante',
}


class RespostaInesperada(ValueError):
    """A forma do payload não bate com o contrato documentado."""


def _num(v):
    """
    Converte o campo V. Devolve None para marcador ou lixo — nunca 0.0.

    O IBGE usa vírgula decimal em algumas séries e ponto em outras; ambas
    aparecem, então o separador é normalizado antes da conversão.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in _MARCADORES:
        return None
    s = s.replace('.', '').replace(',', '.') if ',' in s else s
    try:
        return float(s)
    except ValueError:
        return None


def _e_cabecalho(reg: dict) -> bool:
    """
    O cabeçalho tem o NOME da coluna no lugar do valor, em todas as chaves.

    Detectar em vez de assumir `values[0]`: se o IBGE mudar a posição, assumir
    produziria um registro com V='Valor' passando por dado.
    """
    return str(reg.get('V', '')).strip().lower() in ('valor', 'value')


def parse_valores(payload) -> list[dict]:
    """
    Normaliza a resposta da API em registros utilizáveis.

    Devolve lista de {uf, uf_codigo, valor, unidade, periodo, dimensoes},
    descartando o cabeçalho e as linhas sem valor numérico.

    Levanta `RespostaInesperada` quando a forma não bate — a primeira execução
    com rede precisa falhar alto, não gravar lixo em silêncio.
    """
    if not isinstance(payload, list):
        raise RespostaInesperada(
            f'esperado array no topo, recebido {type(payload).__name__}: '
            f'{str(payload)[:300]}')
    if not payload:
        return []

    registros = []
    viu_cabecalho = False
    for reg in payload:
        if not isinstance(reg, dict):
            raise RespostaInesperada(
                f'elemento não é objeto: {str(reg)[:200]}')
        if _e_cabecalho(reg):
            viu_cabecalho = True
            continue
        valor = _num(reg.get('V'))
        if valor is None:
            continue
        registros.append({
            'uf':        (reg.get('D1N') or reg.get('NN') or '').strip(),
            'uf_codigo': (reg.get('D1C') or reg.get('NC') or '').strip(),
            'valor':     valor,
            'unidade':   (reg.get('MN') or '').strip(),
            'periodo':   (reg.get('D2N') or reg.get('D3N') or '').strip(),
            'dimensoes': {k: v for k, v in reg.items()
                          if k.startswith('D') and k.endswith('N')},
        })

    if not viu_cabecalho and registros:
        # Não é erro fatal — mas é sinal de que o contrato mudou, e a próxima
        # coisa a quebrar seria silenciosa.
        logger.warning(
            '[SIDRA] resposta sem linha de cabeçalho; formato pode ter mudado')
    return registros


def desfrute_por_uf(efetivo: Iterable[dict], abate: Iterable[dict]) -> dict:
    """
    desfrute(UF) = abate ÷ efetivo, em %.

    Casa pelo código da UF, não pelo nome: 'Rondônia' vs 'RONDÔNIA' vs
    'Rondonia' nunca casariam, e o resultado seria um dicionário vazio sem
    nenhum erro.

    Descarta UF sem os dois lados e razões implausíveis — acima de 200% o dado
    está errado ou o recorte não bate, e propagar isso para o parecer seria
    pior que não ter medição.
    """
    ef = {r['uf_codigo']: r for r in efetivo if r.get('uf_codigo')}
    ab = {r['uf_codigo']: r for r in abate if r.get('uf_codigo')}

    fora = []
    saida = {}
    for cod, r_ef in ef.items():
        r_ab = ab.get(cod)
        if not r_ab or r_ef['valor'] <= 0:
            continue
        pct = r_ab['valor'] / r_ef['valor'] * 100
        if not (0 < pct <= 200):
            fora.append((r_ef['uf'], round(pct, 1)))
            continue
        saida[cod] = {
            'uf':      r_ef['uf'],
            'efetivo': r_ef['valor'],
            'abate':   r_ab['valor'],
            'desfrute_pct': round(pct, 2),
        }
    if fora:
        logger.warning('[SIDRA] descartadas UF com desfrute implausível: %s', fora)
    return saida


# ── Rede — a parte fina, isolada de propósito ───────────────────────────────
def _url(tabela: str, variavel: str, periodo: str, classificacao: str = '',
         nivel: str = 'n3/all') -> str:
    partes = [BASE, 't', tabela, nivel, 'v', variavel, 'p', periodo]
    url = '/'.join(partes)
    if classificacao:
        url += f'/{classificacao}'
    return url


def baixar(tabela: str, variavel: str, periodo: str, classificacao: str = '',
           nivel: str = 'n3/all') -> list[dict]:
    """
    Busca e normaliza uma série. Devolve [] em falha de rede (não levanta).

    Falha de FORMATO, essa sim, levanta: rede cai e volta, contrato quebrado
    precisa de gente olhando.
    """
    import requests
    url = _url(tabela, variavel, periodo, classificacao, nivel)
    try:
        r = requests.get(url, timeout=TIMEOUT,
                         headers={'Accept': 'application/json'})
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        logger.warning('[SIDRA] falha ao buscar %s: %s', url, e)
        return []
    return parse_valores(payload)
