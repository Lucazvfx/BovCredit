"""
Parsers de PDF de saldo de rebanho — multi-estado.

Expõe:
  extrair_texto_pdf(path) -> str
  detectar_origem(text)   -> origem (str)  — ver _ORIGENS abaixo
  parsear_idaron(text, pdf_path=None) -> dict   RO
  parsear_indea(text)                 -> dict   MT / GO_DECLARACAO
  parsear_declaracao_idaron(text)     -> dict   RO declaração eletrônica
  parsear_generico(text)              -> dict   MS / MA / TO / PA + fallback

Estados suportados via MAPEAMENTO (Classificação de Rebanho - Fichas.xlsm):
  MT_DECLARACAO  → INDEA    (5 faixas: 0-4m / 5-12m / 13-24m / 25-36m / 36m+)
  GO_DECLARACAO  → INDEA    (mesmo padrão MT)
  GO_IR          → INDEA
  RO_DECLARACAO  → IDARON   (4 faixas: 0-12m / 13-24m / 25-36m / 36m+)
  MS             → GENERICO (4 faixas)
  MA             → GENERICO (4 faixas)
  TO_DECLARACAO  → GENERICO (4 faixas)
  PA_DECLARACAO  → GENERICO (4 faixas)
"""
import os
import re
import subprocess

from services.faixa_0_12 import dividir_0_12

