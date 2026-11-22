"""Módulo de Operações de Barter e Emissão de Minuta de CPR (Cédula de Produto Rural).

Implementa a dinâmica padrão de operações de Barter B2B e estruturação de CPR:
1. Barter: Troca de insumos agrícolas (adubo, sementes, defensivos) por grãos futuros.
2. Análise de Risco de Penhor: Percentual da safra comprometido com a entrega.
3. CPR Digital: Geração da minuta jurídica da Cédula de Produto Rural Física ou Financeira
   em conformidade com a Lei 8.929/1994 e as Leis do Agro (13.986/2020 e 14.421/2022).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Cotações reais de referência (Setembro/2026)
PRAÇAS_REFERENCIA: dict[str, dict[str, Any]] = {
    'SOJA_RONDONOPOLIS_MT': {
        'cultura': 'SOJA',
        'nome': 'Rondonópolis / MT (Mercado Disponível)',
        'preco_saca': 144.00,
        'unidade': 'sc (60kg)',
        'fonte': 'Mercado Físico / Agrural (18/09/2026)',
    },
    'SOJA_PARANAGUA_PR': {
        'cultura': 'SOJA',
        'nome': 'Porto de Paranaguá / PR',
        'preco_saca': 162.00,
        'unidade': 'sc (60kg)',
        'fonte': 'Indicador Porto / Cepea (18/09/2026)',
    },
    'SOJA_CEPEA_PR': {
        'cultura': 'SOJA',
        'nome': 'Paraná — Indicador Cepea/Esalq',
        'preco_saca': 155.18,
        'unidade': 'sc (60kg)',
        'fonte': 'Cepea/Esalq (18/09/2026)',
    },
    'MILHO_CEPEA_B3': {
        'cultura': 'MILHO',
        'nome': 'Indicador Milho Cepea/B3 (Campinas/SP)',
        'preco_saca': 69.29,
        'unidade': 'sc (60kg)',
        'fonte': 'Cepea/B3 (18/09/2026)',
    },
}

RISCO_BAIXO = 'BAIXO'
RISCO_MODERADO = 'MODERADO'
RISCO_ALERTA = 'ALERTA'
RISCO_CRITICO = 'CRITICO'


@dataclass(frozen=True, slots=True)
class OperacaoBarter:
    """Modela a troca de insumos por entrega física de grãos."""
    valor_insumos: float
    preco_saca: float
    produtividade_esperada_ha: float
    area_total_ha: float
    cultura: str = 'SOJA'
    praca_referencia: str = 'SOJA_RONDONOPOLIS_MT'
    unidade: str = 'sc'

    def __post_init__(self):
        if float(self.valor_insumos) <= 0:
            raise ValueError('valor dos insumos deve ser maior que zero')
        if float(self.preco_saca) <= 0:
            raise ValueError('preço da saca deve ser maior que zero')
        if float(self.produtividade_esperada_ha) <= 0:
            raise ValueError('produtividade esperada deve ser maior que zero')
        if float(self.area_total_ha) <= 0:
            raise ValueError('área total deve ser maior que zero')

    @property
    def sacas_a_entregar(self) -> float:
        """Quantidade de sacas de 60kg necessárias para liquidar o pacote de insumos."""
        return round(self.valor_insumos / self.preco_saca, 1)

    @property
    def toneladas_a_entregar(self) -> float:
        """Volume em toneladas métricas (1 saca = 60 kg = 0.06 t)."""
        return round(self.sacas_a_entregar * 0.06, 2)

    @property
    def area_travada_ha(self) -> float:
        """Hectares necessários para produzir as sacas compromissadas."""
        return round(self.sacas_a_entregar / self.produtividade_esperada_ha, 2)

    @property
    def producao_total_esperada_sc(self) -> float:
        """Produção total projetada da área."""
        return round(self.area_total_ha * self.produtividade_esperada_ha, 1)

    @property
    def comprometimento_safra_pct(self) -> float:
        """Percentual da safra comprometido com esta operação de Barter."""
        if self.producao_total_esperada_sc <= 0:
            return 0.0
        return round((self.sacas_a_entregar / self.producao_total_esperada_sc) * 100, 1)

    @property
    def classificacao_risco(self) -> str:
        pct = self.comprometimento_safra_pct
        if pct <= 35.0:
            return RISCO_BAIXO
        if pct <= 50.0:
            return RISCO_MODERADO
        if pct <= 65.0:
            return RISCO_ALERTA
        return RISCO_CRITICO

    @property
    def recomendacao_comite(self) -> str:
        risco = self.classificacao_risco
        pct = self.comprometimento_safra_pct
        if risco == RISCO_BAIXO:
            return f"Operação com excelente margem de segurança ({pct}% da safra). Penhor cedular padrão recomendado."
        if risco == RISCO_MODERADO:
            return f"Nível de comprometimento padrão de mercado ({pct}%). Recomenda-se penhor de primeiro grau sobre a safra."
        if risco == RISCO_ALERTA:
            return f"Atenção: {pct}% da safra empenhada. Exigir garantia adicional (aval ou hipoteca) e seguro agrícola multirrisco."
        return f"Risco crítico: {pct}% da safra comprometida. Alto risco de inadimplência em caso de estresse climático. Não recomendado sem trava de preço e seguro integral."


def calcular_barter(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Calcula os parâmetros de troca (barter) e o nível de risco de penhor."""
    payload = payload or {}
    praca_chave = str(payload.get('praca') or 'SOJA_RONDONOPOLIS_MT').strip().upper()
    praca_info = PRAÇAS_REFERENCIA.get(praca_chave) or PRAÇAS_REFERENCIA['SOJA_RONDONOPOLIS_MT']

    # Preço pode ser o da praça ou customizado
    preco_declarado = payload.get('preco_saca')
    preco = float(preco_declarado) if preco_declarado and float(preco_declarado) > 0 else float(praca_info['preco_saca'])

    operacao = OperacaoBarter(
        valor_insumos=float(payload.get('valor_insumos') or 0.0),
        preco_saca=preco,
        produtividade_esperada_ha=float(payload.get('produtividade_esperada_ha') or 60.0),
        area_total_ha=float(payload.get('area_total_ha') or 1000.0),
        cultura=str(payload.get('cultura') or praca_info['cultura']).strip().upper(),
        praca_referencia=praca_chave,
        unidade='sc',
    )

    return {
        'valido': True,
        'cultura': operacao.cultura,
        'praca': praca_chave,
        'praca_nome': praca_info['nome'],
        'praca_fonte': praca_info['fonte'],
        'valor_insumos': operacao.valor_insumos,
        'preco_saca_referencia': operacao.preco_saca,
        'sacas_a_entregar': operacao.sacas_a_entregar,
        'toneladas_a_entregar': operacao.toneladas_a_entregar,
        'area_total_ha': operacao.area_total_ha,
        'produtividade_esperada_ha': operacao.produtividade_esperada_ha,
        'area_travada_ha': operacao.area_travada_ha,
        'producao_total_esperada_sc': operacao.producao_total_esperada_sc,
        'comprometimento_safra_pct': operacao.comprometimento_safra_pct,
        'classificacao_risco': operacao.classificacao_risco,
        'recomendacao_comite': operacao.recomendacao_comite,
        'pracas_disponiveis': {
            k: {'nome': v['nome'], 'preco_saca': v['preco_saca'], 'cultura': v['cultura'], 'fonte': v['fonte']}
            for k, v in PRAÇAS_REFERENCIA.items()
        },
    }


