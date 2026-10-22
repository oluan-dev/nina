"""Tomada 1: o cérebro da Nina (`nina/cerebro.mjs`) no lugar do LLM do Pipecat.

O Pipecat entrega o contexto da conversa; o cérebro dela guarda a própria
conversa (sessão do Claude Code, pela assinatura), então só a última fala dele
vai. A resposta volta aos pedaços e segue para a voz como `LLMTextFrame`.
"""
from __future__ import annotations

import asyncio
import audioop
import json
import os
import random
import re
import sys
import time
import wave
from pathlib import Path

from loguru import logger
from pipecat.frames.frames import (BotStartedSpeakingFrame, BotStoppedSpeakingFrame,
                                   UserStartedSpeakingFrame,
                                   Frame, LLMContextFrame, LLMFullResponseEndFrame,
                                   LLMFullResponseStartFrame, LLMTextFrame,
                                   OutputAudioRawFrame, StartFrame)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from conversa import regras

RAIZ = Path(__file__).resolve().parent.parent
BORDOES = RAIZ / "bordoes"
MARCAS = "●◐○"          # protocolo de vez do cerebro.mjs: só ● é para falar
JANELA = 20             # s depois da última troca em que ela atende sem o nome.
                        # Com 60 ela respondia a conversa dele com outra pessoa;
                        # quem continua o assunto continua em poucos segundos.
REPETE_EM = 6           # s: o Whisper às vezes entrega a mesma fala duas vezes
ESPERA_ABERTA = 3.0     # s: frase que parou no meio espera a continuação
# Bancada e testes: nada no diário nem na faixa de verdade.
TESTE = os.environ.get("NINA_TESTE") == "1"
# Frases de espera, gravadas na voz dela (gerar_bordoes.py): quando o cérebro
# demora, ela avisa que está nisso em vez de sumir.
ESPERA = ((2.5, ("conferindo", "deixa-eu-olhar", "procurando", "um-instante")),
          (14.0, ("isso-demora",)))
ACENO, VOLUME_DO_ACENO = "hum", 0.35
REPETIDO = 600          # s: o mesmo aviso de sessão não se fala de novo


def som(nome: str, volume: float = 1.0) -> OutputAudioRawFrame | None:
    """Um bordão gravado (`bordoes/*.wav`, 24 kHz mono) pronto para tocar."""
    try:
        with wave.open(str(BORDOES / f"{nome}.wav"), "rb") as w:
            audio, taxa, canais = w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()
    except (OSError, wave.Error):
        return None
    if volume < 0.999:
        audio = audioop.mul(audio, 2, volume)
    return OutputAudioRawFrame(audio=audio, sample_rate=taxa, num_channels=canais)


def ultima_dela(mensagens: list) -> str:
    """O que ele OUVIU da última fala dela: o Pipecat guarda só o que saiu."""
    for m in reversed(mensagens):
        if m.get("role") == "assistant":
            c = m.get("content")
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            return str(c or "").strip()
    return ""


def anotar(linha: str) -> None:
    """O diário da conversa, em `diario/conversas.log` (fica só na máquina)."""
    from datetime import datetime

    if TESTE:
        return
    try:
        (RAIZ / "diario").mkdir(exist_ok=True)
        with (RAIZ / "diario" / "conversas.log").open("a", encoding="utf8") as f:
            print(f"{datetime.now():%H:%M:%S} {linha}", file=f)
    except OSError:
        pass


def legenda(texto: str, de: str) -> None:
    """A faixa embaixo da tela: é como ele sabe que ela ouviu certo."""
    if TESTE:
        return
    try:
        from nina import legenda as faixa

        faixa.mostrar(texto, de=de)
    except Exception as e:                      # faixa é bom, não essencial
        logger.debug(f"legenda falhou: {e}")


def pedido_de_entrega(recado: str) -> str:
    """O resultado de uma tarefa mandada a uma sessão, para o cérebro contar como gente."""
    return (f"[Isto acabou de chegar de uma tarefa que ele pediu: «{recado}». "
            "Conte a ele agora, em uma ou duas frases, como uma colega de "
            "trabalho contaria: o resultado primeiro, sem termo técnico, sem "
            "ler o texto. Se tiver detalhe, ofereça. Não use ferramenta "
            "nenhuma: só conte. Comece com ●.]")


