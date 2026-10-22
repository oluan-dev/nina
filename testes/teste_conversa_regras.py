"""Quando a Nina (Pipecat) atende e os comandos falados.

    python testes/teste_conversa_regras.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conversa.regras import chamou_por_ela, comando, e_sim  # noqa: E402

for chamou in ("Nina, está me ouvindo?", "Menina, você está aí?", "ô Nina, vem cá",
               "nina o que tem pra hoje"):
    assert chamou_por_ela(chamou), chamou
for nao in ("a menina chegou agora", "liga pro João", "vou almoçar e já volto"):
    assert not chamou_por_ela(nao), nao

assert comando("Tchau, Nina.") == "tchau"
assert comando("Pera, Nina.") == "calar"
assert comando("Cala a boca, Nina") == "calar"
assert comando("Voltei, Nina.") == "voltar"
assert comando("Nina, para de ouvir") == "calar"
assert comando("Nina, para.") == "parar"
assert comando("Para, Nina") == "parar"
assert comando("Nina, para de falar") == "parar"
assert comando("Para.") == "parar"
assert comando("Para de mexer nisso") is None
assert comando("Nina, para o que você tá fazendo e me diz o que tem pra hoje") is None
assert comando("o tchau que ele deu foi esquisito demais hoje cedo") is None

for sim in ("Sim.", "Pode.", "pode sim", "Nina, pode fazer", "Claro"):
    assert e_sim(sim), sim
for nao in ("Não.", "hum", "", "espera", "nada"):
    assert not e_sim(nao), nao
print("ok: nome, comandos e sim falado")

from conversa.regras import so_o_nome  # noqa: E402

for nome in ("Nina.", "Ô Nina!", "Menina?", "ei nina"):
    assert so_o_nome(nome), nome
for mais in ("Nina, tá aí?", "Nina quanto é sete vezes oito", "a menina"):
    assert not so_o_nome(mais), mais
print("ok: só o chamado vira 'oi?'")

# Grafias que o Whisper deu ao nome dela.
assert comando("Pera, Mina.") == "calar"
assert comando("Tchau, mina.") == "tchau"
assert so_o_nome("Minna.")
print("ok: grafias do nome valem nos comandos")

# Frase que termina em aberto espera a continuação; eco inventado é lixo.
from conversa.regras import inventado, termina_aberto  # noqa: E402

for aberta in ("Preciso que você mande um recado. É... Falando que",
               "Nina, preciso que você coloque essa tarefa...", "Tá, Nina. Preciso.",
               "e aí da reforma? Eu já fechei com uma empresa para segunda-feira, eles vão",
               "o boleto é três mil e", "manda pra pasta do", "Nina, eu queria,"):
    assert termina_aberto(aberta), aberta
for fechada in ("Nina, tá me ouvindo?", "O nome da empresa é Exemplo Ltda.",
                "Coloca a revisão do carro.", "Pera, Nina.", "Quanto é dois mais dois?"):
    assert not termina_aberto(fechada), fechada
assert inventado("Suja, suja, suja, suja, suja.")
assert inventado("E aí, E aí, E aí, E aí, E aí, E aí,")
assert not inventado("Não, não, não, espera.")
assert not inventado("Nina, me fala das minhas tarefas de hoje.")
print("ok: frase aberta espera; repetição inventada é ignorada")
