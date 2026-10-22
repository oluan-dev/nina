"""O rosto da Nina no navegador: http://localhost:4790/rosto

Serve três coisas e nada mais: a página (`rosto.html`), as seis imagens de
`arte/` e `/api/boca`, que devolve o `diario/boca.json` escrito por
`nina/boca.py` (a boca do som que acabou de tocar).

Só escuta em 127.0.0.1, só atende pedido endereçado ao localhost desta porta e
`/api/boca` exige uma senha sorteada a cada arranque, que só a página servida
conhece — outra página aberta no navegador não lê o estado dela.

    python -m nina.rosto_web          sobe sozinho (a Nina sobe junto em `python -m conversa`)
"""
from __future__ import annotations

import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = Path(__file__).resolve().parent / "rosto.html"
ARTE = Path(__file__).resolve().parent / "arte"
BOCA = RAIZ / "diario" / "boca.json"
PORTA = 4790
# Lista fechada: a rota /arte/ só entrega estes nomes, sem como pedir "../".
ARQUIVOS_DE_ARTE = {"rosto.png", "boca-M.png", "boca-S.png",
                    "boca-AH.png", "boca-E.png", "boca-O.png"}
ENDERECOS_ACEITOS = {f"localhost:{PORTA}", f"127.0.0.1:{PORTA}"}
SENHA = secrets.token_urlsafe(24)


class Servidor(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def _responder(self, corpo: bytes, tipo: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self) -> None:
        if self.headers.get("Host") not in ENDERECOS_ACEITOS:
            return self.send_error(403, "só vale pelo localhost")
        rota = self.path.split("?")[0]
        if rota == "/rosto":
            pagina = PAGINA.read_text(encoding="utf8").replace("__SENHA_DA_SESSAO__", SENHA)
            self._responder(pagina.encode("utf8"), "text/html; charset=utf-8")
        elif rota.startswith("/arte/") and rota[len("/arte/"):] in ARQUIVOS_DE_ARTE:
            self._responder((ARTE / rota[len("/arte/"):]).read_bytes(), "image/png")
        elif rota == "/api/boca":
            if not hmac.compare_digest(self.headers.get("X-Nina", ""), SENHA):
                return self.send_error(403, "senha da sessão não confere")
            try:
                dados = json.loads(BOCA.read_text(encoding="utf8"))
            except (OSError, ValueError):
                dados = {"forma": "M", "abertura": 0}      # calada não é erro
            self._responder(json.dumps(dados).encode("utf8"), "application/json")
        else:
            self.send_error(404)


def ligar() -> threading.Thread | None:
    """Sobe o servidor num fio à parte. Porta ocupada: segue sem ele."""
    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Servidor)
    except OSError:
        return None
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    return fio


if __name__ == "__main__":
    print(f"rosto da Nina em http://localhost:{PORTA}/rosto  (ctrl+c para parar)")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORTA), Servidor).serve_forever()
    except KeyboardInterrupt:
        pass
