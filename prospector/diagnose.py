"""Diagnóstico técnico do site do lead a partir do HTML público.

Regra herdada do método da SoulFork (`padrao-email-diagnostico`):
NUNCA afirmar ausência do que não é verificável por esse caminho.
O crawler lê o HTML servido, onde tags <script> injetadas por gerenciador
não aparecem. Portanto:
  - ausência de GTM e de Meta Pixel é boa evidência (aparecem no <noscript>)
  - ausência de GA4 NÃO é verificável -> fica `None`, e o texto sai como
    "não identifiquei no código público", nunca "não tem".
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .enrich.site import ColetaSite
from .models import Diagnostico

# --- assinaturas de mensuração ---------------------------------------------
RE_GTM = re.compile(r"googletagmanager\.com/(?:ns|gtm)\.(?:html|js)|GTM-[A-Z0-9]{4,}", re.I)
RE_PIXEL = re.compile(r"connect\.facebook\.net/[^\"']*/fbevents\.js|facebook\.com/tr\?id=|fbq\(", re.I)
# G-XXXXXXXXXX sensível a maiúsculas e com borda — "bg-gradient1" não pode casar
RE_GA4 = re.compile(
    r"googletagmanager\.com/gtag/js\?id=G-[A-Z0-9]{6,14}"
    r"|gtag\(\s*['\"]config['\"]\s*,\s*['\"]G-[A-Z0-9]{6,14}"
    r"|\bG-[A-Z0-9]{9,12}\b"
)
RE_ANALYTICS_OUTROS = re.compile(r"(clarity\.ms|hotjar|plausible\.io|umami|matomo)", re.I)

# --- consentimento / LGPD ---------------------------------------------------
RE_CONSENT = re.compile(
    r"(cookieconsent|cookie-consent|cookiebot|onetrust|osano|termly|"
    r"lgpd|aceitar cookies|aceito os cookies|usamos cookies|"
    r"este site utiliza cookies)", re.I,
)
RE_CONSENT_INGLES = re.compile(r"(we use cookies|accept cookies|this website uses cookies)", re.I)

# --- CMS --------------------------------------------------------------------
CMS = [
    ("WordPress", re.compile(r"/wp-content/|/wp-includes/|wp-json", re.I)),
    ("Wix", re.compile(r"wixstatic\.com|_wixCssMedia|wix\.com", re.I)),
    ("Squarespace", re.compile(r"squarespace\.com|static1\.squarespace", re.I)),
    ("Shopify", re.compile(r"cdn\.shopify\.com|Shopify\.theme", re.I)),
    ("Webflow", re.compile(r"webflow\.com|data-wf-page", re.I)),
    ("GoDaddy Website Builder", re.compile(r"img1\.wsimg\.com|godaddy", re.I)),
    ("Lovable", re.compile(r"lovable\.(dev|app)|Edit with Lovable", re.I)),
    ("Framer", re.compile(r"framerusercontent\.com", re.I)),
    ("RD Station", re.compile(r"d335luupugsy2\.cloudfront\.net", re.I)),
]
RE_GERADOR = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', re.I)

# --- formulário e dado sensível ---------------------------------------------
RE_CAMPO_SENSIVEL = re.compile(
    r"(cpf|rg\b|data de nascimento|nascimento|convênio|convenio|plano de saúde|"
    r"carteirinha|queixa|sintoma|diagn[óo]stico|prontu[áa]rio)", re.I,
)


def _texto(html: str) -> str:
    try:
        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    except Exception:
        return html


def analisar(coleta: ColetaSite) -> Diagnostico:
    d = Diagnostico()

    if coleta.erro and not coleta.principal:
        if "robots" in (coleta.erro or ""):
            # o site está no ar — só não deixou o crawler entrar.
            # Não é achado de venda e não pode virar "site não respondeu".
            d.site_no_ar = None
            d.erro = coleta.erro
            return d
        d.site_no_ar = False
        d.erro = coleta.erro
        return d

    p = coleta.principal
    if p is None:
        d.site_no_ar = False
        d.erro = coleta.erro or "sem site"
        return d

    d.status_http = p.status or None
    d.url_final = p.url_final
    d.tempo_resposta_ms = p.tempo_ms
    d.https = (p.url_final or "").startswith("https://")
    d.erro = p.erro

    if p.status == 0:
        d.site_no_ar = False
        return d
    if p.status >= 400:
        d.site_no_ar = False
        return d

    d.site_no_ar = True
    html = p.html or ""
    # junta as páginas internas: política e mensuração às vezes só existem lá
    todo = "\n".join(pg.html for pg in coleta.paginas.values() if pg.html)

    try:
        sopa = BeautifulSoup(html, "html.parser")
    except Exception:
        sopa = None

    if sopa:
        if sopa.title and sopa.title.string:
            d.titulo_pagina = sopa.title.string.strip()[:200]
        md = sopa.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if md and md.get("content"):
            d.meta_description = md["content"].strip()[:300]
        vp = sopa.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)})
        d.responsivo = bool(vp and "width" in (vp.get("content") or ""))
        d.tem_formulario = bool(sopa.find("form")) or bool(
            re.search(r"(wpcf7|elementor-form|rd-station|typeform|forms\.gle|hbspt\.forms)", todo, re.I)
        )
    else:
        d.responsivo = "viewport" in html.lower()
        d.tem_formulario = "<form" in html.lower()

    # mensuração
    d.tem_gtm = bool(RE_GTM.search(todo))
    d.tem_meta_pixel = bool(RE_PIXEL.search(todo))
    # GA4: só afirmamos quando ENCONTRAMOS. Ausência não é conclusão.
    d.tem_ga4 = True if RE_GA4.search(todo) else None

    # política de privacidade
    if coleta.politica_url:
        if coleta.politica_status == 200:
            d.tem_politica_privacidade = True
            d.politica_quebrada = False
        elif coleta.politica_status and coleta.politica_status >= 400:
            d.tem_politica_privacidade = True   # o link existe...
            d.politica_quebrada = True          # ...mas está quebrado
        else:
            d.tem_politica_privacidade = None
    else:
        d.tem_politica_privacidade = False
        d.politica_quebrada = False

    d.tem_sitemap = coleta.tem_sitemap

    # dado sensível no formulário
    if d.tem_formulario:
        campos = " ".join(
            (str(t.get("name", "")) + " " + str(t.get("placeholder", "")) + " " + str(t.get("id", "")))
            for pg in coleta.paginas.values() if pg.html
            for t in (BeautifulSoup(pg.html, "html.parser").find_all(["input", "textarea", "select", "label"]))
        ) if sopa else ""
        d.coleta_dado_sensivel = bool(RE_CAMPO_SENSIVEL.search(campos))

    # CMS
    m = RE_GERADOR.search(html)
    if m:
        g = m.group(1)
        d.cms = g.split()[0] if g else None
        vm = re.search(r"([\d]+\.[\d.]+)", g)
        if vm:
            d.cms_versao = vm.group(1)
    if not d.cms:
        for nome, rx in CMS:
            if rx.search(html):
                d.cms = nome
                break

    return d


def consentimento(coleta: ColetaSite) -> tuple[bool, bool]:
    """(tem aviso de cookie, aviso está em inglês)."""
    todo = "\n".join(pg.html for pg in coleta.paginas.values() if pg.html)
    tem = bool(RE_CONSENT.search(todo))
    ingles = bool(RE_CONSENT_INGLES.search(todo)) and not bool(
        re.search(r"(usamos cookies|aceitar cookies|utiliza cookies)", todo, re.I)
    )
    return tem, ingles
