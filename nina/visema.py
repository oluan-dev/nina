"""De fala para boca: que forma a boca faz, e em que instante.

O edge-tts devolve, junto com o áudio, o tempo exato de cada palavra. E o
português salva o resto: a ortografia é quase fonética, então a própria letra
já diz a forma da boca. Nada de modelo, de treino, de rede neural — é tabela.

São cinco formas, as mesmas de qualquer carta de visema:

    M    lábio fechado        m, b, p
    AH   bem aberta           a
    E    esticada, sorriso    e, i
    O    em bico              o, u
    S    entreaberta          repouso, e palavra só de consoante

    python -m nina.visema        confere o mapeamento e os tempos
"""
from __future__ import annotations

VOGAIS = {
    "a": "AH", "á": "AH", "à": "AH", "â": "AH", "ã": "AH",
    "e": "E", "é": "E", "ê": "E", "i": "E", "í": "E",
    "o": "O", "ó": "O", "ô": "O", "õ": "O",
    "u": "O", "ú": "O", "ü": "O",
}

# Os três sons que fecham o lábio de verdade. O resto de consoante a boca
# atravessa sem mudar de forma — quem manda na forma é a vogal ao lado.
FECHA = set("mbp")

# Abaixo disto vira borrão: duas formas em menos de 60 ms ninguém enxerga.
MINIMO = 0.06

# Silêncio maior que isto entre duas palavras: ela fecha a boca no meio.
PAUSA = 0.12


def formas(palavra: str) -> list[str]:
    """As formas que a boca faz nesta palavra, em ordem.

    Forma repetida seguida vira uma só: em "posso" o lábio já está em bico no
    primeiro "o" e continua lá até o fim, então não há o que redesenhar.
    """
    saida: list[str] = []
    for letra in palavra.lower():
        forma = "M" if letra in FECHA else VOGAIS.get(letra)
        if forma and forma != (saida[-1] if saida else None):
            saida.append(forma)
    return saida or ["S"]


def agenda(eventos: list[dict]) -> list[list]:
    """A linha do tempo da boca, em segundos desde o início da fala.

    `eventos` são os WordBoundary crus do edge-tts, com tempo em unidades de
    100 nanossegundos. Sai o que a página precisa e nada mais: em tal instante,
    faça tal forma.
    """
    linha: list[list] = []
    fim_anterior = 0.0

    for e in eventos:
        inicio = e["offset"] / 1e7
        duracao = e["duration"] / 1e7

        if inicio - fim_anterior > PAUSA:
            linha.append([round(fim_anterior, 3), "M"])

        lista = formas(e["text"])
        # Palavra curta com muita sílaba: fica só o que dá tempo de ver.
        cabem = max(1, int(duracao / MINIMO))
        lista = lista[:cabem]

        passo = duracao / len(lista)
        for i, forma in enumerate(lista):
            linha.append([round(inicio + i * passo, 3), forma])

        fim_anterior = inicio + duracao

    if linha:
        linha.append([round(fim_anterior, 3), "M"])
    return linha


def _conferir() -> None:
    assert formas("Nina") == ["E", "AH"], formas("Nina")
    assert formas("posso") == ["M", "O"], formas("posso")
    assert formas("ajudar") == ["AH", "O", "AH"], formas("ajudar")
    assert formas("mamãe") == ["M", "AH", "M", "AH", "E"], formas("mamãe")
    assert formas("sss") == ["S"], formas("sss")

    # Um segundo de "Nina", começando em zero: duas formas e o fecho no fim.
    linha = agenda([{"offset": 0, "duration": 10_000_000, "text": "Nina"}])
    assert linha == [[0.0, "E"], [0.5, "AH"], [1.0, "M"]], linha

    # Pausa longa entre as duas: a boca fecha no meio.
    linha = agenda([
        {"offset": 0, "duration": 2_000_000, "text": "oi"},
        {"offset": 10_000_000, "duration": 2_000_000, "text": "Lua"},
    ])
    assert [f for _, f in linha] == ["O", "E", "M", "O", "AH", "M"], linha

    # Palavra curta demais para todas as formas: corta, não acelera.
    linha = agenda([{"offset": 0, "duration": 700_000, "text": "ajudar"}])
    assert len(linha) == 2, linha        # uma forma (0,07s) + o fecho

    print("visema: confere")


if __name__ == "__main__":
    _conferir()
    for p in ("Oi", "Lua", "eu", "sou", "a", "Nina", "Como", "posso", "ajudar"):
        print(f"{p:>8}  {' '.join(formas(p))}")
