"""Adaptador do leitor GO Cadastro/Agrodefesa existente."""

from .base_reader import read_ficha_text


def read(text, **kwargs):
    return read_ficha_text(text, estado='GO', modelo='GO_DECLARACAO', **kwargs)
