"""Monta a página de Análises: o que a busca revelou sobre o mercado."""
from __future__ import annotations

from statistics import mean

from .models import Lead


def _pct(parte: int, total: int) -> int:
    return round(100 * parte / total) if total else 0


def resumir(leads: list[Lead], novos: set[str] | None = None) -> dict:
    novos = novos or set()
    total = len(leads)
    if not total:
        return {"total": 0}

    sem_site = [l for l in leads if not l.site]
    site_fora = [l for l in leads if l.site and l.diagnostico.site_no_ar is False]
    com_wa = [l for l in leads if l.contatos.whatsapp]
    com_ig = [l for l in leads if l.redes.instagram]
    com_tt = [l for l in leads if l.redes.tiktok]
    com_mail = [l for l in leads if l.contatos.emails]
    com_tel = [l for l in leads if l.contatos.telefone]
    quentes = [l for l in leads if l.faixa == "quente"]
    mornos = [l for l in leads if l.faixa == "morno"]

    # a conversa mais fácil da lista: fatura bem no Maps e não tem site
    prontos = [l for l in sem_site if (l.avaliacoes or 0) >= 20]
    prontos.sort(key=lambda l: -(l.avaliacoes or 0))

    notas = [l.nota for l in leads if l.nota]
    avals = [l.avaliacoes or 0 for l in leads]
    analisados = [l for l in leads if l.diagnostico.site_no_ar is not None]

    # por que o topo ganha: top 5 do ranking do Maps contra o resto
    ordenados = sorted([l for l in leads if l.posicao_maps], key=lambda l: l.posicao_maps or 999)
    topo, resto = ordenados[:5], ordenados[5:]

    def perfil(grupo: list[Lead]) -> dict:
        if not grupo:
            return {}
        return {
            "n": len(grupo),
            "avaliacoes": round(mean([l.avaliacoes or 0 for l in grupo])),
            "nota": round(mean([l.nota for l in grupo if l.nota] or [0]), 1),
            "com_site": _pct(sum(1 for l in grupo if l.site), len(grupo)),
            "com_instagram": _pct(sum(1 for l in grupo if l.redes.instagram), len(grupo)),
        }

    p_topo, p_resto = perfil(topo), perfil(resto)
    licoes = []
    if p_topo and p_resto:
        if p_topo["avaliacoes"] > p_resto["avaliacoes"] * 1.3:
            licoes.append(
                f"Quem está no topo tem em média {p_topo['avaliacoes']} avaliações contra "
                f"{p_resto['avaliacoes']} do resto. Volume de avaliação é o que separa."
            )
        if p_topo["com_site"] > p_resto["com_site"] + 15:
            licoes.append(
                f"{p_topo['com_site']}% do topo tem site, contra {p_resto['com_site']}% do resto."
            )
        if p_topo["nota"] > p_resto["nota"] + 0.2:
            licoes.append(
                f"Nota média do topo: {p_topo['nota']} contra {p_resto['nota']}."
            )
        if not licoes:
            licoes.append(
                "Topo e resto têm perfil parecido em avaliações, nota e presença de site. "
                "Nesta busca, a posição não está sendo decidida por esses fatores — "
                "provável peso de proximidade e de atividade no Perfil da Empresa."
            )

    return {
        "total": total,
        "novos": len(novos),
        "ja_tinha": total - len(novos),
        "prontos": prontos,
        "quentes": quentes,
        "mornos": mornos,
        "sem_site": sem_site,
        "site_fora": site_fora,
        "com_wa": com_wa,
        "com_ig": com_ig,
        "com_tt": com_tt,
        "com_mail": com_mail,
        "com_tel": com_tel,
        "pct_sem_site": _pct(len(sem_site), total),
        "pct_com_wa": _pct(len(com_wa), total),
        "pct_com_ig": _pct(len(com_ig), total),
        "nota_media": round(mean(notas), 1) if notas else None,
        "com_nota": len(notas),
        "aval_media": round(mean(avals)) if avals else 0,
        "analisados": len(analisados),
        "perfil_topo": p_topo,
        "perfil_resto": p_resto,
        "licoes": licoes,
    }


def comparar_posicoes(atual: list[Lead], anterior: dict[str, int]) -> dict:
    """Quem subiu e quem caiu no ranking do Maps desde a última varredura."""
    subiu, caiu, iguais, estreantes = [], [], [], []
    for lead in atual:
        if not lead.posicao_maps:
            continue
        chave = lead.place_id or lead.nome
        antes = anterior.get(chave)
        if antes is None:
            estreantes.append((lead, None))
        elif antes > lead.posicao_maps:
            subiu.append((lead, antes - lead.posicao_maps))
        elif antes < lead.posicao_maps:
            caiu.append((lead, lead.posicao_maps - antes))
        else:
            iguais.append((lead, 0))
    subiu.sort(key=lambda t: -t[1])
    caiu.sort(key=lambda t: -t[1])
    return {"subiu": subiu, "caiu": caiu, "iguais": iguais,
            "estreantes": estreantes, "tem_historico": bool(anterior)}
