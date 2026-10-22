"""Tomada 2: a voz (edge-tts, nuvem da Microsoft) como TTS do Pipecat.

Em fluxo: o mp3 entra no ffmpeg conforme a Microsoft manda, e o áudio sai
tocando antes de a frase terminar de ser gerada. Voz e velocidade vêm do
`config.json` ("voz", "voz_velocidade").

Daqui sai metade da boca do rosto: a **forma**. O edge-tts manda, junto com o
áudio, o instante de cada palavra (`WordBoundary`), e `nina/visema.py` vira isso
em forma de boca. A outra metade — quando abre e quanto — sai do próprio som,
em `nina/boca.py`, que fica depois da saída de áudio no pipeline. Os tempos da
agenda contam do início do áudio desta fala, e lá se conta amostra tocada: as
duas pontas falam na mesma régua, sem relógio de parede.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import edge_tts
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService

from nina import boca, config, visema

VOZ = config.pegar("voz")
VELOCIDADE = config.pegar("voz_velocidade")
TAXA = 24000


class VozEdge(TTSService):
    def __init__(self, **kwargs) -> None:
        super().__init__(push_start_frame=True, push_stop_frames=True,
                         sample_rate=TAXA,
                         settings=TTSSettings(model=None, voice=VOZ, language=None),
                         **kwargs)

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        # Em fluxo: o mp3 entra no ffmpeg conforme a Microsoft manda, e o áudio
        # sai tocando antes de a frase terminar de ser gerada.
        ff = tarefa = None
        eventos: list[dict] = []

        def publicar() -> None:
            """Entrega a agenda de formas desta fala para `nina/boca.py`; reescreve
            a cada palavra nova, porque ela já começou a falar quando as últimas
            chegam."""
            boca.agendar(context_id, visema.agenda(eventos))

        try:
            await self.start_tts_usage_metrics(text)
            ff = await asyncio.create_subprocess_exec(
                "ffmpeg", "-v", "error", "-f", "mp3", "-i", "pipe:0", "-f", "s16le",
                "-ar", str(self.sample_rate), "-ac", "1", "pipe:1",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                creationflags=0x08000000)

            async def alimentar():
                try:
                    async for p in edge_tts.Communicate(
                            text, VOZ, rate=VELOCIDADE,
                            boundary="WordBoundary").stream():
                        if p["type"] == "audio":
                            ff.stdin.write(p["data"])
                            await ff.stdin.drain()
                        elif p["type"] == "WordBoundary":
                            eventos.append(p)
                            publicar()
                except (ConnectionResetError, BrokenPipeError):
                    pass            # fala cortada: o ffmpeg já foi fechado
                finally:
                    try:
                        ff.stdin.close()
                    except Exception:
                        pass

            tarefa = asyncio.create_task(alimentar())
            passo = self.sample_rate * 2 // 10          # 100 ms por quadro
            sobra = b""
            while True:
                pedaco = await ff.stdout.read(passo)
                if not pedaco:
                    break
                await self.stop_ttfb_metrics()
                sobra += pedaco
                corte = len(sobra) - len(sobra) % 2
                if corte:
                    # O context_id vai junto: é por ele que `nina/boca.py` sabe
                    # de qual fala é este som.
                    yield TTSAudioRawFrame(audio=sobra[:corte], sample_rate=self.sample_rate,
                                           num_channels=1, context_id=context_id)
                    sobra = sobra[corte:]
            await tarefa
        except Exception as e:
            yield ErrorFrame(error=f"voz falhou: {e}")
        finally:
            if tarefa and not tarefa.done():
                tarefa.cancel()
            if ff and ff.returncode is None:
                ff.kill()
            await self.stop_ttfb_metrics()
