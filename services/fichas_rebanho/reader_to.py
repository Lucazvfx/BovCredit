"""Adaptador do leitor TO existente."""

from .base_reader import read_ficha_text


def read(text, **kwargs):
    return read_ficha_text(text, estado='TO', **kwargs)
