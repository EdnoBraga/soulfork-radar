"""O quadro societário já chegava na resposta da BrasilAPI e era jogado fora.

Sem o nome de quem decide, a abordagem cai no atendimento: dos 35 contatos do CRM
só 1 tinha nome de pessoa, e 19 das respostas de WhatsApp eram o robô de recepção
da própria empresa prospectada — 65 envios, 0 respostas humanas.
"""
from prospector.sources.cnpj import escolher_decisor


def test_administrador_ganha_do_socio_comum():
    qsa = [
        {"nome_socio": "CARLOS SILVA", "qualificacao_socio": "Sócio"},
        {"nome_socio": "ANA PAULA LIMA", "qualificacao_socio": "Sócio-Administrador"},
    ]
    assert escolher_decisor(qsa, "BARBEARIA X LTDA") == {
        "nome": "ANA PAULA LIMA", "papel": "Sócio-Administrador"}


def test_sem_administrador_fica_o_primeiro_socio():
    qsa = [{"nome_socio": "JOAO PEREIRA", "qualificacao_socio": "Sócio"}]
    d = escolher_decisor(qsa, "X LTDA")
    assert d["nome"] == "JOAO PEREIRA"


def test_mei_tira_o_dono_da_razao_social():
    # MEI não tem quadro societário: a Receita põe o nome da pessoa + CPF.
    d = escolher_decisor([], "JOSE CARLOS PEREIRA 98765432100")
    assert d == {"nome": "JOSE CARLOS PEREIRA", "papel": "Titular (MEI/EI)"}


def test_empresa_sem_qsa_e_sem_cpf_na_razao_nao_inventa_nome():
    assert escolher_decisor([], "COMERCIO DE PECAS LTDA") is None
    assert escolher_decisor(None, None) is None


def test_ignora_entrada_malformada_sem_quebrar():
    assert escolher_decisor(["texto solto", {}, {"nome_socio": ""}], None) is None


def test_diretor_e_presidente_tambem_decidem():
    for papel in ("Diretor", "Presidente", "Administrador"):
        d = escolher_decisor([
            {"nome_socio": "FULANO", "qualificacao_socio": "Sócio"},
            {"nome_socio": "BELTRANO", "qualificacao_socio": papel},
        ], None)
        assert d["nome"] == "BELTRANO", papel


def test_consultar_devolve_decisor_junto_do_cadastro(monkeypatch):
    """A captura tem que sair na mesma chamada que já era feita, sem requisição extra."""
    from prospector.sources import cnpj as mod

    class RespostaFalsa:
        status_code = 200

        @staticmethod
        def json():
            return {
                "razao_social": "CLINICA ODONTO SORRISO LTDA",
                "nome_fantasia": "Odonto Sorriso",
                "cnae_fiscal": 8630504,
                "cnae_fiscal_descricao": "Atividade odontológica",
                "descricao_situacao_cadastral": "ATIVA",
                "municipio": "BRASILIA", "uf": "DF",
                "data_inicio_atividade": "2026-07-10",
                "ddd_telefone_1": "6133334444",
                "email": "Contato@Odonto.com ",
                "qsa": [{"nome_socio": "RENATA GOMES", "qualificacao_socio": "Sócio-Administrador"}],
            }

    chamadas = []

    class ClienteFalso:
        @staticmethod
        def get(url, timeout=None):
            chamadas.append(url)
            return RespostaFalsa()

    d = mod.consultar("00.000.000/0001-91", sessao=ClienteFalso)
    assert len(chamadas) == 1, "nenhuma requisição a mais que a que já existia"
    assert d["decisor"] == "RENATA GOMES"
    assert d["decisor_papel"] == "Sócio-Administrador"
    assert d["razao_social"] == "CLINICA ODONTO SORRISO LTDA"
    assert d["email_receita"] == "contato@odonto.com"


def test_decisor_chega_no_csv_exportado():
    from prospector.export import COLUNAS

    chaves = [c[0] for c in COLUNAS]
    assert "decisor" in chaves and "decisor_papel" in chaves
    # tem que vir logo depois do CNPJ, junto do resto do cadastro
    assert chaves.index("decisor") == chaves.index("cnpj") + 1
