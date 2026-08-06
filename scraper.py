import requests
import re
import asyncio
import importlib
import math
import logging
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def _session_com_retry() -> requests.Session:
    """Session com retry automático para falhas transitórias (5xx, timeouts)."""
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,          # 1s, 2s, 4s entre tentativas
        status_forcelist={500, 502, 503, 504},
        allowed_methods={"GET"},
        raise_on_status=False,
    )
    s.mount('https://', HTTPAdapter(max_retries=retry))
    s.mount('http://',  HTTPAdapter(max_retries=retry))
    return s

def extrair_valores_especificos(texto, praca_alvo):
    """
    Busca uma praça específica e extrai os dois primeiros valores financeiros 
    que aparecem após o nome dela.
    """
    # Regex que ignora espaços e tags entre a praça e os valores
    padrao = re.compile(rf'{praca_alvo}.*?(\d{{2,3}},\d{{2}}).*?(\d{{2,3}},\d{{2}})', re.IGNORECASE | re.DOTALL)
    match = padrao.search(texto)
    if match:
        v_vista = float(match.group(1).replace(',', '.'))
        v_30d = float(match.group(2).replace(',', '.'))
        return v_vista, v_30d
    return 0.0, 0.0
def _obter_via_agrobr():
    """Tenta obter preços usando a biblioteca `agrobr` se disponível.

    Retorna dict {'boi': float, 'vaca': float, 'boi_china': float} ou None se falhar.
    """
    try:
        agrobr = importlib.import_module('agrobr')
    except Exception:
        return None

    try:
        datasets = agrobr.datasets
        # asyncio.run() cria event loop próprio — seguro em thread sem loop ativo
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Já há um event loop: executa via thread executor para não bloquear
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                df = ex.submit(asyncio.run, datasets.preco_diario('boi')).result(timeout=15)
        else:
            df = asyncio.run(datasets.preco_diario('boi'))
        import pandas as pd
        if not isinstance(df, pd.DataFrame) or df.empty:
            return None

        # Identifica coluna de data e coluna de preço
        cols = [c for c in df.columns]
        date_col = next((c for c in cols if 'data' in c.lower() or 'date' in c.lower()), None)
        price_col = next((c for c in cols if 'preco' in c.lower() or 'valor' in c.lower() or 'price' in c.lower()), None)

        if price_col is None:
            # tenta usar a segunda coluna como fallback
            price_col = cols[1] if len(cols) > 1 else cols[0]

        # Ordena por data se possível e pega o valor mais recente
        if date_col:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df = df.sort_values(date_col, ascending=False)
            except Exception:
                pass

        # Limpa e converte o valor
        val_raw = df[price_col].dropna().iloc[0]
        if isinstance(val_raw, str):
            val = float(str(val_raw).replace('.', '').replace(',', '.'))
        else:
            val = float(val_raw)

        # Retorna preço encontrado; vaca e boi_china não são fornecidos por agrobr -> fallback 0
        return {'boi': float(val), 'vaca': 0.0, 'boi_china': 0.0}
    except Exception:
        return None


_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
_DEFAULTS = {'boi': 342.0, 'vaca': 308.0, 'boi_china': 355.0}
_URL_BOI_NA     = "https://www.noticiasagricolas.com.br/cotacoes/boi-gordo"
_URL_BOI_CEPEA  = "https://cepea.org.br/br/indicador/boi-gordo.aspx"  # backup
_URL_VACA_SCOT  = "https://www.scotconsultoria.com.br/cotacoes/vaca-gorda/?ref=smnb"
_URL_BEZ_CEPEA  = "https://cepea.org.br/br/indicador/bezerro.aspx"


def _parse_boi_cepea(html: str) -> float:
    """Backup: extrai o indicador de boi gordo direto da página CEPEA/ESALQ.

    A página lista o valor mais recente no formato 'nnn,nn' ou '1.nnn,nn'.
    Retorna 0.0 se não achar valor dentro da faixa de sanidade.
    """
    from services.precos_diarios import valido, FAIXA_ARROBA
    import re as _re
    texto = _re.sub(r'<[^>]+>', ' ', html)
    # Boi gordo ESALQ: tipicamente entre 300 e 500 R$/@
    for cand in _re.findall(r'(\d{1,3}[.,]\d{2})', texto):
        v = float(cand.replace('.', '').replace(',', '.'))
        if valido(v, *FAIXA_ARROBA):
            return v
    return 0.0


