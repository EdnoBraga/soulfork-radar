"""Fila de prospecção vinda da base aberta de CNPJ da Receita, guardada no Supabase.

O Find acha empresa pelo Google Places e pega o CNPJ no rodapé do site — então
negócio sem site fica invisível para ele, e é justamente quem mais precisa de um.
Esta tabela cobre esse buraco: vem do registro da Receita, que lista todo mundo,
com filtro por segmento, cidade e data de abertura, e traz o nome de quem decide.

Os 7GB do registro não moram aqui nem na VPS: só o resultado filtrado sobe.

A leitura usa a service key, no servidor. A chave publicável não serve: ela fica
exposta na tela de login, e a tabela tem nome de pessoa.
"""
from __future__ import annotations

import os
from typing import Any

import requests

TEMPO_LIMITE = 20
TABELA = "receita_leads"

# CNAE -> como isso se chama numa conversa. Mesmos oito segmentos dos modelos prontos.
SEGMENTOS = {
    "4789004": "Pet shop",
    "9609208": "Banho e tosa",
    "7500100": "Veterinária",
    "8630504": "Odontologia",
    "9602502": "Estética",
    "9602501": "Barbearia e salão",
    "8650004": "Fisioterapia",
    "8650002": "Nutrição",
    "8650003": "Psicologia",
    "4520006": "Borracharia",
    "4530703": "Autopeças",
    "6920601": "Contabilidade",
    "6911701": "Advocacia",
    "7111100": "Arquitetura",
    "7112000": "Engenharia",
    "7020400": "Consultoria",
    "6622300": "Seguros",
    "6821801": "Imobiliária",
    "6821802": "Imobiliária (aluguel)",
    "9313100": "Academia",
    "5611201": "Restaurante",
    "4120400": "Construção",
    "8230001": "Eventos",
}

# Os nichos que a busca do Find oferece, traduzidos para CNAE. Sem isso a busca
# não sabe o que pedir ao registro: o Places entende "barbearia", a Receita só
# entende 9602501.
#
# Os códigos foram conferidos contra a tabela Cnaes da própria Receita. Dois que
# eu tinha usado antes — 8650041 e 8650052 — simplesmente não existem, e por isso
# fisioterapia e nutrição voltavam vazias sem dar erro nenhum.
#
# Dermatologia, oftalmologia e educação ficam de fora de propósito: a CNAE não
# separa especialidade médica (todas caem em "atividade médica ambulatorial"), e
# mapear para o código genérico devolveria todo médico da cidade. Nesses nichos a
# busca segue só com o Places, que é o certo.
CNAES_POR_NICHO = {
    "fisioterapia": ["8650004"],
    "odontologia": ["8630504"],
    "estética": ["9602502", "9602501"],
    "veterinária": ["7500100", "4789004", "9609208"],
    "psicologia": ["8650003"],
    "nutrição": ["8650002"],
    "contabilidade": ["6920601"],
    "advocacia": ["6911701"],
    "arquitetura": ["7111100"],
    "engenharia": ["7112000"],
    "consultoria": ["7020400"],
    "seguros": ["6622300"],
    "imobiliária": ["6821801", "6821802"],
    "academia": ["9313100"],
    "restaurante": ["5611201"],
    "construção": ["4120400"],
    "automotivo": ["4520006", "4530703"],
    "eventos": ["8230001"],
}


