"""Os ajustes da Nina, num lugar só.

Os números que mudam o jeito dela ficam em `config.json`, na raiz do projeto
(copie de `config.example.json`). Quem não achar o arquivo usa o valor de
fábrica, então a Nina funciona mesmo sem configuração nenhuma.
"""
from __future__ import annotations

import json
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "config.json"

DE_FABRICA = {
    # Ouvido (faster-whisper). Sem GPU NVIDIA: "cpu" e "int8".
    "whisper_modelo": "large-v3-turbo",
    "whisper_device": "cuda",
    "whisper_compute": "float16",
    # Nomes próprios que o Whisper deve reconhecer (hotwords), numa frase só.
    "nomes": "Nina, Claude, Whisper, Pipecat.",
    # Voz (edge-tts, nuvem da Microsoft).
    "voz": "pt-BR-FranciscaNeural",
    "voz_velocidade": "+18%",
    # Id da extensão Canteiro no VS Code (pasta em globalStorage) por onde a
    # Nina vê e digita nas sessões do Claude Code.
    "canteiro_extensao": "oluan-dev.canteiro",
    # Legenda na tela: "balao" (com o nome de quem falou) ou "filme".
    "legenda": "balao",
    "legenda_tamanho": 20,
    "legenda_altura": 140,
}

_lido: dict | None = None


def tudo() -> dict:
    """Lê o arquivo uma vez e guarda. Valor ruim no arquivo não derruba a Nina."""
    global _lido
    if _lido is None:
        _lido = dict(DE_FABRICA)
        if ARQUIVO.exists():
            try:
                _lido.update(json.loads(ARQUIVO.read_text(encoding="utf8")))
            except (json.JSONDecodeError, OSError):
                pass
    return _lido


def pegar(nome: str, padrao=None):
    valor = tudo().get(nome, DE_FABRICA.get(nome, padrao))
    try:
        return type(DE_FABRICA.get(nome, valor))(valor)
    except (TypeError, ValueError):
        return DE_FABRICA.get(nome, padrao)


def recarregar() -> dict:
    """Esquece o que leu e lê de novo — usado depois de salvar pelo painel."""
    global _lido
    _lido = None
    return tudo()


if __name__ == "__main__":
    for nome, valor in tudo().items():
        marca = "" if valor == DE_FABRICA.get(nome) else "  (mudado)"
        print(f"{nome}: {valor}{marca}")
