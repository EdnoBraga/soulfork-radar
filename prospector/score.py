"""Score de oportunidade — 0 a 100, "quanto vale abordar este lead".

Duas forças somam:
  1. DOR  — o que está quebrado/faltando e a SoulFork resolve.
  2. VIABILIDADE — sinais de que a empresa existe de verdade, está ativa,
     tem dinheiro e tem por onde ser abordada.

Um lead com dor enorme e nenhum canal de contato vale zero na prática.
Por isso viabilidade não é bônus: é multiplicador.
"""
from __future__ import annotations

from .models import Lead, Sinal
from .diagnose import consentimento
from .enrich.site import ColetaSite


def _s(chave, titulo, evid, pontos, sev="medio") -> Sinal:
    return Sinal(chave=chave, titulo=titulo, evidencia=evid, pontos=pontos, severidade=sev)


def avaliar(lead: Lead, coleta: ColetaSite | None) -> tuple[int, str, list[Sinal]]:
    d = lead.diagnostico
    sinais: list[Sinal] = []
    dor = 0

    # ---------------- DOR: presença digital ----------------
    if not lead.site:
        # sem site, todos os problemas de site existem implicitamente:
        # sem HTTPS, sem mensuração, sem formulário, sem SEO — dor de presença inteira.
        sinais.append(_s("sem_site", "Nenhum site no Perfil da Empresa",
                         "O cadastro no Google não traz endereço de site. A empresa aparece na busca, mas não tem para onde mandar quem procura — e sem site também não há mensuração, formulário nem SEO.",
                         38, "alto"))
        dor += 38
        if (lead.avaliacoes or 0) >= 30:
            sinais.append(_s("forte_sem_site", "Fatura bem e não tem site",
                             f"{lead.avaliacoes} avaliações no Google sustentando o negócio sozinhas. É a conversa mais fácil da lista: o problema já está na cara.",
                             18, "alto"))
            dor += 18
    elif d.site_no_ar is False:
        motivo = f"HTTP {d.status_http}" if d.status_http else (d.erro or "não respondeu")
        sinais.append(_s("site_fora", "Site não respondeu",
                         f"{lead.site} → {motivo}. ATENÇÃO: confirmar em outra janela de tempo antes de usar como argumento — instabilidade intermitente não é site fora do ar.",
                         20, "alto"))
        dor += 20
    elif d.site_no_ar is None and d.erro and "robots" in d.erro:
        sinais.append(_s("robots", "Site não analisado (robots.txt)",
                         "O site bloqueia crawlers; o diagnóstico técnico não foi feito. Isso NÃO é um problema do site — analise manualmente antes de qualquer afirmação.",
                         0, "info"))
    else:
        if d.https is False:
            sinais.append(_s("sem_https", "Site sem HTTPS",
                             f"A versão final carregada é {d.url_final} — sem certificado. O navegador marca como 'Não seguro'.",
                             14, "alto"))
            dor += 14
        if d.responsivo is False:
            sinais.append(_s("nao_responsivo", "Sem meta viewport",
                             "A página não declara viewport — indício forte de layout não adaptado a celular, que é de onde vem a maior parte do tráfego local.",
                             12, "alto"))
            dor += 12
        if d.tempo_resposta_ms and d.tempo_resposta_ms > 3000:
            sinais.append(_s("lento", "Resposta lenta",
                             f"A home levou {d.tempo_resposta_ms} ms para responder nesta checagem (medida única, não é auditoria de performance).",
                             8, "medio"))
            dor += 8
        elif d.tempo_resposta_ms and d.tempo_resposta_ms > 1800:
            sinais.append(_s("meio_lento", "Resposta acima do confortável",
                             f"{d.tempo_resposta_ms} ms na home nesta checagem.", 4, "baixo"))
            dor += 4

    # ---------------- DOR: mensuração ----------------
    if d.site_no_ar:
        if d.tem_gtm is False and d.tem_meta_pixel is False:
            sinais.append(_s("sem_mensuracao", "Sem GTM e sem Pixel no código público",
                             "Não identifiquei Google Tag Manager nem Meta Pixel no HTML servido (ambos aparecem no <noscript>, então a ausência aqui é evidência boa). GA4 não é verificável por esse caminho.",
                             16, "alto"))
            dor += 16
        elif d.tem_meta_pixel is False:
            sinais.append(_s("sem_pixel", "Sem Meta Pixel no código público",
                             "Não identifiquei o Pixel no HTML servido. Sem ele, campanha no Instagram/Facebook não consegue otimizar nem atribuir venda.",
                             10, "medio"))
            dor += 10
        elif d.tem_gtm is False:
            sinais.append(_s("sem_gtm", "Sem GTM no código público",
                             "Tem Pixel mas não identifiquei gerenciador de tags — cada tag nova vira pedido para o desenvolvedor.",
                             5, "baixo"))
            dor += 5

    # ---------------- DOR: LGPD ----------------
    if d.site_no_ar:
        tem_aviso, aviso_ingles = consentimento(coleta) if coleta else (False, False)
        if d.politica_quebrada:
            sinais.append(_s("politica_quebrada", "Link de política de privacidade quebrado",
                             "O site linka a política de privacidade, mas a página não abre. Do ponto de vista de LGPD é pior do que não ter link: assume o dever e não cumpre.",
                             14, "alto"))
            dor += 14
        elif d.tem_politica_privacidade is False and d.tem_formulario:
            sinais.append(_s("sem_politica", "Formulário sem política de privacidade",
                             "Encontrei formulário de contato e nenhum link para política de privacidade. Coleta de dado pessoal sem base legal declarada.",
                             15, "alto"))
            dor += 15
        if d.coleta_dado_sensivel:
            sinais.append(_s("dado_sensivel", "Formulário pede dado sensível",
                             "Os campos do formulário incluem dado pessoal sensível (saúde, CPF ou equivalente). A LGPD trata isso em regime mais rígido.",
                             12, "alto"))
            dor += 12
        if (d.tem_gtm or d.tem_meta_pixel) and not tem_aviso:
            sinais.append(_s("tag_sem_consentimento", "Tag de rastreio sem aviso de cookies",
                             "Há tag de rastreamento carregando e não identifiquei nenhum banner de consentimento.",
                             10, "alto"))
            dor += 10
        if aviso_ingles:
            sinais.append(_s("aviso_ingles", "Aviso de cookies em inglês",
                             "O banner de cookies aparece em inglês num site em português — é o padrão da plataforma, não configuração feita.",
                             5, "baixo"))
            dor += 5

    # ---------------- DOR: captação ----------------
    if d.site_no_ar and d.tem_formulario is False:
        sinais.append(_s("sem_formulario", "Nenhum formulário no site",
                         "Não encontrei formulário em nenhuma das páginas visitadas. Todo contato depende de a pessoa copiar um telefone.",
                         10, "medio"))
        dor += 10
    if d.site_no_ar and d.tem_sitemap is False:
        sinais.append(_s("sem_sitemap", "Sem sitemap.xml",
                         "/sitemap.xml não responde. Sinal de site publicado sem trabalho de SEO técnico.",
                         4, "baixo"))
        dor += 4

    # ---------------- DOR: redes ----------------
    if not lead.redes.instagram:
        sinais.append(_s("sem_instagram", "Instagram não localizado",
                         "Não encontrei link de Instagram no site nem no cadastro. Para negócio local, é o canal onde a decisão acontece.",
                         8, "medio"))
        dor += 8
    if not lead.redes.tiktok and lead.redes.instagram:
        sinais.append(_s("sem_tiktok", "Sem TikTok",
                         "Tem Instagram, não tem TikTok. Alcance orgânico de graça que está sendo deixado na mesa.",
                         3, "baixo"))
        dor += 3

    # ---------------- VIABILIDADE ----------------
    viab = 0.0
    motivos_viab = []

    # canal de abordagem — sem isso o lead não existe comercialmente
    if lead.contatos.emails:
        viab += 0.30; motivos_viab.append("e-mail público")
    if lead.contatos.whatsapp:
        viab += 0.28; motivos_viab.append("WhatsApp")
    if lead.contatos.telefone:
        viab += 0.12; motivos_viab.append("telefone")
    if lead.redes.instagram:
        viab += 0.10; motivos_viab.append("Instagram")

    # negócio ativo de verdade
    aval = lead.avaliacoes or 0
    if aval >= 100:
        viab += 0.22; motivos_viab.append(f"{aval} avaliações no Google")
    elif aval >= 30:
        viab += 0.16; motivos_viab.append(f"{aval} avaliações no Google")
    elif aval >= 8:
        viab += 0.10; motivos_viab.append(f"{aval} avaliações no Google")
    elif aval > 0:
        viab += 0.04

    if lead.situacao_cadastral and "ATIVA" in lead.situacao_cadastral.upper():
        viab += 0.10; motivos_viab.append("CNPJ ativo")

    viab = min(viab, 1.0)

    if motivos_viab:
        sinais.append(_s("viabilidade", "Canais e sinais de atividade",
                         "Dá para abordar por: " + ", ".join(motivos_viab) + ".",
                         0, "positivo"))

    # ---------------- descarte duro ----------------
    if lead.status_negocio in ("CLOSED_PERMANENTLY",):
        sinais.append(_s("fechado", "Fechado permanentemente",
                         "O Google marca o estabelecimento como fechado em definitivo.", 0, "alto"))
        return 0, "descartar", sinais
    if lead.situacao_cadastral and "BAIXADA" in lead.situacao_cadastral.upper():
        sinais.append(_s("cnpj_baixado", "CNPJ baixado",
                         f"Situação cadastral: {lead.situacao_cadastral}. Descontinuidade, não oportunidade.",
                         0, "alto"))
        return 0, "descartar", sinais
    if not (lead.contatos.emails or lead.contatos.whatsapp or lead.contatos.telefone or lead.redes.instagram):
        sinais.append(_s("sem_canal", "Nenhum canal de contato localizável",
                         "Sem e-mail, sem WhatsApp, sem telefone e sem Instagram. Não há por onde abordar.",
                         0, "alto"))
        return 0, "descartar", sinais

    # ---------------- composição ----------------
    dor_norm = min(dor, 100)
    score = int(round(dor_norm * (0.45 + 0.55 * viab)))
    score = max(0, min(100, score))

    if score >= 65:
        faixa = "quente"
    elif score >= 45:
        faixa = "morno"
    elif score >= 25:
        faixa = "frio"
    else:
        faixa = "fraco"

    sinais.sort(key=lambda s: (-s.pontos, s.chave))
    return score, faixa, sinais
