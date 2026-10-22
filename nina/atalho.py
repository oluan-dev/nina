"""O atalho de teclado que cala e devolve o ouvido da Nina.

A ideia: ela ouvindo sempre, e uma tecla para bloquear quando ele estiver
numa reunião, assistindo vídeo ou falando com outra pessoa — e outra batida na
mesma tecla para voltar. É mais confiável do que qualquer filtro automático:
quem decide é ele, na hora.

    Ctrl + Alt + N     ela para de ouvir / volta a ouvir

Usa o RegisterHotKey do próprio Windows: funciona com qualquer janela na
frente e não precisa de biblioteca nenhuma.

    python -m nina.atalho      mostra o estado agora
"""
from __future__ import annotations

import ctypes
import json
import threading
from ctypes import wintypes
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "memoria" / "ouvido.json"

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_N = 0x4E
ID_DO_ATALHO = 0xB17A
WM_HOTKEY = 0x0312


def surda() -> bool:
    """Ela está bloqueada de ouvir agora?"""
    try:
        return bool(json.loads(ESTADO.read_text(encoding="utf8"))["surda"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return False


def marcar(surda_agora: bool) -> None:
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps({"surda": bool(surda_agora)}), encoding="utf8")


def virar() -> bool:
    """Troca de estado e devolve o novo."""
    novo = not surda()
    marcar(novo)
    return novo


def vigiar(ao_virar=None) -> threading.Thread:
    """Fica de olho na tecla, num fio só dela.

    A fila de mensagens do Windows pertence ao fio que registrou o atalho, então
    o registro e a espera têm de acontecer os dois aqui dentro.
    """
    def laco() -> None:
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, ID_DO_ATALHO,
                                     MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_N):
            return                      # outro programa já usa esta tecla
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY and msg.wParam == ID_DO_ATALHO:
                    novo = virar()
                    if ao_virar:
                        ao_virar(novo)
        finally:
            user32.UnregisterHotKey(None, ID_DO_ATALHO)

    fio = threading.Thread(target=laco, daemon=True)
    fio.start()
    return fio


if __name__ == "__main__":
    print("bloqueada de ouvir" if surda() else "ouvindo")
    print("Ctrl+Alt+N troca, com a Nina ligada.")
