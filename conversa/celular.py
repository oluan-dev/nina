"""Tomada 3: o microfone do celular (scrcpy, `nina/microfone_celular.py`) como
entrada do Pipecat. O microfone do celular perto da boca entende melhor que o do fone.
"""
from __future__ import annotations

import asyncio
import audioop
import time

from loguru import logger
from pipecat.frames.frames import InputAudioRawFrame, StartFrame
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import TransportParams

from nina.microfone_celular import MicrofoneCelular

TAXA_SAIDA = 16000


class CelularEntrada(BaseInputTransport):
    def __init__(self, params: TransportParams) -> None:
        super().__init__(params)
        self._mic: MicrofoneCelular | None = None
        self._leitor = None

    async def start(self, frame: StartFrame):
        await super().start(frame)
        mic = MicrofoneCelular()
        if not await asyncio.to_thread(mic.ligar):
            raise RuntimeError("o microfone do celular não respondeu (cabo e depuração USB?)")
        self._mic = mic
        self._leitor = self.create_task(self._ler())
        await self.set_transport_ready(frame)

    async def _religar(self) -> MicrofoneCelular:
        """O cabo soltou: espera o celular voltar."""
        logger.warning("microfone do celular caiu — esperando o cabo voltar")
        await asyncio.to_thread(self._mic.desligar)
        while True:
            mic = MicrofoneCelular()
            if await asyncio.to_thread(mic.ligar):
                logger.info("microfone do celular de volta")
                self._mic = mic
                return mic
            await asyncio.sleep(3)

    async def _ler(self) -> None:
        mic = self._mic
        quadro = mic.canais * mic.largura
        pos = mic._tamanho()
        pos -= pos % quadro
        vinte_ms = int(mic.taxa * 0.02) * quadro
        estado = None
        calado_desde = time.time()
        while True:
            if mic._tamanho() - pos < vinte_ms:
                # O cano manda áudio sem parar, até silêncio. Dois segundos sem
                # nada é o scrcpy morto: religa em vez de ficar surda.
                parado = time.time() - calado_desde
                if (parado > 2 and not mic.no_ar()) or parado > 6:
                    mic = await self._religar()
                    quadro = mic.canais * mic.largura
                    pos = mic._tamanho() - mic._tamanho() % quadro
                    vinte_ms = int(mic.taxa * 0.02) * quadro
                    estado, calado_desde = None, time.time()
                await asyncio.sleep(0.01)
                continue
            calado_desde = time.time()
            bruto = mic._fatia(pos, pos + vinte_ms)
            pos += len(bruto)
            mic.pos = pos                 # deixa o mic soltar o que já foi lido
            mono = audioop.tomono(bruto, mic.largura, 0.5, 0.5) if mic.canais == 2 else bruto
            audio, estado = audioop.ratecv(mono, mic.largura, 1, mic.taxa, TAXA_SAIDA, estado)
            await self.push_audio_frame(InputAudioRawFrame(
                audio=audio, sample_rate=TAXA_SAIDA, num_channels=1))

    async def _parar(self) -> None:
        if self._leitor:
            await self.cancel_task(self._leitor)
            self._leitor = None
        if self._mic:
            await asyncio.to_thread(self._mic.desligar)
            self._mic = None

    async def stop(self, frame):
        await super().stop(frame)
        await self._parar()

    async def cancel(self, frame):
        await super().cancel(frame)
        await self._parar()
