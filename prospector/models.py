"""Estruturas de dados do prospector."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Contatos:
    telefone: str | None = None
    telefone_e164: str | None = None
    whatsapp: str | None = None          # link wa.me montado
    whatsapp_origem: str | None = None   # 'site' | 'places' | None
    emails: list[str] = field(default_factory=list)


@dataclass
class Redes:
    instagram: str | None = None
    instagram_seguidores: int | None = None
    tiktok: str | None = None
    tiktok_seguidores: int | None = None
    facebook: str | None = None
    linkedin: str | None = None
    youtube: str | None = None


@dataclass
class Sinal:
    """Um achado do diagnóstico. `pontos` soma no score de oportunidade."""
    chave: str
    titulo: str
    evidencia: str
    pontos: int
    severidade: str = "info"   # 'alto' | 'medio' | 'baixo' | 'info' | 'positivo'


@dataclass
class Diagnostico:
    site_no_ar: bool | None = None
    status_http: int | None = None
    url_final: str | None = None
    https: bool | None = None
    tempo_resposta_ms: int | None = None
    responsivo: bool | None = None
    tem_gtm: bool | None = None
    tem_meta_pixel: bool | None = None
    tem_ga4: bool | None = None          # só True quando confirmado; None = não verificável
    tem_politica_privacidade: bool | None = None
    politica_quebrada: bool | None = None
    tem_formulario: bool | None = None
    coleta_dado_sensivel: bool | None = None
    tem_sitemap: bool | None = None
    cms: str | None = None
    cms_versao: str | None = None
    titulo_pagina: str | None = None
    meta_description: str | None = None
    erro: str | None = None


@dataclass
class Lead:
    # identidade
    place_id: str | None = None
    nome: str = ""
    categoria: str | None = None
    # localização
    endereco: str | None = None
    municipio: str | None = None
    uf: str | None = None
    lat: float | None = None
    lng: float | None = None
    # google
    google_maps_url: str | None = None
    nota: float | None = None
    avaliacoes: int | None = None
    status_negocio: str | None = None
    # web
    site: str | None = None
    contatos: Contatos = field(default_factory=Contatos)
    redes: Redes = field(default_factory=Redes)
    # cadastro
    cnpj: str | None = None
    razao_social: str | None = None
    situacao_cadastral: str | None = None
    cnae: str | None = None
    porte: str | None = None
    abertura: str | None = None
    # análise
    diagnostico: Diagnostico = field(default_factory=Diagnostico)
    sinais: list[Sinal] = field(default_factory=list)
    score: int = 0
    faixa: str = ""
    # posição no ranking do Google Maps para a busca que trouxe o lead
    posicao_maps: int | None = None
    frase_oportunidade: str = ""
    # meta
    nicho: str | None = None
    busca: str | None = None
    coletado_em: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
