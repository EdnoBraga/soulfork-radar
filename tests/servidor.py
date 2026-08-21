"""Sobe sites falsos em portas locais para testar o pipeline sem internet."""
import functools, http.server, socketserver, threading, os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def guess_type(self, path):
        if path.endswith("politica-de-privacidade"):
            return "text/html"
        return super().guess_type(path)


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def servir(pasta: str) -> str:
    """Sobe o site e devolve a URL base (porta escolhida pelo SO)."""
    h = functools.partial(Silencioso, directory=os.path.join(BASE, pasta))
    srv = Servidor(("127.0.0.1", 0), h)
    porta = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{porta}/"
