"""Testa a interface web com uma rodada simulada (sem Places API)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PROSPECTOR_BANCO"] = "/tmp/teste_web.db"
os.environ["PROSPECTOR_SAIDA"] = "/tmp/teste_web_saida"
if os.path.exists("/tmp/teste_web.db"): os.remove("/tmp/teste_web.db")

from tests.servidor import servir
from prospector.enrich.site import ColetorSite
from prospector.pipeline import montar_lead, enriquecer
from prospector.store import Banco, chave_do_lead
from prospector import config
from prospector.web.app import app, RODADAS
from datetime import datetime

URLS = {p: servir(p) for p in ("clinica_ruim", "contabil_ok", "estetica_media")}

# monta uma rodada como se a busca tivesse acontecido
CASOS = [
    ("Clínica Vida Plena", URLS["clinica_ruim"], 5.0, 40, 1),
    ("BSB Contábil", URLS["contabil_ok"], 4.8, 120, 2),
    ("Grand Estética", URLS["estetica_media"], 4.2, 15, 3),
    ("Sorriso Norte Odonto", None, 4.9, 320, 4),   # sem site: "pronta pra abordar"
]
leads = []
for nome, url, nota, aval, pos in CASOS:
    coletor = ColetorSite(respeitar_robots=False)
    lead = montar_lead({
        "nome": nome, "site": url, "municipio": "Brasília", "uf": "DF",
        "nota": nota, "avaliacoes": aval, "posicao_maps": pos,
        "telefone": "(61) 99911-2233", "telefone_intl": "+55 61 99911-2233",
        "place_id": "fake_" + nome.replace(" ", "_"),
        "google_maps_url": "https://maps.google.com/?cid=1",
    }, "dentista", "dentista em Brasília, DF")
    leads.append(enriquecer(lead, coletor, consultar_cnpj=False))

banco = Banco(config.caminho_banco())
novos = set()
for l in leads:
    if banco.salvar(l): novos.add(chave_do_lead(l))
banco.registrar_posicoes("dentista|brasília, df", leads)
banco.registrar_rodada("dentista", "Brasília, DF", len(leads), len(novos), rid="teste123abc",
                       dados={"novos": sorted(novos), "anteriores": {}, "chamadas": 2,
                              "chaves": [chave_do_lead(l) for l in leads]})
banco.fechar()

RODADAS["teste123abc"] = {
    "status": "pronta", "nicho": "dentista", "local": "Brasília, DF",
    "quantidade": 4, "log": ["ok"], "leads": [l.to_dict() for l in leads],
    "novos": sorted(novos), "anteriores": {}, "chamadas": 2,
    "criada_em": datetime.now().astimezone().isoformat(timespec="seconds"),
    "terminou_em": datetime.now().astimezone().isoformat(timespec="seconds"),
}

c = app.test_client()
falhas = []
def check(cond, msg):
    if not cond: falhas.append(msg)

r = c.get("/");                              check(r.status_code == 200, f"/ -> {r.status_code}")
check("Diagnóstico antes" in r.text and "Radar" not in r.text, "home sem hero novo / com marca antiga")
check("Dentistas" in r.text, "home sem placeholder de sugestões")

r = c.get("/rodada/teste123abc/leads");      check(r.status_code == 200, f"leads -> {r.status_code}")
check("Sorriso Norte Odonto" in r.text, "lead sem site não apareceu")
check("sem site nenhum" in r.text, "frase de oportunidade não apareceu")
check("wa.me/5561999112233" in r.text, "link de whatsapp ausente")
check("@clinicavidaplena" in r.text, "instagram ausente")
check("Novo" in r.text, "badge Novo ausente")
check("no Maps" in r.text, "ranking ausente")

r = c.get("/rodada/teste123abc/leads?p=sem-site"); check("Sorriso Norte" in r.text and "BSB" not in r.text, "filtro sem-site errado")
r = c.get("/rodada/teste123abc/leads?c=whatsapp"); check(r.status_code == 200, "filtro whatsapp falhou")
r = c.get("/rodada/teste123abc/leads?p=lgpd");     check("Clínica Vida Plena" in r.text, "filtro lgpd não pegou a clínica")

r = c.get("/rodada/teste123abc/analises");   check(r.status_code == 200, f"analises -> {r.status_code}")
check("pronta" in r.text and "abordar hoje" in r.text, "seção 'prontas pra abordar' ausente")
check("Sorriso Norte Odonto" in r.text, "empresa pronta não listada")
check("Por que o topo ganha" in r.text, "seção topo ausente")
check("Primeira varredura" in r.text, "aviso de primeira varredura ausente")

r = c.get("/rodada/teste123abc/exportar/csv");  check(r.status_code == 200 and len(r.data) > 500, "csv falhou")
r = c.get("/rodada/teste123abc/exportar/xlsx"); check(r.status_code == 200 and len(r.data) > 3000, "xlsx falhou")
r = c.get("/rodada/teste123abc/exportar/pdf");  check(r.status_code == 200 and r.data[:4] == b"%PDF", "pdf falhou")

r = c.get("/banco");                         check(r.status_code == 200 and "Sorriso Norte" in r.text, "banco falhou")

# motivos da nota e custo da busca
r = c.get("/rodada/teste123abc/leads")
check("Por que" in r.text and "Site sem HTTPS" in r.text, "motivos da nota ausentes")
check("2</b> chamada(s) ao Google" in r.text, "custo da busca ausente")

# andamento do lead
chave_clinica = chave_do_lead(leads[0])
r = c.post("/lead/status", json={"chave": chave_clinica, "status": "contatado"})
check(r.status_code == 200 and r.json["ok"], f"mudar status falhou: {r.status_code}")
r = c.post("/lead/status", json={"chave": chave_clinica, "status": "inventado"})
check(r.status_code == 400, "status inválido foi aceito")
r = c.post("/lead/status", json={"chave": "place:nao_existe", "status": "ganho"})
check(r.status_code == 404, "lead inexistente foi aceito")
r = c.get("/rodada/teste123abc/leads?s=contatado")
check("Clínica Vida Plena" in r.text and "BSB Contábil" not in r.text, "filtro de andamento errado")
r = c.get("/banco?s=contatado")
check("Clínica Vida Plena" in r.text and "BSB Contábil" not in r.text, "filtro de andamento no banco errado")
check("3 ainda não abordados" in c.get("/banco").text, "resumo de não abordados não mudou")

# rodada sobrevive a reinício do servidor (some da memória, volta do banco)
RODADAS.clear()
r = c.get("/rodada/teste123abc/leads")
check(r.status_code == 200 and "Sorriso Norte Odonto" in r.text, "rodada não reabriu do banco")
check("/rodada/teste123abc/leads" in c.get("/").text, "histórico sem a rodada salva")
check(c.get("/rodada/naoexiste/leads").status_code == 404, "rodada inexistente não deu 404")

# resolução de nicho
nichos = {"odontologia": {"termos": ["clínica odontológica", "dentista"], "tipo": "dentist"},
          "restaurante": {"termos": ["restaurante", "pizzaria", "hamburgueria"], "tipo": "restaurant"}}
check(config.termos_do_nicho("Odontologia", nichos) == ("odontologia", ["clínica odontológica", "dentista"], "dentist"),
      "nome do nicho não expandiu")
check(config.termos_do_nicho("Dentistas", nichos) == ("odontologia", ["Dentistas"], "dentist"),
      "termo do nicho não virou busca única com tipo")
check(config.termos_do_nicho("pizzaria", nichos)[1] == ["pizzaria"], "pizzaria puxou hamburgueria")
check(config.termos_do_nicho("tatuagem", nichos) == (None, ["tatuagem"], None), "termo livre errado")

# login: com FIND_SENHA definida, nada abre sem entrar
os.environ["FIND_SENHA"] = "senha-de-teste-123"
anon = app.test_client()
r = anon.get("/banco")
check(r.status_code == 302 and "/entrar" in r.headers["Location"], "banco abriu sem login")
check(anon.get("/configuracao").status_code == 302, "configuração abriu sem login")
check(anon.get("/rodada/teste123abc/exportar/csv").status_code == 302, "exportação abriu sem login")
r = anon.post("/lead/status", json={"chave": chave_clinica, "status": "ganho"})
check(r.status_code == 401, f"POST sem login não deu 401: {r.status_code}")
check(anon.get("/saude").text == "ok", "rota de saúde exige login")
r = anon.post("/entrar", data={"senha": "errada", "proximo": "/banco"})
check(r.status_code == 200 and "Senha incorreta" in r.text, "senha errada não foi recusada")
r = anon.post("/entrar", data={"senha": "senha-de-teste-123", "proximo": "//evil.com"})
check(r.status_code == 302 and r.headers["Location"] == "/", "redirecionou para fora do site")
check(anon.get("/banco").status_code == 200, "login certo não abriu o banco")
check("Sair" in anon.get("/banco").text, "link de sair ausente")
anon.get("/sair")
check(anon.get("/banco").status_code == 302, "sair não encerrou a sessão")
del os.environ["FIND_SENHA"]

# frases de oportunidade coerentes
por_nome = {l.nome: l for l in leads}
s = por_nome["Sorriso Norte Odonto"].frase_oportunidade
check("sem site nenhum" in s and "320" in s, f"frase do sem-site errada: {s}")
s = por_nome["BSB Contábil"].frase_oportunidade
check("presença completa" in s, f"frase do completo errada: {s}")

print()
if falhas:
    print(f"✗ {len(falhas)} FALHAS:"); [print("  -", f) for f in falhas]; sys.exit(1)
print("✓ interface web: todas as checagens passaram")
for l in sorted(leads, key=lambda x: -x.score):
    print(f"  {l.score:>3} #{l.posicao_maps} {l.nome:<24} {l.frase_oportunidade}")
