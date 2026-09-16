"""Entrada de produção (gunicorn wsgi:app). Recusa subir sem senha e sem
chave de sessão: publicado aberto, qualquer um gastaria a chave do Google."""
import os

for obrigatoria in ("FIND_SENHA", "FIND_SECRET_KEY"):
    if len(os.environ.get(obrigatoria, "")) < 12:
        raise SystemExit(f"{obrigatoria} ausente ou curta demais (mínimo 12 caracteres).")

from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

from prospector.web.app import app  # noqa: E402

# atrás do proxy do Easypanel: confia no cabeçalho de 1 salto para saber que é HTTPS
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SESSION_COOKIE_SECURE"] = True
