"""Traduz o diagnóstico numa frase que o vendedor entende sem pensar.

A tabela de leads não mostra "score 72" e pronto: mostra a razão em português,
do jeito que sairia numa conversa. Ex.: "4,9★, 474 avaliações, mas sem site
nem Instagram — fatura bem e some do digital."
"""
from __future__ import annotations

from .models import Lead


def _nota(lead: Lead) -> str:
    if lead.nota and lead.avaliacoes:
        n = f"{lead.nota:.1f}".replace(".", ",")
        return f"{n}★, {lead.avaliacoes} avaliaç{'ões' if lead.avaliacoes != 1 else 'ão'}"
    if lead.avaliacoes:
        return f"{lead.avaliacoes} avaliações"
    return "sem avaliações no Maps"


def _lacunas(lead: Lead) -> list[str]:
    faltas = []
    if not lead.site:
        faltas.append("site")
    elif lead.diagnostico.site_no_ar is False:
        faltas.append("site no ar")
    if not lead.redes.instagram:
        faltas.append("Instagram")
    if not lead.contatos.whatsapp:
        faltas.append("WhatsApp")
    return faltas


def _lista(itens: list[str], junto: str = "nem") -> str:
    if len(itens) == 1:
        return itens[0]
    if len(itens) == 2:
        return f"{itens[0]} {junto} {itens[1]}"
    return ", ".join(itens[:-1]) + f" {junto} {itens[-1]}"


def frase_oportunidade(lead: Lead) -> str:
    nota = _nota(lead)
    faltas = _lacunas(lead)
    d = lead.diagnostico

    # 1. faturam bem e não têm site — a conversa mais fácil que existe
    if not lead.site and (lead.avaliacoes or 0) >= 30:
        return f"{nota}, mas sem site nenhum — o Maps sustenta o negócio sozinho."
    if not lead.site:
        return f"{nota} e sem site — presença começa do zero."

    # 2. site fora do ar
    if d.site_no_ar is False:
        motivo = f"HTTP {d.status_http}" if d.status_http else (d.erro or "não respondeu")
        return f"{nota}, e o site não abriu nesta checagem ({motivo}) — reconfirmar antes de citar."

    # 3. lacunas de canal
    if faltas:
        return f"{nota}, mas sem {_lista(faltas)} — {'canal de entrada faltando' if len(faltas) > 1 else 'falta o canal principal'}."

    # 4. presença completa: o gancho vira o que está quebrado por dentro
    problemas = []
    if d.https is False:
        problemas.append("site sem HTTPS")
    if d.responsivo is False:
        problemas.append("não adaptado a celular")
    if d.tem_gtm is False and d.tem_meta_pixel is False:
        problemas.append("nenhuma medição no código")
    elif d.tem_meta_pixel is False:
        problemas.append("sem Pixel")
    if d.politica_quebrada:
        problemas.append("política de privacidade quebrada")
    elif d.tem_politica_privacidade is False and d.tem_formulario:
        problemas.append("formulário sem política de LGPD")
    if d.coleta_dado_sensivel:
        problemas.append("formulário pede dado sensível")
    if d.tem_formulario is False:
        problemas.append("nenhum formulário")

    if problemas:
        return f"{nota} e presença completa, mas {_lista(problemas[:2], 'e')}."

    return f"{nota} e presença completa (site, Instagram e contato) — pouco a atacar."


def rotulo_faixa(faixa: str) -> str:
    return {
        "quente": "Oportunidade quente",
        "morno": "Vale abordar",
        "frio": "Talvez",
        "fraco": "Pouco a oferecer",
        "descartar": "Descartar",
    }.get(faixa, faixa)
