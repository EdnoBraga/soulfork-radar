"""Entrada de produção (gunicorn wsgi:app). Recusa subir sem uma forma de login
e sem chave de sessão: publicado aberto, qualquer um gastaria a chave do Google."""
import os

if len(os.environ.get("FIND_SECRET_KEY", "")) < 12:
    raise SystemExit("FIND_SECRET_KEY ausente ou curta demais (mínimo 12 caracteres).")

# Entrar com a conta Google basta; a senha vira reserva opcional. Mas uma das duas
# precisa existir, senão o before_request libera tudo e o app sobe aberto.
_google = os.environ.get("SUPABASE_URL") and (
    os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_PUBLISHABLE_KEY"))
if _google and not os.environ.get("FIND_EMAILS", "").strip():
    raise SystemExit("FIND_EMAILS vazio: com login Google e sem lista, qualquer conta entraria.")
if not _google and len(os.environ.get("FIND_SENHA", "")) < 12:
    raise SystemExit(
        "Sem login configurado. Defina SUPABASE_URL + SUPABASE_ANON_KEY + FIND_EMAILS "
        "(entrar com Google), ou FIND_SENHA com 12+ caracteres.")

from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

from prospector.web.app import app  # noqa: E402

# atrás do proxy do Easypanel: confia no cabeçalho de 1 salto para saber que é HTTPS
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SESSION_COOKIE_SECURE"] = True
