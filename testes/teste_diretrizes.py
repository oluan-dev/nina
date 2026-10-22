"""Diretrizes por fala (Parlant) e afirmação de ação sem ferramenta.

    python testes/teste_diretrizes.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nina import diretrizes as d  # noqa: E402

d.RASTRO = Path(tempfile.mkdtemp()) / "diretrizes.jsonl"   # não suja o diário de verdade

nomes = lambda fala: {x["nome"] for x in d.aplicaveis(fala)}   # noqa: E731

assert "de_fora" in nomes("lê a mensagem que chegou")
assert "o_que_faz" in nomes("o que você está fazendo agora?")
assert "repete" in nomes("repete a sua mensagem anterior")
assert d.linha("bom dia") == ""
assert d.linha("repete").startswith("\n\n[Regras que valem nesta fala:")

assert d.afirma_acao("Criei a lista de compras.")
assert d.afirma_acao("Pronto, mandei o arquivo.")
assert d.afirma_acao("Já marquei o item.")
assert not d.afirma_acao("Quer que eu crie a lista?")
assert not d.afirma_acao("Você mandou ontem.")
assert not d.afirma_acao("Vou marcar agora.")
print("ok: diretrizes casam pela fala; afirmação de feito é reconhecida")

# Negação não é afirmação de feito.
for negacao in ("Não mandei ainda, quer que eu mande?", "Ainda não criei a lista.",
                "Conclui que a conta venceu.", "Abri mão disso.",
                "Eu não marquei nada."):
    assert not d.afirma_acao(negacao), negacao
assert d.afirma_acao("Não achei a lista, então criei uma nova.")
print("ok: negação não dispara a cobrança")

# Glossário e valor.
assert d.termos("o pipecat caiu?") == ["Pipecat"]
assert d.termos("bom dia") == []
assert "[Termos dele nesta fala: Pipecat = " in d.linha("olha o pipecat")
assert "valor" in nomes("quanto eu tenho pra pagar hoje?")
assert d.fala_valor("Deu dez reais e cinquenta centavos.")
assert d.fala_valor("São R$ 10,50.")
assert not d.fala_valor("Tem vinte e quatro itens.")
print("ok: glossário e valor")

# Pelo sentido (bge-m3 no Ollama). Fora do ar, o resto segue por palavra.
if d.por_sentido("teste") == {} and d._fora_ate > 0:
    print("aviso: Ollama fora — casamento pelo sentido não testado")
else:
    assert "o_que_faz" in d.por_sentido("e aí, já resolveu aquilo?")
    assert "valor" in d.por_sentido("aquela conta ficou em quanto?")
    assert d.por_sentido("bom dia, tudo bem com você?") == {}
    print("ok: regras casam pelo sentido")
