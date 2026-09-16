"""robots.txt segue a RFC 9309: 4xx libera, 5xx/429 bloqueia, regras valem."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from prospector.enrich.site import UA, ColetorSite


class Resp:
    def __init__(self, status, texto=""):
        self.status_code, self.text = status, texto


def coletor(resposta):
    c = ColetorSite()
    vistos = []

    def get(url, **kw):
        vistos.append(kw.get("headers") or c.sessao.headers)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    c.sessao.get = get
    return c, vistos


URL = "https://exemplo.com.br/contato"

c, vistos = coletor(Resp(403, "<h1>Forbidden</h1>"))
assert c._pode(URL), "403 no robots.txt deve liberar (RFC 9309)"
assert vistos[0]["User-Agent"] == UA, "robots.txt tem que ser pedido com o nosso User-Agent"

c, _ = coletor(Resp(404))
assert c._pode(URL), "404 libera"

c, _ = coletor(Resp(503))
assert not c._pode(URL), "5xx bloqueia"

c, _ = coletor(Resp(429))
assert not c._pode(URL), "429 bloqueia"

c, _ = coletor(Resp(200, "User-agent: *\nAllow: /\n"))
assert c._pode(URL), "Allow: / libera"

c, _ = coletor(Resp(200, "User-agent: *\nDisallow: /contato\n"))
assert not c._pode(URL), "Disallow do caminho bloqueia"
assert c._pode("https://exemplo.com.br/"), "Disallow de /contato não bloqueia a home"

c, _ = coletor(Resp(200, "User-agent: SoulForkProspector\nDisallow: /\n\nUser-agent: *\nAllow: /\n"))
assert not c._pode(URL), "regra específica para o nosso robô vale"

c, _ = coletor(requests.ConnectionError())
assert c._pode(URL), "sem resposta: deixa a visita à página dizer se o site caiu"

print("✓ robots.txt: segue a RFC 9309")
