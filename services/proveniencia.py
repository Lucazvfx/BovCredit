"""
Proveniência dos parâmetros: de onde cada número vem.

O parecer é cheio de números — desfrute de referência, deságio da garantia,
DSCR mínimo, diferencial de praça, natalidade. Todos aparecem iguais na tela:
são só floats. Mas eles não são a mesma coisa.

Um deságio de 35% é **política de crédito** — a instituição escolheu, e pode
mudar. Um desfrute de 21,7% seria **medição** — o IBGE apurou, e não se
discute, se cita. Uma natalidade de 70% é **referência** — alguém escreveu a
partir de bibliografia, e ninguém apurou nesta fazenda. Um custo de
R$ 107,50/cab·mês é **declaração** — o analista digitou.

Confundir os quatro é o que faz um parecer não se sustentar em comitê. Quando
o analista do banco pergunta "de onde vem esse número?", a resposta precisa
estar no próprio parecer, não no código.

COMO USAR

`Parametro` herda de `float`. Isso é deliberado: todo o motor de simulação
continua fazendo aritmética normalmente, sem saber que o número tem etiqueta.

    NATALIDADE = Parametro(70.0, origem=REFERENCIA,
                           fonte='Embrapa/ABCZ — faixa 60–80%')

    NATALIDADE * 2          # 140.0, funciona
    NATALIDADE > 65         # True, funciona
    json.dumps(NATALIDADE)  # 70.0, funciona
    NATALIDADE.fonte        # 'Embrapa/ABCZ — faixa 60–80%'

Trocar referência por medição é trocar o registro. Nenhuma fórmula muda.
"""
from __future__ import annotations

# ── As quatro origens ───────────────────────────────────────────────────────
MEDIDO     = 'medido'      # série apurada por terceiro, com fonte, ano e recorte
REFERENCIA = 'referencia'  # calibração nossa a partir de bibliografia ou ficha
POLITICA   = 'politica'    # escolha da instituição — se discute, não se cita
DECLARADO  = 'declarado'   # informado pelo proponente ou digitado pelo analista

ORIGENS = (MEDIDO, REFERENCIA, POLITICA, DECLARADO)

_ROTULO = {
    MEDIDO:     'Medido',
    REFERENCIA: 'Referência',
    POLITICA:   'Política',
    DECLARADO:  'Declarado',
}

# Peso do argumento em comitê. Medição se cita; política se discute; referência
# se questiona; declaração se confere. A ordem importa para a apresentação.
_PESO = {MEDIDO: 0, REFERENCIA: 1, POLITICA: 2, DECLARADO: 3}

_EXPLICACAO = {
    MEDIDO:     'Série apurada por terceiro. Cita-se a fonte.',
    REFERENCIA: 'Calibração a partir de bibliografia ou ficha. Não foi apurado '
                'nesta fazenda.',
    POLITICA:   'Escolha da instituição, ajustável. Não descreve fato — define '
                'critério.',
    DECLARADO:  'Informado pelo proponente ou digitado pelo analista. Não '
                'verificado.',
}


class Parametro(float):
    """
    Um número que carrega de onde veio.

    Herda de `float` para que a aritmética existente siga funcionando sem
    nenhuma alteração — o motor de simulação nunca precisa saber que existe
    etiqueta.
    """

    __slots__ = ('origem', 'fonte', 'ano', 'uf', 'nota', 'rotulo')

    def __new__(cls, valor, *, origem, fonte='', ano=None, uf=None,
                nota='', rotulo=''):
        if origem not in ORIGENS:
            raise ValueError(
                f'origem inválida: {origem!r}. Esperado um de {ORIGENS}.')
        if origem == MEDIDO and not fonte:
            # Medição sem fonte não é medição — é referência com pretensão.
            raise ValueError('origem "medido" exige `fonte`.')
        obj = super().__new__(cls, valor)
        obj.origem = origem
        obj.fonte  = fonte
        obj.ano    = ano
        obj.uf     = uf
        obj.nota   = nota
        obj.rotulo = rotulo
        return obj

    # A aritmética devolve float puro de propósito: o resultado de uma conta
    # entre parâmetros não herda a proveniência de nenhum deles.

    def __repr__(self):
        return f'Parametro({float(self)}, origem={self.origem!r})'

    def descrever(self) -> str:
        """Uma linha legível com a origem completa."""
        partes = [_ROTULO[self.origem]]
        if self.fonte:
            partes.append(self.fonte)
        recorte = ' · '.join(str(x) for x in (self.uf, self.ano) if x)
        if recorte:
            partes.append(recorte)
        return ' — '.join(partes)

    def para_dict(self) -> dict:
        return {
            'valor':      float(self),
            'origem':     self.origem,
            'origem_rotulo': _ROTULO[self.origem],
            'fonte':      self.fonte,
            'ano':        self.ano,
            'uf':         self.uf,
            'nota':       self.nota,
            'rotulo':     self.rotulo,
            'descricao':  self.descrever(),
        }


