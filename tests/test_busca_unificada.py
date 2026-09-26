"""Uma busca só: Places e registro da Receita no mesmo resultado.

O Places só conhece quem está no Maps, e o CNPJ só é lido do rodapé do site. Quem
abriu o CNPJ mês passado e ainda não tem nem site nem ficha no Google desaparecia
da busca — sendo exatamente quem precisa comprar um site.
"""
import pytest

from prospector.sources import receita_leads as rl


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)


def configurar(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "chave")


class _Resp:
    def __init__(self, corpo, status=200):
        self._c, self.status_code = corpo, status
        self.headers = {"Content-Range": f"0-0/{len(corpo)}"}

    def json(self):
        return self._c


class _Cliente:
    def __init__(self, resp):
        self.resp, self.chamadas = resp, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.chamadas.append(dict(params or []))
        return self.resp


# --- nicho -> CNAE ---------------------------------------------------------------

def test_nicho_vira_cnae():
    assert rl.cnaes_do_nicho("odontologia") == ["8630504"]
    assert rl.cnaes_do_nicho("automotivo") == ["4520006", "4530703"]


def test_acento_e_caixa_nao_atrapalham():
    """A tela manda "estética"; quem digita pode mandar "ESTETICA"."""
    assert rl.cnaes_do_nicho("estética") == rl.cnaes_do_nicho("ESTETICA") != []


def test_fisioterapia_e_nutricao_usam_os_codigos_que_existem():
    """8650041 e 8650052 não existem na tabela da Receita e voltavam vazio calado."""
    assert rl.cnaes_do_nicho("fisioterapia") == ["8650004"]
    assert rl.cnaes_do_nicho("nutrição") == ["8650002"]
    for codigo in ("8650041", "8650052"):
        assert codigo not in rl.SEGMENTOS


def test_nicho_sem_cnae_proprio_nao_inventa():
    """A CNAE não separa especialidade médica: mapear dermatologia para o código
    genérico devolveria todo médico da cidade."""
    assert rl.cnaes_do_nicho("dermatologia") == []
    assert rl.cnaes_do_nicho("oftalmologia") == []
    assert rl.cnaes_do_nicho("nicho que nao existe") == []


# --- local -----------------------------------------------------------------------

def test_local_vira_municipio_e_uf():
    assert rl.partes_do_local("Brasília, DF") == ("BRASILIA", "DF")
    assert rl.partes_do_local("São Paulo, SP") == ("SAO PAULO", "SP")


def test_local_so_com_uf():
    assert rl.partes_do_local("DF") == ("", "DF")


# --- a consulta que complementa ---------------------------------------------------

def test_complementar_pede_os_cnaes_do_nicho(monkeypatch):
    configurar(monkeypatch)
    c = _Cliente(_Resp([{"cnpj": "11111111000155"}]))
    rl.complementar("automotivo", "Cuiabá, MT", limite=30, sessao=c)
    p = c.chamadas[0]
    assert p["cnae"] == "in.(4520006,4530703)"
    assert p["uf"] == "eq.MT"
    assert p["municipio"] == "eq.CUIABA"
    assert p["order"] == "chance_dono.desc,abertura.desc"


def test_nao_repete_quem_o_places_ja_trouxe(monkeypatch):
    configurar(monkeypatch)
    c = _Cliente(_Resp([{"cnpj": "11111111000155"}, {"cnpj": "22222222000166"}]))
    r = rl.complementar("odontologia", "Brasília, DF",
                        cnpjs_ignorados={"11111111000155"}, sessao=c)
    assert [d["cnpj"] for d in r] == ["22222222000166"]


def test_nicho_sem_cnae_nao_consulta_nada(monkeypatch):
    configurar(monkeypatch)
    c = _Cliente(_Resp([]))
    assert rl.complementar("dermatologia", "Brasília, DF", sessao=c) == []
    assert c.chamadas == [], "não gasta requisição quando não há o que pedir"


def test_sem_configuracao_nao_quebra():
    assert rl.complementar("odontologia", "Brasília, DF") == []


def test_registro_fora_do_ar_devolve_vazio(monkeypatch):
    """Perder o complemento é aceitável; perder a busca do Places não é."""
    import requests
    configurar(monkeypatch)

    class Caindo:
        def get(self, *a, **k):
            raise requests.RequestException("502")

    assert rl.complementar("odontologia", "Brasília, DF", sessao=Caindo()) == []


# --- a conversão em Lead -----------------------------------------------------------

LINHA = {"empresa": "DAVID LUIZ SOARES CAMARGO", "decisor": "DAVID LUIZ SOARES CAMARGO",
         "decisor_papel": "Titular (MEI/EI)", "telefone": "6598159451",
         "tipo_telefone": "celular", "email": "davy@gmail.com", "municipio": "CUIABA",
         "uf": "MT", "abertura": "2026-09-13", "cnae": "9602501",
         "cnpj": "69097419000100", "chance_dono": 80}


def test_lead_do_registro_e_marcado_como_tal():
    l = rl.para_lead(LINHA, "estética", "estética|Cuiabá, MT")
    assert l.origem == "receita", "a lista precisa distinguir de onde veio"
    assert l.cnpj == "69097419000100"
    assert l.decisor == "DAVID LUIZ SOARES CAMARGO"
    assert l.categoria == "Barbearia e salão"


def test_sem_site_e_a_oportunidade_nao_um_defeito():
    """Nota do Google vazia aqui não é sinal ruim: o Maps só não o conhece."""
    l = rl.para_lead(LINHA)
    assert l.score >= 45 and l.faixa in ("quente", "morno")
    assert any(s.chave == "sem_site_no_registro" for s in l.sinais)
    assert l.nota is None and l.site is None


def test_lead_traz_o_contato_pronto():
    l = rl.para_lead(LINHA)
    assert l.contatos.telefone == "6598159451"
    assert "wa.me/556598159451" in (l.contatos.whatsapp or "")
    assert l.contatos.emails == ["davy@gmail.com"]


def test_lead_sem_decisor_nao_quebra():
    l = rl.para_lead({"empresa": "LOJA X", "cnae": "9602501", "cnpj": "1", "abertura": "2026-05-01"})
    assert l.nome == "LOJA X"
    assert l.decisor is None
    assert not any(s.chave == "decisor_conhecido" for s in l.sinais)


def test_celular_vale_mais_que_fixo_no_score():
    com = rl.para_lead({**LINHA, "tipo_telefone": "celular"})
    sem = rl.para_lead({**LINHA, "tipo_telefone": "fixo"})
    assert com.score > sem.score, "celular quase sempre é o dono; fixo é a recepção"
