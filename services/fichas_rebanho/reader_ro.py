"""Adaptador do leitor RO existente para a camada central."""

from .base_reader import read_ficha_text


def read(text, **kwargs):
    return read_ficha_text(text, estado='RO', **kwargs)
