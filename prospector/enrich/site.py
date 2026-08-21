"""Visita o site do lead e extrai contato, redes sociais e matéria-prima do diagnóstico.

Só lê o HTML servido publicamente — o mesmo que qualquer crawler enxerga.
Respeita robots.txt e usa User-Agent identificado.
"""
from __future__ import annotations

import re
import time
import urllib.parse as up
from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

UA = "SoulForkProspector/1.0 (+https://soulfork.com.br; prospeccao B2B)"

# páginas onde contato e política costumam morar
CAMINHOS_EXTRA = [
    "/contato", "/contato/", "/fale-conosco", "/fale-conosco/",
    "/sobre", "/sobre/", "/quem-somos", "/quem-somos/",
    "/politica-de-privacidade", "/politica-de-privacidade/",
    "/privacidade", "/privacidade/", "/politica-privacidade/",
]

RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
RE_WA_LINK = re.compile(r"(?:wa\.me|api\.whatsapp\.com/send|web\.whatsapp\.com/send)[^\"'\s]*", re.I)
RE_TEL_BR = re.compile(
    r"(?:\+?55[\s.-]*)?\(?(\d{2})\)?[\s.-]*(9[\s.-]?\d{4}|\d{4})[\s.-]?(\d{4})\b"
)

# e-mails que não são contato de verdade
LIXO_EMAIL = re.compile(
    r"(example|dominio|seuemail|seu-email|email@email|sentry\.io|wixpress|"
    r"\.png$|\.jpg$|\.jpeg$|\.gif$|\.webp$|\.svg$|"
    r"@sentry|@2x|godaddy|wordpress\.(com|org)|elementor)", re.I
)

REDES = {
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]{2,30})", re.I),
    "tiktok":    re.compile(r"https?://(?:www\.)?tiktok\.com/@([A-Za-z0-9_.]{2,30})", re.I),
    "facebook":  re.compile(r"https?://(?:www\.|m\.|pt-br\.)?facebook\.com/([A-Za-z0-9_.\-/]{2,60})", re.I),
    "linkedin":  re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|in)/([A-Za-z0-9_.\-]{2,60})", re.I),
    "youtube":   re.compile(r"https?://(?:www\.)?youtube\.com/(?:@|c/|channel/|user/)([A-Za-z0-9_.\-]{2,60})", re.I),
}

# handles de plataforma/agência que não são o perfil do cliente
HANDLES_IGNORAR = {
    "explore", "reel", "reels", "p", "tv", "stories", "accounts", "about",
    "instagram", "facebook", "tiktok", "youtube", "linkedin", "sharer",
    "share", "home", "pages", "profile.php", "plugins", "dialog", "tr",
    "wix", "wixsite", "elementor", "wordpressdotcom",
}


@dataclass
class PaginaSite:
    url: str
    url_final: str
    status: int
    html: str
    tempo_ms: int
    erro: str | None = None


@dataclass
class ColetaSite:
    base: str | None = None
    principal: PaginaSite | None = None
    paginas: dict[str, PaginaSite] = field(default_factory=dict)
    emails: list[str] = field(default_factory=list)
    whatsapp: str | None = None
    telefones: list[str] = field(default_factory=list)
    redes: dict[str, str] = field(default_factory=dict)
    cnpj: str | None = None
    tem_sitemap: bool | None = None
    politica_url: str | None = None
    politica_status: int | None = None
    erro: str | None = None


def _normalizar_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _limpo(email: str) -> bool:
    if LIXO_EMAIL.search(email):
        return False
    if len(email) > 80:
        return False
    return True


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", t or "")


def _telefone_valido_br(numero: str) -> bool:
    n = _digitos(numero)
    if n.startswith("55") and len(n) in (12, 13):
        n = n[2:]
    if len(n) not in (10, 11):
        return False
    ddd = int(n[:2])
    if ddd < 11 or ddd > 99:
        return False
    if len(n) == 11 and n[2] != "9":
        return False
    return True


def _e164(numero: str) -> str | None:
    n = _digitos(numero)
    if n.startswith("55") and len(n) in (12, 13):
        n = n[2:]
    if len(n) not in (10, 11):
        return None
    return "55" + n


def _eh_celular(numero: str) -> bool:
    n = _digitos(numero)
    if n.startswith("55") and len(n) in (12, 13):
        n = n[2:]
    return len(n) == 11 and n[2] == "9"