def ultima_fala(mensagens: list) -> str:
    """O texto da última mensagem dele no contexto do Pipecat."""
    for m in reversed(mensagens):
        if m.get("role") != "user":
            continue
        conteudo = m.get("content")
        if isinstance(conteudo, list):
            conteudo = " ".join(p.get("text", "") for p in conteudo if isinstance(p, dict))
        return str(conteudo or "").strip()
    return ""


def falavel(texto: str) -> str:
    """Tira da fala o que não se fala: código, caminho, link, marcação, marcador."""
    texto = re.sub(r"```.*?```", " te mandei na tela. ", texto, flags=re.S)
    texto = re.sub(r"`[^`]+`", " isso aí na tela ", texto)
    texto = re.sub(r"https?://\S+", " o link tá na tela ", texto)
    texto = re.sub(r"[A-Za-z]:\\[\\\w .-]+", " o caminho tá na tela ", texto)
    texto = re.sub(r"[*#_>|" + MARCAS + "]", "", texto)
    return texto


class CerebroNina(FrameProcessor):
    def __init__(self) -> None:
        super().__init__()
        self._proc: asyncio.subprocess.Process | None = None
        self._eventos: asyncio.Queue = asyncio.Queue()
        self._em_aberto = 0        # perguntas mandadas sem "fim" de volta
        self._vez = asyncio.Lock()   # resposta a ele e entrega de sessão não se misturam
        self._vigiando = False
        self._ultimo = 0.0           # última troca com ele: abre a janela sem o nome
        self._surda = False          # "pera, Nina" até "voltei"
        self._licenca: int | None = None   # pergunta "posso?" esperando o sim dele
        self._ultima_resposta = ""   # o que ela GEROU; o contexto diz o que ele ouviu
        self._falou_em = 0.0         # hora da última fala dele que chegou aqui
        self._ultima_fala = ""
        self._cobranca = ""          # vai junto da próxima fala dele (Parlant)
        self._espera_texto = ""      # frase dele parada no meio, esperando o resto
        # τ-Voice: ela está falando? quando ele começou a falar por cima?
        self._ela_fala = False
        self._por_cima_em: float | None = None
        self._ja_avisou: dict[str, float] = {}   # aviso de sessão -> quando falou

    async def _ligar(self) -> None:
        if self._proc and self._proc.returncode is None:
            return
        self._proc = await asyncio.create_subprocess_exec(
            "node", str(RAIZ / "nina" / "cerebro.mjs"), cwd=str(RAIZ),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=1 << 20,
            # o cérebro chama `-m nina.sessoes` com este mesmo Python
            env={**os.environ, "NINA_PYTHON": sys.executable})
        self._em_aberto = 0
        self.create_task(self._ler(self._proc))

    async def _ler(self, proc) -> None:
        async for linha in proc.stdout:
            try:
                ev = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if ev.get("tipo") == "confirmar":
                # Coisa séria: ela pergunta e a próxima fala dele decide. Na voz
                # vai só "posso?" — ela já explicou com as palavras dela antes;
                # o detalhe técnico fica no diário (igual à Nina antiga). Sem
                # resposta em 2 min, o cerebro.mjs trata como não.
                anotar(f"NINA pergunta: {ev.get('oque')}")
                self._licenca = ev["id"]
                await self._dizer("Posso fazer isso?")
                continue
            await self._eventos.put(ev)

    async def cleanup(self):
        """Fecha o cérebro junto: node órfão segue vivo segurando a sessão."""
        await super().cleanup()
        if self._proc and self._proc.returncode is None:
            # A árvore inteira: o node abre o Claude, e fechar o stdin não basta
            # (o cerebro.mjs fica esperando a próxima pergunta para sempre).
            mata = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(self._proc.pid),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await mata.wait()
            await self._proc.wait()

    async def _drenar(self) -> None:
        """Resposta cortada pela metade ainda chega: joga fora até o "fim"."""
        while self._em_aberto > 0:
            if (await self._eventos.get()).get("tipo") == "fim":
                self._em_aberto -= 1

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            # Nascer custa ~8 s: que seja agora, não na primeira fala dele.
            await self._ligar()
            await self.push_frame(frame, direction)
            # Em teste, nunca: o vigia lê e ESVAZIA a caixa de recados de verdade.
            if not self._vigiando and not TESTE:
                self._vigiando = True
                self.create_task(self._vigiar_sessoes())
        elif isinstance(frame, LLMContextFrame):
            mensagens = frame.context.get_messages()
            texto = ultima_fala(mensagens)
            if texto:
                await self._atender(texto, ouviu=ultima_dela(mensagens))
        else:
            self._medir_turno(frame)
            await self.push_frame(frame, direction)

    def _medir_turno(self, frame: Frame) -> None:
        """As métricas de voz do τ-Voice, no diário: quantas vezes ele falou por
        cima dela e quanto ela demorou para calar."""
        if isinstance(frame, BotStartedSpeakingFrame):
            self._ela_fala = True
        elif isinstance(frame, UserStartedSpeakingFrame) and self._ela_fala:
            self._por_cima_em = self._por_cima_em or time.time()
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._ela_fala = False
            # A janela sem o nome conta de quando a voz dela PAROU de sair. Contava
            # de quando o cérebro terminou de escrever: numa resposta longa ele
            # respondia e ela achava que não era com ela.
            self._ultimo = time.time()
            if self._por_cima_em:
                anotar(f"(ele falou por cima — ela calou em "
                       f"{time.time() - self._por_cima_em:.1f}s)")
                self._por_cima_em = None

    async def _dizer(self, texto: str) -> None:
        """Frase pronta, sem passar pelo cérebro ("Tá.", "Posso fazer isso?")."""
        await self.push_frame(LLMFullResponseStartFrame())
        await self.push_frame(LLMTextFrame(texto))
        await self.push_frame(LLMFullResponseEndFrame())
        anotar(f"NINA: {texto}")
        legenda(texto, de="nina")

    async def _atender(self, texto: str, ouviu: str = "", inteira: bool = False) -> None:
        """Decide se a fala é com ela, e o que fazer — antes de ir ao cérebro.

        A resposta roda numa tarefa à parte: o Pipecat entrega uma fala por vez
        a este processador, e o "sim" de uma confirmação tem de chegar enquanto
        a resposta anterior ainda espera por ele.
        """
        agora = time.time()
        if regras.inventado(texto):
            # Som ruim (fone em modo de ligação) e o Whisper repete palavra.
            anotar(f"(o ouvido inventou — ignorei): {texto}")
            return
        if self._espera_texto:
            # Ele continuou a frase que tinha parado no meio: junta as duas.
            texto, self._espera_texto = f"{self._espera_texto} {texto}", ""
        elif texto == self._ultima_fala and agora - self._falou_em < REPETE_EM:
            # A mesma fala chegou duas vezes do ouvido: responde uma.
            anotar(f"(fala repetida pelo ouvido — ignorei): {texto}")
            return
        if not inteira and regras.termina_aberto(texto):
            # Parou no meio ("…falando que", "preciso.", "…"): espera ele
            # continuar, em vez de agir sobre meia frase.
            self._espera_texto = texto
            self._falou_em = agora
            anotar(f"(esperando ele terminar): {texto}")
            self.create_task(self._soltar_se_parou(texto, ouviu))
            return
        self._ultima_fala = texto
        self._falou_em = agora       # cancela um "Oi?" que esperava o resto da frase
        if self._licenca is not None:
            ok = regras.e_sim(texto)
            anotar(f"USUARIO responde: {texto!r} -> {'liberado' if ok else 'negado'}")
            self._proc.stdin.write((json.dumps({"confirmacao": self._licenca, "ok": ok}) + "\n").encode())
            await self._proc.stdin.drain()
            self._licenca, self._ultimo = None, agora
            if not ok:
                await self._dizer("Tá, deixa pra lá.")
            return
        from nina import atalho

        cmd = regras.comando(texto)
        if cmd == "voltar":
            self._surda, self._ultimo = False, agora
            atalho.marcar(False)
            await self._dizer("Voltei.")
            return
        if self._surda or atalho.surda():      # "pera, Nina" ou Ctrl+Alt+N
            anotar(f"(pediu para eu não ouvir — ignorei): {texto}")
            return
        if cmd == "calar":
            self._surda = True
            await self._dizer("Tá.")
            return
        if cmd == "parar":
            # Ele cortou para falar: a fala dela já parou (interrupção do
            # Pipecat). Ela fica quieta e ouvindo, sem "tá" por cima dele.
            self._ultimo = agora
            anotar("(parei de falar, sigo ouvindo)")
            return
        if cmd == "tchau":
            self._ultimo = 0.0          # fecha a janela: só volta pelo nome
            await self._dizer("Falou, tô por aqui.")
            return
        # Fala dele enquanto a voz dela sai, ou até JANELA s depois de ela
        # CALAR, é resposta a ela (não precisa do nome).
        if (not self._ela_fala and agora - self._ultimo > JANELA
                and not regras.chamou_por_ela(texto)):
            anotar(f"(não era comigo): {texto}")
            return
        recente = agora - self._ultimo < 4
        self._ultimo = agora
        if regras.so_o_nome(texto):
            # "Nina." e pausa: gente responde "oi?", não um parágrafo. Se ela
            # acabou de falar ("Voltei." e o Whisper separou o "Nina"), nada.
            # E espera 1,5 s: muitas vezes o resto da frase vem logo atrás.
            if not recente:
                self.create_task(self._oi_se_ficar_nisso(agora))
            return
        # O aceno: acusa NA HORA que ouviu, baixinho, antes de a resposta
        # existir (o silêncio é o que parece máquina).
        aceno = som(ACENO, VOLUME_DO_ACENO)
        if aceno:
            await self.push_frame(aceno)
        cortada = ""
        if (self._ultima_resposta and ouviu
                and len(ouviu) < 0.8 * len(self._ultima_resposta)):
            # Ele cortou a fala dela: a conversa guarda o que ele OUVIU, não o
            # que foi gerado (como faz o LiveKit Agents).
            cortada = (f"\n\n[Da sua última fala, ele só ouviu: «{ouviu[-300:]}». "
                       "O resto foi cortado e ele não sabe o que você ia dizer.]")
        self.create_task(self._preparar(texto, cortada))

    async def _preparar(self, texto: str, cortada: str) -> None:
        """Monta o pedido fora do caminho do áudio: o casamento pelo sentido vai
        ao Ollama (~50 ms), se ele estiver ligado."""
        extra = await asyncio.to_thread(self._o_que_ela_sabe, texto)
        extra += cortada
        if self._cobranca:
            # Parlant: na resposta anterior ela disse que fez, ou disse valor,
            # sem usar ferramenta — o cérebro confere e corrige se for o caso.
            extra += self._cobranca
            self._cobranca = ""
        await self._responder(texto + extra, esperar_com_som=True)

    async def _soltar_se_parou(self, texto: str, ouviu: str) -> None:
        """Frase aberta e ele não continuou em ESPERA_ABERTA s: vai assim mesmo."""
        await asyncio.sleep(ESPERA_ABERTA)
        if self._espera_texto == texto:
            self._espera_texto = ""
            await self._atender(texto, ouviu, inteira=True)

    async def _oi_se_ficar_nisso(self, quando: float) -> None:
        await asyncio.sleep(1.5)
        if self._falou_em == quando:           # nada veio depois do nome
            await self._dizer("Oi?")

    @staticmethod
    def _o_que_ela_sabe(fala: str) -> str:
        """O que ela mandou e espera, as regras curtas desta fala e — quando a
        fala é de sessão — os painéis abertos no Canteiro: sem eles ela gastava
        uma ida ao terminal só para descobrir os nomes."""
        from nina import diretrizes, sessoes

        espero = sessoes.linha_do_que_espero()
        extra = ("\n\n" + espero if espero else "") + diretrizes.linha(fala, sentido=True)
        if sessoes.fala_de_sessao(fala):
            paineis = sessoes.linha_dos_paineis()
            if paineis:
                extra += "\n\n" + paineis
        return extra

    async def _vigiar_sessoes(self) -> None:
        """Sessão que ela acionou terminou ou parou: ela conta sem ele perguntar.

        O vigia (`nina.sessoes.vigiar`) roda num fio: ele dorme 5 s entre uma
        olhada e outra e não pode travar a conversa.
        """
        import threading

        from nina import sessoes

        loop = asyncio.get_running_loop()
        chegou: asyncio.Queue = asyncio.Queue()
        threading.Thread(target=sessoes.vigiar, daemon=True, args=(
            lambda r: loop.call_soon_threadsafe(chegou.put_nowait, r),)).start()
        while True:
            recado = await chegou.get()
            # O mesmo "a sessão X parou" pode chegar várias vezes seguidas: um
            # aviso igual dentro de 10 min não se fala de novo.
            if time.time() - self._ja_avisou.get(recado, 0) < REPETIDO:
                logger.info(f"(aviso repetido, calei): {recado[:120]}")
                continue
            self._ja_avisou[recado] = time.time()
            logger.info(f"(resultado de sessão): {recado[:300]}")
            anotar(f"(resultado de sessão): {recado}")
            await self._responder(pedido_de_entrega(recado))
            sessoes.recados()          # já contou: sai da caixa

    async def _responder(self, texto: str, esperar_com_som: bool = False) -> None:
        async with self._vez:
            await self._responder_ja(texto, esperar_com_som)

    async def _esperar_com_som(self, chegou: asyncio.Event) -> None:
        """Cérebro demorando: uma frase de espera por degrau, nunca por cima dele."""
        inicio = time.time()
        for degrau, nomes in ESPERA:
            espera = degrau - (time.time() - inicio)
            try:
                await asyncio.wait_for(chegou.wait(), max(0.0, espera))
                return                     # a resposta começou: nada a dizer
            except asyncio.TimeoutError:
                pass
            frase = som(random.choice(nomes))
            if frase:
                anotar(f"(fala de espera): {nomes[0]}")
                await self.push_frame(frase)

    async def _responder_ja(self, texto: str, esperar_com_som: bool = False) -> None:
        await self._ligar()
        await self._drenar()
        self._em_aberto += 1
        self._proc.stdin.write((json.dumps({"pergunta": texto}) + "\n").encode())
        await self._proc.stdin.drain()
        fala = texto.split(chr(10) * 2)[0]
        logger.info(f"USUARIO: {fala[:300]}")
        if not fala.startswith("[Isto acabou de chegar"):
            anotar(f"USUARIO: {fala}")
            legenda(fala, de="usuario")
        inicio = time.time()
        chegou = asyncio.Event()       # primeiro sinal do cérebro: cala a espera
        espera = self.create_task(self._esperar_com_som(chegou)) if esperar_com_som else None
        await self.push_frame(LLMFullResponseStartFrame())
        marca, tudo, ferramentas = "", [], 0
        try:
            while True:
                ev = await self._eventos.get()
                if ev.get("tipo") == "fim":
                    self._em_aberto -= 1
                    ferramentas = ev.get("ferramentas", 0)
                    break
                if ev.get("tipo") != "pedaco":
                    continue
                pedaco = ev["texto"]
                if not marca:
                    nu = pedaco.lstrip()
                    if not nu:
                        continue
                    marca = nu[0] if nu[0] in MARCAS else "●"
                    pedaco = nu[1:] if nu[0] in MARCAS else nu
                    if marca != "●":
                        chegou.set()   # ◐/○: ela espera calada, sem bordão
                if pedaco.strip():
                    chegou.set()
                if marca != "●":
                    continue        # ◐/○: ele não terminou, ela não abre a boca
                tudo.append(pedaco)
                limpo = falavel(pedaco)
                if limpo.strip():
                    await self.push_frame(LLMTextFrame(limpo))
        finally:
            chegou.set()
            if espera:
                await self.cancel_task(espera)
            await self.push_frame(LLMFullResponseEndFrame())
            self._ultimo = time.time()      # a janela conta da fala DELA também
            resposta = "".join(tudo).strip()
            if resposta:
                self._ultima_resposta = falavel(resposta)
            if resposta and esperar_com_som and ferramentas == 0:
                # A checagem do Parlant depois da resposta (resposta a ELE; a
                # entrega de sessão traz o próprio valor no recado).
                from nina import diretrizes

                if diretrizes.afirma_acao(resposta) or diretrizes.fala_valor(resposta):
                    anotar(f"(afirmou ação ou valor sem ferramenta): {resposta[:120]}")
                    self._cobranca = (
                        "\n\n[Na sua última resposta você disse que fez algo, ou disse "
                        "um valor, sem usar ferramenta nesta volta. Se isso não veio "
                        "de uma ferramenta nesta conversa, corrija agora, em uma frase.]")
            logger.info(f"NINA {marca}: {resposta}")
            if resposta:
                anotar(f"NINA ({time.time() - inicio:.1f}s): {resposta}")
                legenda(resposta, de="nina")
            elif marca in "◐○":
                anotar(f"[{marca} o Claude diz que ele não terminou]")
