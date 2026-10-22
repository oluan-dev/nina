"""A Nina.

Uma coisa só acontece aqui, e acontece antes de qualquer módulo dela: a saída
passa a ser UTF-8.

O console do Windows entrega cp1252, e aí todo comando dela que imprime texto
com acento ou símbolo estoura `UnicodeEncodeError` no meio da resposta — ou,
pior, chega torto ("h� 4 min"): ela vai contar algo e recebe um traceback no
lugar da resposta.

O lugar é este porque `python -m nina.<qualquer coisa>` importa o pacote antes
do módulo, então o conserto vale para todos os comandos dela, inclusive os que
ainda não existem.
"""
from __future__ import annotations

import sys

for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass        # saída redirecionada ou sem suporte: segue como estava