def _url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def _service_key() -> str:
    return (os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_SECRET_KEY") or "").strip()


def configurado() -> bool:
    return bool(_url() and _service_key())


def _pedir(params: list[tuple[str, str]], sessao=None, prefer: str = "") -> tuple[Any, int]:
    """Devolve (json, total). O total vem do cabeçalho Content-Range do PostgREST."""
    chave = _service_key()
    cab = {"apikey": chave, "Authorization": f"Bearer {chave}",
           "Prefer": prefer or "count=exact"}
    cliente = sessao or requests
    r = cliente.get(f"{_url()}/rest/v1/{TABELA}", params=params, headers=cab, timeout=TEMPO_LIMITE)
    if getattr(r, "status_code", None) != 200:
        raise RuntimeError(f"Supabase respondeu {getattr(r, 'status_code', '?')}")
    faixa = (r.headers.get("Content-Range") or "").split("/")[-1]
    total = int(faixa) if faixa.isdigit() else 0
    return r.json(), total


def montar_filtros(cidade: str = "", segmento: str = "", so_celular: bool = False,
                   so_com_nome: bool = False, aberta_apos: str = "") -> list[tuple[str, str]]:
    """Traduz a tela em filtros do PostgREST. Separado para poder testar sem rede."""
    p: list[tuple[str, str]] = []
    if cidade:
        # a tela manda "BRASILIA/DF"; municipio e uf são colunas separadas
        nome, _, uf = cidade.partition("/")
        if nome:
            p.append(("municipio", f"eq.{nome}"))
        if uf:
            p.append(("uf", f"eq.{uf}"))
    if segmento:
        p.append(("cnae", f"eq.{segmento}"))
    if so_celular:
        p.append(("tipo_telefone", "eq.celular"))
    if so_com_nome:
        p.append(("decisor", "not.is.null"))
    if aberta_apos:
        p.append(("abertura", f"gte.{aberta_apos}"))
    return p


def buscar(cidade: str = "", segmento: str = "", so_celular: bool = False,
           so_com_nome: bool = False, aberta_apos: str = "", pagina: int = 0,
           por_pagina: int = 100, sessao=None) -> dict:
    """Uma página da fila, do melhor alvo para o pior."""
    params = montar_filtros(cidade, segmento, so_celular, so_com_nome, aberta_apos)
    params += [("select", "*"), ("order", "chance_dono.desc,abertura.desc")]
    inicio = max(0, pagina) * por_pagina
    chave = _service_key()
    cab = {"apikey": chave, "Authorization": f"Bearer {chave}",
           "Prefer": "count=exact", "Range-Unit": "items",
           "Range": f"{inicio}-{inicio + por_pagina - 1}"}
    cliente = sessao or requests
    r = cliente.get(f"{_url()}/rest/v1/{TABELA}", params=params, headers=cab, timeout=TEMPO_LIMITE)
    if getattr(r, "status_code", None) not in (200, 206):
        raise RuntimeError(f"Supabase respondeu {getattr(r, 'status_code', '?')}")
    faixa = (r.headers.get("Content-Range") or "").split("/")[-1]
    return {"linhas": r.json(), "total": int(faixa) if faixa.isdigit() else 0,
            "pagina": max(0, pagina), "por_pagina": por_pagina}


def cidades(sessao=None) -> list[str]:
    """Cidades presentes na base, para o seletor. Lista curta: cabe numa consulta só."""
    try:
        dados, _ = _pedir([("select", "municipio,uf"), ("limit", "10000")], sessao,
                          prefer="count=none")
    except (requests.RequestException, RuntimeError):
        return []
    vistos = {f"{d.get('municipio')}/{d.get('uf')}" for d in dados if d.get("municipio")}
    return sorted(vistos)


def primeiro_nome(completo: str | None) -> str:
    """"MARIA DAS DORES SOUZA" -> "Maria". O registro grava tudo em caixa alta."""
    bruto = (completo or "").strip().split()
    return bruto[0].capitalize() if bruto and len(bruto[0]) > 1 else ""


def link_whatsapp(telefone: str | None, decisor: str | None) -> str:
    """Abre a conversa já chamando a pessoa pelo nome — é isso que passa da recepção."""
    d = "".join(c for c in (telefone or "") if c.isdigit())
    if len(d) < 10:
        return ""
    nome = primeiro_nome(decisor)
    saudacao = f"Oi, {nome}? " if nome else "Oi! "
    from urllib.parse import quote
    return (f"https://wa.me/55{d}?text="
            + quote(f"{saudacao}Aqui é o Edno, da SoulFork, aqui de Brasília."))


# --- fusão com a busca do Places ------------------------------------------------

def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn")


def cnaes_do_nicho(nicho: str) -> list[str]:
    """Nicho da tela -> CNAEs. Vazio quando a CNAE não separa esse nicho."""
    chave = _sem_acento((nicho or "").strip().lower())
    for nome, codigos in CNAES_POR_NICHO.items():
        if _sem_acento(nome) == chave:
            return codigos
    return []


def partes_do_local(local: str) -> tuple[str, str]:
    """"Brasília, DF" -> ("BRASILIA", "DF"). O registro grava sem acento e em caixa alta."""
    bruto = (local or "").strip()
    if "," in bruto:
        cidade, _, uf = bruto.rpartition(",")
    else:
        cidade, uf = "", bruto
    return _sem_acento(cidade.strip()).upper(), uf.strip().upper()[:2]


def complementar(nicho: str, local: str, limite: int = 60,
                 cnpjs_ignorados: set[str] | None = None, sessao=None) -> list[dict]:
    """Empresas do registro que a busca do Places não traria.

    O Places só devolve quem está no Maps, e o CNPJ só aparece se houver site com
    rodapé. Quem abriu ontem e ainda não tem nem um nem outro só existe aqui.
    """
    if not configurado():
        return []
    cnaes = cnaes_do_nicho(nicho)
    cidade, uf = partes_do_local(local)
    if not cnaes or not uf:
        return []

    params = [("select", "*"), ("uf", f"eq.{uf}"),
              ("cnae", "in.(" + ",".join(cnaes) + ")"),
              ("order", "chance_dono.desc,abertura.desc"),
              ("limit", str(max(1, limite)))]
    if cidade:
        params.append(("municipio", f"eq.{cidade}"))
    try:
        dados, _ = _pedir(params, sessao, prefer="count=none")
    except (requests.RequestException, RuntimeError):
        return []          # registro fora do ar não pode derrubar a busca do Places

    ignorar = cnpjs_ignorados or set()
    return [d for d in dados if "".join(filter(str.isdigit, d.get("cnpj") or "")) not in ignorar]


def para_lead(linha: dict, nicho: str = "", busca: str = ""):
    """Converte uma linha do registro num Lead, para entrar na mesma lista do Places.

    Estes leads não têm diagnóstico de site — não há site para diagnosticar, e é
    justamente esse o ponto. O score é alto de propósito: empresa recém-aberta e
    sem presença é a maior dor que este serviço resolve, e vir sem nota do Google
    não é sinal de nada, só de que o Places não a conhece ainda.
    """
    from datetime import datetime

    from ..models import Contatos, Lead, Sinal

    fone = "".join(filter(str.isdigit, linha.get("telefone") or ""))
    email = (linha.get("email") or "").strip().lower()
    decisor = linha.get("decisor")
    celular = (linha.get("tipo_telefone") or "") == "celular"

    sinais = [Sinal(chave="sem_site_no_registro",
                    titulo="Não tem site que o Google conheça",
                    evidencia="Apareceu no registro da Receita, não no Maps: "
                              "provavelmente não tem site nem ficha no Google.",
                    pontos=40, severidade="alto")]
    if linha.get("abertura"):
        sinais.append(Sinal(chave="empresa_nova", titulo="Empresa recém-aberta",
                            evidencia=f"CNPJ aberto em {linha['abertura']}.",
                            pontos=20, severidade="medio"))
    if decisor:
        sinais.append(Sinal(
            chave="decisor_conhecido",
            titulo=f"Fala direto com {decisor.split()[0].capitalize()}",
            evidencia=f"{decisor} — {linha.get('decisor_papel') or 'responsável'}, "
                      + ("no celular do cadastro." if celular else "pelo telefone do cadastro."),
            pontos=15, severidade="positivo"))

    score = min(100, sum(s.pontos for s in sinais if s.severidade != "positivo") + (15 if celular else 0))
    faixa = "quente" if score >= 65 else "morno" if score >= 45 else "frio"

    return Lead(
        nome=linha.get("empresa") or linha.get("decisor") or "(sem nome)",
        categoria=SEGMENTOS.get(linha.get("cnae"), linha.get("cnae")),
        municipio=linha.get("municipio"), uf=linha.get("uf"),
        contatos=Contatos(telefone=fone or None,
                          whatsapp=link_whatsapp(fone, decisor) or None,
                          whatsapp_origem="receita" if celular else None,
                          emails=[email] if email else []),
        cnpj=linha.get("cnpj"), razao_social=linha.get("empresa"),
        decisor=decisor, decisor_papel=linha.get("decisor_papel"),
        situacao_cadastral="Ativa", cnae=linha.get("cnae"),
        abertura=linha.get("abertura"),
        sinais=sinais, score=score, faixa=faixa,
        frase_oportunidade=("Abriu em " + str(linha.get("abertura")) + " e não tem site. "
                            + (f"O dono é {decisor.split()[0].capitalize()}." if decisor else "")),
        origem="receita", nicho=nicho or None, busca=busca or None,
        coletado_em=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
