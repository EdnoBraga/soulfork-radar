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


# Quem assina contrato. Sócio sem poder de administração não decide compra, então
# o administrador ganha do sócio comum quando os dois aparecem no quadro.
_RE_ADMIN = re.compile(r"administrador|titular|presidente|diretor", re.IGNORECASE)
# MEI e empresário individual não têm quadro societário: a Receita põe o nome da
# pessoa na própria razão social, seguido do CPF. "MARIA SOUZA 12345678901"
_RE_NOME_NA_RAZAO = re.compile(r"^(.+?)\s+\d{11}$")


def escolher_decisor(qsa: list | None, razao_social: str | None) -> dict | None:
    """Devolve {'nome', 'papel'} de quem decide, ou None quando não dá para saber."""
    for so in qsa or []:
        if not isinstance(so, dict):
            continue
        nome = (so.get("nome_socio") or so.get("nome") or "").strip()
        if not nome:
            continue
        papel = (so.get("qualificacao_socio") or "").strip()
        if _RE_ADMIN.search(papel):
            return {"nome": nome, "papel": papel or "Administrador"}
    for so in qsa or []:  # nenhum administrador marcado: fica o primeiro sócio
        if isinstance(so, dict):
            nome = (so.get("nome_socio") or so.get("nome") or "").strip()
            if nome:
                return {"nome": nome, "papel": (so.get("qualificacao_socio") or "Sócio").strip()}
    m = _RE_NOME_NA_RAZAO.match((razao_social or "").strip())
    if m and len(m.group(1).strip()) >= 5:
        return {"nome": m.group(1).strip(), "papel": "Titular (MEI/EI)"}
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

    # O quadro societário já vem nesta mesma resposta e era descartado. É o nome que
    # faz a abordagem chegar em quem decide em vez de morrer no atendimento.
    decisor = escolher_decisor(d.get("qsa"), d.get("razao_social"))

    return {
        "cnpj": formatar(n),
        "decisor": decisor["nome"] if decisor else None,
        "decisor_papel": decisor["papel"] if decisor else None,
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
