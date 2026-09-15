"""Business Discovery da Graph API da Meta — seguidores de perfis de terceiros.

Uma conta Comercial ou Criador de conteúdo (a sua) consulta QUALQUER outro
perfil Comercial/Criador público. Perfil pessoal não é visível pela API: isso
devolve erro e significa "não disponível", NUNCA "sem Instagram".

Doc: https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/business-discovery

A Meta permite ~200 chamadas por hora por usuário. Por isso a consulta é sob
demanda — um lead por clique — e nunca entra na varredura automática.
"""
from __future__ import annotations

import requests

VERSAO = "v21.0"
BASE = f"https://graph.facebook.com/{VERSAO}"


class InstagramError(RuntimeError):
    """Problema do lado do Radar: token, limite de chamadas, rede."""


class IndisponivelError(RuntimeError):
    """O perfil existe mas a API não devolve: conta pessoal, privada ou @ errado."""


def _chamar(caminho: str, token: str, **params) -> dict:
    params["access_token"] = token
    try:
        resp = requests.get(f"{BASE}/{caminho}", params=params, timeout=20)
    except requests.RequestException as e:
        raise InstagramError(f"Não consegui falar com a Meta: {e}") from e
    dados = resp.json() if resp.content else {}
    if "error" in dados:
        raise _traduzir(dados["error"])
    if resp.status_code != 200:
        raise InstagramError(f"A Meta respondeu HTTP {resp.status_code}.")
    return dados


def _traduzir(erro: dict) -> Exception:
    codigo = erro.get("code")
    msg = erro.get("message", "erro desconhecido")
    if codigo in (4, 17, 32, 613):
        return InstagramError(
            "Limite de chamadas da Meta atingido (são ~200 por hora). "
            "Espere um pouco e tente de novo."
        )
    if codigo in (102, 190):
        return InstagramError(
            "A Meta recusou o token (expirou ou perdeu permissão). "
            "Gere outro em Configuração."
        )
    if codigo == 100:
        return IndisponivelError(
            "A Meta não devolve esse perfil. Quase sempre é conta pessoal — "
            "só conta Comercial ou Criador de conteúdo aparece na API."
        )
    return InstagramError(f"A Meta recusou a chamada ({codigo}): {msg}")


def descobrir_conta(token: str) -> tuple[str, str]:
    """Acha o ig-user-id ligado ao token. Devolve (id, @usuario)."""
    dados = _chamar("me/accounts", token,
                    fields="instagram_business_account{id,username}")
    for pagina in dados.get("data", []):
        conta = pagina.get("instagram_business_account")
        if conta and conta.get("id"):
            return conta["id"], conta.get("username", "")
    raise InstagramError(
        "Esse token não tem nenhuma conta do Instagram ligada a uma Página do "
        "Facebook. Confira se o perfil é Comercial/Criador e está vinculado a "
        "uma Página."
    )


def extrair(bd: dict) -> dict:
    """Achata a resposta de business_discovery no que o Radar usa."""
    midias = (bd.get("media") or {}).get("data") or []
    carimbo = midias[0].get("timestamp") if midias else None
    return {
        "usuario": bd.get("username"),
        "seguidores": bd.get("followers_count"),
        "publicacoes": bd.get("media_count"),
        "bio": bd.get("biography") or None,
        "ultima_publicacao": carimbo[:10] if carimbo else None,
    }


def consultar(usuario: str, token: str, ig_user_id: str) -> dict:
    """Seguidores e data da última publicação de um @ qualquer."""
    usuario = (usuario or "").lstrip("@").strip()
    if not usuario:
        raise IndisponivelError("Esse lead não tem @ do Instagram.")
    campos = (f"business_discovery.username({usuario})"
              "{username,followers_count,media_count,biography,"
              "media.limit(1){timestamp}}")
    dados = _chamar(ig_user_id, token, fields=campos)
    bd = dados.get("business_discovery")
    if not bd:
        raise IndisponivelError("A Meta não devolveu dados desse perfil.")
    return extrair(bd)
