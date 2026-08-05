"""Leitura, mapeamento e validação das fichas estaduais de rebanho."""

from .base_reader import read_ficha_pdf, read_ficha_text, registros_do_parse

__all__ = ['read_ficha_pdf', 'read_ficha_text', 'registros_do_parse']
