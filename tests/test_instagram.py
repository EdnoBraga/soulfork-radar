"""Business Discovery: achatamento da resposta e tradução dos erros da Meta."""
import pytest

from prospector.sources import instagram as ig


def test_extrai_seguidores_e_ultima_publicacao():
    d = ig.extrair({
        "username": "padaria_x",
        "followers_count": 1840,
        "media_count": 97,
        "biography": "Pães desde 1998",
        "media": {"data": [{"timestamp": "2024-11-03T14:22:10+0000"}]},
    })
    assert d["seguidores"] == 1840
    assert d["ultima_publicacao"] == "2024-11-03"
    assert d["publicacoes"] == 97


def test_perfil_sem_publicacao_nao_quebra():
    d = ig.extrair({"username": "novo", "followers_count": 12})
    assert d["ultima_publicacao"] is None
    assert d["bio"] is None


def test_conta_pessoal_vira_indisponivel_nao_erro():
    erro = ig._traduzir({"code": 100, "message": "does not exist"})
    assert isinstance(erro, ig.IndisponivelError)


def test_limite_e_token_sao_erro_do_radar():
    assert isinstance(ig._traduzir({"code": 4, "message": "x"}), ig.InstagramError)
    assert isinstance(ig._traduzir({"code": 190, "message": "x"}), ig.InstagramError)


def test_arroba_vazio_nao_gasta_chamada():
    with pytest.raises(ig.IndisponivelError):
        ig.consultar("", "token", "123")
