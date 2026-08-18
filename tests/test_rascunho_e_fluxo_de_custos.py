"""Rascunho local e a ordem em que o analista consegue trabalhar.

Dois atritos que faziam abandonar a ferramenta:

1. Nada era salvo. Uma análise completa são mais de 40 campos, e um refresh
   sem querer mandava tudo embora.

2. O desembolso real do produtor morava numa aba travada até a primeira
   classificação. Ou seja: rodar uma análise com os custos padrão só para
   abrir a porta, e depois rodar de novo — a primeira ainda gravando
   histórico se houvesse cliente selecionado.

O que estes testes protegem não é o rascunho existir, é o que ele NÃO guarda.
Verificado ponta a ponta em navegador antes de escrever: campos restaurados
(inclusive a linha de credor, que nasce depois), CPF fora, cotação fora, e o
preço negociado sobrevivendo ao atualizarPrecos() assíncrono.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def _bloco(inicio: str, fim: str = "\n}") -> str:
    i = INDEX.index(inicio)
    return INDEX[i:INDEX.index(fim, i)]


# ── O rascunho existe e é allowlist ──────────────────────────────────────────

def test_o_rascunho_salva_e_restaura():
    for fn in ("function salvarRascunho()", "function restaurarRascunho()",
               "function descartarRascunho()"):
        assert fn in INDEX, fn
    assert "document.addEventListener('input', salvarRascunho, true)" in INDEX
    assert "restaurarRascunho();" in INDEX


def test_a_selecao_e_allowlist_e_nao_salva_tudo():
    """Allowlist para que um campo sensível novo não entre em silêncio."""
    bloco = _bloco("function _rascunhoIds()")
    assert "RASCUNHO_PREFIXOS.some" in bloco
    assert "RASCUNHO_PREFIXOS" in INDEX


def test_o_documento_da_consulta_cadastral_fica_fora():
    """CPF/CNPJ de terceiro não fica no disco de quem consultou.

    O prefixo 'sc-' não pode entrar na allowlist: pegaria sc-documento junto.
    """
    prefixos = re.search(r"const RASCUNHO_PREFIXOS = \[(.*?)\];", INDEX).group(1)
    assert "'sc-'" not in prefixos, 'sc- na allowlist arrastaria o CPF/CNPJ'
    # 's-' não casa com 'sc-documento', que é o que permite guardar s-preco-arr
    assert not "sc-documento".startswith("s-")


def test_o_consentimento_nao_e_restaurado():
    """Consentir é ato novo a cada consulta, não estado guardado."""
    bloco = _bloco("function _rascunhoIds()")
    assert "el.type === 'checkbox'" in bloco


def test_as_cotacoes_ficam_fora_do_rascunho():
    """cot-* carrega dataset.auto, que separa cotação do sistema de preço digitado.

    Restaurar o valor sem o dataset faria a cotação de ontem passar por preço
    digitado e escapar do diferencial de praça — errado e silencioso.
    """
    bloco = _bloco("function _rascunhoIds()")
    assert "el.id.startsWith('cot-')" in bloco


def test_o_preco_negociado_sobrevive_a_cotacao_assincrona():
    """atualizarPrecos() é async e termina DEPOIS do restore.

    Sem a guarda ela apagava o preço do rascunho com o boi do dia. Medido:
    rascunho com 312, cotação 330 — tem que continuar 312.
    """
    assert "if(!_rascunhoDefiniuPreco) usarCotacaoDia();" in INDEX
    assert "_rascunhoDefiniuPreco = 's-preco-arr' in d.campos;" in INDEX


def test_o_rascunho_expira():
    assert "RASCUNHO_VALIDADE_MS" in INDEX
    assert "descartarRascunho(); return;" in INDEX


def test_o_analista_consegue_descartar():
    assert "limparRascunhoEFormulario()" in INDEX
    assert "Descartar e começar do zero" in INDEX


# ── Custos acessíveis antes da primeira análise ──────────────────────────────

def test_a_aba_de_cenarios_nasce_destravada():
    """tab-locked é pointer-events:none — travava de verdade."""
    linha = re.search(r'<button[^>]*id="tab-cen"[^>]*>', INDEX).group(0)
    assert "tab-locked" not in linha, 'Cenários travada esconde o campo de custo'
    assert 'aria-disabled' not in linha


def test_o_resultado_continua_travado_ate_existir_analise():
    """Só Cenários abre antes: Resultado sem dado é tela vazia mesmo."""
    linha = re.search(r'<button[^>]*id="tab-res"[^>]*>', INDEX).group(0)
    assert "tab-locked" in linha


def test_abrir_cenarios_sem_classificar_cai_em_parametros():
    """Sem classificação o Dashboard é uma tela de zeros; o custo está em Parâmetros."""
    assert "if(id==='cenarios' && !lastVals){" in INDEX
    assert "showScSub('params'" in INDEX


def test_a_tela_de_entrada_diz_onde_ficam_os_custos():
    """Destravar não basta: sem o aviso, o analista não sabe que deve ir lá antes."""
    assert "Usa o desembolso padrão (GEP médio) se você não informar o do produtor" in INDEX
    assert "informe em Simular Cenários → Parâmetros" in INDEX
