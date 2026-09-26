"""Fila de prospecção vinda da base aberta de CNPJ da Receita, guardada no Supabase.

O Find acha empresa pelo Google Places e pega o CNPJ no rodapé do site — então
negócio sem site fica invisível para ele, e é justamente quem mais precisa de um.
Esta tabela cobre esse buraco: vem do registro da Receita, que lista todo mundo,
com filtro por segmento, cidade e data de abertura, e traz o nome de quem decide.

Os 7GB do registro não moram aqui nem na VPS: só o resultado filtrado sobe.

A leitura usa a service key, no servidor. A chave publicável não serve: ela fica
exposta na tela de login, e a tabela tem nome de pessoa.
"""
from __future__ import annotations

import os
from typing import Any

import requests

TEMPO_LIMITE = 20
TABELA = "receita_leads"

# CNAE -> como isso se chama numa conversa. Mesmos oito segmentos dos modelos prontos.
SEGMENTOS = {
    "4789004": "Pet shop",
    "9609208": "Banho e tosa",
    "7500100": "Veterinária",
    "8630504": "Odontologia",
    "9602502": "Estética",
    "9602501": "Barbearia e salão",
    "8650041": "Fisioterapia",
    "8650052": "Nutrição",
    "4520006": "Borracharia",
    "4530703": "Autopeças",
}


def _url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def _service_key() -> str:
    return (os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_SECRET_KEY") or "").strip()


def configurado() -> bool:
    return bool(_url() and _service_key())


def _pedir(params: list[tuple[str, str]], sessao=None, prefer: str = "") -> tuple[Any, int]:
    """Devolve (json, total). O total vem do cabeçalho Content-Range do PostgREST."""
    chave = _service_key()
    cab = {"apikey": chave, "Authorization": f"Bearer {chave}",
           "Prefer": prefer or "count=exact"}
    cliente = sessao or requests
    r = cliente.get(f"{_url()}/rest/v1/{TABELA}", params=params, headers=cab, timeout=TEMPO_LIMITE)
    if getattr(r, "status_code", None) != 200:
        raise RuntimeError(f"Supabase respondeu {getattr(r, 'status_code', '?')}")
    faixa = (r.headers.get("Content-Range") or "").split("/")[-1]
    total = int(faixa) if faixa.isdigit() else 0
    return r.json(), total


def montar_filtros(cidade: str = "", segmento: str = "", so_celular: bool = False,
                   so_com_nome: bool = False, aberta_apos: str = "") -> list[tuple[str, str]]:
    """Traduz a tela em filtros do PostgREST. Separado para poder testar sem rede."""
    p: list[tuple[str, str]] = []
    if cidade:
        # a tela manda "BRASILIA/DF"; municipio e uf são colunas separadas
        nome, _, uf = cidade.partition("/")
        if nome:
            p.append(("municipio", f"eq.{nome}"))
        if uf:
            p.append(("uf", f"eq.{uf}"))
    if segmento:
        p.append(("cnae", f"eq.{segmento}"))
    if so_celular:
        p.append(("tipo_telefone", "eq.celular"))
    if so_com_nome:
        p.append(("decisor", "not.is.null"))
    if aberta_apos:
        p.append(("abertura", f"gte.{aberta_apos}"))
    return p


def buscar(cidade: str = "", segmento: str = "", so_celular: bool = False,
           so_com_nome: bool = False, aberta_apos: str = "", pagina: int = 0,
           por_pagina: int = 100, sessao=None) -> dict:
    """Uma página da fila, do melhor alvo para o pior."""
    params = montar_filtros(cidade, segmento, so_celular, so_com_nome, aberta_apos)
    params += [("select", "*"), ("order", "chance_dono.desc,abertura.desc")]
    inicio = max(0, pagina) * por_pagina
    chave = _service_key()
    cab = {"apikey": chave, "Authorization": f"Bearer {chave}",
           "Prefer": "count=exact", "Range-Unit": "items",
           "Range": f"{inicio}-{inicio + por_pagina - 1}"}
    cliente = sessao or requests
    r = cliente.get(f"{_url()}/rest/v1/{TABELA}", params=params, headers=cab, timeout=TEMPO_LIMITE)
    if getattr(r, "status_code", None) not in (200, 206):
        raise RuntimeError(f"Supabase respondeu {getattr(r, 'status_code', '?')}")
    faixa = (r.headers.get("Content-Range") or "").split("/")[-1]
    return {"linhas": r.json(), "total": int(faixa) if faixa.isdigit() else 0,
            "pagina": max(0, pagina), "por_pagina": por_pagina}


def cidades(sessao=None) -> list[str]:
    """Cidades presentes na base, para o seletor. Lista curta: cabe numa consulta só."""
    try:
        dados, _ = _pedir([("select", "municipio,uf"), ("limit", "10000")], sessao,
                          prefer="count=none")
    except (requests.RequestException, RuntimeError):
        return []
    vistos = {f"{d.get('municipio')}/{d.get('uf')}" for d in dados if d.get("municipio")}
    return sorted(vistos)


def primeiro_nome(completo: str | None) -> str:
    """"MARIA DAS DORES SOUZA" -> "Maria". O registro grava tudo em caixa alta."""
    bruto = (completo or "").strip().split()
    return bruto[0].capitalize() if bruto and len(bruto[0]) > 1 else ""


def link_whatsapp(telefone: str | None, decisor: str | None) -> str:
    """Abre a conversa já chamando a pessoa pelo nome — é isso que passa da recepção."""
    d = "".join(c for c in (telefone or "") if c.isdigit())
    if len(d) < 10:
        return ""
    nome = primeiro_nome(decisor)
    saudacao = f"Oi, {nome}? " if nome else "Oi! "
    from urllib.parse import quote
    return (f"https://wa.me/55{d}?text="
            + quote(f"{saudacao}Aqui é o Edno, da SoulFork, aqui de Brasília."))
