"""O microfone do fone, aberto só quando ele vai falar.

Microfone de fone Bluetooth aberto põe o fone inteiro no modo "mãos-livres" (o
de ligação, 16 kHz): música, vídeo, tudo fica ruim. Com o fone ligado o dia todo
na Nina, o som do computador fica ruim o dia todo. Então o microfone
fica FECHADO; Ctrl+Alt+N abre, e ele fecha sozinho depois de um tempo sem
conversa (ou na mesma tecla). Fechado de verdade — o stream é destruído, não só
pausado: pausado, o Windows mantém o fone no modo mãos-livres.
"""
from __future__ import annotations

import asyncio
import time

import pyaudio
from loguru import logger
from pipecat.frames.frames import InputAudioRawFrame, StartFrame
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import TransportParams


class FoneSobDemanda(BaseInputTransport):
    def __init__(self, params: TransportParams) -> None:
        super().__init__(params)
        self._pa = pyaudio.PyAudio()
        self._stream = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.aberto_em = 0.0

    @property
    def aberto(self) -> bool:
        return self._stream is not None

    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._loop = self.get_event_loop()
        await self.set_transport_ready(frame)

    def _chegou(self, dados, quadros, info, estado):
        if self._loop:
            asyncio.run_coroutine_threadsafe(self.push_audio_frame(InputAudioRawFrame(
                audio=dados, sample_rate=self.sample_rate, num_channels=1)), self._loop)
        return (None, pyaudio.paContinue)

    def abrir(self) -> bool:
        """Abre o microfone padrão do Windows (pode vir de outro fio: a tecla)."""
        if self._stream:
            return True
        try:
            self._stream = self._pa.open(
                format=pyaudio.paInt16, channels=1, rate=self.sample_rate, input=True,
                frames_per_buffer=self.sample_rate // 50, stream_callback=self._chegou)
            self._stream.start_stream()
            self.aberto_em = time.time()
            logger.info("microfone aberto")
            return True
        except Exception as e:
            self._stream = None
            logger.error(f"não abriu o microfone: {e}")
            return False

    def fechar(self) -> None:
        stream, self._stream = self._stream, None
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            logger.info("microfone fechado — o fone volta ao som normal")

    async def stop(self, frame):
        await super().stop(frame)
        self.fechar()

    async def cancel(self, frame):
        await super().cancel(frame)
        self.fechar()