# ─────────────────────────────────────────────
# EXTRAÇÃO DE TEXTO
# ─────────────────────────────────────────────
def extrair_texto_pdf(path: str) -> str:
    """Extrai texto de PDF: pdftotext → pdfplumber → OCR (Tesseract) para PDFs escaneados."""
    # 1. pdftotext
    try:
        result = subprocess.run(
            ['pdftotext', '-layout', path, '-'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2. pdfplumber
    text = ''
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or '') + '\n'
        if text.strip():
            return text
    except Exception as e:
        raise RuntimeError(f'Não foi possível extrair texto do PDF: {e}')

    # 3. OCR com Tesseract (PDF baseado em imagem / escaneado)
    #
    # --psm 6 ("um único bloco uniforme de texto") não é detalhe de ajuste
    # fino: no modo automático (psm 3, o padrão) o Tesseract trata a coluna
    # QUANTIDADE das fichas como região à parte e a descarta. Medido numa
    # ficha real do INDEA escaneada — no padrão saem o cabeçalho, o produtor e
    # o total, mas nenhuma linha de animal, e o parser devolve rebanho zerado
    # com fazenda e CPF corretos. Silenciosamente errado é pior que falhar.
    OCR_CONFIG = '--psm 6'
    try:
        import pytesseract
        import pdfplumber
        tess_win = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(tess_win):
            pytesseract.pytesseract.tesseract_cmd = tess_win
        ocr_text = ''
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                img = page.to_image(resolution=200).original
                try:
                    ocr_text += pytesseract.image_to_string(
                        img, lang='por+eng', config=OCR_CONFIG) + '\n'
                except Exception:
                    ocr_text += pytesseract.image_to_string(
                        img, lang='eng', config=OCR_CONFIG) + '\n'
        if ocr_text.strip():
            return ocr_text
    except Exception:
        pass

    return text

# ─────────────────────────────────────────────
# DETECÇÃO DE ORIGEM
# ─────────────────────────────────────────────
def detectar_origem(text: str) -> str:
    """Detecta agência/estado do documento.

    Retorna um dos valores:
      'DECLARACAO_IDARON' — declaração eletrônica IDARON (RO)
      'IDARON'            — formulário de anotações IDARON (RO)
      'INDEA'             — INDEA-MT ou AGRODEFESA-GO (5 faixas etárias)
      'IAGRO_MS'          — IAGRO Mato Grosso do Sul (4 faixas)
      'ADAPEC_TO'         — ADAPEC Tocantins (4 faixas)
      'AGED_MA'           — AGED Maranhão (4 faixas)
      'ADEPARA_PA'        — ADEPARÁ Pará (4 faixas)
      'GENERICO'          — fallback
    """
    up = text.upper()
    norm = _normalizar(text)

    if ('FAZENDA' in norm and 'SITUA' in norm and 'TOTAL BOVINOS' in norm
            and 'MACHO 0-12' in norm and 'FEMEA 0-12' in norm):
        return 'RESUMO_FAZENDAS'

    # — RO (IDARON) — prioridade máxima pois 'IDARON' é inequívoco
    if 'DECLARAÇÃO Nº' in up and 'IDARON' in up:
        return 'DECLARACAO_IDARON'
    if ('IDARON' in up
            or 'AGÊNCIA DE DEFESA SANITÁRIA AGROSILVOPASTORIL' in up
            or 'AGENCIA DE DEFESA SANITARIA AGROSILVOPASTORIL' in up
            or 'FORMULÁRIO DE ANOTAÇÕES' in up
            or 'FORMULARIO DE ANOTACOES' in up
            or ('RONDÔNIA' in up and ('SALDO' in up or 'REBANHO' in up or 'GTA' in up))):
        return 'IDARON'

    # — MT (INDEA — 5 faixas: 0-4m / 5-12m / 13-24m / 25-36m / 36m+) —
    if ('INDEA' in up
            or 'INSTITUTO DE DEFESA AGROPECUÁRIA' in up
            or 'INSTITUTO DE DEFESA AGROPECUARIA' in up
            or 'SALDO ATUAL DA EXPLORAÇÃO' in up
            or 'SALDO ATUAL DA EXPLORACAO' in up):
        return 'INDEA'

    # — GO Declaração Rebanho via sistema web (4 faixas, 8 colunas M/F) —
    if (re.search(r'UF/Munic[íi]pio:\s*GO/', text, re.I)
            and re.search(r'DECLARA[CÇ][AÃ]O\s+REBANHO', text, re.I)):
        return 'GO_DEC_WEB'

    # — GO (AGRODEFESA — 4 faixas, ficha cadastral, igual a MA) —
    if ('AGRODEFESA' in up
            or 'AGÊNCIA GOIANA DE DEFESA' in up
            or 'AGENCIA GOIANA DE DEFESA' in up):
        return 'AGRODEFESA_GO'

    # — MS (IAGRO — 4 faixas) —
    if ('IAGRO' in up
            or 'AGÊNCIA ESTADUAL DE DEFESA SANITÁRIA ANIMAL E VEGETAL' in up
            or 'AGENCIA ESTADUAL DE DEFESA SANITARIA ANIMAL E VEGETAL' in up
            or ('MATO GROSSO DO SUL' in up and ('REBANHO' in up or 'SALDO' in up))):
        return 'IAGRO_MS'

    # — TO (ADAPEC — 4 faixas) —
    if ('ADAPEC' in up
            or 'AGÊNCIA DE DEFESA AGROPECUÁRIA DO TOCANTINS' in up
            or 'AGENCIA DE DEFESA AGROPECUARIA DO TOCANTINS' in up
            or ('TOCANTINS' in norm and 'DECLARACAO DE DADOS CADASTRAIS' in norm)):
        return 'ADAPEC_TO'

    # — MA (AGED — 4 faixas) —
    if ('AGED' in up
            or 'AGÊNCIA ESTADUAL DE DEFESA AGROPECUÁRIA' in up
            or 'AGENCIA ESTADUAL DE DEFESA AGROPECUARIA' in up
            or ('MARANHÃO' in up and ('REBANHO' in up or 'SALDO' in up))):
        return 'AGED_MA'

    # — PA (ADEPARÁ — 4 faixas) —
    if ('ADEPAR' in up
            or 'AGÊNCIA DE DEFESA AGROPECUÁRIA DO ESTADO DO PARÁ' in up
            or 'AGENCIA DE DEFESA AGROPECUARIA DO ESTADO DO PARA' in up
            or 'SIGEAGRO' in up                          # sistema online PA
            or 'SIGEAGRO.ADEPARA' in up):               # URL do sistema
        return 'ADEPARA_PA'

    return 'GENERICO'


# Origens que usam parser GENERICO (fallback)
ORIGENS_GENERICAS = {'GENERICO'}

# Origens que usam parser INDEA (5 faixas: 0-4m / 5-12m / 13-24m / 25-36m / 36m+)
ORIGENS_INDEA = {'INDEA'}

# ─────────────────────────────────────────────
# HELPERS COMUNS
# ─────────────────────────────────────────────
def _animais_vazios() -> dict:
    return {
        'f00_F': 0, 'f00_M': 0, 'f05_F': 0, 'f05_M': 0,
        'f13_F': 0, 'f13_M': 0, 'f25_F': 0, 'f25_M': 0,
        'fac_F': 0, 'fac_M': 0,
    }

def _para_valores(animais: dict) -> list:
    return [
        animais['f00_F'], animais['f00_M'],
        animais['f05_F'], animais['f05_M'],
        animais['f13_F'], animais['f13_M'],
        animais['f25_F'], animais['f25_M'],
        animais['fac_F'], animais['fac_M'],
    ]

def _sexo_da_linha(up: str):
    if 'FEMEA' in up or 'FÊMEA' in up:
        return 'F'
    if 'MACHO' in up:
        return 'M'
    return None

# ─────────────────────────────────────────────
# PARSER INDEA-MT
# ─────────────────────────────────────────────
def _indea_faixa(up: str):
    if   '00 A 04' in up or '0 A 04' in up or '0 A 4' in up: return 'f00'
    elif '05 A 12' in up or '5 A 12' in up:                  return 'f05'
    elif '13 A 24' in up:                                    return 'f13'
    elif '25 A 36' in up:                                    return 'f25'
    elif 'ACIMA'   in up:                                    return 'fac'
    return None

def _parse_indea_tabelas(pdf_path: str) -> dict:
    """Lê a tabela INDEA por célula via pdfplumber — evita desalinhamento do pdftotext."""
    try:
        import pdfplumber
        animais = _animais_vazios()
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for settings in [
                    {'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'},
                    {'vertical_strategy': 'lines_strict', 'horizontal_strategy': 'lines_strict'},
                    {'vertical_strategy': 'text', 'horizontal_strategy': 'text',
                     'min_words_vertical': 2, 'min_words_horizontal': 1},
                ]:
                    tables = page.extract_tables(settings) or []
                    for tbl in tables:
                        for row in tbl:
                            if not row or len(row) < 3:
                                continue
                            cells = [str(c or '').upper().strip() for c in row]
                            # espera colunas: ..., ESTRATIFICAÇÃO, SEXO, QUANTIDADE
                            # procura a coluna que tem faixa e sexo
                            especie = cells[0] if cells else ''
                            if 'BOVINO' not in especie and not any('BOVINO' in c for c in cells):
                                continue
                            # tenta as 3 últimas colunas como (estratificação, sexo, qtd)
                            for offset in range(len(cells) - 2):
                                faixa = _indea_faixa(cells[offset])
                                sexo  = _sexo_da_linha(cells[offset + 1])
                                if not faixa or not sexo:
                                    continue
                                m_q = re.search(r'(\d+)', cells[offset + 2] if offset + 2 < len(cells) else '')
                                if not m_q:
                                    continue
                                qtd = int(m_q.group(1))
                                if 0 < qtd <= 500_000:
                                    animais[f'{faixa}_{sexo}'] = qtd
                                break
                    if sum(animais.values()) > 0:
                        return animais
        return animais
    except Exception:
        return _animais_vazios()

def _parse_indea_words(pdf_path: str) -> dict:
    """Extração palavra-a-palavra por coordenada Y — fallback robusto quando tabela não extrai."""
    try:
        import pdfplumber
        animais = _animais_vazios()
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words(x_tolerance=4, y_tolerance=4)
                if not words:
                    continue
                # Agrupa palavras por linha (Y arredondado)
                linhas: dict = {}
                for w in words:
                    y = round(w['top'] / 3) * 3
                    linhas.setdefault(y, []).append(w)
                # Cada linha: ordena por X e analisa
                for y in sorted(linhas):
                    ws = sorted(linhas[y], key=lambda w: w['x0'])
                    texto_linha = ' '.join(w['text'].upper() for w in ws)
                    if 'BOVINO' not in texto_linha:
                        continue
                    faixa = _indea_faixa(texto_linha)
                    sexo  = _sexo_da_linha(texto_linha)
                    if not faixa or not sexo:
                        continue
                    # Último número na linha
                    nums = re.findall(r'\b(\d{1,6})\b', texto_linha)
                    if not nums:
                        continue
                    qtd = int(nums[-1])
                    if 0 < qtd <= 500_000:
                        animais[f'{faixa}_{sexo}'] = qtd
        return animais
    except Exception:
        return _animais_vazios()

def parsear_indea(text: str, pdf_path: str = None) -> dict:
    animais = _animais_vazios()
    fazenda = municipio = proprietario = cpf = data_saldo = ''

    m = re.search(r'PROPRIEDADE[:\s]+[\d\-]+\s*[-–]\s*(.+)', text)
    if m:
        fazenda = m.group(1).strip()[:60]

    m = re.search(r'MUNIC[IÍ]PIO[:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s\-]+?)(?:\s{3,}|SIT\.)', text, re.I)
    if m:
        municipio = m.group(1).strip()

    m = re.search(r'(\d{11})\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s]+?)(?:\s{3,}|\n)', text, re.I)
    if m:
        cpf, proprietario = m.group(1), m.group(2).strip()

    m = re.search(r'(\d{2}/\d{2}/\d{4})', text)
    if m:
        data_saldo = m.group(1)

    # 1ª tentativa: tabela pdfplumber (evita desalinhamento de colunas do pdftotext)
    if pdf_path:
        animais = _parse_indea_tabelas(pdf_path)
    # 2ª tentativa: palavras por coordenada Y
    if pdf_path and sum(animais.values()) == 0:
        animais = _parse_indea_words(pdf_path)
    # 3ª tentativa: parsing linha a linha do texto (fallback)
    if sum(animais.values()) == 0:
        for line in text.split('\n'):
            up = line.upper()
            if 'BOVINO' not in up:
                continue
            m_qtd = re.search(r'(\d{1,6})\s*$', line.strip())
            if not m_qtd:
                continue
            qtd = int(m_qtd.group(1))
            if qtd <= 0 or qtd > 500_000:
                continue
            sexo = _sexo_da_linha(up)
            faixa = _indea_faixa(up)
            if not sexo or not faixa:
                continue
            animais[f'{faixa}_{sexo}'] = qtd

    valores = _para_valores(animais)
    return {
        'fazenda': fazenda, 'municipio': municipio,
        'proprietario': proprietario, 'cpf': cpf,
        'data_saldo': data_saldo, 'total': sum(valores),
        'animais': animais, 'valores': valores,
    }

# ─────────────────────────────────────────────
# PARSER IDARON-RO — extração por tabela (formulário de anotações)
# ─────────────────────────────────────────────
_FAIXA_PATS = [
    (r'0\s*[AÀ]\s*0?6\s*(M[EÊ]S)?|ATÉ\s*6|ATE\s*6',           'f00'),
    (r'0?7\s*[AÀ]\s*12\s*(M[EÊ]S)?',                           'f05'),
    (r'0\s*[AÀ]\s*12\s*(M[EÊ]S)?|ATÉ\s*12|ATE\s*12',           'f00_12'),
    (r'13\s*[AÀ]\s*24\s*(M[EÊ]S)?',                            'f13'),
    (r'25\s*[AÀ]\s*36\s*(M[EÊ]S)?',                            'f25'),
    (r'ACIMA|MAIOR\s*DE?\s*36|>\s*36',                         'fac'),
]

def _faixa_de_celula(cell_up: str):
    for pat, faixa in _FAIXA_PATS:
        if re.search(pat, cell_up):
            return faixa
    return None

def _adicionar(animais: dict, faixa: str, sexo: str, qtd: int):
    if faixa == 'f00_12':
        f00, f05 = dividir_0_12(qtd)
        animais[f'f00_{sexo}'] += f00
        animais[f'f05_{sexo}'] += f05
    else:
        animais[f'{faixa}_{sexo}'] += qtd

def _parsear_tabela_bovinos(table) -> dict:
    animais = _animais_vazios()
    if not table or len(table) < 2:
        return animais

    rows = [[str(c or '').upper().strip() for c in row] for row in table]

    faixa_col = {}
    for row in rows:
        for c_idx, cell in enumerate(row):
            f = _faixa_de_celula(cell)
            if f and c_idx not in faixa_col:
                faixa_col[c_idx] = f

    if not faixa_col:
        return animais

    sexo_col = {}
    for row in rows:
        for c_idx, cell in enumerate(row):
            if cell in ('F', 'FÊMEA', 'FEMEA') or re.match(r'^F[EÊ]MEA$', cell):
                sexo_col[c_idx] = 'F'
            elif cell in ('M', 'MACHO') or re.match(r'^MACHO$', cell):
                sexo_col[c_idx] = 'M'

    col_map = {}
    if sexo_col:
        for c_idx, sexo in sexo_col.items():
            candidatos = {fc: f for fc, f in faixa_col.items() if abs(fc - c_idx) <= 4}
            if candidatos:
                nearest = min(candidatos, key=lambda x: abs(x - c_idx))
                col_map[c_idx] = (candidatos[nearest], sexo)
    else:
        sorted_f = sorted(faixa_col.items())
        for i, (c_idx, faixa) in enumerate(sorted_f):
            col_map[c_idx] = (faixa, 'F' if i % 2 == 0 else 'M')

    for row in rows:
        for c_idx, cell in enumerate(row):
            if c_idx not in col_map:
                continue
            if not re.match(r'^\d+$', cell):
                continue
            qtd = int(cell)
            if qtd <= 0 or qtd > 500_000:
                continue
            faixa, sexo = col_map[c_idx]
            _adicionar(animais, faixa, sexo, qtd)

    return animais

def _parse_idaron_tabelas(pdf_path: str) -> dict:
    try:
        import pdfplumber
        animais = _animais_vazios()

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for settings in [
                    {'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'},
                    {'vertical_strategy': 'lines_strict', 'horizontal_strategy': 'lines_strict'},
                    {'vertical_strategy': 'text', 'horizontal_strategy': 'text',
                     'min_words_vertical': 3, 'min_words_horizontal': 1},
                ]:
                    try:
                        tables = page.extract_tables(settings)
                    except Exception:
                        continue
                    for tbl in (tables or []):
                        result = _parsear_tabela_bovinos(tbl)
                        if sum(result.values()) > 0:
                            for k, v in result.items():
                                if v > 0:
                                    animais[k] = max(animais[k], v)
                    if sum(animais.values()) > 0:
                        break
        return animais
    except Exception:
        return _animais_vazios()

def _parse_idaron_words(pdf_path: str) -> dict:
    try:
        import pdfplumber
        animais = _animais_vazios()

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words(x_tolerance=5, y_tolerance=5)
                if not words:
                    continue

                linhas: dict[float, list] = {}
                for w in words:
                    y = round(w['top'] / 4) * 4
                    linhas.setdefault(y, []).append(w)

                faixa_x: dict[float, str] = {}
                for y, ws in linhas.items():
                    texto = ' '.join(w['text'].upper() for w in ws)
                    f = _faixa_de_celula(texto)
                    if f:
                        x_mid = sum((w['x0'] + w['x1']) / 2 for w in ws) / len(ws)
                        faixa_x[x_mid] = f

                if not faixa_x:
                    continue

                col_map: dict[float, tuple] = {}
                for y, ws in linhas.items():
                    for w in ws:
                        t = w['text'].upper()
                        if t in ('F', 'FÊMEA', 'FEMEA', 'M', 'MACHO'):
                            sexo = 'F' if t in ('F', 'FÊMEA', 'FEMEA') else 'M'
                            x_mid = (w['x0'] + w['x1']) / 2
                            nearest = min(faixa_x, key=lambda x: abs(x - x_mid))
                            if abs(nearest - x_mid) < 60:
                                col_map[x_mid] = (faixa_x[nearest], sexo)

                if not col_map:
                    for i, (xf, faixa) in enumerate(sorted(faixa_x.items())):
                        col_map[xf] = (faixa, 'F' if i % 2 == 0 else 'M')

                for y, ws in linhas.items():
                    for w in ws:
                        if not re.match(r'^\d+$', w['text']):
                            continue
                        qtd = int(w['text'])
                        if qtd <= 0 or qtd > 500_000:
                            continue
                        x_mid = (w['x0'] + w['x1']) / 2
                        nearest = min(col_map, key=lambda x: abs(x - x_mid))
                        if abs(nearest - x_mid) < 40:
                            faixa, sexo = col_map[nearest]
                            _adicionar(animais, faixa, sexo, qtd)

        return animais
    except Exception:
        return _animais_vazios()

def _parse_idaron_linhas(text: str) -> dict:
    animais = _animais_vazios()

    for line in text.split('\n'):
        up = line.upper()
        if 'BOVINO' not in up:
            continue
        m_qtd = re.search(r'(\d{1,6})\s*$', line.strip())
        if not m_qtd:
            continue
        qtd = int(m_qtd.group(1))
        if qtd <= 0 or qtd > 500_000:
            continue
        sexo = _sexo_da_linha(up)
        if not sexo:
            continue

        if re.search(r'0\s*A\s*12', up) or 'ATÉ 12' in up or 'ATE 12' in up:
            f00, f05 = dividir_0_12(qtd)
            animais[f'f00_{sexo}'] += f00
            animais[f'f05_{sexo}'] += f05
        elif re.search(r'0\s*A\s*0?6', up) or re.search(r'ATÉ\s*6', up, re.I):
            animais[f'f00_{sexo}'] += qtd
        elif re.search(r'0?7\s*A\s*12', up):
            animais[f'f05_{sexo}'] += qtd
        elif re.search(r'0?0\s*A\s*0?4', up):
            animais[f'f00_{sexo}'] = qtd
        elif re.search(r'0?5\s*A\s*12', up):
            animais[f'f05_{sexo}'] = qtd
        elif '13 A 24' in up:
            animais[f'f13_{sexo}'] = qtd
        elif '25 A 36' in up:
            animais[f'f25_{sexo}'] = qtd
        elif 'ACIMA' in up:
            animais[f'fac_{sexo}'] = qtd

    # Mapeamento conforme Excel MAPEAMENTO: Desmama=13-24m, Bezerra/Bezerro=0-12m,
    # Garrote=25-36m (não 13-24m!). DESMAMA vem ANTES de BEZERRA/BEZERRO.
    _categorias = [
        (['DESMAMA'],              'f13',    None),  # Bezerra/Bezerro Desmama 13-24m
        (['BEZERRA', 'BEZERRO'],   'f00_12', None),  # 0-12m → split 50/50 em f00+f05
        (['GARROTA', 'GARROTE'],   'f25',    None),  # Garrote 25-36m
        (['NOVILHA', 'NOVILHO'],   'f25',    None),  # Novilha 25-36m
        (['VACA'],                 'fac',    'F'),
        (['TOURO', 'BOI', 'BOIS'], 'fac',    'M'),
    ]
    for line in text.split('\n'):
        up = line.upper()
        if 'BOVINO' not in up:
            continue
        m_qtd = re.search(r'(\d{1,6})\s*$', line.strip())
        if not m_qtd:
            continue
        qtd = int(m_qtd.group(1))
        if qtd <= 0 or qtd > 500_000:
            continue
        for palavras, faixa, sexo_fixo in _categorias:
            if any(p in up for p in palavras):
                sexo = sexo_fixo or _sexo_da_linha(up)
                if sexo:
                    if faixa == 'f00_12':
                        if animais[f'f00_{sexo}'] == 0 and animais[f'f05_{sexo}'] == 0:
                            f00, f05 = dividir_0_12(qtd)
                            animais[f'f00_{sexo}'] += f00
                            animais[f'f05_{sexo}'] += f05
                    elif animais[f'{faixa}_{sexo}'] == 0:
                        animais[f'{faixa}_{sexo}'] = qtd
                break

    return animais

# ─────────────────────────────────────────────
# PARSER IDARON-RO — orquestrador
# ─────────────────────────────────────────────
def parsear_idaron(text: str, pdf_path: str = None) -> dict:
    fazenda = municipio = proprietario = cpf = data_saldo = ie = ''

    m = re.search(r'\bI\.?E\.?\b[:\s]+([A-Z0-9\.\-\/]+)', text, re.I)
    if m:
        ie = m.group(1).strip()

    for pat in [
        r'NOME\s+DA\s+PROPRIEDADE[:\s]+(.+)',
        r'PROPRIEDADE[:\s]+(.+)',
        r'ESTABELECIMENTO[:\s]+(.+)',
        r'FAZENDA[:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s\.\-]+)',
    ]:
        m = re.search(pat, text, re.I)
        if m:
            fazenda = m.group(1).strip()[:60]
            break

    m = re.search(
        r'MUNIC[IÍ]PIO[:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s\-]+?(?:/\s*RO)?)(?:\s{2,}|\n|$)',
        text, re.I
    )
    if m:
        municipio = m.group(1).strip()

    m = re.search(
        r'(?:CPF|PRODUTOR)[:\s/]*'
        r'(\d{3}\.?\d{3}\.?\d{3}[\-\.]?\d{2})'
        r'[:\s/]*([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s]+?)(?:\s{2,}|\n)',
        text, re.I
    )
    if not m:
        m = re.search(r'(\d{11})\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s]+?)(?:\s{3,}|\n)', text, re.I)
    if m:
        cpf = re.sub(r'[^\d]', '', m.group(1))
        proprietario = m.group(2).strip()

    m = re.search(r'(\d{2}/\d{2}/\d{4})', text)
    if m:
        data_saldo = m.group(1)

    animais = _animais_vazios()

    if pdf_path:
        animais = _parse_idaron_tabelas(pdf_path)

    if pdf_path and sum(animais.values()) == 0:
        animais = _parse_idaron_words(pdf_path)

    if sum(animais.values()) == 0:
        animais = _parse_idaron_linhas(text)

    valores = _para_valores(animais)
    return {
        'fazenda': fazenda, 'municipio': municipio,
        'proprietario': proprietario, 'cpf': cpf, 'ie': ie,
        'data_saldo': data_saldo, 'total': sum(valores),
        'animais': animais, 'valores': valores,
    }

# ─────────────────────────────────────────────
# PARSER DECLARAÇÃO IDARON (emitida eletronicamente)
# ─────────────────────────────────────────────
def parsear_declaracao_idaron(text: str) -> dict:
    """
    Parser para a Declaração IDARON com tabela horizontal:
    0 A 6 MESES  7 A 12 MESES  ... TOTAL
    M F M F ... M F
    0 0 88 0 316 ... 404 13
    """
    animais = _animais_vazios()
    fazenda = municipio = proprietario = cpf = data_saldo = ''

    # Metadados
    m = re.search(r'FAZENDA\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s\.\-]+)', text, re.I)
    if m:
        fazenda = m.group(1).strip()[:60]
    else:
        m = re.search(r'endereço:\s*([^.\n]+)', text, re.I)
        if m:
            fazenda = m.group(1).strip()[:60]

    m = re.search(r'município\s+de\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s\-]+?)(?:\s*\-|\n)', text, re.I)
    if m:
        municipio = m.group(1).strip()

    m = re.search(r'CPF[:\s]*(\d{11})\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s]+?)(?:\n|$)', text, re.I)
    if m:
        cpf = m.group(1)
        proprietario = m.group(2).strip()

    m = re.search(r'Emitido em:\s*(\d{2}/\d{2}/\d{4})', text)
    if m:
        data_saldo = m.group(1)

    # Extração dos 10 números da tabela
    # Padrão: captura 10 números após a sequência "M F M F M F M F M F"
    padrao = r'M\s+F\s+M\s+F\s+M\s+F\s+M\s+F\s+M\s+F\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)'
    match = re.search(padrao, text)
    if match:
        valores = [int(g) for g in match.groups()]
        # Ordem: f00_M, f00_F, f05_M, f05_F, f13_M, f13_F, f25_M, f25_F, fac_M, fac_F
        animais['f00_M'] = valores[0]
        animais['f00_F'] = valores[1]
        animais['f05_M'] = valores[2]
        animais['f05_F'] = valores[3]
        animais['f13_M'] = valores[4]
        animais['f13_F'] = valores[5]
        animais['f25_M'] = valores[6]
        animais['f25_F'] = valores[7]
        animais['fac_M'] = valores[8]
        animais['fac_F'] = valores[9]

    # Fallback: captura uma sequência de 12 números (10 valores + 2 totais)
    if sum(animais.values()) == 0:
        bloco = re.search(r'(\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+)', text)
        if bloco:
            nums = list(map(int, bloco.group(1).split()))
            if len(nums) == 12:
                animais['f00_M'] = nums[0]
                animais['f00_F'] = nums[1]
                animais['f05_M'] = nums[2]
                animais['f05_F'] = nums[3]
                animais['f13_M'] = nums[4]
                animais['f13_F'] = nums[5]
                animais['f25_M'] = nums[6]
                animais['f25_F'] = nums[7]
                animais['fac_M'] = nums[8]
                animais['fac_F'] = nums[9]

    valores_lista = _para_valores(animais)
    return {
        'fazenda': fazenda,
        'municipio': municipio,
        'proprietario': proprietario,
        'cpf': cpf,
        'ie': '',
        'data_saldo': data_saldo,
        'total': sum(valores_lista),
        'animais': animais,
        'valores': valores_lista,
    }

# ─────────────────────────────────────────────
# PARSER GO — Declaração Rebanho sistema web
# ─────────────────────────────────────────────
def _dividir_faixa_0_12(total: int) -> tuple[int, int]:
    primeiro = total // 2
    return primeiro, total - primeiro


def _dividir_go_0_12(text: str, sexo: str) -> tuple[int, int]:
    """Obtém 0-4 e 5-12 pela tabela mensal da declaração GO."""
    inicio = text.upper().find('IDADE TOTAL')
    if inicio < 0:
        return 0, 0
    linhas = []
    for linha in text[inicio:].splitlines():
        if linha.strip().upper().startswith('TOTAL'):
            break
        nums = re.findall(r'(?:AT[EÉ] 1|\d+)\s+M[EÊ]S(?:ES)?\s+(\d+)', linha, re.I)
        if len(nums) >= 2:
            linhas.append([int(nums[0]), int(nums[1])])
    if len(linhas) < 13:
        return 0, 0
    indice = 0 if sexo == 'M' else 1
    valores = [linha[indice] for linha in linhas[:13]]
    return sum(valores[:5]), sum(valores[5:13])


def parsear_go_declaracao_web(text: str) -> dict:
    """
    Parser para Declaração de Rebanho GO emitida pelo sistema web AGRODEFESA.

    Tabela na seção 'DECLARAÇÃO REBANHO' → linha 'Existentes' com 8 colunas:
    M 0-12m | F 0-12m | M 13-24m | F 13-24m | M 25-36m | F 25-36m | M 36m+ | F 36m+
    """
    animais = _animais_vazios()
    fazenda = municipio = proprietario = cpf = data_saldo = ''

    # Fazenda e produtor: "Nome: FAZENDA X   ...   Nome: PRODUTOR Y"
    nomes = re.findall(
        r'Nome:\s*([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s\.\-]*?)(?=\s{3,}|Nome:|CPF|\n)',
        text, re.I
    )
    if len(nomes) >= 1:
        fazenda = nomes[0].strip()[:60]
    if len(nomes) >= 2:
        proprietario = nomes[1].strip()[:60]

    m = re.search(r'CPF/CNPJ:\s*([\d]{11,14})', text, re.I)
    if m:
        cpf = m.group(1).strip()

    m = re.search(r'UF/Munic[íi]pio:\s*GO/([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s\-]+?)(?:\s{2,}|\n|$)', text, re.I)
    if m:
        municipio = m.group(1).strip()

    m = re.search(r'Data:\s*(\d{2}/\d{2}/\d{4})', text)
    if m:
        data_saldo = m.group(1)

    # Extrai linha "Existentes" da seção "DECLARAÇÃO REBANHO" (não da seção "MORTES")
    secao_m = re.search(r'DECLARAÇÃO REBANHO', text, re.I)
    secao = text[secao_m.end():] if secao_m else text
    ex_linha = re.search(r'EXISTENTES\s+([^\n]+)', secao, re.I)
    if ex_linha:
        nums = [int(n) for n in re.findall(r'\d+', ex_linha.group(1))]
        # A Ãºltima coluna Ã© o total da linha, nÃ£o uma faixa etÃ¡ria.
        if len(nums) >= 9:
            nums = nums[:8]
        if len(nums) >= 8:
            m0_4, m5_12 = _dividir_go_0_12(text, 'M')
            f0_4, f5_12 = _dividir_go_0_12(text, 'F')
            if m0_4 + m5_12 == 0:
                m0_4, m5_12 = _dividir_faixa_0_12(nums[0])
            if f0_4 + f5_12 == 0:
                f0_4, f5_12 = _dividir_faixa_0_12(nums[1])
            animais.update({
                'f00_M': m0_4, 'f05_M': m5_12,
                'f00_F': f0_4, 'f05_F': f5_12,
                'f13_M': nums[2], 'f13_F': nums[3],
                'f25_M': nums[4], 'f25_F': nums[5],
                'fac_M': nums[6], 'fac_F': nums[7],
            })

    return _resultado({
        'fazenda': fazenda,
        'municipio': municipio,
        'proprietario': proprietario,
        'cpf': cpf,
        'data_saldo': data_saldo,
    }, animais)


# ─────────────────────────────────────────────
# PARSER GENÉRICO (fallback robusto)
# ─────────────────────────────────────────────
_FAIXA_PATS_GENERICO = [
    (re.compile(r'\b(?:0?0\s*[aà\-]\s*0?6|at[ée]\s*0?6)(?:\s*m[eê]s(?:es)?)?\b', re.I), 'f00'),
    (re.compile(r'\b0?7\s*[aà\-]\s*12(?:\s*m[eê]s(?:es)?)?\b', re.I),               'f05'),
    (re.compile(r'\b0?0\s*[aà\-]\s*0?4(?:\s*m[eê]s(?:es)?)?\b', re.I),               'f00'),
    (re.compile(r'\b0?5\s*[aà\-]\s*12(?:\s*m[eê]s(?:es)?)?\b', re.I),                'f05'),
    (re.compile(r'\b(?:0?0\s*[aà\-]\s*12|at[ée]\s*12)(?:\s*m[eê]s(?:es)?)?\b', re.I), 'f00_12'),
    (re.compile(r'\b13\s*[aà\-]\s*24(?:\s*m[eê]s(?:es)?)?\b', re.I),                 'f13'),
    (re.compile(r'\b25\s*[aà\-]\s*36(?:\s*m[eê]s(?:es)?)?\b', re.I),                 'f25'),
    (re.compile(r'(?:\b(?:acima(?:\s*de)?|maior\s*(?:que|de))|>)\s*36\b', re.I),     'fac'),
]

def _faixa_generica(texto: str):
    for pat, faixa in _FAIXA_PATS_GENERICO:
        if pat.search(texto):
            return faixa
    return None

_CATEGORIAS_ZOOTECNICAS = [
    (re.compile(r'\bbezerr([ao])s?\b', re.I),       'f00',  None),
    (re.compile(r'\bgarrot([ao])s?\b', re.I),       'f13',  None),
    (re.compile(r'\bnovilh([ao])s?\b', re.I),       'f25',  None),
    (re.compile(r'\bvacas?\b',         re.I),       'fac',  'F'),
    (re.compile(r'\b(?:touros?|boi(?:s)?)\b', re.I), 'fac', 'M'),
]

def _categoria_zootecnica(up: str):
    """
    Retorna (faixa, sexo) para uma linha com nome de categoria zootécnica.
    sexo pode ser 'F', 'M' ou 'AMBOS'.

    Regras de inferência pela terminação da palavra:
      - "...A"  (novilha)   -> F (singular feminino)
      - "...AS" (novilhas)  -> F (plural feminino, inequívoco)
      - "...O"  (novilho)   -> M (singular masculino)
      - "...OS" (novilhos)  -> AMBOS — em português "novilhos"/"bezerros" no
        plural é comumente usado tanto como "só machos" quanto como termo
        genérico do rebanho jovem sem distinção de sexo. Sem uma coluna
        explícita de Fêmea/Macho, a leitura mais segura é dividir 50/50
        (mesma lógica já usada para faixas etárias mistas).
    """
    for pat, faixa, sexo_fixo in _CATEGORIAS_ZOOTECNICAS:
        m = pat.search(up)
        if not m:
            continue
        sexo = sexo_fixo
        if sexo is None and m.groups():
            letra = m.group(1).upper()
            plural = m.group(0).upper().endswith('S')
            if letra == 'A':
                sexo = 'F'                  # "...a" ou "...as" -> sempre feminino
            else:
                sexo = 'AMBOS' if plural else 'M'   # "...os" ambíguo; "...o" -> masculino
        return faixa, sexo
    return None, None

def parsear_resumo_fazendas(text: str, pdf_path: str = None) -> dict:
    """Lê o resumo consolidado com uma linha por fazenda.

    O formato distribui as oito faixas em duas páginas: a primeira traz
    nome, município, situação e três colunas; a segunda traz as cinco colunas
    restantes na mesma ordem das fazendas.
    """
    linhas = [linha.strip() for linha in text.splitlines() if linha.strip()]
    prefixos = []
    for linha in linhas:
        m = re.match(
            r'^(.*?)\s+(ATIVO|INATIVO)\s+'
            r'(\d+)\s+(\d+)\s+(\d+)\s*$', linha, re.I)
        if m:
            prefixos.append({
                'prefixo': m.group(1).strip(),
                'situacao': m.group(2).upper(),
                'm0': int(m.group(3)), 'f0': int(m.group(4)),
                'm13': int(m.group(5)),
            })

    # Descobre municípios compostos pela repetição dos sufixos nas linhas.
    sufixos = {}
    for item in prefixos:
        palavras = item['prefixo'].split()
        for tamanho in (3, 2, 1):
            if len(palavras) >= tamanho:
                sufixo = ' '.join(palavras[-tamanho:])
                sufixos[sufixo] = sufixos.get(sufixo, 0) + 1
    municipios_repetidos = [s for s, n in sufixos.items() if n >= 2]
    municipio_padrao = max(municipios_repetidos, key=len) if municipios_repetidos else ''
    linhas_fazendas = []
    for item in prefixos:
        prefixo = item.pop('prefixo')
        municipio = municipio_padrao if prefixo.upper().endswith(municipio_padrao.upper()) else prefixo.split()[-1]
        nome = prefixo[:-len(municipio)].strip() if municipio else prefixo
        linhas_fazendas.append({**item, 'fazenda': nome, 'municipio': municipio})

    continuacoes = []
    for linha in linhas:
        nums = re.findall(r'\d+', linha)
        if not re.fullmatch(r'[\d\s]+', linha):
            continue
        if len(nums) >= 6 and not re.search(r'FAZENDA|MUNIC[IÍ]PIO|SITUA', linha, re.I):
            continuacoes.append([int(n) for n in nums])

    fazendas = []
    for base, cont in zip(linhas_fazendas, continuacoes):
        animais = _animais_vazios()
        _adicionar(animais, 'f00_12', 'M', base['m0'])
        _adicionar(animais, 'f00_12', 'F', base['f0'])
        _adicionar(animais, 'f13', 'M', base['m13'])
        _adicionar(animais, 'f13', 'F', cont[0])
        _adicionar(animais, 'f25', 'M', cont[1])
        _adicionar(animais, 'f25', 'F', cont[2])
        _adicionar(animais, 'fac', 'M', cont[3])
        _adicionar(animais, 'fac', 'F', cont[4])
        item = _resultado({
            'fazenda': base['fazenda'], 'municipio': base['municipio'],
            'situacao': base['situacao'], 'proprietario': '', 'cpf': '',
            'ie': '', 'data_saldo': '',
        }, animais)
        item['total_bovinos_documento'] = cont[5]
        fazendas.append(item)

    agregado = _animais_vazios()
    for fazenda in fazendas:
        for chave, valor in fazenda['animais'].items():
            agregado[chave] += valor
    resultado = _resultado({
        'fazenda': f'{len(fazendas)} fazendas', 'municipio': '',
        'proprietario': '', 'cpf': '', 'ie': '', 'data_saldo': '',
    }, agregado)
    resultado['fazendas'] = fazendas
    resultado['total_bovinos_documento'] = sum(
        f['total_bovinos_documento'] for f in fazendas)
    return resultado


def parsear_generico(text: str) -> dict:
    animais = _animais_vazios()
    fazenda = municipio = proprietario = cpf = data_saldo = ''

    # 1. Etiqueta explícita com ":" — "Propriedade: FAZENDA X" / "FAZENDA: X"
    for pat in [
        r'(?:NOME\s+DA\s+)?(?:PROPRIEDADE|FAZENDA|ESTABELECIMENTO):\s*(.+)',
    ]:
        m = re.search(pat, text, re.I)
        if m:
            fazenda = m.group(1).strip().splitlines()[0][:60]
            break

    # 2. Fallback: "FAZENDA NOME" em linha isolada (sem rótulo)
    if not fazenda:
        m = re.search(r'(?m)^\s*(FAZENDA\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s]+?)\s*$',
                      text, re.I)
        if m:
            fazenda = m.group(1).strip()[:60]

    # 3. Fallback: "— Fazenda NOME" ou "/ Fazenda NOME" em qualquer posição da linha
    if not fazenda:
        m = re.search(r'[—\-/]\s*FAZENDA\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s]+?)(?:\s*$|\s{2,})',
                      text, re.I | re.M)
        if m:
            fazenda = m.group(1).strip()[:60]

    m = re.search(r'MUNIC[IÍ]PIO[:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s\-/]+?)(?:\s{2,}|\n|$)', text, re.I)
    if m:
        municipio = m.group(1).strip()[:60]

    m = re.search(r'\b(\d{3}\.?\d{3}\.?\d{3}[\-\.]?\d{2}|\d{11})\b', text)
    if m:
        cpf = re.sub(r'[^\d]', '', m.group(1))

    m = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', text)
    if m:
        data_saldo = m.group(1)

    for line in text.split('\n'):
        bruto = line.strip()
        if not bruto:
            continue
        m_qtd = re.search(r'(\d{1,6})\s*$', bruto)
        if not m_qtd:
            continue
        qtd = int(m_qtd.group(1))
        if qtd <= 0 or qtd > 500_000:
            continue

        up = bruto.upper()
        sexo = _sexo_da_linha(up)

        faixa = _faixa_generica(up)
        if not faixa or not sexo:
            cat_faixa, cat_sexo = _categoria_zootecnica(up)
            if not faixa:
                faixa = cat_faixa
            if not sexo:
                sexo = cat_sexo

        if not faixa or not sexo:
            continue

        if sexo == 'AMBOS':
            metade = qtd // 2
            _adicionar(animais, faixa, 'F', metade)
            _adicionar(animais, faixa, 'M', qtd - metade)
        else:
            _adicionar(animais, faixa, sexo, qtd)

    valores = _para_valores(animais)
    return {
        'fazenda': fazenda, 'municipio': municipio,
        'proprietario': proprietario, 'cpf': cpf, 'ie': '',
        'data_saldo': data_saldo, 'total': sum(valores),
        'animais': animais, 'valores': valores,
    }

# ─────────────────────────────────────────────────────────────
# HELPERS COMUNS AOS NOVOS PARSERS
# ─────────────────────────────────────────────────────────────

def _normalizar(text: str) -> str:
    """Upper + remove acentos (equivalente ao UCase + Replace do VBA)."""
    t = text.upper()
    for src, dst in [
        ('Ã','A'),('Â','A'),('Á','A'),('À','A'),
        ('Ê','E'),('É','E'),('È','E'),
        ('Î','I'),('Í','I'),
        ('Ô','O'),('Ó','O'),('Õ','O'),
        ('Û','U'),('Ú','U'),
        ('Ç','C'),('Ñ','N'),
    ]:
        t = t.replace(src, dst)
    return t


def _meta_basica(text: str) -> dict:
    fazenda = municipio = proprietario = cpf = data_saldo = ''
    # Prioriza "FAZENDA:" e "ESTABELECIMENTO:" antes de "PROPRIEDADE:" para
    # evitar capturar "RURAL" de "FICHA SANITARIA PROPRIEDADE RURAL"
    for pat in [
        r'(?:NOME\s+DA\s+)?(?:FAZENDA|ESTABELECIMENTO)[:\s]+(.+)',
        r'PROPRIEDADE:\s*(.+)',   # requer ":" para não casar "PROPRIEDADE RURAL"
    ]:
        m = re.search(pat, text, re.I)
        if m:
            fazenda = m.group(1).strip().splitlines()[0][:60]
            break
    m = re.search(r'MUNIC[IÍ]PIO[:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s\-/]+?)(?:\s{2,}|\n|$)', text, re.I)
    if m:
        municipio = m.group(1).strip()[:60]
    # Proprietario: NOME - CPF  (padrão RAC / SIGEAGRO)
    m = re.search(r'Propriet[aá]rio[:\s]+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ\s]+?)\s*[-–]\s*[\d]',
                  text, re.I)
    if m:
        proprietario = m.group(1).strip()[:80]
    m = re.search(r'\b(\d{3}\.?\d{3}\.?\d{3}[\-\.]\d{2}|\d{11})\b', text)
    if m:
        cpf = re.sub(r'[^\d]', '', m.group(1))
    m = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', text)
    if m:
        data_saldo = m.group(1)
    meta = {'fazenda': fazenda, 'municipio': municipio, 'proprietario': proprietario,
            'cpf': cpf, 'ie': '', 'data_saldo': data_saldo}
    # Fase e sistema são comuns a todos os modelos PA
    up = text.upper()
    for fase in ('CICLO COMPLETO', 'ENGORDA', 'RECRIA', 'CRIA'):
        if fase in up:
            meta['fase'] = fase
            break
    for sist in ('CONFINAMENTO', 'PASTO'):
        if sist in up:
            meta['sistema'] = sist
            break
    return meta


def _categorias_comerciais(animais: dict) -> dict:
    """Converte faixas etárias → categorias comerciais (nomenclatura do mercado)."""
    return {
        'bezerra':         animais['f00_F'] + animais['f05_F'],
        'bezerra_desmama': animais['f13_F'],
        'novilha':         animais['f25_F'],
        'vaca':            animais['fac_F'],
        'bezerro':         animais['f00_M'] + animais['f05_M'],
        'bezerro_desmama': animais['f13_M'],
        'garrote':         animais['f25_M'],
        'boi_gordo':       animais['fac_M'],
    }


def _resultado(meta: dict, animais: dict) -> dict:
    valores = _para_valores(animais)
    return {**meta, 'total': sum(valores), 'animais': animais, 'valores': valores,
            'categorias': _categorias_comerciais(animais)}


def _numeros_puros(bloco: str, n: int) -> list:
    """
    Igual a BuscarNumerosMA / BuscarNumerosBovinosGO:
    Extrai os primeiros N inteiros de linhas que contêm apenas dígitos.
    """
    nums = []
    for linha in bloco.split('\n'):
        t = linha.strip()
        if t and re.match(r'^\d+$', t):
            nums.append(int(t))
            if len(nums) >= n:
                break
    return nums


# Mapeamento 8 valores: M0-12, F0-12, M13-24, F13-24, M25-36, F25-36, M36+, F36+
_MAP_8 = [
    ('f00_12', 'M'), ('f00_12', 'F'),
    ('f13',    'M'), ('f13',    'F'),
    ('f25',    'M'), ('f25',    'F'),
    ('fac',    'M'), ('fac',    'F'),
]

def _aplicar_mapa8(animais: dict, nums: list) -> None:
    for i, (faixa, sexo) in enumerate(_MAP_8):
        if i < len(nums) and nums[i] > 0:
            _adicionar(animais, faixa, sexo, nums[i])


# ─────────────────────────────────────────────────────────────
# PARSER MS — IAGRO (modLeitorMS.bas)
# ─────────────────────────────────────────────────────────────

def parsear_iagro_ms(text: str) -> dict:
    """
    Idêntico ao modLeitorMS.bas:
    Para FÊMEA e MACHO: localiza bloco, busca cada faixa etária,
    retorna o 3º número após a faixa (PegarSaldoTotal).
    """
    animais = _animais_vazios()

    def _pegar_saldo_total(trecho: str) -> int:
        """VBA PegarSaldoTotal: retorna o 3º grupo de dígitos consecutivos."""
        numero = ''
        contador = 0
        for c in trecho:
            if c.isdigit():
                numero += c
            else:
                if numero:
                    contador += 1
                    if contador == 3:
                        return int(numero)
                    numero = ''
        return 0

    FAIXAS_MS = [
        ("0 A 12 MESES",      'f00_12'),
        ("13 A 24 MESES",     'f13'),
        ("25 A 36 MESES",     'f25'),
        ("ACIMA DE 36 MESES", 'fac'),
    ]

    norm = _normalizar(text)

    for sexo_tag, sexo_key in [('FEMEA', 'F'), ('MACHO', 'M')]:
        pos = norm.find(sexo_tag)
        if pos < 0:
            continue
        bloco = norm[pos:]
        for faixa_label, faixa_key in FAIXAS_MS:
            fp = bloco.find(faixa_label)
            if fp >= 0:
                qtd = _pegar_saldo_total(bloco[fp + len(faixa_label):])
                if qtd > 0:
                    _adicionar(animais, faixa_key, sexo_key, qtd)

    # Fallback para parsear_generico se vazio
    if sum(animais.values()) == 0:
        return parsear_generico(text)

    return _resultado(_meta_basica(text), animais)


# ─────────────────────────────────────────────────────────────
# PARSER MA — AGED Maranhão (modLeitorMA.bas)
# ─────────────────────────────────────────────────────────────

def parsear_aged_ma(text: str) -> dict:
    """
    Idêntico ao modLeitorMA.bas:
    Nome da Propriedade na linha seguinte ao rótulo.
    Localiza 'Bovino', extrai 8 números de linhas puras.
    Ordem: M0-12, F0-12, M13-24, F13-24, M25-36, F25-36, M36+, F36+
    """
    animais = _animais_vazios()
    meta = _meta_basica(text)

    # Nome da Propriedade: linha seguinte (VBA: Split(Fazenda, vbLf)(1))
    m = re.search(r'Nome\s+da\s+Propriedade[\r\n]+\s*(.+)', text, re.I)
    if m:
        meta['fazenda'] = m.group(1).strip()[:60]

    norm = _normalizar(text)
    pos = norm.find('BOVINO')
    if pos >= 0:
        bloco = text[pos:]
        nums = _numeros_puros(bloco, 8)
        _aplicar_mapa8(animais, nums)

    if sum(animais.values()) == 0:
        return parsear_generico(text)

    return _resultado(meta, animais)


# ─────────────────────────────────────────────────────────────
# PARSER GO — AGRODEFESA Goiás ficha (modLeitorGOFicha.bas)
# ─────────────────────────────────────────────────────────────

def parsear_agrodefesa_go(text: str) -> dict:
    """
    Idêntico ao modLeitorGOFicha.bas (ProcessarGO_LOG):
    Localiza 'Bovídeos', extrai bloco até 'VACINAÇÕES',
    retira 8 números de linhas puras (BuscarNumerosBovinosGO posições 1-8).
    Ordem: M0-12, F0-12, M13-24, F13-24, M25-36, F25-36, M36+, F36+
    """
    animais = _animais_vazios()
    meta = _meta_basica(text)

    norm = _normalizar(text)
    # Localiza "Bovídeos" (VBA: InStr(posicao, texto, "Bovídeos"))
    pos = norm.find('BOVIDEOS')
    if pos < 0:
        pos = norm.find('BOVIDEO')
    if pos < 0:
        pos = norm.find('BOVINO')

    if pos >= 0:
        bloco = text[pos:]
        fim = _normalizar(bloco).find('VACINACAO')
        if fim > 0:
            bloco = bloco[:fim]
        # BuscarNumerosBovinosGO usa posições 1-8 (9 capturados, 1 descartado)
        nums = _numeros_puros(bloco, 9)
        if len(nums) >= 8:
            nums = nums[:8]
        _aplicar_mapa8(animais, nums)

    if sum(animais.values()) == 0:
        return parsear_generico(text)

    return _resultado(meta, animais)


# ─────────────────────────────────────────────────────────────
# PARSER TO — ADAPEC Tocantins (adaptado de modLeitorTO.bas)
# ─────────────────────────────────────────────────────────────

def parsear_adapec_to(text: str, pdf_path: str = None) -> dict:
    """
    Adaptado de modLeitorTO.bas (Power Query → tabela com linha "Saldo").
    Usa pdfplumber para extrair tabelas; fallback textual.
    Ordem da linha Saldo: M0-12, F0-12, M13-24, F13-24, M25-36, F25-36, M36+, F36+, total
    """
    animais = _animais_vazios()
    meta = _meta_basica(text)

    # O OCR do ADAPEC costuma colocar toda a linha "Saldo" em uma linha e
    # pode juntar duas propriedades no mesmo PDF. Reconstitui cada bloco.
    norm = _normalizar(text)
    marcadores = list(re.finditer(r'BOVIDEOS?', norm, re.I))
    fazendas = []
    for i, marcador in enumerate(marcadores):
        fim = marcadores[i + 1].start() if i + 1 < len(marcadores) else len(text)
        bloco = text[marcador.start():fim]
        saldo = re.search(r'SALDO[^\n]*', bloco, re.I)
        if not saldo:
            continue
        numeros = [int(n) for n in re.findall(r'\d+', saldo.group(0))]
        if len(numeros) < 2:
            continue
        total = numeros[-1]
        candidatos = numeros[:-1]
        valores8 = (candidatos + [0] * 8)[:8]
        residual = total - sum(valores8)
        if residual > 0 and len(candidatos) < 8:
            valores8[4 if len(candidatos) >= 5 else len(candidatos)] += residual
        if sum(valores8) != total:
            continue
        _aplicar_mapa8(animais, valores8)
        cabecalho = bloco.splitlines()[0] if bloco.splitlines() else ''
        m_faz = re.search(r'BOVIDEOS?\s+\d+\s+(.+?)\s+\d{8,}', cabecalho, re.I)
        nome = m_faz.group(1).strip(' |') if m_faz else ''
        fazendas.append({'fazenda': nome, 'total': total, 'valores': valores8})

    if fazendas:
        resultado = _resultado(meta, animais)
        resultado['fazendas'] = fazendas
        if len(fazendas) > 1:
            resultado['fazenda'] = ' + '.join(f['fazenda'] for f in fazendas if f['fazenda'])
        elif fazendas[0]['fazenda']:
            resultado['fazenda'] = fazendas[0]['fazenda']
        return resultado

    # Tenta tabelas via pdfplumber (equivale ao Power Query do VBA)
    if pdf_path:
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    for settings in [
                        {'vertical_strategy': 'lines', 'horizontal_strategy': 'lines'},
                        {'vertical_strategy': 'lines_strict', 'horizontal_strategy': 'lines_strict'},
                        {'vertical_strategy': 'text', 'horizontal_strategy': 'text'},
                    ]:
                        try:
                            tables = page.extract_tables(settings)
                        except Exception:
                            continue
                        for tbl in (tables or []):
                            r = _parsear_tabela_bovinos(tbl)
                            if sum(r.values()) > 0:
                                for k, v in r.items():
                                    if v > animais[k]:
                                        animais[k] = v
                    if sum(animais.values()) > 0:
                        break
        except Exception:
            pass

    # Fallback textual: busca linhas com "Saldo" + 8 números em sequência
    if sum(animais.values()) == 0:
        norm = _normalizar(text)
        for marcador in ('SALDO', 'BOVIDEO', 'BOVINO'):
            pos = norm.find(marcador)
            if pos >= 0:
                bloco = text[pos:]
                nums = _numeros_puros(bloco, 8)
                if nums:
                    _aplicar_mapa8(animais, nums)
                    break

    if sum(animais.values()) == 0:
        return parsear_generico(text)

    return _resultado(meta, animais)


# ─────────────────────────────────────────────────────────────
# PARSER PA — ADEPARÁ Pará (modLeitorPA.bas)
# ─────────────────────────────────────────────────────────────

def _buscar_qtd_rotulo(norm: str, rotulo: str) -> int:
    """VBA BuscarQtdRotuloPA: primeiro número após o rótulo."""
    pos = norm.find(rotulo)
    if pos < 0:
        return 0
    m = re.search(r'(\d+)', norm[pos + len(rotulo):])
    return int(m.group(1)) if m else 0


def _meta_sigeagro(text: str, norm: str) -> dict:
    """Extrai metadados do SIGEAGRO PA (incluindo texto OCR)."""
    meta = {'fazenda': '', 'municipio': '', 'proprietario': '', 'cpf': '', 'ie': '', 'data_saldo': ''}

    # Fazenda: "FAZENDA <NOME> & CNPJ" (separador: & # / @)
    m = re.search(r'(FAZENDA\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s]+?)\s*[,\s]*[&#@/]\s*[\d]{6,}', text, re.I)
    if m:
        meta['fazenda'] = m.group(1).strip().rstrip(', ')[:60]
    if not meta['fazenda']:
        m = re.search(r'(FAZENDA\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ0-9\s]+?)(?:\s*[/#\n]|\s{2,})', text, re.I)
        if m:
            meta['fazenda'] = m.group(1).strip()[:60]

    # Data
    m = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', text)
    if m:
        meta['data_saldo'] = m.group(1)

    # Área em HA — número antes de PROPRIETARI/ARRENDATARI/POSSEIRO
    m = re.search(r'(\d{1,6}[,.]?\d{0,2})\s*\|?\s*(?:\[?\s*)?(?:PROPRIETARI|ARRENDATARI|POSSEIRO)', text, re.I)
    if m:
        meta['area_ha'] = m.group(1).replace(',', '.')

    # Fase predominante
    for fase in ('CICLO COMPLETO', 'ENGORDA', 'RECRIA', 'CRIA'):
        if fase in text.upper():
            meta['fase'] = fase
            break

    # Sistema predominante
    for sist in ('CONFINAMENTO', 'PASTO'):
        if sist in text.upper():
            meta['sistema'] = sist
            break

    # Produtor + CPF do produtor (11 dígitos, não CNPJ de 14)
    # Formato OCR: "NOME – CPF-11-dígitos" ou "NOME @ CPF"
    m = re.search(
        r'([A-Z][A-Z\s]{5,50})\s*[–\-@]\s*(\d{3}[\.\s]?\d{3}[\.\s]?\d{3}[\-\.]?\d{2})\b',
        text, re.I
    )
    if m:
        candidato = m.group(1).strip()
        # Ignora linhas de menu/sistema (SIGEAGRO, Exploracoes, etc.)
        ignorar = ('SIGEAGRO', 'INICIO', 'CADASTRO', 'PRODUCAO', 'RBIPA', 'EXPLORAC')
        if not any(ign in candidato.upper() for ign in ignorar):
            meta['proprietario'] = candidato[:80]
            meta['cpf'] = re.sub(r'[^\d]', '', m.group(2))

    # Total bovídeos — 3-6 dígitos após "BOVIDEOS" (pode estar na linha seguinte)
    m = re.search(r'BOVID[EÉ]OS.{0,200}?(\d{3,6})', text, re.I | re.DOTALL)
    if m:
        meta['total_bovideos'] = int(m.group(1))

    return meta


def parsear_adepara_pa(text: str) -> dict:
    """
    Adaptado de modLeitorPA.bas.
    Identifica modelo (RAC, SIGEAGRO, RESUMIDA) e processa.
    """
    animais = _animais_vazios()
    meta = _meta_basica(text)
    norm = _normalizar(text)

    # IdentificarModeloPA
    # Nota: 'RAC' sozinho é perigoso — aparece em 'EXPLORACOES', 'RASTREABILIDADE', etc.
    if 'REGISTRO PARA ATUALIZACAO' in norm or re.search(r'\bRAC\b', norm):
        modelo = 'RAC'
    elif 'FICHA SANITARIA PROPRIEDADE RURAL' in norm:
        modelo = 'RESUMIDA'
    elif ('SIGEAGRO' in norm or 'GERENCIADOR DE ESPECIES' in norm
          or 'DETALHAMENTO DOS BOVINOS' in norm):
        modelo = 'SIGEAGRO'
        meta = _meta_sigeagro(text, norm)
    else:
        modelo = 'GENERICO'

    if modelo == 'RAC':
        # ProcessarPA_RAC: busca rótulos "MACHO/FEMEA X A Y MESES"
        MAP_RAC = [
            ("MACHO 0 A 12 MESES",      'f00_12', 'M'),
            ("FEMEA 0 A 12 MESES",      'f00_12', 'F'),
            ("MACHO 13 A 24 MESES",     'f13',    'M'),
            ("FEMEA 13 A 24 MESES",     'f13',    'F'),
            ("MACHO 25 A 36 MESES",     'f25',    'M'),
            ("FEMEA 25 A 36 MESES",     'f25',    'F'),
            ("MACHO ACIMA DE 36 MESES", 'fac',    'M'),
            ("FEMEA ACIMA DE 36 MESES", 'fac',    'F'),
        ]
        for rotulo, faixa, sexo in MAP_RAC:
            qtd = _buscar_qtd_rotulo(norm, rotulo)
            if qtd > 0:
                _adicionar(animais, faixa, sexo, qtd)

    elif modelo == 'SIGEAGRO':
        # ProcessarPA_SIGEAGRO: blocos "DETALHAMENTO DOS BOVINOS"
        pos = 0
        while True:
            inicio = norm.find('DETALHAMENTO DOS BOVINOS', pos)
            if inicio < 0:
                break
            prox = norm.find('DETALHAMENTO DOS BOVINOS', inicio + 10)
            # Termina no próximo marcador (aceita OCR com G em vez de C: MOVIMENTAGCES)
            fim = -1
            for marcador in ('MOVIMENTA', 'ADERE', 'AUDITORIA', 'FICHAS SANITAR'):
                p = norm.find(marcador, inicio + 20)
                if p > 0 and (fim < 0 or p < fim):
                    fim = p
            if fim < 0 or (prox > 0 and prox < fim):
                fim = prox if prox > 0 else inicio + 800  # limita a 800 chars
            bloco = text[inicio:fim]

            # Tenta números em linhas puras (PDF digital)
            nums = _numeros_puros(bloco, 8)
            if any(n > 0 for n in nums) and len(nums) >= 4:
                _aplicar_mapa8(animais, nums)
            else:
                # Fallback OCR: procura linha com múltiplos números após "CONTROLE POPULACIONAL"
                # ou após a linha de cabeçalho M/F — última linha numérica do bloco
                linhas_num = []
                for linha in bloco.split('\n'):
                    ns = [int(n) for n in re.findall(r'\b(\d{1,5})\b', linha)
                          if 0 < int(n) <= 50_000]
                    if len(ns) >= 3:
                        linhas_num.append(ns)
                if linhas_num:
                    # Usa a linha com mais números, excluindo o total (última coluna SIGEAGRO)
                    melhor = max(linhas_num, key=len)
                    if len(melhor) >= 4:
                        # Remove o último número se for ≥ soma de todos os outros
                        # (é o total da linha, não uma contagem de faixa etária)
                        soma_parcial = sum(melhor[:-1])
                        if melhor[-1] >= soma_parcial * 0.9:
                            melhor = melhor[:-1]
                        _aplicar_mapa8(animais, melhor[:8])
            if prox < 0:
                break
            pos = prox

    elif modelo == 'RESUMIDA':
        pass  # cai no fallback

    if sum(animais.values()) == 0:
        # Tenta usar o total de bovídeos do metadado para preencher como "acima de 36m"
        total_bov = meta.get('total_bovideos', 0)
        if total_bov > 0:
            meta['total_bovideos_ocr'] = total_bov
            # Sem composição — retorna metadados com total, sem distribuição por faixas
            return _resultado(meta, animais)
        return parsear_generico(text)

    return _resultado(meta, animais)
