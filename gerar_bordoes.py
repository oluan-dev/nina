"""Pré-grava as frases de espera da Nina na mesma voz da fala. Tocam em 0 s, de disco.

Precisam ser a MESMA voz da fala principal: voz diferente no bordão e na
resposta soa como remendo. Voz e velocidade vêm de `config.json`.

    python gerar_bordoes.py      grava em bordoes/*.wav (precisa de internet e ffmpeg)
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import edge_tts

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from conversa.voz import VELOCIDADE, VOZ  # noqa: E402

SAIDA = RAIZ / "bordoes"

BORDOES = {
    "ja-vejo": "Já vejo.",
    "deixa-eu-olhar": "Deixa eu olhar.",
    "um-instante": "Um instante.",
    "ta": "Tá.",
    "entendi-vou-ver": "Entendi, vou ver isso.",
    "procurando": "Tô procurando aqui.",
    "isso-demora": "Isso vai demorar um pouco, eu te aviso quando terminar.",
    "pensando": "Boa pergunta, deixa eu pensar.",
    "abrindo": "Abrindo aqui.",
    "conferindo": "Tô conferindo.",
    # aceno curto, tocado no instante em que a vez dele acaba
    "hum": "Hum.",
    "sei": "Sei.",
    "entendi": "Entendi.",
}

# O edge-tts devolve ~1,9 s mesmo para "Tá.": tira o silêncio do começo e do
# fim, deixa 80 ms de folga. Aceno com 1,7 s de silêncio atrasa a resposta.
APARAR = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
          "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
          "apad=pad_dur=0.08")


async def gerar(texto: str) -> bytes:
    com = edge_tts.Communicate(texto, VOZ, rate=VELOCIDADE)
    return b"".join([p["data"] async for p in com.stream() if p["type"] == "audio"])


async def principal() -> None:
    SAIDA.mkdir(exist_ok=True)
    for nome, texto in BORDOES.items():
        mp3 = await gerar(texto)
        destino = SAIDA / f"{nome}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", "pipe:0", "-af", APARAR,
             "-ar", "24000", "-ac", "1", str(destino)],
            input=mp3, check=True,
        )
        print(f"{nome}: ok ({destino.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    asyncio.run(principal())