def obter_precos_arroba():
    """Cotação diária nacional por categoria, com fallback por categoria.

    Boi: indicador CEPEA/ESALQ republicado pela Notícias Agrícolas.
    Vaca: Scot Consultoria (praça de referência nacional).
    Bezerro: último valor salvo (se o analista ajustou) ou referência de mercado.
    Bezerra: derivada do bezerro (× 0,90).

    Retorna {'boi','vaca','boi_china','bezerro','bezerra','fonte'}. Nunca lança;
    cai para último salvo → default quando a fonte falha.
    """
    from services.precos_diarios import (
        parse_boi_na, parse_vaca_scot, parse_bezerro_cepea, bezerra_de, valido,
        FAIXA_BEZERRO, BEZERRO_REF,
    )
    try:
        import database as db
        ultimo = db.obter_cotacoes_atuais() or {}
    except Exception:
        ultimo = {}

    # ── BOI — Notícias Agrícolas (CEPEA/ESALQ) → backup direto CEPEA ──
    boi, fonte_boi = 0.0, ''
    sess = _session_com_retry()
    try:
        html = sess.get(_URL_BOI_NA, headers=_HEADERS, timeout=20).text
        boi = parse_boi_na(html)
        if boi:
            fonte_boi = 'CEPEA/ESALQ (Notícias Agrícolas)'
    except Exception as e:
        logger.warning(f'[Scraper] Falha ao buscar boi (NA): {e}')
    if not boi:
        try:
            html_cepea = sess.get(_URL_BOI_CEPEA, headers=_HEADERS, timeout=20).text
            boi = _parse_boi_cepea(html_cepea)
            if boi:
                fonte_boi = 'CEPEA/ESALQ (direto)'
        except Exception as e:
            logger.warning(f'[Scraper] Falha ao buscar boi (CEPEA backup): {e}')
    if not boi:
        boi = float(ultimo.get('boi') or 0) or _DEFAULTS['boi']
        fonte_boi = 'último salvo' if ultimo.get('boi') else 'default'

    # ── VACA — Scot ──
    vaca, fonte_vaca = 0.0, ''
    try:
        html = sess.get(_URL_VACA_SCOT, headers=_HEADERS, timeout=20).text
        vaca = parse_vaca_scot(html)
        if vaca:
            fonte_vaca = 'Scot Consultoria'
    except Exception as e:
        logger.warning(f'[Scraper] Falha ao buscar vaca: {e}')
    if not vaca:
        vaca = float(ultimo.get('vaca') or 0) or _DEFAULTS['vaca']
        fonte_vaca = 'último salvo' if ultimo.get('vaca') else 'default'

    # ── BEZERRO — CEPEA (indicador oficial) → último salvo → referência ──
    bezerro, fonte_bezerro = 0.0, ''
    try:
        html_bez = sess.get(_URL_BEZ_CEPEA, headers=_HEADERS, timeout=20).text
        bezerro = parse_bezerro_cepea(html_bez)
        if bezerro:
            fonte_bezerro = 'CEPEA/ESALQ (bezerro)'
    except Exception as e:
        logger.warning(f'[Scraper] Falha ao buscar bezerro CEPEA: {e}')
    if not valido(bezerro, *FAIXA_BEZERRO):
        bezerro = float(ultimo.get('bezerro') or 0)
        fonte_bezerro = 'último salvo' if valido(bezerro, *FAIXA_BEZERRO) else 'referência'
        if not valido(bezerro, *FAIXA_BEZERRO):
            bezerro = BEZERRO_REF
    bezerra = bezerra_de(bezerro)

    boi_china = float(ultimo.get('boi_china') or 0) or _DEFAULTS['boi_china']
    fonte = f'boi: {fonte_boi}; vaca: {fonte_vaca}; bezerro: {fonte_bezerro}'
    logger.info(f"[Cotação] boi {boi} ({fonte_boi}) | vaca {vaca} ({fonte_vaca}) | "
                f"bezerro {bezerro} ({fonte_bezerro}) | bezerra {bezerra}")
    return {'boi': boi, 'vaca': vaca, 'boi_china': boi_china,
            'bezerro': bezerro, 'bezerra': bezerra, 'fonte': fonte}


def obter_precos_agrobr_strict():
    """Força a obtenção de preços apenas via `agrobr`.

    Retorna dicionário {'boi','vaca','boi_china'} ou lança RuntimeError se não for possível.
    """
    res = _obter_via_agrobr()
    if not res:
        raise RuntimeError("agrobr não disponível ou falha ao obter dados — instale 'agrobr' e dependências.")
    return res