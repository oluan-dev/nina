"""A faixa de legenda da Nina, embaixo da tela.

Mostra o que ela ouviu (cinza, "Você") e o que respondeu (claro, "Nina"). Serve
principalmente para o usuário saber que ela está ouvindo — sem isso ele fala sem
saber se ela pegou.

O balão é desenhado num canvas com canto arredondado de verdade: a janela é
transparente por cor-chave, então não existe a moldura preta retangular que
havia antes, e ele aparece e sai em fade. Fica sempre no mesmo lugar: faixa
centralizada embaixo da tela, fora do caminho do que ele está lendo.

    python -m nina.legenda        teste: mostra as duas linhas
"""
from __future__ import annotations

import ctypes
import queue
import threading
import time
from ctypes import wintypes

_fila: "queue.Queue[tuple[str, str | None] | None]" = queue.Queue()
_ligada = False

SEGUNDOS_NA_TELA = 7.0

# Cor-chave: o Windows apaga tudo que for exatamente este tom, e é assim que o
# canto arredondado aparece. Tem de ser uma cor que não exista no desenho.
COR_VAZIO = "#ff00fe"

# Um balão por voz: ela clara, ele azul. Dá pra saber quem falou de relance,
# sem ler o nome.
PALETA = {
    "nina": {"fundo": "#f7f7f5", "borda": "#d8d8d2",
             "texto": "#14141c", "nome": "#c2603c"},
    "usuario": {"fundo": "#1d4ed8", "borda": "#3b6ae8",
             "texto": "#eef2ff", "nome": "#bfd0ff"},
}

LIMITE = 240                # texto maior que isso vira parede na tela

FONTE = ("Segoe UI", 13)
FONTE_NOME = ("Segoe UI Semibold", 9)
LARGURA_MAX = 340
MARGEM_X, MARGEM_Y = 18, 12
# O estilo de filme: faixa preta translúcida embaixo da tela, sem nome e sem
# rabicho, letra grande centralizada.
# Fundo translúcido em vez da faixa preta: uma janela só
# de fundo, semitransparente, e o texto numa janela por cima com opacidade cheia.
# O acrílico do Windows foi testado e recusado: borra tanto que parece opaco.
# A cor-chave é escura para a borda suavizada da letra não sair rosa.
COR_FILME = {"nina": "#f4f4f5", "usuario": "#c7ccd4"}
CHAVE_FILME = "#1a1a1e"
COR_FUNDO_FILME = "#202024"
OPACIDADE_FUNDO = 0.45      # 0 = invisível, 1 = faixa sólida
PADDING_X, PADDING_Y = 28, 14
LARGURA_FILME = 0.70        # fração da largura da tela que o texto ocupa

RAIO = 16
RABICHO = 11
ALPHA_CHEIO = 0.96

_user32 = ctypes.windll.user32


def _curto(texto: str) -> str:
    """O balão é um balão, não um documento: corta no fim de uma frase."""
    texto = " ".join(texto.split())
    if len(texto) <= LIMITE:
        return texto
    corte = texto[:LIMITE]
    fim = max(corte.rfind(". "), corte.rfind("? "), corte.rfind("! "))
    if fim > LIMITE // 2:
        return corte[:fim + 1] + " …"
    return corte.rsplit(" ", 1)[0] + " …"


def mostrar(texto: str, de: str = "nina") -> None:
    """Põe uma linha no balão. `de` é 'nina' ou 'usuario'."""
    if texto and texto.strip():
        _fila.put((de, _curto(texto.strip())))


def pensando(de: str = "nina") -> None:
    """Balão de três pontinhos: ela está pensando, ainda não tem resposta.
    Fica na tela até a próxima fala."""
    _fila.put((de, None))


def fechar() -> None:
    _fila.put(None)


def _retangulo_redondo(tela, x1, y1, x2, y2, r, **kw):
    """Canto arredondado sem imagem: um polígono com os cantos suavizados.
    `smooth=True` faz o tk curvar nos pontos repetidos de cada esquina."""
    pontos = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return tela.create_polygon(pontos, smooth=True, splinesteps=24, **kw)