def medido(valor, fonte, *, ano=None, uf=None, rotulo='', nota=''):
    return Parametro(valor, origem=MEDIDO, fonte=fonte, ano=ano, uf=uf,
                     rotulo=rotulo, nota=nota)


def referencia(valor, fonte='', *, ano=None, rotulo='', nota=''):
    return Parametro(valor, origem=REFERENCIA, fonte=fonte, ano=ano,
                     rotulo=rotulo, nota=nota)


def politica(valor, fonte='', *, rotulo='', nota=''):
    return Parametro(valor, origem=POLITICA, fonte=fonte, rotulo=rotulo,
                     nota=nota)


def declarado(valor, fonte='', *, rotulo='', nota=''):
    return Parametro(valor, origem=DECLARADO, fonte=fonte, rotulo=rotulo,
                     nota=nota)


def e_parametro(v) -> bool:
    return isinstance(v, Parametro)


def catalogo(*grupos) -> list:
    """
    Reúne os parâmetros usados numa análise para o parecer listar.

    Aceita dicts (usa a chave como rótulo quando o próprio parâmetro não tem)
    e parâmetros soltos. Ignora tudo que não for `Parametro`, então pode
    receber estruturas mistas sem tratamento prévio.

    Ordena por peso do argumento: medição primeiro, declaração por último — é
    a ordem em que o comitê quer ler.
    """
    achados = []

    def _coletar(obj, chave=''):
        if isinstance(obj, Parametro):
            d = obj.para_dict()
            if not d['rotulo']:
                d['rotulo'] = chave
            achados.append(d)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _coletar(v, str(k))
        elif isinstance(obj, (list, tuple, set)):
            for v in obj:
                _coletar(v, chave)

    for g in grupos:
        _coletar(g)

    vistos, unicos = set(), []
    for d in achados:
        marca = (d['rotulo'], d['valor'], d['origem'])
        if marca not in vistos:
            vistos.add(marca)
            unicos.append(d)

    unicos.sort(key=lambda d: (_PESO[d['origem']], d['rotulo']))
    return unicos


def resumo(catalogo_: list) -> dict:
    """Quantos parâmetros de cada origem — o quadro que o comitê lê primeiro."""
    contagem = {o: 0 for o in ORIGENS}
    for d in catalogo_:
        contagem[d['origem']] += 1
    total = sum(contagem.values())
    return {
        'contagem':  contagem,
        'rotulos':   dict(_ROTULO),
        'explicacao': dict(_EXPLICACAO),
        'total':     total,
        'medidos_pct': round(contagem[MEDIDO] / total * 100, 1) if total else 0.0,
    }


def do_modulo(*modulos) -> list:
    """Todo `Parametro` definido no nível de módulo, para o catálogo se montar só.

    POR QUE ISTO EXISTE. `catalogo()` era alimentado por uma lista escrita à mão
    em parecer_credito.py. Toda medição registrada depois dela ficava invisível:
    treze parâmetros medidos existiam em parametros_zootecnicos e o parecer
    publicava CINCO — as quatro do painel do Pantanal e as quatro da cadeia
    reprodutiva de Vieira et al. nunca chegaram ao documento.

    O rodapé de proveniência é o que separa este parecer de uma planilha com
    opinião. Uma medição que não aparece nele é, para o comitê, uma medição que
    não existe — e o defeito era silencioso: nada quebrava, o número só ficava
    menor do que a verdade.

    É a mesma família de defeito das três cópias das faixas de desfrute: duas
    fontes da mesma informação, sincronizadas à mão, e uma fica para trás.

    O nome do atributo vira rótulo quando o parâmetro não trouxe um.
    """
    achados = []
    for m in modulos:
        for nome, valor in vars(m).items():
            if nome.startswith('_'):
                continue
            if isinstance(valor, Parametro):
                achados.append((nome, valor))
            elif isinstance(valor, dict):
                achados.extend((f'{nome}.{k}', v) for k, v in valor.items()
                               if isinstance(v, Parametro))
    return [v if v.rotulo else Parametro(
                float(v), origem=v.origem, fonte=v.fonte, ano=v.ano, uf=v.uf,
                rotulo=nome, nota=v.nota)
            for nome, v in achados]
