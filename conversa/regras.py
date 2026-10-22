"""Quando ela atende e os comandos falados — as mesmas listas da Nina antiga
(nina/__main__.py), sem as dependências dela."""
from __future__ import annotations

import re
import unicodedata

# Ela só entra na conversa quando é chamada; o Whisper escreve o nome dela de
# vários jeitos ("Menina, você está aí?").
NOMES_DELA = ("nina", "ninna", "nia", "mina", "minna", "nima")
NOMES_DELA_NO_COMECO = ("menina", "nenina", "ninah", "nena")

DESPEDIDAS = ("tchau nina", "dorme nina", "sai nina", "tchau", "desliga")
# Parar de OUVIR (fica surda até "voltei").
CALAR = ("pera nina", "perai nina", "espera nina", "espera ai nina",
         "cala a boca nina", "cala boca nina", "fica quieta nina",
         "silencio nina", "nao escuta nina", "para de ouvir nina",
         "nina para de ouvir", "nina cala a boca", "nina pera", "nina espera",
         "nina silencio", "nina fica quieta", "nina nao escuta")
# Parar de FALAR e seguir ouvindo. "Nina, para" é isso numa conversa: com ele
# na lista de cima, ela ficava surda no meio da conversa.
PARAR = ("para nina", "nina para", "chega nina", "nina chega",
         "para de falar nina", "nina para de falar", "ja entendi nina")
# O Whisper parte "Nina, para." em "Nina." + "para.": sozinhas, valem.
PARAR_SO = ("para", "chega", "para de falar", "ja entendi", "ta bom para")
VOLTAR = ("volta nina", "nina volta", "pode ouvir nina", "nina pode ouvir",
          "pode falar nina", "nina pode falar", "voltei nina", "nina voltei",
          "nina ta liberado", "escuta nina", "nina escuta", "voltei")
SIM = ("sim", "pode", "pode sim", "manda", "vai", "isso", "ok", "ta", "beleza",
       "claro", "libera", "autorizo", "confirmo", "faz", "faca", "pode mandar",
       "pode fazer", "pode ir")


def _limpo(texto: str) -> str:
    k = "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z ]+", " ", k).split())


def _com_nome(texto: str) -> str:
    """Toda grafia do nome dela vira "nina": "Pera, Mina." é "pera nina"."""
    palavras = _limpo(texto).split()
    return " ".join("nina" if p in NOMES_DELA or (i == 0 and p in NOMES_DELA_NO_COMECO)
                    else p for i, p in enumerate(palavras))


def chamou_por_ela(texto: str) -> bool:
    """O nome dela no começo da fala (palavra inteira: "a menina chegou" não é)."""
    k = _limpo(texto)
    inicio = " ".join(k.split()[:4])
    if re.search(r"\b(" + "|".join(NOMES_DELA) + r")\b", inicio):
        return True
    return bool(re.match(r"^(" + "|".join(NOMES_DELA_NO_COMECO) + r")\b", k))


def so_o_nome(texto: str) -> bool:
    """A fala é só o chamado ("Nina.", "Ô Nina!", "Menina?")."""
    k = [p for p in _limpo(texto).split() if p not in ("o", "oi", "ei", "e", "hey")]
    return len(k) == 1 and (k[0] in NOMES_DELA or k[0] in NOMES_DELA_NO_COMECO)


def comando(texto: str) -> str | None:
    """'tchau', 'calar' ou 'voltar' — só quando a fala INTEIRA é o comando.

    "Nina, para…" no meio de um pedido não é ordem para calar (visto antes).
    """
    k = _com_nome(texto)
    if not k or len(k.split()) > 6:
        return None
    if k in PARAR_SO:
        return "parar"
    for nome, lista in (("calar", CALAR), ("voltar", VOLTAR), ("parar", PARAR),
                        ("tchau", DESPEDIDAS)):
        if any(k == alvo or k.startswith(alvo + " ") or k.endswith(" " + alvo)
               for alvo in lista):
            return nome
    return None


def e_sim(texto: str) -> bool:
    """Só afirmação clara libera coisa séria; silêncio e "hum" não."""
    k = _limpo(texto)
    k = re.sub(r"^(nina )", "", k)
    return any(k == s or k.startswith(s + " ") for s in SIM)


# Frase que acaba no meio: a última palavra pede continuação. Sem isto o turno
# fechou em "…Falando que" e ela mandou o recado pela metade.
FIM_ABERTO = {"e", "mas", "porque", "que", "do", "da", "de", "dos", "das", "pra", "para",
              "o", "a", "os", "as", "um", "uma", "no", "na", "nos", "nas", "com", "em",
              "se", "quando", "tipo", "e", "eh", "entao", "ai", "ou", "pelo", "pela",
              "sobre", "como", "onde", "vao", "vou", "vai", "preciso", "quero", "queria",
              "gostaria", "meu", "minha", "seu", "sua", "esse",
              "essa", "aquele", "aquela"}   # "faz isso." e "fala com ela." fecham: ficam fora


def termina_aberto(texto: str) -> bool:
    """A fala parou no meio do pensamento (reticências, vírgula ou palavra aberta)?"""
    cru = texto.strip()
    if not cru:
        return False
    if cru.endswith(("...", "…", ",")):
        return True
    if cru.endswith("?"):
        return False
    palavras = _limpo(cru).split()
    return bool(palavras) and palavras[-1] in FIM_ABERTO


def inventado(texto: str) -> bool:
    """O Whisper, em som ruim, repete a mesma palavra: "suja, suja, suja, suja"."""
    palavras = _limpo(texto).split()
    seguidas = 1
    for a, b in zip(palavras, palavras[1:]):
        seguidas = seguidas + 1 if a == b else 1
        if seguidas >= 4:
            return True
    # "e ai, e ai, e ai, e ai": o mesmo par repetido
    pares = [" ".join(palavras[i:i + 2]) for i in range(0, len(palavras) - 1, 2)]
    return len(pares) >= 4 and len(set(pares)) == 1
