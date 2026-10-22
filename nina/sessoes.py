"""As sessões do Claude Code no Canteiro: a Nina vê todas, digita nelas e acompanha.

O Canteiro (https://github.com/oluan-dev/canteiro) é uma extensão do VS Code em
que cada painel é uma sessão do Claude Code, com nome, pasta e conversa. A Nina
conversa com essa extensão por dois arquivos numa pasta, e é só isso:

1. **Mandar** — ela escreve `estado/_entrada.json`; a extensão digita o texto no
   terminal da sessão e aperta ENTER. **O usuário vê chegar e vê a sessão
   responder.** A confirmação volta em `_entrada.ack.json`: sem ack, não houve envio.
2. **Acompanhar** — o relator da extensão grava `<painel>.evento.json` quando a
   sessão termina de responder (`respondeu`) ou quando ela espera o usuário
   (`atencao`), já com o caminho do transcrito. É empurrão, não espiar tela: a
   Nina sabe no instante em que qualquer das sessões para.

A pasta da extensão é `%APPDATA%/Code/User/globalStorage/<id da extensão>`; o id
vem de `config.json` ("canteiro_extensao", padrão "oluan-dev.canteiro").

    python -m nina.sessoes                           lista o que está na tela
    python -m nina.sessoes --mandar <chave> "texto"   digita na sessão
    python -m nina.sessoes --ler <chave>              as últimas falas dela
    python -m nina.sessoes --achar <chave>            quais sessões casam
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
import unicodedata
import uuid
import sys
from pathlib import Path

from nina import config

# Nada do que a Nina roda pode piscar janela de console na tela.
SEM_JANELA = 0x08000000      # CREATE_NO_WINDOW

CANTEIRO = (Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
            / "Code" / "User" / "globalStorage" / config.pegar("canteiro_extensao"))
ESTADO = CANTEIRO / "estado"
ENTRADA = ESTADO / "_entrada.json"
ACK = ESTADO / "_entrada.ack.json"

TEMPO_LISTA = 40
TEMPO_PROMPT = 300
TEMPO_ACK = 8          # a extensão responde em milissegundos; 8 s é folga


def nome_limpo(nome: str | None) -> str:
    """O nome do painel sem o sinal de estado na frente.

    O Canteiro põe ✳ ◐ ◑ ⑂ no título. Ela FALA esse nome em voz alta, e esses
    sinais não se falam — e ainda estouravam o console do Windows (cp1252).
    """
    return str(nome or "").lstrip("✳◐◑●○⑂ ").strip()


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto).lower())
                   if unicodedata.category(c) != "Mn")


def _rodar(cmd: list[str], tempo: int, pasta: str | None = None) -> tuple[str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=tempo, cwd=pasta,
                       creationflags=SEM_JANELA)
    return r.stdout or "", r.stderr or ""


# ------------------------------------------------- falar com a extensão


def _pedir(pedido: dict, tempo: int = TEMPO_ACK) -> dict:
    """Entrega um pedido à extensão e espera o ack dela.

    O ack antigo é apagado antes de pedir, e o novo tem de trazer o id deste
    pedido. Sem isso ela leria a confirmação da vez anterior e diria "mandei".
    """
    if not ESTADO.exists():
        return {"ok": False,
                "erro": "o Canteiro não está rodando (a pasta de estado não existe)"}
    marca = uuid.uuid4().hex[:8]
    for arquivo in (ACK, ENTRADA):
        try:
            arquivo.unlink()
        except OSError:
            pass
    try:
        ENTRADA.write_text(json.dumps({**pedido, "id": marca}, ensure_ascii=False),
                           encoding="utf8")
    except OSError as erro:
        return {"ok": False, "erro": f"não deu para escrever o pedido: {erro}"}

    limite = time.time() + tempo
    while time.time() < limite:
        try:
            resposta = json.loads(ACK.read_text(encoding="utf8"))
        except (OSError, json.JSONDecodeError):
            time.sleep(0.1)
            continue
        if resposta.get("pedido") == marca:
            try:
                ACK.unlink()
            except OSError:
                pass
            return resposta
        time.sleep(0.1)
    return {"ok": False, "erro": "o Canteiro não respondeu: o VS Code está aberto?"}


def _do_layout() -> list[dict]:
    """As sessões como o último layout salvo as conhece.

    Rede de segurança para quando o VS Code está fechado: serve para contar a
    ele o que existia, nunca para afirmar que mandou.
    """
    arquivos = sorted(CANTEIRO.glob("layout-*.json"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    if not arquivos:
        return []
    try:
        d = json.loads(arquivos[0].read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        return []

    achadas: list[dict] = []

    def descer(no, guia):
        if not isinstance(no, dict):
            return
        if no.get("tipo") == "sessao":
            achadas.append({"id": no.get("id", ""), "nome": no.get("nome") or guia,
                            "pasta": no.get("pasta", ""),
                            "conversa": no.get("conversa", ""),
                            "transcrito": no.get("transcrito", "")})
            return
        for filho in no.get("filhos") or []:
            descer(filho, guia)

    for canteiro in d.get("canteiros") or []:
        for guia in canteiro.get("guias") or []:
            descer(guia.get("raiz"), guia.get("nome", ""))
    return achadas


def na_tela() -> list[dict]:
    """Toda sessão aberta num painel, com o nome que ele vê na tela."""
    resposta = _pedir({"oque": "listar"}, tempo=4)
    if resposta.get("ok"):
        return resposta.get("sessoes") or []
    return _do_layout()


def candidatos(chave: str) -> list[dict]:
    """As sessões que casam com a chave, da mais provável à menos.

    Quem decide de verdade é a extensão, que sabe quais estão vivas; isto serve
    para a Nina CONTAR as opções a ele quando houver dúvida.
    """
    k = _sem_acento(chave).strip()
    if not k:
        return []
    notas = []
    for s in na_tela():
        nota = 0
        if s.get("id") == chave or str(s.get("conversa", "")).startswith(chave):
            nota = 100
        elif k in _sem_acento(s.get("nome", "")):
            nota = 60
        elif k in _sem_acento(s.get("pasta", "")):
            nota = 30
        if nota:
            notas.append((nota, s))
    notas.sort(key=lambda x: -x[0])
    return [s for _, s in notas]


def achar(chave: str) -> dict | None:
    lista = candidatos(chave)
    if lista:
        return lista[0]
    # nenhum painel casa: pode ser o id da conversa de agora, que o painel
    # ainda não sabe que é dele
    return _por_id_de_conversa(chave)


# ------------------------------------------------------------- o transcrito


PROJETOS = Path.home() / ".claude" / "projects"


def _pasta_do_projeto(pasta: str) -> Path:
    """A pasta onde o Claude grava as conversas de um projeto.

    Ele troca tudo o que não é letra nem número por "-": "C:\\Projetos\\Meu
    App" vira "C--Projetos-Meu-App".
    """
    import re
    return PROJETOS / re.sub(r"[^A-Za-z0-9]", "-", str(pasta).rstrip("\\/"))


def _seguir_continuacao(arq: Path, voltas: int = 8) -> Path:
    """Segue a conversa até o arquivo em que ela está AGORA.

    Quando a conversa é compactada, o Claude fecha o arquivo e abre outro, e o
    antigo fica com uma linha `continued-in` apontando para o novo. O Canteiro
    guarda o id de quando a sessão NASCEU, então o caminho que ele tem envelhece
    sozinho: sem seguir a corrente, `--ler` respondia "ainda não tem conversa
    gravada" com a conversa viva noutro arquivo, ao lado.
    """
    visto = {arq.stem}
    while voltas > 0 and arq.exists():
        voltas -= 1
        proximo = ""
        try:
            with arq.open(encoding="utf8", errors="replace") as f:
                for linha in f:
                    # prefiltro de texto: o arquivo tem milhares de linhas e só
                    # esta interessa
                    if '"continued-in"' not in linha:
                        continue
                    try:
                        d = json.loads(linha)
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") == "continued-in":
                        proximo = d.get("continuedInSessionId") or ""
        except OSError:
            break
        if not proximo or proximo in visto:
            break
        seguinte = arq.parent / f"{proximo}.jsonl"
        if not seguinte.exists():
            break
        visto.add(proximo)
        arq = seguinte
    return arq


def _tem_conversa(caminho: str) -> bool:
    return bool(caminho) and bool(_falas(caminho, 1))


def _por_titulo(pasta: str, nome: str) -> str:
    """A conversa do projeto cujo TÍTULO é o nome do painel.

    Rede para quando a corrente `continued-in` arrebenta: o elo do meio pode não
    ter arquivo nenhum (pasta de histórico sem nenhum `.jsonl`). O título
    sobrevive: o Claude grava
    `<id>/custom-title.json`, e é de lá que sai o nome do painel no Canteiro,
    então os dois casam.
    """
    alvo = _sem_acento(nome_limpo(nome))
    if not alvo or not pasta:
        return ""
    raiz = _pasta_do_projeto(pasta)
    if not raiz.exists():
        return ""
    melhor, quando = "", 0.0
    for titulo in raiz.glob("*/custom-title.json"):
        try:
            escrito = json.loads(titulo.read_text(encoding="utf8")).get("customTitle", "")
        except (OSError, json.JSONDecodeError):
            continue
        if _sem_acento(nome_limpo(escrito)) != alvo:
            continue
        arq = raiz / f"{titulo.parent.name}.jsonl"
        try:
            idade = arq.stat().st_mtime
        except OSError:
            continue
        if idade > quando:                 # o mesmo título pode ter várias voltas
            melhor, quando = str(arq), idade
    return melhor


def transcrito_de(sessao: dict) -> str:
    """O arquivo da conversa de um painel, resolvido na hora de ler.

    Nunca confiar no caminho guardado: ele vale no nascimento da sessão e
    envelhece na primeira compactação. Três tentativas, da mais exata para a
    menos: a corrente de continuação, o título do painel, e o que foi guardado.
    """
    bruto = sessao.get("transcrito") or ""
    if not bruto and sessao.get("conversa") and sessao.get("pasta"):
        bruto = str(_pasta_do_projeto(sessao["pasta"]) / f"{sessao['conversa']}.jsonl")
    seguido = str(_seguir_continuacao(Path(bruto))) if bruto else ""
    if _tem_conversa(seguido):
        return seguido

    pelo_titulo = _por_titulo(sessao.get("pasta", ""), sessao.get("nome", ""))
    if pelo_titulo:
        resolvido = str(_seguir_continuacao(Path(pelo_titulo)))
        if _tem_conversa(resolvido):
            return resolvido
    return seguido or bruto


def _por_id_de_conversa(chave: str) -> dict | None:
    """A conversa pelo id, mesmo que nenhum painel diga que é dele.

    Ela às vezes tem na mão o id que leu na tela ("ad0067da"), e esse id é o da
    conversa de AGORA — justamente o que o painel ainda não sabe.
    """
    chave = str(chave or "").strip()
    if len(chave) < 6 or not PROJETOS.exists():
        return None
    for arq in PROJETOS.glob(f"*/{chave}*.jsonl"):
        return {"id": "", "nome": f"conversa {chave}", "pasta": "",
                "conversa": arq.stem, "transcrito": str(arq)}
    return None


def _falas(transcrito: str, quantas: int = 6) -> list[tuple[str, str]]:
    """As últimas falas da conversa, como ("ele"|"sessao", texto).

    O `.jsonl` da sessão tem dezenas de tipos de linha (anexo, custo, título);
    só `user` e `assistant` são conversa.
    """
    caminho = Path(transcrito) if transcrito else None
    if not caminho or not caminho.exists():
        return []
    try:
        linhas = caminho.read_text(encoding="utf8", errors="replace").splitlines()
    except OSError:
        return []

    falas: list[tuple[str, str]] = []
    for linha in reversed(linhas):
        if len(falas) >= quantas:
            break
        try:
            d = json.loads(linha)
        except json.JSONDecodeError:
            continue
        if d.get("type") not in ("user", "assistant"):
            continue
        conteudo = (d.get("message") or {}).get("content")
        if isinstance(conteudo, str):
            pedacos = [conteudo]
        else:
            pedacos = [c.get("text", "") for c in (conteudo or [])
                       if isinstance(c, dict) and c.get("type") == "text"]
        texto = " ".join(p.strip() for p in pedacos if p and p.strip())
        if texto:
            falas.append(("ele" if d["type"] == "user" else "sessao", texto))
    return list(reversed(falas))


def ultima_resposta(transcrito: str) -> str:
    """O que a sessão respondeu por último. Vazio se ela ainda não falou."""
    for quem, texto in reversed(_falas(transcrito, 10)):
        if quem == "sessao":
            return texto
    return ""


def resposta_para(transcrito: str, enviado: str) -> tuple[str, bool]:
    """A resposta ao prompt QUE ELA mandou, e se é dela mesmo.

    O relator só diz "a sessão parou"; ele não diz a quem a sessão respondeu. Se
    o usuário digitar naquele painel logo depois dela, a última resposta é à
    pergunta DELE — e ela contaria isso como se fosse o retorno da tarefa.
    Então o casamento é pelo texto: acha a última fala do painel que começa com
    o que ela enviou e pega o que veio depois.
    """
    falas = _falas(transcrito, 30)
    chave = " ".join(str(enviado or "").split())[:40]
    corte = -1
    if chave:
        for i, (quem, texto) in enumerate(falas):
            if quem == "ele" and chave in " ".join(texto.split()):
                corte = i
    if corte < 0:
        return ultima_resposta(transcrito), False
    # Só o que a sessão falou DENTRO da vez dela: para na próxima fala do usuário.
    # Sem esse limite, uma conversa que seguiu no painel devolvia a resposta de
    # outro assunto como se fosse o retorno da tarefa.
    dentro = []
    for quem, texto in falas[corte + 1:]:
        if quem == "ele":
            break
        dentro.append(texto)
    return (dentro[-1] if dentro else ""), True


def ler(chave: str, quantas: int = 6) -> str:
    alvo = achar(chave)
    if not alvo:
        return f"não achei sessão com '{chave}'."
    falas = _falas(transcrito_de(alvo), quantas)
    if not falas:
        return (f"a sessão {nome_limpo(alvo.get('nome')) or chave} ainda não "
                f"tem conversa gravada.")
    return chr(10).join(f"{'USUARIO' if q == 'ele' else 'SESSAO'}: {t[:400]}"
                        for q, t in falas)


def resumo() -> str:
    linhas = []
    for s in na_tela():
        evento = _evento(s.get("id", "")) or {}
        # Sem evento nenhum ela NÃO sabe o estado: o relator só grava quando a
        # sessão para. Dizer "trabalhando" ali era chute.
        estado = {"atencao": "esperando ele",
                  "respondeu": "respondeu e parou"}.get(evento.get("tipo", ""),
                                                        "sem sinal ainda")
        linhas.append(f"[{s.get('id','')}] {nome_limpo(s.get('nome'))} "
                      f"({Path(s.get('pasta','')).name}) — {estado}")
    for s in sessoes_de_fundo():
        linhas.append(f"[{s['id'][:8]}] {s['assunto']} (de fundo, {s['estado']})")
    return chr(10).join(linhas) or "Nenhuma sessão aberta."


# ------------------------------------------------------ sessões sem painel


def sessoes_de_fundo() -> list[dict]:
    """As sessões de fundo (`claude --bg`), que não têm painel no Canteiro."""
    saida, _ = _rodar(["claude", "agents", "--json"], TEMPO_LISTA)
    try:
        cruas = json.loads(saida)
    except json.JSONDecodeError:
        return []
    return [{
        "id": s.get("sessionId", ""),
        "projeto": s.get("cwd", "").rstrip("\\/").split("\\")[-1].split("/")[-1],
        "assunto": s.get("name") or "",
        # as de fundo dizem `state`, as interativas dizem `status`: lendo só
        # `status` ela chamava "parada" uma sessão que estava trabalhando.
        "estado": s.get("state") or s.get("status") or "aberta",
        "pasta": s.get("cwd", ""),
    } for s in cruas if s.get("kind") == "background"]


def mandar_por_dentro(id_sessao: str, texto: str, pasta: str | None = None) -> str:
    """Entrega o prompt numa sessão sem painel e traz a resposta.

    Três coisas precisam estar certas, senão a sessão recebe o pedido e não
    consegue fazer nada:

    1. **rodar na pasta dela** (`cwd`), senão o Claude abre na pasta da Nina;
    2. **liberar a pasta** com `--add-dir`, porque a permissão é por diretório;
    3. **deixar editar sem perguntar** (`--permission-mode acceptEdits`): em modo
       sem tela não existe ninguém para clicar em "permitir", então toda escrita
       era negada em silêncio.
    """
    comando = ["claude", "--resume", id_sessao]
    if pasta:
        comando += ["--add-dir", pasta]
    comando += ["--permission-mode", "acceptEdits", "-p", texto]
    saida, erro = _rodar(comando, TEMPO_PROMPT, pasta)
    return (saida or erro).strip()


# ----------------------------------------------------------------- mandar


def mandar(chave: str, texto: str, esperar_resposta: bool = False) -> str:
    """Digita o prompt na sessão que ele escolheu e volta na hora.

    Só devolve MANDEI com a confirmação da extensão na mão. Dizer "mandei" sem
    ack é o pior defeito dela: ele fica esperando à toa.
    """
    resposta = _pedir({"alvo": chave, "texto": texto})
    if resposta.get("ok"):
        anotar_pendencia({**resposta, "enviado": texto})
        pasta = Path(resposta.get("pasta", "")).name
        return (f"MANDEI na sessão {nome_limpo(resposta.get('nome')) or chave} ({pasta}) — "
                f"ele vê o texto chegar. Eu aviso quando ela responder.")

    outras = resposta.get("sessoes") or []
    if "mais de uma" in str(resposta.get("erro", "")):
        lista = "; ".join(f"[{o.get('id','')}] {nome_limpo(o.get('nome'))}" for o in outras[:4])
        return (f"DUVIDA: '{chave}' casa com mais de uma sessão: {lista}. "
                f"Pergunte ao usuário qual é e mande pelo id.")

    # Sem painel: pode ser sessão de fundo. Aí vale o caminho de dentro, que
    # não tem confirmação nenhuma — e ela precisa dizer isso a ele.
    fundo = next((s for s in sessoes_de_fundo()
                  if _sem_acento(chave) in _sem_acento(s["assunto"] + " " + s["projeto"])
                  or (chave and s["id"].startswith(chave))), None)
    if fundo:
        if esperar_resposta:
            devolta = mandar_por_dentro(fundo["id"], texto, fundo["pasta"] or None)
            return f"mandei por dentro de {fundo['projeto']}. Resposta:{chr(10)}{devolta}"
        threading.Thread(target=mandar_por_dentro,
                         args=(fundo["id"], texto, fundo["pasta"] or None),
                         daemon=True).start()
        return (f"SEM CONFIRMACAO: tentei por fora, na sessão de fundo "
                f"{fundo['assunto']}. Diga ao usuário que você TENTOU e ainda não "
                f"tem confirmação.")

    # O painel existe, mas a aba dele está fechada: depois de recarregar a
    # janela só montam as abas que ele abriu de fato. Dizer o NOME do painel economiza a ida e volta de "qual?".
    k = _sem_acento(chave)
    fechado = next((s for s in _do_layout()
                    if k and (k in _sem_acento(s.get("nome", ""))
                              or k in _sem_acento(s.get("pasta", "")))), None)
    if fechado:
        return (f"ABA FECHADA: o painel {nome_limpo(fechado['nome'])} existe, mas a "
                f"aba dele não está aberta no VS Code. Peça ao usuário para abrir "
                f"essa aba que você manda na hora.")

    nomes = ", ".join(nome_limpo(o.get("nome")) for o in outras[:6])
    return (f"NÃO MANDEI: {resposta.get('erro', 'sem resposta do Canteiro')}."
            + (f" Abertos agora: {nomes}." if nomes else ""))


# ------------------------------------------- acompanhar sem ele pedir

PENDENCIAS = Path(__file__).resolve().parent.parent / "memoria" / "pendencias.json"


def _pendencias() -> list[dict]:
    try:
        return json.loads(PENDENCIAS.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        return []


def linha_do_que_espero(agora_ms: int | None = None) -> str:
    """O que ela mandou e ainda espera, numa linha para ir em cada fala.

    É daqui que sai a resposta a "o que você está fazendo?". Sem isto ela
    respondia de cabeça — e já inventou trabalho que não existia.
    """
    agora_ms = agora_ms or int(time.time() * 1000)
    partes = []
    for p in _pendencias():
        minutos = max(0, round((agora_ms - p.get("quando", agora_ms)) / 60_000))
        pedido = str(p.get("enviado", "")).replace("Pedido por voz:", "").strip()
        partes.append(f"«{p.get('nome') or p.get('id')}» há {minutos} min ({pedido[:80]})")
    if not partes:
        return ""
    return "[O que você mandou e ainda espera: " + "; ".join(partes) + "]"


def _gravar_pendencias(lista: list[dict]) -> None:
    PENDENCIAS.parent.mkdir(exist_ok=True)
    PENDENCIAS.write_text(json.dumps(lista[-12:], ensure_ascii=False), encoding="utf8")


def anotar_pendencia(enviada: dict) -> None:
    """Guarda que mandou algo e ainda não contou o resultado a ele.

    Guarda o id do painel e o transcrito, não só o nome: era o nome que ficava
    aqui, e com ele não havia como saber se a sessão respondeu.
    """
    lista = _pendencias()
    lista.append({
        "id": enviada.get("id", ""),
        "nome": nome_limpo(enviada.get("nome")),
        "transcrito": enviada.get("transcrito", ""),
        # o texto enviado é o que prova que a resposta é a DELA, não a de um
        # prompt que o usuário digitou no mesmo painel depois
        "enviado": enviada.get("enviado", ""),
        "quando": enviada.get("quando") or int(time.time() * 1000),
    })
    _gravar_pendencias(lista)


def _evento(painel: str) -> dict | None:
    """O último recado do relator sobre esse painel."""
    if not painel:
        return None
    try:
        return json.loads((ESTADO / f"{painel}.evento.json").read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        return None


RECADOS = Path(__file__).resolve().parent.parent / "memoria" / "recados.json"


def guardar_recado(texto: str, assunto: str = "") -> None:
    """Põe o resultado numa caixa de entrada que sobrevive à legenda.

    A legenda fica 7 s na tela e corta em 240 caracteres: se ele estiver
    digitando noutro painel naquele instante, o resultado se perdia para sempre
    e, quando ele perguntava, ela não sabia do que ele falava. Agora o recado
    espera em disco até entrar na próxima conversa.
    """
    try:
        lista = json.loads(RECADOS.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        lista = []
    lista.append({"texto": texto, "assunto": assunto, "quando": time.time()})
    RECADOS.parent.mkdir(exist_ok=True)
    RECADOS.write_text(json.dumps(lista[-10:], ensure_ascii=False), encoding="utf8")


def recados(limpar: bool = True) -> list[dict]:
    """Os recados que ela ainda não contou a ele. Ler consome, por padrão."""
    try:
        lista = json.loads(RECADOS.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        return []
    # Recado de mais de duas horas não se conta mais: ele já virou outra coisa.
    lista = [r for r in lista if time.time() - r.get("quando", 0) < 7200]
    if limpar and lista:
        try:
            RECADOS.write_text("[]", encoding="utf8")
        except OSError:
            pass
    return lista


# Verbos e palavras que querem dizer "outra sessão". Quando a fala dele tem um
# destes, a lista de painéis abertos vai junto no pedido ao cérebro: sem isso
# ela gastava uma ida ao terminal para descobrir os nomes e outra para desfazer
# a DUVIDA entre dois painéis do mesmo projeto.
FALA_DE_SESSAO = (
    "manda", "mande", "mandar", "pede", "peca", "peça", "pedir", "avisa",
    "avise", "pergunta", "pergunte", "fala la", "fala lá", "sessao", "sessão",
    "painel", "aba", "conversa do", "claude", "conferir com", "cobra",
)


def fala_de_sessao(texto: str) -> bool:
    k = _sem_acento(texto)
    return any(_sem_acento(p) in k for p in FALA_DE_SESSAO)


def linha_dos_paineis() -> str:
    """Os painéis abertos agora, numa linha, para ir no pedido ao cérebro."""
    try:
        abertos = na_tela()
    except Exception:
        return ""
    if not abertos:
        return ""
    nomes = "; ".join(f"{nome_limpo(s.get('nome'))} (pasta {Path(s.get('pasta','')).name})"
                      for s in abertos[:14])
    return (f"[Painéis abertos agora, pelo nome que ele vê: {nomes}. "
            f"Use o nome inteiro em --mandar, sem precisar de --achar.]")


def vigiar(avisar, intervalo: int = 5) -> None:
    """Acena quando uma sessão termina de responder ou para esperando ele.

    Tarefa mandada é dela: o usuário não precisa perguntar se terminou. O relator da
    extensão grava o evento no instante em que a sessão para; aqui é só ver se o
    evento é mais novo do que o que ela mandou.
    """
    while True:
        time.sleep(intervalo)
        lista = _pendencias()
        if not lista:
            continue
        restantes = []
        for p in lista:
            if time.time() * 1000 - p["quando"] > 3_600_000:   # uma hora: desisto calada
                continue
            evento = _evento(p["id"])
            if not evento or evento.get("quando", 0) <= p["quando"]:
                restantes.append(p)
                continue
            nome = p.get("nome") or p["id"]
            # o caminho do evento é o mais novo que existe, mas até ele envelhece
            # se a conversa compactar depois: resolve na hora, sempre
            transcrito = transcrito_de({
                "transcrito": evento.get("transcrito") or p.get("transcrito", ""),
            })
            if evento.get("tipo") == "atencao":
                aviso = evento.get("mensagem") or "está esperando você"
                recado = f"a sessão {nome} parou e {aviso}"
                guardar_recado(recado, nome)
                avisar(recado)
            elif evento.get("tipo") == "respondeu":
                texto, e_dela = resposta_para(transcrito, p.get("enviado", ""))
                if not e_dela and texto:
                    # A sessão respondeu a outra coisa (ele digitou no painel
                    # depois dela). Não é o retorno da tarefa: continua esperando.
                    restantes.append(p)
                    continue
                # 4.000 e não 400: cortado, ela dizia "a mensagem chegou
                # cortada, não sei o resto"
                recado = (f"a sessão {nome} terminou: {texto[:4000]}" if texto
                          else f"a sessão {nome} terminou de responder")
                guardar_recado(recado, nome)
                avisar(recado)
            else:
                restantes.append(p)
        if len(restantes) != len(lista):
            _gravar_pendencias(restantes)


# O bloco de linha de comando fica NO FIM de proposito: ele estava no
# meio do arquivo e, rodando como `python -m nina.sessoes`, as funcoes
# definidas depois dele ainda nao existiam. Ela entregava o recado e
# estourava NameError logo em seguida, dizendo que tinha mandado.

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="sessões do Claude Code no Canteiro")
    p.add_argument("--mandar", nargs=2, metavar=("CHAVE", "TEXTO"))
    p.add_argument("--esperar", action="store_true",
                   help="só para sessão de fundo: espera a resposta (demora)")
    p.add_argument("--ler", metavar="CHAVE")
    p.add_argument("--achar", metavar="CHAVE", help="quais sessões casam com a chave")
    a = p.parse_args()       # a saída já é UTF-8: ver nina/__init__.py

    if a.mandar:
        print(mandar(a.mandar[0], a.mandar[1], esperar_resposta=a.esperar))
    elif a.achar:
        for c in candidatos(a.achar)[:8]:
            print(f"[{c.get('id','')}] {nome_limpo(c.get('nome'))} "
                  f"({Path(c.get('pasta','')).name})")
    elif a.ler:
        print(ler(a.ler))
    else:
        print(resumo())
        sys.exit(0)
