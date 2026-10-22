"""Ela sabe o que mandou às sessões e ainda espera — é o "o que você está fazendo?".

Sem isto ela respondia de cabeça e podia inventar trabalho que não existia.
A lista de pendências vai junto em cada fala.

    python testes/teste_o_que_espero.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nina import sessoes  # noqa: E402

agora = int(time.time() * 1000)
arq = Path(tempfile.mkdtemp()) / "pendencias.json"
sessoes.PENDENCIAS = arq

arq.write_text(json.dumps([{"id": "x", "nome": "Meu App",
                            "enviado": "Pedido por voz: roda os testes do login",
                            "quando": agora - 3 * 60_000}]), encoding="utf8")
linha = sessoes.linha_do_que_espero(agora)
assert "Meu App" in linha and "há 3 min" in linha, linha
assert "roda os testes do login" in linha and "Pedido por voz" not in linha

arq.write_text("[]", encoding="utf8")
assert sessoes.linha_do_que_espero(agora) == ""
print("ok: pendência vira linha com nome e tempo; sem pendência, nada")

# A pasta do Canteiro vem do config (padrão: a extensão pública oluan-dev.canteiro).
assert sessoes.CANTEIRO.name == "oluan-dev.canteiro", sessoes.CANTEIRO

# Mandar só diz MANDEI com o ack da extensão na mão (extensão de mentira).
import threading  # noqa: E402

estado = Path(tempfile.mkdtemp())
sessoes.ESTADO, sessoes.ENTRADA, sessoes.ACK = (
    estado, estado / "_entrada.json", estado / "_entrada.ack.json")


def extensao_de_mentira() -> None:
    for _ in range(100):
        if sessoes.ENTRADA.exists():
            pedido = json.loads(sessoes.ENTRADA.read_text(encoding="utf8"))
            sessoes.ACK.write_text(json.dumps({"pedido": pedido["id"], "ok": True,
                                               "id": "p1", "nome": "Meu App",
                                               "pasta": "C:/Projetos/meu-app"}),
                                   encoding="utf8")
            return
        time.sleep(0.05)


threading.Thread(target=extensao_de_mentira, daemon=True).start()
saida = sessoes.mandar("meu app", "Pedido por voz: roda os testes")
assert saida.startswith("MANDEI na sessão Meu App (meu-app)"), saida
assert "Meu App" in sessoes.linha_do_que_espero()
print("ok: MANDEI só com o ack da extensão; a pendência fica anotada")
