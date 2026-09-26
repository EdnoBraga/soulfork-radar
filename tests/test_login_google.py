"""Entrar com a conta Google, verificado no servidor.

O risco desta mudança não é o login não funcionar — é o portão abrir sozinho.
Antes, `before_request` liberava tudo quando FIND_SENHA estava vazia; trocar a
senha pelo Google sem mexer nisso publicaria o Find aberto na internet.
"""
import os

import pytest

from prospector.web import google_auth


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    for k in ("FIND_SENHA", "SUPABASE_URL", "SUPABASE_ANON_KEY",
              "SUPABASE_PUBLISHABLE_KEY", "FIND_EMAILS"):
        monkeypatch.delenv(k, raising=False)


class _Resposta:
    def __init__(self, status, corpo=None):
        self.status_code = status
        self._corpo = corpo if corpo is not None else {}

    def json(self):
        if self._corpo == "lixo":
            raise ValueError("não é json")
        return self._corpo


class _Cliente:
    def __init__(self, resposta):
        self.resposta = resposta
        self.chamadas = []

    def get(self, url, headers=None, timeout=None):
        self.chamadas.append((url, headers))
        return self.resposta


def _configurar(monkeypatch, emails="edno@soulfork.com.br"):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co/")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "chave-publica")
    monkeypatch.setenv("FIND_EMAILS", emails)


def test_sem_config_nao_oferece_google():
    assert google_auth.configurado() is False
    assert google_auth.email_do_token("qualquer") is None


def test_token_valido_devolve_email(monkeypatch):
    _configurar(monkeypatch)
    c = _Cliente(_Resposta(200, {"email": "Edno@SoulFork.com.br", "aud": "authenticated"}))
    assert google_auth.email_do_token("tok", sessao=c) == "edno@soulfork.com.br"
    url, headers = c.chamadas[0]
    assert url == "https://proj.supabase.co/auth/v1/user", "barra final da URL não pode duplicar"
    assert headers["Authorization"] == "Bearer tok"
    assert headers["apikey"] == "chave-publica"


def test_token_recusado_pelo_supabase(monkeypatch):
    _configurar(monkeypatch)
    assert google_auth.email_do_token("tok", sessao=_Cliente(_Resposta(401))) is None


def test_resposta_sem_json_nao_quebra(monkeypatch):
    _configurar(monkeypatch)
    assert google_auth.email_do_token("tok", sessao=_Cliente(_Resposta(200, "lixo"))) is None


def test_supabase_fora_do_ar_nao_deixa_entrar(monkeypatch):
    import requests
    _configurar(monkeypatch)

    class Caindo:
        def get(self, *a, **k):
            raise requests.RequestException("sem rede")

    assert google_auth.email_do_token("tok", sessao=Caindo()) is None


def test_lista_vazia_nao_libera_ninguem(monkeypatch):
    """Falha fechado: sem FIND_EMAILS, o mundo inteiro tem conta Google."""
    _configurar(monkeypatch, emails="")
    assert google_auth.liberado("edno@soulfork.com.br") is False


def test_so_entra_quem_esta_na_lista(monkeypatch):
    _configurar(monkeypatch, emails="edno@soulfork.com.br, socio@soulfork.com.br")
    assert google_auth.liberado("socio@soulfork.com.br") is True
    assert google_auth.liberado("estranho@gmail.com") is False
    assert google_auth.liberado(None) is False


# --- o portão -----------------------------------------------------------------

def test_portao_fechado_quando_so_ha_google(monkeypatch):
    from prospector.web.app import protegido
    _configurar(monkeypatch)
    assert protegido() is True, "com Google configurado o app não pode ficar aberto"


def test_portao_fechado_quando_so_ha_senha(monkeypatch):
    from prospector.web.app import protegido
    monkeypatch.setenv("FIND_SENHA", "uma-senha-longa")
    assert protegido() is True


def test_portao_aberto_apenas_sem_nenhuma_config():
    from prospector.web.app import protegido
    assert protegido() is False, "uso local sem login continua permitido"


def test_rota_google_recusa_token_invalido(monkeypatch):
    from prospector.web.app import app
    _configurar(monkeypatch)
    monkeypatch.setattr(google_auth, "email_do_token", lambda *a, **k: None)
    monkeypatch.setattr("prospector.web.app.time.sleep", lambda s: None)
    with app.test_client() as c:
        r = c.post("/entrar/google", json={"token": "falso"})
    assert r.status_code == 403
    assert r.get_json()["ok"] is False


def test_rota_google_recusa_email_fora_da_lista(monkeypatch):
    from prospector.web.app import app
    _configurar(monkeypatch, emails="edno@soulfork.com.br")
    monkeypatch.setattr(google_auth, "email_do_token", lambda *a, **k: "invasor@gmail.com")
    monkeypatch.setattr("prospector.web.app.time.sleep", lambda s: None)
    with app.test_client() as c:
        r = c.post("/entrar/google", json={"token": "ok"})
    assert r.status_code == 403


def test_rota_google_abre_sessao_para_email_liberado(monkeypatch):
    from prospector.web.app import app
    _configurar(monkeypatch, emails="edno@soulfork.com.br")
    monkeypatch.setattr(google_auth, "email_do_token", lambda *a, **k: "edno@soulfork.com.br")
    with app.test_client() as c:
        r = c.post("/entrar/google", json={"token": "ok"})
        assert r.status_code == 200 and r.get_json()["ok"] is True
        with c.session_transaction() as s:
            assert s["logado"] is True
            assert s["email"] == "edno@soulfork.com.br"


def test_tela_de_login_mostra_o_botao_do_google(monkeypatch):
    from prospector.web.app import app
    _configurar(monkeypatch)
    with app.test_client() as c:
        html = c.get("/entrar").get_data(as_text=True)
    assert "Entrar com Google" in html
    assert "proj.supabase.co" in html, "a chave publicável vai para o navegador, como no dashboard"