def gerar_minuta_cpr(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Gera a minuta formal e jurídica de Cédula de Produto Rural (CPR Física).

    Em conformidade com a Lei nº 8.929/1994, alterada pelas Leis nº 13.986/2020 e 14.421/2022.
    """
    barter = calcular_barter(payload.get('barter') or payload)

    emitente = payload.get('emitente') or {}
    credor = payload.get('credor') or {}
    condicoes = payload.get('condicoes') or {}

    nome_emitente = emitente.get('nome') or 'PRODUTOR RURAL EMITENTE'
    doc_emitente = emitente.get('cpf_cnpj') or '000.000.000-00'
    fazenda = emitente.get('fazenda') or 'Fazenda Modelo'
    municipio_uf = emitente.get('municipio_uf') or 'Rondonópolis / MT'
    car_numero = emitente.get('car') or 'MT-0000000-00000000000000000000000000000000'

    nome_credor = credor.get('nome') or 'REVENDA / CREDOR DE INSUMOS LTDA'
    doc_credor = credor.get('cnpj') or '00.000.000/0001-00'

    local_entrega = condicoes.get('local_entrega') or f'Armazém credenciado na região de {municipio_uf}'
    data_limite_entrega = condicoes.get('data_entrega') or '30 de abril de 2027'
    ano_safra = condicoes.get('ano_safra') or '2026/2027'

    # Texto legal da CPR Física
    texto_cpr = f"""================================================================================
                    CÉDULA DE PRODUTO RURAL (CPR FÍSICA)
             Emitida nos termos da Lei nº 8.929/94 e alterações legais
================================================================================

1. CLÁUSULA DA PROMESSA DE ENTREGA
Pelo presente título, o EMITENTE abaixo qualificado promete pura e simplesmente
entregar ao CREDOR a quantidade do produto rural adiante descrita e caracterizada,
nas condições de qualidade, prazo e local estipulados nesta Cédula.

2. QUALIFICAÇÃO DAS PARTES
EMITENTE:
  Nome/Razão Social: {nome_emitente}
  CPF/CNPJ: {doc_emitente}
  Propriedade Rural: {fazenda}
  Localização: {municipio_uf}
  Registro CAR (SICAR): {car_numero}

CREDOR:
  Razão Social: {nome_credor}
  CNPJ: {doc_credor}

3. DESCRIÇÃO E CARACTERIZAÇÃO DO PRODUTO
  Produto: {barter['cultura']} em grãos a granel, Safra {ano_safra}
  Quantidade Total: {barter['sacas_a_entregar']:,.1f} sacas de 60 kg ({barter['toneladas_a_entregar']:,.2f} toneladas métricas)
  Padrão de Qualidade Conab:
    - Umidade máxima: 14,0%
    - Impurezas e matérias estranhas: máximo 1,0%
    - Grãos avariados: máximo 8,0% (ardidos/queimados máx 4,0%)
    - Isento de insetos vivos, odores estranhos e substâncias nocivas.

4. LOCAL E CONDIÇÕES DE ENTREGA
  Local: {local_entrega}
  Data Limite para Entrega: {data_limite_entrega}
  Frete: Por conta do Emitente (FOB fazenda ou CIF armazém, conforme estipulado).

5. GARANTIA CEDULAR — PENHOR DA SAFRA
Em garantia do fiel cumprimento das obrigações assumidas nesta CPR, o EMITENTE
constitui em favor do CREDOR, em PENHOR CEDULAR DE PRIMEIRO GRAU, a totalidade
da safra de {barter['cultura']} a ser colhida em {barter['area_travada_ha']:,.2f} hectares da propriedade {fazenda},
abrangendo os frutos pendentes e colhidos, permanecendo sob a guarda do Emitente
na condição de fiel depositário.

6. LIQUIDAÇÃO E VALOR DE REFERÊNCIA
A presente CPR foi originada a partir do fornecimento de pacote tecnológico de
insumos agrícolas no valor total de R$ {barter['valor_insumos']:,.2f}, com preço
referencial de R$ {barter['preco_saca_referencia']:.2f} por saca ({barter['praca_nome']}).

7. REGISTRO OBRIGATÓRIO
Em estrito cumprimento ao art. 12 da Lei nº 8.929/1994, esta CPR será levada a
registro em entidade registradora autorizada pelo Banco Central do Brasil (B3 ou CERC)
no prazo legal.

Local e Data de Emissão: {municipio_uf}, ____ de ______________ de 2026.


________________________________________       ________________________________________
             EMITENTE                                          CREDOR
  {nome_emitente}                               {nome_credor}
================================================================================
"""

    return {
        'titulo': 'CÉDULA DE PRODUTO RURAL (CPR FÍSICA)',
        'modalidade': 'CPR_FISICA',
        'barter': barter,
        'emitente': {
            'nome': nome_emitente,
            'cpf_cnpj': doc_emitente,
            'fazenda': fazenda,
            'municipio_uf': municipio_uf,
            'car': car_numero,
        },
        'credor': {
            'nome': nome_credor,
            'cnpj': doc_credor,
        },
        'especificacoes': {
            'cultura': barter['cultura'],
            'safra': ano_safra,
            'quantidade_sacas': barter['sacas_a_entregar'],
            'quantidade_toneladas': barter['toneladas_a_entregar'],
            'area_penhor_ha': barter['area_travada_ha'],
            'data_limite_entrega': data_limite_entrega,
            'local_entrega': local_entrega,
        },
        'texto_minuta': texto_cpr.strip(),
    }
