"""Fila da Receita: filtros, link de WhatsApp e a tela que não pode cair.

O Find depende de o CNPJ estar no rodapé do site. Quem não tem site fica de fora —
e é exatamente quem mais precisa de um. Esta tela cobre esse buraco lendo a tabela
receita_leads no Supabase.
"""
import pytest

from urllib.parse import unquote

from prospector.sources import receita_leads as rl


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_SECRET_KEY",
              "FIND_SENHA", "SUPABASE_ANON_KEY", "FIND_EMAILS"):
        monkeypatch.delenv(k, raising=False)


def configurar(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "chave-de-servico")


class _Resp:
    def __init__(self, corpo, status=200, total=0):
        self._c, self.status_code = corpo, status
        self.headers = {"Content-Range": f"0-{max(0, len(corpo) - 1)}/{total or len(corpo)}"}

    def json(self):
        return self._c


class _Cliente:
    def __init__(self, resp):
        self.resp, self.chamadas = resp, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.chamadas.append({"url": url, "params": params, "headers": headers})
        return self.resp


# --- filtros -------------------------------------------------------------------

def test_sem_filtro_nenhum_nao_manda_condicao():
    assert rl.montar_filtros() == []


def test_cidade_vira_municipio_mais_uf():
    """A tela manda "BRASILIA/DF" num campo só; a tabela tem duas colunas.
    Sem separar, Belem-PA e Belem-PB voltariam juntas."""
    assert rl.montar_filtros(cidade="BRASILIA/DF") == [("municipio", "eq.BRASILIA"), ("uf", "eq.DF")]


def test_filtros_combinados():
    p = dict(rl.montar_filtros(cidade="SALVADOR/BA", segmento="9602501",
                               so_celular=True, so_com_nome=True, aberta_apos="2026-01-01"))
    assert p["cnae"] == "eq.9602501"
    assert p["tipo_telefone"] == "eq.celular"
    assert p["decisor"] == "not.is.null"
    assert p["abertura"] == "gte.2026-01-01"


def test_checkbox_desmarcado_nao_filtra():
    assert ("tipo_telefone", "eq.celular") not in rl.montar_filtros(so_celular=False)


# --- leitura --------------------------------------------------------------------

def test_busca_ordena_pela_chance_e_pagina(monkeypatch):
    configurar(monkeypatch)
    c = _Cliente(_Resp([{"cnpj": "1"}], total=13052))
    r = rl.buscar(pagina=2, por_pagina=100, sessao=c)
    assert r["total"] == 13052
    p = dict(c.chamadas[0]["params"])
    assert p["order"] == "chance_dono.desc,abertura.desc"
    assert c.chamadas[0]["headers"]["Range"] == "200-299", "terceira página"
    assert c.chamadas[0]["headers"]["Authorization"] == "Bearer chave-de-servico"


def test_erro_do_supabase_vira_excecao_clara(monkeypatch):
    configurar(monkeypatch)
    with pytest.raises(RuntimeError):
        rl.buscar(sessao=_Cliente(_Resp([], status=401)))


def test_cidades_sem_rede_devolve_lista_vazia(monkeypatch):
    import requests
    configurar(monkeypatch)

    class Caindo:
        def get(self, *a, **k):
            raise requests.RequestException("sem rede")

    assert rl.cidades(sessao=Caindo()) == []


def test_cidades_sao_unicas_e_ordenadas(monkeypatch):
    configurar(monkeypatch)
    c = _Cliente(_Resp([{"municipio": "SALVADOR", "uf": "BA"},
                        {"municipio": "BRASILIA", "uf": "DF"},
                        {"municipio": "SALVADOR", "uf": "BA"}]))
    assert rl.cidades(sessao=c) == ["BRASILIA/DF", "SALVADOR/BA"]


# --- o link que fura a recepção --------------------------------------------------

