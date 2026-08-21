"""Orquestra a coleta: Places -> site -> CNPJ -> diagnóstico -> score."""
from __future__ import annotations

import concurrent.futures as cf
from datetime import datetime
from typing import Callable

import requests

from .diagnose import analisar
from .enrich.site import ColetorSite, _e164
from .models import Contatos, Diagnostico, Lead, Redes
from .score import avaliar
from .sources import cnpj as fonte_cnpj
from .sources.places import PlacesClient, normalizar


def montar_lead(bruto: dict, nicho: str, busca: str) -> Lead:
    lead = Lead(
        place_id=bruto.get("place_id"),
        nome=bruto.get("nome") or "",
        categoria=bruto.get("categoria"),
        endereco=bruto.get("endereco"),
        municipio=bruto.get("municipio"),
        uf=bruto.get("uf"),
        lat=bruto.get("lat"),
        lng=bruto.get("lng"),
        google_maps_url=bruto.get("google_maps_url"),
        nota=bruto.get("nota"),
        avaliacoes=bruto.get("avaliacoes"),
        status_negocio=bruto.get("status_negocio"),
        site=bruto.get("site"),
        posicao_maps=bruto.get("posicao_maps"),
        nicho=nicho,
        busca=busca,
        coletado_em=datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    tel = bruto.get("telefone_intl") or bruto.get("telefone")
    if tel:
        lead.contatos.telefone = bruto.get("telefone") or tel
        lead.contatos.telefone_e164 = _e164(tel)
    return lead


def enriquecer(
    lead: Lead,
    coletor: ColetorSite,
    *,
    consultar_cnpj: bool = True,
    sessao_cnpj: requests.Session | None = None,
) -> Lead:
    coleta = None
    if lead.site:
        coleta = coletor.coletar(lead.site)

        if coleta.emails:
            lead.contatos.emails = coleta.emails
        if coleta.whatsapp:
            lead.contatos.whatsapp = coleta.whatsapp
            lead.contatos.whatsapp_origem = "site"
        r = coleta.redes
        lead.redes = Redes(
            instagram=r.get("instagram"),
            tiktok=r.get("tiktok"),
            facebook=r.get("facebook"),
            linkedin=r.get("linkedin"),
            youtube=r.get("youtube"),
        )
        if coleta.cnpj:
            lead.cnpj = fonte_cnpj.formatar(coleta.cnpj)

        lead.diagnostico = analisar(coleta)
    else:
        lead.diagnostico = Diagnostico(site_no_ar=None, erro="sem site cadastrado")

    # WhatsApp deduzido do telefone do Places, se o site não deu nada
    if not lead.contatos.whatsapp and lead.contatos.telefone_e164:
        n = lead.contatos.telefone_e164
        if len(n) == 13 and n[4] == "9":   # 55 + DDD + 9xxxxxxxx
            lead.contatos.whatsapp = n
            lead.contatos.whatsapp_origem = "places (não confirmado)"

    # cadastro na Receita, quando achamos o CNPJ no rodapé
    if consultar_cnpj and lead.cnpj:
        dados = fonte_cnpj.consultar(lead.cnpj, sessao=sessao_cnpj)
        if dados:
            lead.razao_social = dados["razao_social"]
            lead.situacao_cadastral = dados["situacao_cadastral"]
            lead.cnae = dados["cnae"]
            lead.porte = dados["porte"]
            lead.abertura = dados["abertura"]
            if dados.get("email_receita") and dados["email_receita"] not in lead.contatos.emails:
                lead.contatos.emails.append(dados["email_receita"])
            if not lead.municipio:
                lead.municipio = dados.get("municipio")
            if not lead.uf:
                lead.uf = dados.get("uf")

    lead.score, lead.faixa, lead.sinais = avaliar(lead, coleta)
    from .frases import frase_oportunidade
    lead.frase_oportunidade = frase_oportunidade(lead)
    return lead


def rodar(
    nicho: str,
    termos: list[str],
    local: str,
    *,
    chave_places: str,
    max_por_termo: int = 60,
    tipo: str | None = None,
    paralelismo: int = 6,
    consultar_cnpj: bool = True,
    respeitar_robots: bool = True,
    progresso: Callable[[str], None] | None = None,
) -> list[Lead]:
    def aviso(msg: str) -> None:
        if progresso:
            progresso(msg)

    cliente = PlacesClient(chave_places)
    vistos: set[str] = set()
    brutos: list[tuple[dict, str]] = []

    for i_termo, termo in enumerate(termos):
        consulta = f"{termo} em {local}"
        aviso(f"buscando: {consulta}")
        try:
            achados = list(cliente.buscar(consulta, max_resultados=max_por_termo, tipo=tipo))
        except Exception as e:
            aviso(f"  falhou: {e}")
            continue
        novos = 0
        for posicao, place in enumerate(achados, start=1):
            pid = place.get("id")
            if pid and pid in vistos:
                continue   # dedupe: mantém a posição da PRIMEIRA consulta em que apareceu
            if pid:
                vistos.add(pid)
            item = normalizar(place)
            # posição no ranking só faz sentido dentro da própria consulta;
            # termos de complemento (2º em diante) não formam ranking comparável
            item["posicao_maps"] = posicao if i_termo == 0 else None
            brutos.append((item, consulta))
            novos += 1
        aviso(f"  {len(achados)} resultados, {novos} inéditos")

    aviso(f"{len(brutos)} empresas únicas. Analisando sites…")

    leads: list[Lead] = []
    feitos = 0

    def tarefa(item):
        bruto, consulta = item
        # coletor e sessão POR THREAD — requests.Session não é thread-safe
        coletor = ColetorSite(respeitar_robots=respeitar_robots)
        sessao_cnpj = requests.Session()
        sessao_cnpj.headers.update({"User-Agent": "SoulForkProspector/1.0"})
        lead = montar_lead(bruto, nicho, consulta)
        return enriquecer(lead, coletor, consultar_cnpj=consultar_cnpj, sessao_cnpj=sessao_cnpj)

    with cf.ThreadPoolExecutor(max_workers=paralelismo) as pool:
        for lead in pool.map(tarefa, brutos):
            leads.append(lead)
            feitos += 1
            if feitos % 5 == 0 or feitos == len(brutos):
                aviso(f"  {feitos}/{len(brutos)} analisados")

    leads.sort(key=lambda l: (-l.score, l.nome))
    return leads
