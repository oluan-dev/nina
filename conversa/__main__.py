"""A Nina sobre o Pipecat. A conversa é do Pipecat; ela só pensa e fala.

    python -m conversa                  microfone do celular (sem cabo, o do Windows)
    python -m conversa --fone           microfone padrão do Windows
    python -m conversa --deixar-cortar  deixa interromper a fala dela
    python -m conversa --sob-demanda    (com --fone) só abre o microfone no Ctrl+Alt+N

Por padrão ela NÃO é interrompida enquanto fala: o microfone do celular ouve a
caixa de som, e a voz dela a cortaria. Com fone de ouvido, `--deixar-cortar`
liga a interrupção (exige 2 palavras dele, para tecla e tosse não cortarem).
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import InputAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair, LLMUserAggregatorParams)
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy
from pipecat.turns.user_start.min_words_user_turn_start_strategy import (
    MinWordsUserTurnStartStrategy)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from conversa.cerebro import CerebroNina
from conversa.voz import VozEdge

RAIZ = Path(__file__).resolve().parent.parent
LOG = RAIZ / "diario" / "conversa.log"

logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(LOG, level="INFO", encoding="utf8", rotation="5 MB")


def celular_no_cabo() -> bool:
    import subprocess

    try:
        from nina.microfone_celular import ADB

        saida = subprocess.run([str(ADB), "devices"], capture_output=True, text=True,
                               timeout=10, creationflags=0x08000000).stdout
    except Exception:
        return False
    return any(l.strip().endswith("\tdevice") for l in saida.splitlines()[1:])


def microfone_do_windows() -> bool:
    import pyaudio

    p = pyaudio.PyAudio()
    try:
        p.get_default_input_device_info()
        return True
    except OSError:
        return False
    finally:
        p.terminate()


TRAVA = RAIZ / "nina.lock"     # a mesma do nina-sempre.ps1


def so_uma_nina() -> None:
    """Duas Ninas disputam o microfone e falam uma por cima da outra."""
    import os

    try:
        antigo = int(TRAVA.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        antigo = 0
    if antigo and antigo != os.getpid():
        import subprocess

        vivo = subprocess.run(["tasklist", "/FI", f"PID eq {antigo}", "/NH"],
                              capture_output=True, text=True,
                              creationflags=0x08000000).stdout
        if "python" in vivo.lower():
            logger.error(f"Já tem uma Nina ligada (processo {antigo}). Feche a outra antes.")
            sys.exit(3)                 # o conversa.cmd não religa com 3
    TRAVA.write_text(str(os.getpid()))


class VigiaDoMicrofone(FrameProcessor):
    """O microfone manda som sem parar, até silêncio. Parou por 10 s, morreu:
    o fone dormiu ou caiu do Bluetooth e ela ficou surda sem ninguém saber. Fecha com erro e o conversa.cmd religa, reabrindo o mic."""

    def __init__(self, fone=None) -> None:
        super().__init__()
        self._ultimo = time.time()
        self._vigiando = False
        self._fone = fone        # microfone sob demanda: fechado não é "morreu"

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            self._ultimo = time.time()
            if not self._vigiando:
                self._vigiando = True
                self.create_task(self._vigiar())
        await self.push_frame(frame, direction)

    async def _vigiar(self) -> None:
        while True:
            await asyncio.sleep(2)
            if self._fone is not None:
                if not self._fone.aberto:
                    continue
                desde = max(self._ultimo, self._fone.aberto_em)
            else:
                desde = self._ultimo
            if time.time() - desde > 10:
                logger.error("microfone parou de mandar som há 10 s — religando a Nina")
                os._exit(2)


def parametros_do_turno(deixar_cortar: bool) -> LLMUserAggregatorParams:
    """Quando a vez dele começa e termina — o mesmo para a Nina e para os testes.

    - Fim: 1 s de silêncio antes de perguntar "ele terminou?"; o padrão de
      0,2 s fechava a vez em toda pausa de pensar.
    - Começo, com fone: o PRIMEIRO som de voz dele corta a fala dela. Antes
      exigia 2 palavras transcritas, e o Whisper só transcreve depois que ele
      termina — ela falava por cima da frase inteira e a dele entrava atrasada.
      Com o fone a voz dela não vaza para o microfone. 0,2 s de voz
      seguida (o padrão): com 0,3 s o "Nina," curto e a pausa depois zeravam a
      conta e ela só calava 1,3 s depois.
    - Sem fone (celular e caixa de som), ela não ouve enquanto fala: senão a
      própria voz a cortaria.
    - Fim: o smart-turn v3 do Pipecat. Se existir um modelo ajustado em
      `modelos/smart-turn-pt.onnx`, usa ele; sem o arquivo, o original.
    """
    from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
    from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

    ajustado = RAIZ / "modelos" / "smart-turn-pt.onnx"
    fim = [TurnAnalyzerUserTurnStopStrategy(turn_analyzer=LocalSmartTurnAnalyzerV3(
        smart_turn_model_path=str(ajustado) if ajustado.exists() else None))]
    turnos = UserTurnStrategies(stop=fim)              # começo por VAD (e por texto)
    mudo = [] if deixar_cortar else [AlwaysUserMuteStrategy()]
    return LLMUserAggregatorParams(
        vad_analyzer=SileroVADAnalyzer(params=VADParams(start_secs=0.2, stop_secs=1.0)),
        user_turn_strategies=turnos, user_mute_strategies=mudo)


def ligar_tecla_do_microfone(fone, cerebro, faixa, loop) -> None:
    """Ctrl+Alt+N abre o microfone (e ela atende sem o nome); a mesma tecla, ou
    JANELA segundos sem conversa, fecha — e o fone volta ao som normal."""
    import threading

    from conversa.cerebro import JANELA, anotar, som
    from nina import atalho

    def tecla(_surda) -> None:
        atalho.marcar(False)          # aqui a tecla abre/fecha o mic, não ensurdece
        if fone.aberto:
            fone.fechar()
            faixa.mostrar("parei de ouvir", de="nina")
            anotar("(microfone fechado na tecla)")
            return
        if fone.abrir():
            cerebro._ultimo = time.time()            # pode falar sem dizer "Nina"
            faixa.mostrar("ouvindo…", de="nina")
            anotar("(microfone aberto na tecla)")
            aviso = som("hum", 0.6)
            if aviso:                                # depois de o fone trocar de modo
                threading.Timer(0.8, lambda: asyncio.run_coroutine_threadsafe(
                    cerebro.push_frame(aviso), loop)).start()

    def fechar_sozinho() -> None:
        while True:
            time.sleep(1)
            parado = time.time() - max(cerebro._ultimo, fone.aberto_em)
            if (fone.aberto and parado > JANELA and not cerebro._ela_fala
                    and not cerebro._vez.locked()):
                fone.fechar()
                faixa.mostrar("parei de ouvir (Ctrl+Alt+N abre)", de="nina")
                anotar("(microfone fechado: sem conversa)")

    atalho.vigiar(tecla)
    threading.Thread(target=fechar_sozinho, daemon=True).start()


async def main() -> None:
    so_uma_nina()
    fone = "--fone" in sys.argv
    if fone and not microfone_do_windows():
        logger.error("Pediu --fone, mas o Windows não tem microfone.")
        sys.exit(1)
    if not fone and not celular_no_cabo():
        if microfone_do_windows():
            logger.warning("celular fora do cabo: usando o microfone padrão do Windows")
            fone = True
        else:
            # Subir dizendo "ouvindo" sem ter de onde ouvir deixa ela muda sem
            # ninguém saber por quê.
            logger.warning("Sem microfone: ligue o celular no cabo (depuração USB). Esperando…")
            while not celular_no_cabo():
                await asyncio.sleep(3)
    # Interromper só é seguro quando a voz dela não volta pelo microfone: com
    # microfone de fone (o do Windows) a voz sai no ouvido dele.
    # No celular a caixa de som vaza e ela se cortaria sozinha.
    deixar_cortar = ("--deixar-cortar" in sys.argv
                     or (fone and "--sem-cortar" not in sys.argv))
    # Microfone de fone aberto o tempo todo deixa o som do computador ruim
    # (Bluetooth em modo mãos-livres). "--sob-demanda" só abre no Ctrl+Alt+N;
    # o padrão é ouvir sempre.
    sob_demanda = fone and "--sob-demanda" in sys.argv
    logger.info(f"microfone: {'Windows' if fone else 'celular'}"
                f"{' (só no Ctrl+Alt+N)' if sob_demanda else ''}; "
                f"interromper: {'sim' if deixar_cortar else 'não'}")

    # A faixa de legenda embaixo da tela e o Ctrl+Alt+N que tira e devolve o
    # ouvido dela.
    from nina import atalho, legenda as faixa

    faixa.ligar()
    # O rosto: flutuando no canto da tela e em http://localhost:4790/rosto,
    # com a boca mexendo junto da voz (nina/boca.py escreve diario/boca.json).
    from nina import rosto_flutuante, rosto_web

    rosto_flutuante.ligar()
    rosto_web.ligar()
    atalho.marcar(False)
    if not sob_demanda:
        atalho.vigiar(lambda surda: faixa.mostrar(
            "não estou ouvindo (Ctrl+Alt+N volta)" if surda else "voltei a ouvir", de="nina"))

    saida = LocalAudioTransport(LocalAudioTransportParams(
        audio_in_enabled=fone and not sob_demanda, audio_out_enabled=True))
    if sob_demanda:
        from conversa.fone import FoneSobDemanda
        entrada = FoneSobDemanda(TransportParams(audio_in_enabled=True,
                                                 audio_in_sample_rate=16000))
    elif fone:
        entrada = saida.input()
    else:
        from conversa.celular import CelularEntrada
        entrada = CelularEntrada(TransportParams(audio_in_enabled=True,
                                                 audio_in_sample_rate=16000))

    # Nomes próprios que o Whisper deve reconhecer (config.json, "nomes"). Só
    # no `hotwords`: com `initial_prompt` o Whisper repete palavra em fala curta.
    from nina import config

    stt = WhisperSTTService(
        device=config.pegar("whisper_device"), compute_type=config.pegar("whisper_compute"),
        settings=WhisperSTTService.Settings(
            model=config.pegar("whisper_modelo"), language=Language.PT,
            hotwords=config.pegar("nomes") or None))

    contexto = LLMContext()
    do_usuario, da_nina = LLMContextAggregatorPair(
        contexto, user_params=parametros_do_turno(deixar_cortar))

    # Boca() vai DEPOIS de saida.output(): o transporte escreve o áudio na placa
    # e só então empurra o quadro adiante, então o que chega nela é o som que
    # acabou de tocar. Antes da saída a boca desencontraria da voz.
    from nina.boca import Boca

    cerebro = CerebroNina()
    pipeline = Pipeline([
        entrada, VigiaDoMicrofone(entrada if sob_demanda else None), stt,
        do_usuario, cerebro, VozEdge(), saida.output(), Boca(), da_nina,
    ])
    if sob_demanda:
        ligar_tecla_do_microfone(entrada, cerebro, faixa, asyncio.get_running_loop())
    # idle_timeout_secs=None: de fábrica o Pipecat desliga tudo depois de 5 min
    # sem conversa — feito para chamada telefônica, não para quem fica ligada
    # o dia inteiro.
    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True),
                            idle_timeout_secs=None)
    runner = WorkerRunner()
    await runner.add_workers(worker)
    logger.info("Nina (Pipecat) ouvindo. Ctrl+C encerra.")
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