def test_whatsapp_chama_a_pessoa_pelo_nome():
    url = rl.link_whatsapp("61999990001", "RENATA GOMES DA SILVA")
    assert url.startswith("https://wa.me/5561999990001?text=")
    assert "Oi, Renata?" in unquote(url), "o nome na primeira palavra e o que passa da recepcao"


def test_whatsapp_sem_nome_nao_inventa():
    url = rl.link_whatsapp("61999990001", None)
    assert url and "Oi!" in unquote(url)
    assert "None" not in unquote(url), "sem nome nao pode vazar o None do banco"


def test_whatsapp_recusa_numero_curto():
    assert rl.link_whatsapp("9999", "ALGUEM") == ""
    assert rl.link_whatsapp(None, "ALGUEM") == ""


def test_primeiro_nome_do_registro_em_caixa_alta():
    assert rl.primeiro_nome("MARIA DAS DORES SOUZA") == "Maria"
    assert rl.primeiro_nome("") == ""
    assert rl.primeiro_nome("X SILVA") == "", "inicial solta não é nome"


# --- a tela ---------------------------------------------------------------------

def test_tela_explica_o_que_falta_quando_nao_ha_chave(monkeypatch):
    from prospector.web.app import app
    with app.test_client() as c:
        html = c.get("/receita").get_data(as_text=True)
    # O nome tem que bater com o que ele ve na tela do Supabase hoje: a chave virou
    # "Secret key" / sb_secret_, e mandar procurar "service_role" e mandar procurar
    # um nome que nao existe mais na interface.
    assert "SUPABASE_SECRET_KEY" in html
    assert "sb_secret_" in html
    assert "Secret keys" in html


def test_tela_nao_cai_quando_o_supabase_esta_fora(monkeypatch):
    """Perder a base é chato; derrubar o Find inteiro por causa disso é pior."""
    from prospector.web.app import app
    configurar(monkeypatch)
    monkeypatch.setattr(rl, "buscar", lambda **k: (_ for _ in ()).throw(RuntimeError("502")))
    monkeypatch.setattr(rl, "cidades", lambda *a, **k: [])
    with app.test_client() as c:
        r = c.get("/receita")
    assert r.status_code == 200
    assert "Não consegui ler a base agora" in r.get_data(as_text=True)


def test_tela_lista_as_empresas(monkeypatch):
    from prospector.web.app import app
    configurar(monkeypatch)
    monkeypatch.setattr(rl, "cidades", lambda *a, **k: ["BRASILIA/DF"])
    monkeypatch.setattr(rl, "buscar", lambda **k: {"total": 1, "pagina": 0, "por_pagina": 100,
        "linhas": [{"cnpj": "69097419000100", "empresa": "DAVID LUIZ SOARES CAMARGO",
                    "decisor": "DAVID LUIZ SOARES CAMARGO", "decisor_papel": "Titular (MEI/EI)",
                    "telefone": "6598159451", "tipo_telefone": "celular", "municipio": "CUIABA",
                    "uf": "MT", "abertura": "2026-09-13", "cnae": "9602501", "chance_dono": 80}]})
    with app.test_client() as c:
        html = c.get("/receita").get_data(as_text=True)
    assert "DAVID LUIZ SOARES CAMARGO" in html
    assert "Barbearia e salão" in html, "o CNAE vira nome de gente entender"
    assert "wa.me/556598159451" in html
    assert "celular" in html


def test_pagina_invalida_na_url_nao_quebra(monkeypatch):
    from prospector.web.app import app
    configurar(monkeypatch)
    monkeypatch.setattr(rl, "cidades", lambda *a, **k: [])
    vistos = {}

    def falso(**k):
        vistos.update(k)
        return {"total": 0, "pagina": 0, "por_pagina": 100, "linhas": []}

    monkeypatch.setattr(rl, "buscar", falso)
    with app.test_client() as c:
        assert c.get("/receita?p=abacaxi").status_code == 200
        assert c.get("/receita?p=-5").status_code == 200
    assert vistos["pagina"] == 0