class ColetorSite:
    def __init__(self, timeout: int = 15, respeitar_robots: bool = True, paginas_extra: int = 3):
        self.timeout = timeout
        self.respeitar_robots = respeitar_robots
        self.paginas_extra = paginas_extra
        self.sessao = requests.Session()
        self.sessao.headers.update({
            "User-Agent": UA,
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        })
        self._robots: dict[str, RobotFileParser | None] = {}

    # ---------- rede ----------

    def _pode(self, url: str) -> bool:
        if not self.respeitar_robots:
            return True
        p = up.urlparse(url)
        raiz = f"{p.scheme}://{p.netloc}"
        if raiz not in self._robots:
            rp = RobotFileParser()
            rp.set_url(raiz + "/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None
            self._robots[raiz] = rp
        rp = self._robots[raiz]
        if rp is None:
            return True
        try:
            return rp.can_fetch(UA, url)
        except Exception:
            return True

    def _get(self, url: str, permitir_redirect: bool = True) -> PaginaSite:
        t0 = time.time()
        try:
            resp = self.sessao.get(
                url, timeout=self.timeout, allow_redirects=permitir_redirect
            )
            ms = int((time.time() - t0) * 1000)
            ctype = resp.headers.get("Content-Type", "")
            if "charset" not in ctype.lower():
                # sem charset no header o requests assume ISO-8859-1 e "ç" vira lixo;
                # apparent_encoding fareja o real (meta charset/chardet)
                try:
                    resp.encoding = resp.apparent_encoding or resp.encoding
                except Exception:
                    pass
            html = resp.text if "html" in ctype or "xml" in ctype or not ctype else ""
            return PaginaSite(url, resp.url, resp.status_code, html, ms)
        except requests.exceptions.SSLError as e:
            return PaginaSite(url, url, 0, "", int((time.time() - t0) * 1000), f"SSL: {e.__class__.__name__}")
        except requests.exceptions.ConnectTimeout:
            return PaginaSite(url, url, 0, "", int((time.time() - t0) * 1000), "timeout de conexão")
        except requests.exceptions.ReadTimeout:
            return PaginaSite(url, url, 0, "", int((time.time() - t0) * 1000), "timeout de leitura")
        except requests.RequestException as e:
            return PaginaSite(url, url, 0, "", int((time.time() - t0) * 1000), f"{e.__class__.__name__}")

    # ---------- extração ----------

    def _extrair(self, coleta: ColetaSite, pagina: PaginaSite) -> None:
        html = pagina.html
        if not html:
            return
        try:
            sopa = BeautifulSoup(html, "html.parser")
        except Exception:
            sopa = None

        texto_bruto = html

        # e-mails: mailto: primeiro (mais confiável), depois varredura no texto
        vistos = set(coleta.emails)
        if sopa:
            for a in sopa.find_all("a", href=True):
                href = a["href"]
                if href.lower().startswith("mailto:"):
                    alvo = up.unquote(href[7:].split("?")[0]).strip().lower()
                    for m in RE_EMAIL.finditer(alvo):
                        e = m.group(0).lower()
                        if _limpo(e) and e not in vistos:
                            vistos.add(e)
                            coleta.emails.append(e)
        for m in RE_EMAIL.finditer(texto_bruto):
            e = m.group(0).lower().rstrip(".")
            if _limpo(e) and e not in vistos:
                vistos.add(e)
                coleta.emails.append(e)

        # whatsapp por link
        if not coleta.whatsapp:
            m = RE_WA_LINK.search(texto_bruto)
            if m:
                link = m.group(0)
                num = _digitos(re.sub(r"^.*?(?:wa\.me/|phone=)", "", link).split("&")[0].split("?")[0])
                if num and _telefone_valido_br(num):
                    coleta.whatsapp = _e164(num)

        # telefones no texto
        alvo = sopa.get_text(" ", strip=True) if sopa else texto_bruto
        for m in RE_TEL_BR.finditer(alvo):
            numero = _digitos("".join(m.groups()))
            if _telefone_valido_br(numero):
                n = _e164(numero)
                if n and n not in coleta.telefones:
                    coleta.telefones.append(n)

        # redes sociais
        for rede, regex in REDES.items():
            if rede in coleta.redes:
                continue
            for m in regex.finditer(texto_bruto):
                handle = m.group(1).strip("/").split("/")[0].split("?")[0]
                if not handle or handle.lower() in HANDLES_IGNORAR:
                    continue
                coleta.redes[rede] = handle
                break

        # cnpj no rodapé
        if not coleta.cnpj:
            from ..sources.cnpj import extrair_do_texto
            achado = extrair_do_texto(alvo)
            if achado:
                coleta.cnpj = achado

    def _links_politica(self, pagina: PaginaSite) -> list[str]:
        """URLs de política de privacidade DECLARADAS em âncoras da página.

        Só o que o site linka de verdade conta. Caminho adivinhado que devolve
        404 não é 'link quebrado' — é caminho que não existe, e afirmar o
        contrário numa proposta é alegação falsa.
        """
        if not pagina.html:
            return []
        try:
            sopa = BeautifulSoup(pagina.html, "html.parser")
        except Exception:
            return []
        alvos, vistos = [], set()
        for a in sopa.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            texto = (a.get_text(" ", strip=True) or "").lower()
            if not (re.search(r"(privacidade|privacy|lgpd)", href, re.I)
                    or re.search(r"(privacidade|privacy|lgpd)", texto)):
                continue
            completo = up.urljoin(pagina.url_final, href)
            if completo.startswith(("http://", "https://")) and completo not in vistos:
                vistos.add(completo)
                alvos.append(completo)
        return alvos

    def _links_internos(self, pagina: PaginaSite) -> list[str]:
        if not pagina.html:
            return []
        try:
            sopa = BeautifulSoup(pagina.html, "html.parser")
        except Exception:
            return []
        base = up.urlparse(pagina.url_final)
        raiz = f"{base.scheme}://{base.netloc}"
        alvos, vistos = [], set()
        palavras = ("contato", "fale", "sobre", "quem-somos", "privacidade", "lgpd")
        for a in sopa.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            completo = up.urljoin(raiz, href)
            p = up.urlparse(completo)
            if p.netloc != base.netloc:
                continue
            caminho = p.path.lower()
            if not any(w in caminho for w in palavras):
                continue
            limpo = f"{p.scheme}://{p.netloc}{p.path}"
            if limpo not in vistos and limpo.rstrip("/") != pagina.url_final.rstrip("/"):
                vistos.add(limpo)
                alvos.append(limpo)
        return alvos

    # ---------- entrada ----------

    def coletar(self, url: str) -> ColetaSite:
        coleta = ColetaSite()
        url = _normalizar_url(url)
        if not url:
            coleta.erro = "sem site"
            return coleta

        p = up.urlparse(url)
        coleta.base = f"{p.scheme}://{p.netloc}"

        if not self._pode(url):
            coleta.erro = "bloqueado por robots.txt"
            return coleta

        principal = self._get(url)
        # se https falhou de cara, tenta http (site sem certificado ainda é site)
        if principal.status == 0 and url.startswith("https://"):
            alt = self._get("http://" + p.netloc + (p.path or "/"))
            if alt.status:
                principal = alt
                coleta.base = "http://" + p.netloc   # sitemap e páginas extras na origem viva
        coleta.principal = principal
        coleta.paginas["principal"] = principal

        if principal.status == 0:
            coleta.erro = principal.erro or "não respondeu"
            return coleta

        self._extrair(coleta, principal)

        # páginas internas relevantes
        candidatos = self._links_internos(principal)
        for caminho in CAMINHOS_EXTRA:
            alvo = coleta.base + caminho
            if alvo not in candidatos:
                candidatos.append(alvo)

        declarados = self._links_politica(principal)

        visitadas = 0
        for alvo in candidatos:
            if visitadas >= self.paginas_extra:
                break
            if not self._pode(alvo):
                continue
            pag = self._get(alvo)
            if pag.status == 200 and pag.html:
                chave = up.urlparse(alvo).path or "/"
                coleta.paginas[chave] = pag
                self._extrair(coleta, pag)
                visitadas += 1
                for extra in self._links_politica(pag):
                    if extra not in declarados:
                        declarados.append(extra)

        # Política de privacidade: julgada SOMENTE pelos links que o site declara.
        # Nenhum link declarado -> não tem. Todos quebrados -> quebrada.
        if declarados:
            melhor_status = None
            for alvo in declarados[:4]:
                pag = self._get(alvo)
                if melhor_status is None or pag.status == 200:
                    coleta.politica_url = alvo
                    melhor_status = pag.status
                if pag.status == 200:
                    break
            coleta.politica_status = melhor_status

        # sitemap
        sm = self._get(coleta.base + "/sitemap.xml", permitir_redirect=True)
        coleta.tem_sitemap = sm.status == 200 and ("<urlset" in sm.html or "<sitemapindex" in sm.html)

        # ordena e-mails: institucional antes de pessoal
        def peso(e: str) -> tuple:
            local = e.split("@")[0]
            bons = ("contato", "comercial", "atendimento", "faleconosco", "fale", "sac", "info")
            return (0 if any(b in local for b in bons) else 1, len(e))

        coleta.emails = sorted(dict.fromkeys(coleta.emails), key=peso)[:6]

        # whatsapp por dedução: celular encontrado no site, se não houver link wa.me
        if not coleta.whatsapp:
            for t in coleta.telefones:
                if _eh_celular(t):
                    coleta.whatsapp = t
                    break

        return coleta