def _janela() -> None:
    import tkinter as tk

    from . import config
    ESTILO = config.pegar("legenda", "balao")
    FONTE_FILME = ("Segoe UI", config.pegar("legenda_tamanho", 20))
    ALTURA = config.pegar("legenda_altura", 140)    # px acima do pé da tela
    chave = CHAVE_FILME if ESTILO == "filme" else COR_VAZIO

    raiz = tk.Tk()
    raiz.withdraw()
    fundo = None
    if ESTILO == "filme":
        fundo = tk.Toplevel(raiz)
        fundo.overrideredirect(True)
        fundo.attributes("-topmost", True)
        fundo.configure(bg=COR_FUNDO_FILME)
        fundo.attributes("-alpha", 0.0)
        fundo.withdraw()
    balao = tk.Toplevel(raiz)
    balao.overrideredirect(True)
    balao.attributes("-topmost", True)
    balao.configure(bg=chave)
    balao.attributes("-transparentcolor", chave)
    balao.attributes("-alpha", 0.0)

    tela = tk.Canvas(balao, bg=chave, highlightthickness=0, bd=0)
    tela.pack()

    tela_l = balao.winfo_screenwidth()
    tela_a = balao.winfo_screenheight()
    estado = {"some_em": 0.0, "alvo": 0.0, "alpha": 0.0, "tam": (0, 0),
              "pontos": [], "cor_ponto": "#14141c", "passo": 0}

    def desenhar_balao(de: str, frase: str | None) -> None:
        """Monta o balão do tamanho exato do texto e devolve nada: o tamanho
        fica em estado['tam'], que o posicionar() usa. `frase` None = pensando."""
        tela.delete("all")
        cor = PALETA.get(de, PALETA["nina"])
        estado["pontos"] = []
        nome = "Nina" if de == "nina" else "Você"
        t_nome = tela.create_text(MARGEM_X, MARGEM_Y, text=nome, anchor="nw",
                                  font=FONTE_NOME, fill=cor["nome"])
        topo = tela.bbox(t_nome)[3] + 4
        if frase is None:
            t_frase = None
            for i in range(3):
                x = MARGEM_X + i * 18
                estado["pontos"].append(
                    tela.create_oval(x, topo + 4, x + 10, topo + 14,
                                     fill=cor["texto"], outline="")
                )
        else:
            t_frase = tela.create_text(MARGEM_X, topo, text=frase, anchor="nw",
                                       font=FONTE, width=LARGURA_MAX,
                                       fill=cor["texto"])
        _, _, x2, y2 = tela.bbox("all")
        larg, alt = x2 + MARGEM_X, y2 + MARGEM_Y
        corpo = _retangulo_redondo(tela, 1, 1, larg - 1, alt, RAIO,
                                   fill=cor["fundo"], outline=cor["borda"], width=1)
        meio = larg // 2
        rabicho = tela.create_polygon(
            meio - 9, alt - 2, meio + 9, alt - 2, meio, alt + RABICHO - 2,
            fill=cor["fundo"], outline=cor["fundo"],
        )
        tela.tag_lower(rabicho)
        tela.tag_lower(corpo)
        tela.tag_raise(t_nome)
        for item in ([t_frase] if t_frase else estado["pontos"]):
            tela.tag_raise(item)
        tela.configure(width=larg, height=alt + RABICHO)
        estado["tam"] = (larg, alt + RABICHO)

    def desenhar_filme(de: str, frase: str | None) -> None:
        """Legenda de cinema: letra grande clara centralizada. O fundo fosco é
        a janela `fundo`, não um desenho aqui."""
        tela.delete("all")
        estado["pontos"] = []
        cor = COR_FILME.get(de, COR_FILME["nina"])
        if frase is None:
            for i in range(3):
                x = PADDING_X + i * 26
                estado["pontos"].append(
                    tela.create_oval(x, PADDING_Y, x + 14, PADDING_Y + 14,
                                     fill=cor, outline=""))
        else:
            tela.create_text(PADDING_X, PADDING_Y, text=frase, anchor="nw",
                             font=FONTE_FILME, width=int(tela_l * LARGURA_FILME),
                             justify="center", fill=cor)
        _, _, x2, y2 = tela.bbox("all")
        larg, alt = x2 + PADDING_X, y2 + PADDING_Y
        tela.configure(width=larg, height=alt)
        estado["tam"] = (larg, alt)

    desenhar = desenhar_filme if ESTILO == "filme" else desenhar_balao

    def posicionar() -> None:
        larg, alt = estado["tam"]
        if not larg:
            return
        x, y = (tela_l - larg) // 2, tela_a - alt - ALTURA
        x = max(8, min(x, tela_l - larg - 8))
        y = max(8, min(y, tela_a - alt - 8))
        balao.geometry(f"{larg}x{alt}+{x}+{y}")
        if fundo is not None:
            fundo.geometry(f"{larg}x{alt}+{x}+{y}")

    def bater() -> None:
        try:
            while True:
                item = _fila.get_nowait()
                if item is None:
                    raiz.destroy()
                    return
                de, frase = item
                desenhar(de, frase)
                estado["cor_ponto"] = PALETA.get(de, PALETA["nina"])["texto"]
                posicionar()
                if fundo is not None:
                    fundo.deiconify()
                balao.deiconify()
                balao.lift()
                # pensando não tem prazo: fica até ela ter o que dizer
                estado["some_em"] = time.time() + (
                    600.0 if frase is None else SEGUNDOS_NA_TELA)
                estado["alvo"] = ALPHA_CHEIO
        except queue.Empty:
            pass

        if estado["some_em"]:
            if time.time() > estado["some_em"]:
                estado["alvo"] = 0.0
                estado["some_em"] = 0.0
            else:
                posicionar()

        # os três pontinhos pulsando, um de cada vez
        if estado["pontos"]:
            estado["passo"] = (estado["passo"] + 1) % 12
            aceso = estado["passo"] // 3
            for i, ponto in enumerate(estado["pontos"]):
                tela.itemconfigure(ponto, fill=estado["cor_ponto"],
                                   stipple="" if i == aceso else "gray50")

        # fade: o balão nunca aparece nem some de supetão
        atual, alvo = estado["alpha"], estado["alvo"]
        if atual != alvo:
            passo = 0.16 if alvo > atual else -0.10
            atual = max(0.0, min(ALPHA_CHEIO, atual + passo))
            if abs(atual - alvo) < 0.02:
                atual = alvo
            estado["alpha"] = atual
            balao.attributes("-alpha", atual)
            if fundo is not None:
                fundo.attributes("-alpha", atual / ALPHA_CHEIO * OPACIDADE_FUNDO)
            if atual == 0.0:
                balao.withdraw()
                if fundo is not None:
                    fundo.withdraw()
        raiz.after(60, bater)

    balao.withdraw()
    raiz.after(60, bater)
    raiz.mainloop()


def ligar() -> None:
    """Sobe o balão num fio à parte. A conversa nunca espera por ele."""
    global _ligada
    if _ligada:
        return
    _ligada = True
    threading.Thread(target=_janela, daemon=True).start()


if __name__ == "__main__":
    ligar()
    time.sleep(1)
    mostrar("Nina, o que tem pra hoje?", de="usuario")
    time.sleep(4)
    mostrar("Duas tarefas: revisar o texto e responder o e-mail da tarde.")
    time.sleep(9)
    fechar()
