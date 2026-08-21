"""Enriquecimento cadastral via BrasilAPI (base pública da Receita Federal).

Endpoint: https://brasilapi.com.br/api/cnpj/v1/{cnpj}

Não existe busca pública gratuita por CNAE + município que devolva contato
utilizável. Então a estratégia é o contrário: o CNPJ é extraído do rodapé do
site do próprio lead (a esmagadora maioria dos sites de PME brasileira publica
o CNPJ) e só então validado na base pública. Isso é gratuito, legal e preciso.
"""
from __future__ import annotations

import re

import requests

ENDPOINT = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"

# 00.000.000/0000-00 com separadores opcionais
RE_CNPJ = re.compile(r"\b(\d{2})[.\s]?(\d{3})[.\s]?(\d{3})[/\s]?(\d{4})[-\s]?(\d{2})\b")


def _digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def valido(cnpj: str) -> bool:
    """Valida os dois dígitos verificadores. Evita gastar requisição com lixo."""
    n = _digitos(cnpj)
    if len(n) != 14 or n == n[0] * 14:
        return False
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(int(d) * p for d, p in zip(n[:tamanho], pesos))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if int(n[tamanho]) != digito:
            return False
    return True


def extrair_do_texto(texto: str) -> str | None:
    """Acha o primeiro CNPJ válido dentro de um texto (rodapé de site, etc.)."""
    for m in RE_CNPJ.finditer(texto or ""):
        candidato = "".join(m.groups())
        if valido(candidato):
            return candidato
    return None


def formatar(cnpj: str) -> str:
    n = _digitos(cnpj)
    if len(n) != 14:
        return cnpj
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


def consultar(cnpj: str, timeout: int = 15, sessao: requests.Session | None = None) -> dict | None:
    """Consulta a BrasilAPI. Devolve None se não achar ou se a API falhar."""
    n = _digitos(cnpj)
    if not valido(n):
        return None
    cliente = sessao or requests
    try:
        resp = cliente.get(ENDPOINT.format(cnpj=n), timeout=timeout)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        d = resp.json()
    except ValueError:
        return None

    cnae = None
    if d.get("cnae_fiscal"):
        cnae = f"{d.get('cnae_fiscal')} — {d.get('cnae_fiscal_descricao') or ''}".strip(" —")

    telefone = None
    ddd = (d.get("ddd_telefone_1") or "").strip()
    if ddd:
        telefone = re.sub(r"\D", "", ddd)

    return {
        "cnpj": formatar(n),
        "razao_social": d.get("razao_social"),
        "nome_fantasia": d.get("nome_fantasia"),
        "situacao_cadastral": d.get("descricao_situacao_cadastral"),
        "cnae": cnae,
        "porte": d.get("descricao_porte") or d.get("porte"),
        "abertura": d.get("data_inicio_atividade"),
        "municipio": d.get("municipio"),
        "uf": d.get("uf"),
        "email_receita": (d.get("email") or "").strip().lower() or None,
        "telefone_receita": telefone,
        "capital_social": d.get("capital_social"),
        "simples": d.get("opcao_pelo_simples"),
        "mei": d.get("opcao_pelo_mei"),
    }
