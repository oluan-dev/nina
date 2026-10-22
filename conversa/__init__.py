"""A Nina sobre o Pipecat: o projeto pronto cuida da conversa, ela só pensa.

Ouvido, fim de fala, interrupção e boca são do Pipecat (BSD-2, tudo local).
Daqui saem só três tomadas: o cérebro dela (`nina/cerebro.mjs`, pela
assinatura do Claude Code), a voz (edge-tts) e o microfone do celular.

    python -m conversa
"""
import os
import sys
from pathlib import Path

# O Whisper (ctranslate2) precisa do cuBLAS/cuDNN que vêm com o torch CUDA.
# Só o PATH resolve no Windows. NINA_CUDA_LIB aponta outra pasta, se preciso.
_LIB = os.environ.get("NINA_CUDA_LIB") or str(
    Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib")
os.environ["PATH"] = f"{_LIB}{os.pathsep}{os.environ.get('PATH', '')}"
