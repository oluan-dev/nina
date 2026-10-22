"""A boca da Nina, tirada do som que está tocando agora.

A versão anterior marcava a hora na *geração* da fala e mandava a página tocar
essa agenda pelo relógio. Funcionava na primeira frase e desandava na segunda:
o Pipecat gera a frase 2 enquanto a 1 ainda toca, então a 2 entrava adiantada,
corria sozinha e a boca congelava. Era o "só funciona por 5 segundos".

Agora não há relógio. Este processador fica **depois** de `saida.output()` no
pipeline, e o transporte só empurra o quadro adiante depois de escrever o áudio
na placa (base_output.py, linhas 1042-1050). Ou seja: o que chega aqui é o som
que acabou de sair da caixa. Contando amostras por `context_id` temos a posição
exata dentro da frase, sem relógio de parede e sem nada para calibrar.

Divisão de trabalho, e o motivo de cada metade:

- **Quanto a boca abre** vem da força do som. Medido, não chutado.
- **Qual a forma** vem da letra (`visema.py`). Tentei tirar do som também: as
  faixas de frequência não separam as vogais nessa voz (o /a/ mediu brilho
  0,05–0,34 e cobre o /i/ inteiro, que mede 0,24–0,33). A letra acerta de graça.
"""
from __future__ import annotations

import json
import numpy as np
from pathlib import Path

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame, Frame, OutputAudioRawFrame, TTSStoppedFrame)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

BOCA = Path(__file__).resolve().parent.parent / "diario" / "boca.json"

# Medido na voz Francisca (+18%), frase real: silêncio fica abaixo de
# ~350, fala forte bate ~6400, pico absoluto ~10900. Se a boca abrir de menos,
# baixe o TETO; se ficar escancarada o tempo todo, suba.
PISO, TETO = 350.0, 6500.0

# Quanto a boca precisa abrir para sair de fechada e de fresta. Abaixo do
# primeiro ela fecha (silêncio entre palavras), e é isso que dá o ritmo.
FRESTA, ABERTA = 0.10, 0.30

# Suavização: sem isto a boca treme a cada 10 ms. Alto demais e ela fica mole.
LISO = 0.45

GRAVACAO = 1 / 30       # no máximo 30 escritas por segundo: a página não lê mais que isso


# As agendas de forma, por fala. `VozFrancisca` registra, daqui a gente lê.
# Processo é o mesmo, então é só um dicionário - não precisa de arquivo.
_agendas: dict[str, list] = {}


def agendar(context_id: str, agenda: list) -> None:
    """Guarda a agenda de formas de uma fala, para casar com o som depois."""
    _agendas[context_id] = agenda
    if len(_agendas) > 16:                 # fala antiga não volta
        del _agendas[next(iter(_agendas))]


def forca(pcm: bytes) -> float:
    """A força do som neste pedaço, normalizada em 0..1."""
    if len(pcm) < 2:
        return 0.0
    a = np.frombuffer(pcm[:len(pcm) - len(pcm) % 2], dtype=np.int16).astype(np.float32)
    rms = float(np.sqrt((a * a).mean()))
    return min(1.0, max(0.0, (rms - PISO) / (TETO - PISO)))


def forma_em(agenda: list, t: float) -> str | None:
    """A forma da letra no instante `t` da fala, ou None se não há agenda.

    None e "M" são coisas diferentes e foi confundi-las que travou a boca
    fechada: sem agenda isto devolvia "M", `escolher` lia como "lábio colado"
    e fechava a boca mesmo com o som a 0,79.
    """
    if not agenda:
        return None
    forma = "M"
    for quando, qual in agenda:
        if t >= quando:
            forma = qual
        else:
            break
    return forma


def escolher(abertura: float, da_letra: str | None) -> str:
    """Junta as duas metades: o som manda no quanto, a letra manda no qual."""
    if abertura < FRESTA:
        return "M"                  # silêncio: fecha. É daqui que vem o ritmo.
    if da_letra == "M":
        return "M"                  # m, b, p: lábio colado mesmo havendo som
    if abertura < ABERTA:
        return "S"
    # Sem agenda a boca ainda abre no ritmo certo, só não sabe a forma exata.
    # Parada é pior que genérica.
    return da_letra or "AH"


class Rastro:
    """Acompanha o som tocado e diz a boca de agora.

    Sem Pipecat de propósito: dá para alimentar com áudio na mão e conferir o
    resultado (é o que `_autoteste` faz), inclusive o caso que estava quebrado —
    duas falas seguidas com `context_id` diferente.
    """

    def __init__(self) -> None:
        self.fala: str | None = None
        self.amostras = 0
        self.abertura = 0.0
        self.com_agenda = False         # só para diagnóstico, sai no boca.json

    def ouvir(self, pcm: bytes, taxa: int, fala: str | None) -> tuple[str, float]:
        if fala != self.fala:                   # fala nova: recomeça a contagem
            self.fala, self.amostras = fala, 0

        self.abertura += (forca(pcm) - self.abertura) * LISO

        # Posição exata dentro desta fala, em amostras tocadas. É isto que
        # substitui o relógio: não tem como adiantar nem atrasar.
        t = self.amostras / taxa
        self.amostras += len(pcm) // 2

        agenda = _agendas.get(fala or "", [])
        self.com_agenda = bool(agenda)
        return escolher(self.abertura, forma_em(agenda, t)), self.abertura

    def fechar(self) -> tuple[str, float]:
        self.abertura = 0.0
        return "M", 0.0


