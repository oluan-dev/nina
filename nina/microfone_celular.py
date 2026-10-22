"""Microfone do celular em tempo real: um rio de áudio, por cano.

O scrcpy (com `--audio-source=mic`) fica ligado o tempo todo e entrega o áudio
cru num CANO NOMEADO do Windows; `conversa/celular.py` lê daqui e passa ao
Pipecat. Precisa de `adb` e `scrcpy` (NINA_ADB / NINA_SCRCPY, ou no PATH) e do
celular no cabo com depuração USB ligada.

Por que cano e não arquivo: escrevendo num arquivo WAV o scrcpy entrega em
blocos de 256 KiB — 1,4 s de áudio por escrita, um piso de mais de um segundo
na reação dela. No cano, o mesmo áudio chega em pedaços de 4 KiB a cada ~20 ms.
O caminho do arquivo continua como reserva, se o cano não subir.
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import threading
import tempfile
import time
from pathlib import Path


# Nada do que a Nina roda pode piscar janela de console na tela.
SEM_JANELA = 0x08000000      # CREATE_NO_WINDOW

# adb e scrcpy: variável de ambiente, senão o que estiver no PATH.
ADB = Path(os.environ.get("NINA_ADB") or shutil.which("adb") or "adb")
SCRCPY = Path(os.environ.get("NINA_SCRCPY") or shutil.which("scrcpy") or "scrcpy")

# Quanto áudio guardar na memória atrás da posição de leitura; o resto é solto
# para não crescer sozinha num dia inteiro (192 KB/s).
GUARDAR_ATRAS = 4.0
# Quanto áudio jogar fora logo depois de abrir o microfone, para o ganho do
# aparelho assentar.
DESCARTAR_NO_INICIO = 0.6


class MicrofoneCelular:
    """Mantém o scrcpy de pé e guarda o áudio que chega do celular."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        # nome por sessão: um scrcpy esquecido segurava o arquivo e a Nina
        # não conseguia nem apagar nem gravar por cima
        self.arquivo = Path(tempfile.gettempdir()) / f"nina-mic-{os.getpid()}.wav"
        self.pos = 0
        self.taxa = 48000
        self.canais = 2
        self.largura = 2
        # --- o cano: quando ele está de pé, o áudio mora aqui, não em disco
        self.cano = None           # alça do cano nomeado
        self.nome_do_cano = ""
        self._buffer = bytearray()  # amostras já recebidas
        self._base = 0              # posição absoluta do primeiro byte do buffer
        self._trava_buffer = threading.Lock()
        self._lendo = False

    # --------------------------------------------------------- o cano

    def _abrir_cano(self) -> bool:
        """Sobe o scrcpy escrevendo num cano nomeado e começa a ler.

        Devolve False se qualquer parte falhar — aí o chamador cai para o
        caminho do arquivo, que é o de antes.
        """
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateNamedPipeW.restype = wintypes.HANDLE
        self.nome_do_cano = rf"\\.\pipe\nina-mic-{os.getpid()}-{int(time.time())}"
        cano = k32.CreateNamedPipeW(
            self.nome_do_cano, 0x00000001,       # PIPE_ACCESS_INBOUND
            0x00000000,                          # PIPE_TYPE_BYTE | PIPE_WAIT
            1, 1 << 21, 1 << 21, 0, None)
        if cano == wintypes.HANDLE(-1).value:
            return False

        self.proc = subprocess.Popen(
            [str(SCRCPY), "--no-video", "--no-window", "--audio-source=mic",
             "--no-audio-playback",
             "--audio-codec=raw", "--record-format=wav",
             f"--record={self.nome_do_cano}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "ADB": str(ADB)},
            creationflags=SEM_JANELA)

        def conectar() -> bool:
            if k32.ConnectNamedPipe(cano, None):
                return True
            return ctypes.get_last_error() in (0, 535)   # 535 = já conectado

        fim = time.time() + 20
        while time.time() < fim:
            if self.proc.poll() is not None:
                k32.CloseHandle(cano)
                return False
            if conectar():
                break
            time.sleep(0.1)
        else:
            k32.CloseHandle(cano)
            return False

        self.cano = cano
        self._buffer = bytearray()
        self._base = 0
        self._lendo = True
        pronto = threading.Event()

        def ler() -> None:
            buf = (ctypes.c_char * 65536)()
            lido = wintypes.DWORD()
            cabecalho = bytearray()
            comecou = False
            while self._lendo:
                if not k32.ReadFile(cano, buf, 65536, ctypes.byref(lido), None):
                    break
                dados = bytes(buf[:lido.value])
                if not comecou:
                    cabecalho += dados
                    i = cabecalho.find(b"data")
                    if i < 0 or len(cabecalho) < i + 8:
                        continue
                    self._ler_cabecalho_de(bytes(cabecalho))
                    dados = bytes(cabecalho[i + 8:])
                    comecou = True
                    pronto.set()
                with self._trava_buffer:
                    self._buffer += dados
                    # solta o que já passou: a posição de leitura manda
                    sobra = int(self.taxa * self.canais * self.largura
                                * GUARDAR_ATRAS)
                    corte = max(0, (self.pos - sobra) - self._base)
                    if corte > (1 << 20):
                        del self._buffer[:corte]
                        self._base += corte
            self._lendo = False

        threading.Thread(target=ler, daemon=True).start()
        if not pronto.wait(20):
            return False
        # O ganho do microfone leva um instante para assentar: o primeiro meio
        # segundo é descartado.
        time.sleep(DESCARTAR_NO_INICIO)
        self.pos = self._tamanho()
        return True

    def _ler_cabecalho_de(self, cab: bytes) -> None:
        """Taxa, canais e largura a partir dos primeiros bytes do WAV."""
        i = cab.find(b"fmt ")
        if i > 0:
            self.canais, self.taxa = struct.unpack("<HI", cab[i + 10:i + 16])
            self.largura = struct.unpack("<H", cab[i + 22:i + 24])[0] // 8

    def no_cano(self) -> bool:
        return self.cano is not None and self._lendo

    # ------------------------------------------- ler de onde o áudio estiver

    def _tamanho(self) -> int:
        """Quantos bytes de amostra já existem, em posição absoluta."""
        if self.no_cano():
            with self._trava_buffer:
                return self._base + len(self._buffer)
        try:
            return self.arquivo.stat().st_size
        except OSError:
            return 0

    def _fatia(self, comeco: int, fim: int) -> bytes:
        """As amostras entre duas posições absolutas."""
        if fim <= comeco:
            return b""
        if self.no_cano():
            with self._trava_buffer:
                a = max(0, comeco - self._base)
                b = max(0, fim - self._base)
                return bytes(self._buffer[a:b])
        try:
            with self.arquivo.open("rb") as f:
                f.seek(comeco)
                return f.read(fim - comeco)
        except OSError:
            return b""


    def ligar(self) -> bool:
        if self.proc and self.proc.poll() is None:
            return True
        # Primeiro o cano: 4 KiB a cada 20 ms em vez de 256 KiB a cada 1,4 s.
        try:
            if self._abrir_cano():
                return True
        except Exception:
            pass
        if self.proc and self.proc.poll() is None:   # cano falhou com scrcpy de pé
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.cano = None
        try:
            self.arquivo.unlink(missing_ok=True)
        except PermissionError:          # sobra de uma sessão anterior
            self.arquivo = self.arquivo.with_name(
                f"nina-mic-{os.getpid()}-{int(time.time())}.wav")
        self.proc = subprocess.Popen(
            [str(SCRCPY), "--no-video", "--no-window", "--audio-source=mic",
             # sem isto o PC toca de volta o que o microfone do celular capta
             "--no-audio-playback",
             # WAV exige áudio cru; sem isso o scrcpy recusa gravar em wav
             "--audio-codec=raw", "--record-format=wav", f"--record={self.arquivo}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "ADB": str(ADB)},
        creationflags=SEM_JANELA)
        # espera o cabeçalho aparecer para saber taxa e canais
        for _ in range(100):
            if self.arquivo.exists() and self.arquivo.stat().st_size > 64:
                self._ler_cabecalho()
                self.pos = self._tamanho_cabecalho()
                return True
            time.sleep(0.1)
        return False

    def desligar(self) -> None:
        self._lendo = False
        if self.cano is not None:
            try:
                import ctypes

                ctypes.WinDLL("kernel32").CloseHandle(self.cano)
            except Exception:
                pass
            self.cano = None
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.arquivo.unlink(missing_ok=True)

    def no_ar(self) -> bool:
        if not (self.proc and self.proc.poll() is None):
            return False
        return self.cano is None or self._lendo

    # --------------------------------------------------------- cabeçalho

    def _ler_cabecalho(self) -> None:
        with self.arquivo.open("rb") as f:
            cab = f.read(64)
        i = cab.find(b"fmt ")
        if i > 0:
            self.canais, self.taxa = struct.unpack("<HI", cab[i + 10:i + 16])
            self.largura = struct.unpack("<H", cab[i + 22:i + 24])[0] // 8

    def _tamanho_cabecalho(self) -> int:
        with self.arquivo.open("rb") as f:
            cab = f.read(128)
        i = cab.find(b"data")
        return i + 8 if i > 0 else 44

