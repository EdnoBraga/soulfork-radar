"""Site montado por JavaScript: ausência de rede/formulário/política não vira dor."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prospector.diagnose import analisar
from prospector.enrich.site import ColetaSite, PaginaSite
from prospector.frases import frase_oportunidade
from prospector.models import Contatos, Lead
from prospector.score import avaliar

CASCA = """<!doctype html><html><head><meta name="viewport" content="width=device-width">
<title>Clínica</title><script type="module" src="/assets/index.js"></script></head>
<body><div id="root"></div></body></html>"""

ESTATICO = """<!doctype html><html><head><meta name="viewport" content="width=device-width">
<title>Clínica</title></head><body><h1>Clínica Sorriso</h1>
<p>""" + "Atendimento odontológico completo em Brasília. " * 12 + """</p>
<a href="/sobre">Sobre</a><a href="/servicos">Serviços</a><a href="/contato">Contato</a>
</body></html>"""


def lead_de(html, status=200):
    pg = PaginaSite(url="https://x.com.br/", url_final="https://x.com.br/",
                    status=status, html=html, tempo_ms=300,
                    erro="ConnectionError" if status == 0 else None)
    coleta = ColetaSite(base="https://x.com.br", principal=pg,
                        paginas={"principal": pg}, tem_sitemap=True)
    lead = Lead(nome="Clínica", site="https://x.com.br/", nota=4.9, avaliacoes=200,
                contatos=Contatos(telefone="(61) 3333-4444", whatsapp="5561999990000"))
    lead.diagnostico = analisar(coleta)
    lead.score, lead.faixa, lead.sinais = avaliar(lead, coleta)
    lead.frase_oportunidade = frase_oportunidade(lead)
    return lead


js = lead_de(CASCA)
chaves = {s.chave for s in js.sinais}
assert js.diagnostico.renderizado_js is True
assert js.diagnostico.https is True and js.diagnostico.responsivo is True, "o que está no HTML servido continua valendo"
for falsa in ("sem_instagram", "sem_formulario", "sem_politica", "sem_mensuracao", "tag_sem_consentimento"):
    assert falsa not in chaves, f"afirmou {falsa} num site montado por JS"
assert "site_js" in chaves
assert "Instagram" not in js.frase_oportunidade and "conferência manual" in js.frase_oportunidade, js.frase_oportunidade

est = lead_de(ESTATICO)
chaves = {s.chave for s in est.sinais}
assert est.diagnostico.renderizado_js is False
assert {"sem_instagram", "sem_formulario", "sem_mensuracao"} <= chaves, chaves
assert "site_js" not in chaves
assert est.score > js.score

fora = lead_de("", status=0)
chaves = {s.chave for s in fora.sinais}
assert "site_fora" in chaves and "sem_instagram" not in chaves, chaves
assert "Instagram" not in fora.frase_oportunidade, fora.frase_oportunidade

print("✓ site montado por JS: só afirma o que o HTML servido mostra")