class Boca(FrameProcessor):
    """Põe no `diario/boca.json` a boca do som que está tocando agora.

    Vai no pipeline logo **depois** de `saida.output()`. Antes dele não serve:
    ali o áudio ainda não foi tocado.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rastro = Rastro()
        self._ultima_escrita = 0.0
        self._ultima_forma = ""

    def _escrever(self, forma: str, abertura: float, forcado: bool = False) -> None:
        agora = self.get_event_loop().time()
        if not forcado and forma == self._ultima_forma and agora - self._ultima_escrita < GRAVACAO:
            return
        self._ultima_escrita, self._ultima_forma = agora, forma
        try:
            BOCA.parent.mkdir(parents=True, exist_ok=True)
            BOCA.write_text(json.dumps({
                "forma": forma,
                "abertura": round(abertura, 2),
                # Diagnóstico: de qual fala é este som e se a agenda de formas
                # foi encontrada. Sem agenda a boca abre no ritmo certo mas só
                # faz AH - é o sinal de que o context_id não casou.
                "fala": self._rastro.fala,
                "com_agenda": self._rastro.com_agenda,
            }), encoding="utf8")
        except OSError:
            pass                    # rosto sem boca é melhor que Nina sem voz

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, OutputAudioRawFrame) and frame.audio:
            forma, abertura = self._rastro.ouvir(
                frame.audio, frame.sample_rate or 24000,
                getattr(frame, "context_id", None))
            self._escrever(forma, abertura)

        elif isinstance(frame, (BotStoppedSpeakingFrame, TTSStoppedFrame)):
            self._escrever(*self._rastro.fechar(), forcado=True)

        await self.push_frame(frame, direction)


def _autoteste() -> None:
    import struct

    def tom(rms: float, n: int = 480) -> bytes:
        return struct.pack(f"<{n}h", *([int(rms)] * n))

    assert forca(b"") == 0.0
    assert forca(tom(0)) == 0.0, "silêncio tem de dar zero"
    assert forca(tom(300)) == 0.0, "abaixo do piso ainda é silêncio"
    assert forca(tom(20000)) == 1.0, "acima do teto satura em 1"
    meio = forca(tom(int((PISO + TETO) / 2)))
    assert 0.45 < meio < 0.55, f"meio do caminho deu {meio}"

    agenda = [[0.0, "M"], [0.2, "AH"], [0.5, "O"]]
    assert forma_em(agenda, 0.0) == "M"
    assert forma_em(agenda, 0.3) == "AH"
    assert forma_em(agenda, 9.9) == "O", "depois do fim, segura a última"
    assert forma_em([], 1.0) is None, "sem agenda é None, não M"

    assert escolher(0.02, "AH") == "M", "silêncio fecha, mesmo a letra pedindo AH"
    assert escolher(0.90, "M") == "M", "m/b/p fecha, mesmo com som alto"
    assert escolher(0.20, "AH") == "S", "som fraco é fresta"
    assert escolher(0.90, "O") == "O"

    # O que já travou a boca fechada: sem agenda, com som alto, ela tem
    # de abrir assim mesmo. Fechar era ler "não sei" como "lábio colado".
    assert escolher(0.79, None) == "AH", "sem agenda e som alto: abre"
    assert escolher(0.02, None) == "M", "sem agenda e silêncio: fecha"
    assert escolher(0.20, None) == "S", "sem agenda e som fraco: fresta"

    # O caso que estava quebrado: duas falas seguidas. A segunda tem de começar
    # do zero, não continuar contando de onde a primeira parou - era isso que
    # fazia a boca congelar depois da primeira frase.
    agendar("fala-1", [[0.0, "AH"]])
    agendar("fala-2", [[0.0, "O"]])
    r = Rastro()
    alto = tom(9000, 2400)                      # 100 ms de som forte a 24 kHz
    for _ in range(10):
        r.ouvir(alto, 24000, "fala-1")
    assert r.amostras == 24000, f"1 s de fala-1 deu {r.amostras} amostras"
    assert r.ouvir(alto, 24000, "fala-1")[0] == "AH"

    forma, _ = r.ouvir(alto, 24000, "fala-2")   # troca de fala no meio do som
    assert r.amostras == 2400, "fala nova tem de recomeçar a contagem"
    assert forma == "O", f"fala-2 devia dar O, deu {forma}"

    assert r.fechar() == ("M", 0.0)
    _agendas.clear()

    print("boca: ok")
    print(f"  silêncio<{PISO:.0f}  fresta>{FRESTA}  aberta>{ABERTA}  teto {TETO:.0f}")


if __name__ == "__main__":
    _autoteste()
