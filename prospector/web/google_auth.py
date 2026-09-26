"""Entrar com a conta Google, pelo mesmo Supabase que o dashboard já usa.

O navegador faz o fluxo do Google pelo supabase-js e devolve um token. Aqui o
servidor pergunta ao Supabase de quem é esse token — não confiamos no que o
navegador diz ser. Só então a sessão é aberta, e apenas para e-mail que está na
lista. Sem service key no servidor: a chave publicável basta para essa pergunta.
"""
from __future__ import annotations

import os

import requests

TEMPO_LIMITE = 10


def _url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def _chave() -> str:
    # aceita os dois nomes: o CRM chama de PUBLISHABLE_KEY, o Supabase antigo de ANON_KEY
    return (os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_PUBLISHABLE_KEY") or "").strip()


def configurado() -> bool:
    """Só oferece o botão do Google quando dá para verificar o token de verdade."""
    return bool(_url() and _chave())


def emails_liberados() -> set[str]:
    bruto = os.environ.get("FIND_EMAILS", "")
    return {e.strip().lower() for e in bruto.replace(";", ",").split(",") if e.strip()}


def email_do_token(token: str, sessao=None) -> str | None:
    """Pergunta ao Supabase de quem é o token. None se inválido, expirado ou fora do ar."""
    if not token or not configurado():
        return None
    cliente = sessao or requests
    try:
        r = cliente.get(
            f"{_url()}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": _chave()},
            timeout=TEMPO_LIMITE,
        )
    except requests.RequestException:
        return None
    if getattr(r, "status_code", None) != 200:
        return None
    try:
        dados = r.json()
    except ValueError:
        return None
    email = (dados.get("email") or "").strip().lower()
    # e-mail não confirmado no provedor não serve como identidade
    if not email or dados.get("aud") not in (None, "authenticated"):
        return None
    return email


def liberado(email: str | None) -> bool:
    """Falha fechado: sem FIND_EMAILS configurado, ninguém entra.

    O contrário abriria o Find para qualquer pessoa com conta Google, que é o
    planeta inteiro — e a chave do Places é paga por uso.
    """
    if not email:
        return False
    return email in emails_liberados()
