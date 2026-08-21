"""Teste ponta a ponta contra sites locais — sem internet."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.servidor import servir
from prospector.enrich.site import ColetorSite
from prospector.pipeline import montar_lead, enriquecer
from prospector import export, report

URLS = {p: servir(p) for p in ("clinica_ruim", "contabil_ok", "estetica_media")}

CASOS = [
    ("Clínica Vida Plena", URLS["clinica_ruim"],   "fisioterapia",  5.0, 40),
    ("BSB Contábil",       URLS["contabil_ok"],    "contabilidade", 4.8, 120),
    ("Grand Estética",     URLS["estetica_media"], "estetica",      4.2, 15),
]

leads = []
for nome, url, nicho, nota, aval in CASOS:
    coletor = ColetorSite(respeitar_robots=False)
    lead = montar_lead({
        "nome": nome, "site": url, "nicho": nicho,
        "municipio": "Brasília", "uf": "DF", "nota": nota, "avaliacoes": aval,
        "telefone": "(61) 3344-5566", "telefone_intl": "+55 61 3344-5566",
        "endereco": "SQN 000, Brasília - DF", "place_id": "fake_" + nicho,
        "google_maps_url": "https://maps.google.com/?cid=1",
    }, nicho, "teste local")
    lead = enriquecer(lead, coletor, consultar_cnpj=False)  # sem internet -> pula Receita
    leads.append(lead)

leads.sort(key=lambda l: -l.score)

falhas = []
def check(cond, msg):
    if not cond:
        falhas.append(msg)

for l in leads:
    d = l.diagnostico
    print(f"\n{'='*70}\n{l.score:>3} [{l.faixa}] {l.nome}")
    print(f"  site_no_ar={d.site_no_ar} https={d.https} resp={d.responsivo} "
          f"gtm={d.tem_gtm} pixel={d.tem_meta_pixel} ga4={d.tem_ga4}")
    print(f"  politica={d.tem_politica_privacidade} quebrada={d.politica_quebrada} "
          f"form={d.tem_formulario} sensivel={d.coleta_dado_sensivel} sitemap={d.tem_sitemap}")
    print(f"  cms={d.cms} {d.cms_versao or ''}")
    print(f"  emails={l.contatos.emails}")
    print(f"  wa={l.contatos.whatsapp} ig=@{l.redes.instagram} tt=@{l.redes.tiktok} "
          f"fb={l.redes.facebook} li={l.redes.linkedin}")
    print(f"  cnpj={l.cnpj}")
    for s in l.sinais:
        print(f"    {'+' if s.pontos else ' '}{s.pontos or '':>3}  {s.titulo}")

por_nome = {l.nome: l for l in leads}

# --- asserções ---
c = por_nome["Clínica Vida Plena"]
check(c.diagnostico.site_no_ar is True, "clinica: site deveria estar no ar")
check(c.diagnostico.responsivo is False, "clinica: deveria detectar falta de viewport")
check(c.diagnostico.tem_gtm is False and c.diagnostico.tem_meta_pixel is False, "clinica: nao deveria achar GTM/Pixel")
check(c.diagnostico.tem_ga4 is None, "clinica: GA4 deve ser None (nao verificavel)")
check(c.diagnostico.tem_politica_privacidade is False, "clinica: deveria acusar falta de politica")
check(c.diagnostico.coleta_dado_sensivel is True, "clinica: deveria detectar CPF/queixa no form")
check(c.diagnostico.cms == "WordPress" and c.diagnostico.cms_versao == "5.4.2", f"clinica: CMS errado ({c.diagnostico.cms} {c.diagnostico.cms_versao})")
check(c.contatos.whatsapp == "5561991234567", f"clinica: whatsapp errado ({c.contatos.whatsapp})")
check(c.redes.instagram == "clinicavidaplena", f"clinica: instagram errado ({c.redes.instagram})")
check(c.cnpj == "19.131.243/0001-97", f"clinica: cnpj errado ({c.cnpj})")
check(c.diagnostico.tem_sitemap is False, "clinica: nao deveria achar sitemap")

b = por_nome["BSB Contábil"]
check(b.diagnostico.tem_gtm is True, "contabil: deveria achar GTM")
check(b.diagnostico.tem_meta_pixel is True, "contabil: deveria achar Pixel")
check(b.diagnostico.tem_politica_privacidade is True and not b.diagnostico.politica_quebrada, "contabil: politica deveria estar ok")
check(b.diagnostico.tem_sitemap is True, "contabil: deveria achar sitemap")
check(b.diagnostico.responsivo is True, "contabil: deveria ser responsivo")
check("contato@bsbcontabil.com.br" == b.contatos.emails[0], f"contabil: email principal errado ({b.contatos.emails})")
check(b.redes.tiktok == "bsbcontabil", f"contabil: tiktok errado ({b.redes.tiktok})")
check(b.redes.linkedin == "bsbcontabil", f"contabil: linkedin errado ({b.redes.linkedin})")

g = por_nome["Grand Estética"]
check(g.diagnostico.tem_meta_pixel is True, "estetica: deveria achar Pixel")
check(g.diagnostico.tem_gtm is False, "estetica: nao deveria achar GTM")
check(g.diagnostico.politica_quebrada is True, f"estetica: politica deveria estar quebrada (status={g.diagnostico.tem_politica_privacidade})")
check(g.contatos.whatsapp == "5561998887777", f"estetica: whatsapp errado ({g.contatos.whatsapp})")
check(any(s.chave == "aviso_ingles" for s in g.sinais), "estetica: deveria sinalizar aviso em ingles")

check(c.score > b.score, f"clinica ({c.score}) deveria pontuar mais que contabil ({b.score})")

# saídas
os.makedirs("/tmp/saida_teste", exist_ok=True)
export.para_csv(leads, "/tmp/saida_teste/teste.csv")
x = export.para_xlsx(leads, "/tmp/saida_teste/teste.xlsx")
h = report.gerar(leads, "/tmp/saida_teste/teste.html", "Teste local", "3 sites falsos")
check(os.path.getsize("/tmp/saida_teste/teste.csv") > 500, "csv vazio")
check(x and os.path.getsize(x) > 3000, "xlsx vazio")
check(os.path.getsize(h) > 5000, "html vazio")

print("\n" + "="*70)
if falhas:
    print(f"✗ {len(falhas)} FALHAS:")
    for f in falhas: print("  -", f)
    sys.exit(1)
print("✓ todas as asserções passaram")
