"""PDF do resumo da busca — o 'Baixar PDF' das Análises."""
from __future__ import annotations

from pathlib import Path

from ..models import Lead


def gerar_pdf(leads: list[Lead], d: dict, rodada: dict, destino: str | Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    escuro = colors.HexColor("#0b1220")
    verde = colors.HexColor("#134e2f")
    fraco = colors.HexColor("#7a7d85")
    linha = colors.HexColor("#e6e4dd")

    st_t = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=18, textColor=escuro,
                          spaceAfter=2)
    st_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, textColor=fraco,
                            spaceAfter=14)
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12, textColor=verde,
                          spaceBefore=14, spaceAfter=6)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=10, leading=14)
    st_nota = ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=8.5,
                             textColor=fraco, leading=12, spaceBefore=16)

    doc = SimpleDocTemplate(str(destino), pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=16*mm, bottomMargin=16*mm)
    fl = []
    fl.append(Paragraph("SoulFork Radar — resumo da busca", st_t))
    fl.append(Paragraph(
        f"“{rodada['nicho']}” em {rodada['local']} · {rodada.get('terminou_em','')[:16].replace('T',' ')}",
        st_sub))

    fl.append(Paragraph("O que você recebeu", st_h))
    fl.append(Paragraph(
        f"<b>{d['total']}</b> leads com empresa, contato e diagnóstico — "
        f"<b>{d['novos']}</b> inéditos, <b>{d['ja_tinha']}</b> já conhecidos de rodadas "
        f"anteriores.", st_p))

    fl.append(Paragraph("Por onde começar", st_h))
    itens = [
        f"<b>{len(d['quentes'])}</b> oportunidades quentes",
        f"<b>{len(d['sem_site'])}</b> sem site nenhum ({d['pct_sem_site']}% da lista)",
        f"<b>{len(d['com_wa'])}</b> com WhatsApp — dá pra chamar sem ligar",
        f"<b>{len(d['com_ig'])}</b> com Instagram — dá pra espiar o perfil antes de falar",
    ]
    for i in itens:
        fl.append(Paragraph("• " + i, st_p))

    if d.get("prontos"):
        fl.append(Paragraph("Empresas prontas pra abordar hoje", st_h))
        fl.append(Paragraph(
            "Faturam bem no Google Maps e ainda não têm site. É a conversa mais fácil "
            "da lista: o problema já está na cara.", st_p))
        dados = [["Empresa", "Nota", "Avaliações", "WhatsApp"]]
        for l in d["prontos"][:10]:
            dados.append([
                l.nome[:44],
                f"{l.nota:.1f}".replace(".", ",") if l.nota else "—",
                str(l.avaliacoes or "—"),
                "sim" if l.contatos.whatsapp else "—",
            ])
        t = Table(dados, colWidths=[86*mm, 20*mm, 26*mm, 24*mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), escuro),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, linha),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        fl.append(Spacer(1, 4))
        fl.append(t)

    fl.append(Paragraph("O mercado desta busca", st_h))
    mercado = [
        f"<b>{d['total']}</b> empresas no Maps — tudo o que apareceu, não só o que virou lead",
        f"<b>{d['nota_media'] or '—'}</b> nota média ({d['com_nota']} têm avaliação)",
        f"<b>{d['analisados']}</b> sites analisados com leitura de código",
        f"<b>{len(d['site_fora'])}</b> com site fora do ar nesta checagem",
        f"<b>{d['pct_com_wa']}%</b> têm WhatsApp visível · <b>{d['pct_com_ig']}%</b> têm Instagram",
    ]
    for i in mercado:
        fl.append(Paragraph("• " + i, st_p))

    fl.append(Paragraph(
        "Checagens feitas no HTML público de cada site. Antes de citar um achado numa "
        "proposta, reconfirme em outra janela de tempo — instabilidade intermitente não é "
        "site fora do ar. GA4 nunca é afirmado como ausente (não é verificável por esse "
        "caminho). Gerado pelo SoulFork Radar.", st_nota))

    doc.build(fl)
    return destino
