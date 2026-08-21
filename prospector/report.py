"""Relatório HTML — arquivo único, abre no navegador, funciona offline."""
from __future__ import annotations

import html as _h
import json
from pathlib import Path

from .models import Lead

CSS = """
*{box-sizing:border-box}
:root{
 --bg:#f6f7f9; --card:#fff; --linha:#e4e7ec; --txt:#111827; --fraco:#6b7280;
 --quente:#dc2626; --morno:#d97706; --frio:#0284c7; --neutro:#9ca3af;
 --quente-bg:#fef2f2; --morno-bg:#fffbeb; --frio-bg:#f0f9ff; --fraco-bg:#f9fafb;
 --acento:#4f46e5;
}
@media (prefers-color-scheme:dark){:root{
 --bg:#0d1117; --card:#161b22; --linha:#272d36; --txt:#e6edf3; --fraco:#8b949e;
 --quente-bg:#2a1214; --morno-bg:#2a1f0e; --frio-bg:#0d1f2c; --fraco-bg:#161b22;
 --quente:#f87171; --morno:#fbbf24; --frio:#38bdf8; --acento:#818cf8;
}}
body{margin:0;background:var(--bg);color:var(--txt);
 font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
header h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em}
header p{margin:0;color:var(--fraco);font-size:13px}
.kpis{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}
.kpi{background:var(--card);border:1px solid var(--linha);border-radius:10px;
 padding:12px 16px;min-width:112px}
.kpi b{display:block;font-size:24px;line-height:1.1;font-variant-numeric:tabular-nums}
.kpi span{font-size:11px;color:var(--fraco);text-transform:uppercase;letter-spacing:.06em}
.barra{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:18px;
 position:sticky;top:0;background:var(--bg);padding:10px 0;z-index:5;border-bottom:1px solid var(--linha)}
input[type=search]{flex:1;min-width:200px;padding:9px 12px;border:1px solid var(--linha);
 border-radius:8px;background:var(--card);color:var(--txt);font-size:14px}
.chip{padding:7px 13px;border:1px solid var(--linha);border-radius:999px;background:var(--card);
 color:var(--fraco);cursor:pointer;font-size:13px;font-weight:500}
.chip.on{background:var(--acento);border-color:var(--acento);color:#fff}
.lead{background:var(--card);border:1px solid var(--linha);border-left-width:4px;
 border-radius:10px;margin-bottom:10px;overflow:hidden}
.lead[data-faixa=quente]{border-left-color:var(--quente)}
.lead[data-faixa=morno]{border-left-color:var(--morno)}
.lead[data-faixa=frio]{border-left-color:var(--frio)}
.lead[data-faixa=fraco],.lead[data-faixa=descartar]{border-left-color:var(--neutro)}
.topo{display:flex;gap:14px;align-items:flex-start;padding:14px 16px;cursor:pointer}
.score{flex:0 0 52px;text-align:center}
.score b{display:block;font-size:23px;line-height:1;font-variant-numeric:tabular-nums}
.score span{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--fraco)}
.info{flex:1;min-width:0}
.info h2{margin:0 0 3px;font-size:16px;font-weight:600;letter-spacing:-.01em}
.meta{font-size:12.5px;color:var(--fraco)}
.tags{margin-top:7px;display:flex;flex-wrap:wrap;gap:5px}
.tag{font-size:11px;padding:2.5px 8px;border-radius:5px;background:var(--fraco-bg);
 border:1px solid var(--linha);color:var(--fraco)}
.tag.alto{background:var(--quente-bg);color:var(--quente);border-color:transparent}
.tag.medio{background:var(--morno-bg);color:var(--morno);border-color:transparent}
.canais{flex:0 0 auto;display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;max-width:230px}
.canais a{font-size:12px;text-decoration:none;padding:5px 10px;border-radius:6px;
 border:1px solid var(--linha);color:var(--txt);white-space:nowrap}
.canais a:hover{border-color:var(--acento);color:var(--acento)}
.detalhe{display:none;padding:0 16px 16px;border-top:1px solid var(--linha)}
.lead.aberto .detalhe{display:block}
.detalhe h3{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--fraco);
 margin:16px 0 8px;font-weight:600}
.achado{padding:9px 0;border-bottom:1px dashed var(--linha)}
.achado:last-child{border-bottom:0}
.achado b{font-size:13.5px;font-weight:600}
.achado p{margin:3px 0 0;font-size:13px;color:var(--fraco)}
.pts{float:right;font-size:11px;color:var(--fraco);font-variant-numeric:tabular-nums}
.grade{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px}
.campo{font-size:12.5px}
.campo span{display:block;color:var(--fraco);font-size:10.5px;text-transform:uppercase;
 letter-spacing:.05em;margin-bottom:1px}
.campo a{color:var(--acento);text-decoration:none;word-break:break-all}
.vazio{text-align:center;padding:60px 20px;color:var(--fraco)}
.rodape{margin-top:40px;padding-top:18px;border-top:1px solid var(--linha);
 font-size:12px;color:var(--fraco);line-height:1.7}
"""

JS = """
const leads=[...document.querySelectorAll('.lead')];
const busca=document.getElementById('busca');
const chips=[...document.querySelectorAll('.chip')];
let faixa='todos';
function filtrar(){
  const q=busca.value.toLowerCase().trim();
  let n=0;
  leads.forEach(el=>{
    const okF = faixa==='todos' || el.dataset.faixa===faixa;
    const okQ = !q || el.dataset.busca.includes(q);
    const ok = okF && okQ;
    el.style.display = ok ? '' : 'none';
    if(ok) n++;
  });
  document.getElementById('vazio').style.display = n ? 'none' : 'block';
  document.getElementById('contador').textContent = n;
}
busca.addEventListener('input',filtrar);
chips.forEach(c=>c.addEventListener('click',()=>{
  chips.forEach(x=>x.classList.remove('on'));
  c.classList.add('on'); faixa=c.dataset.faixa; filtrar();
}));
document.querySelectorAll('.topo').forEach(t=>t.addEventListener('click',e=>{
  if(e.target.closest('a')) return;
  t.parentElement.classList.toggle('aberto');
}));
"""


def _e(v) -> str:
    return _h.escape(str(v)) if v is not None else ""


def _canais(lead: Lead) -> str:
    c, r = lead.contatos, lead.redes
    out = []
    if c.whatsapp:
        msg = "Ol%C3%A1%2C%20tudo%20bem%3F"
        out.append(f'<a href="https://wa.me/{_e(c.whatsapp)}?text={msg}" target="_blank" rel="noopener">WhatsApp</a>')
    if c.emails:
        out.append(f'<a href="mailto:{_e(c.emails[0])}">E-mail</a>')
    if lead.site:
        out.append(f'<a href="{_e(lead.site)}" target="_blank" rel="noopener">Site</a>')
    if r.instagram:
        out.append(f'<a href="https://instagram.com/{_e(r.instagram)}" target="_blank" rel="noopener">@{_e(r.instagram)}</a>')
    if r.tiktok:
        out.append(f'<a href="https://tiktok.com/@{_e(r.tiktok)}" target="_blank" rel="noopener">TikTok</a>')
    if lead.google_maps_url:
        out.append(f'<a href="{_e(lead.google_maps_url)}" target="_blank" rel="noopener">Maps</a>')
    return "".join(out)


def _campos(lead: Lead) -> str:
    d = lead.diagnostico
    def sn(v):
        return "sim" if v is True else ("não" if v is False else "não verificável")
    itens = [
        ("Telefone", _e(lead.contatos.telefone)),
        ("E-mails", _e(", ".join(lead.contatos.emails))),
        ("Nota Google", f"{lead.nota} ({lead.avaliacoes} avaliações)" if lead.nota else "—"),
        ("CNPJ", _e(lead.cnpj) or "não localizado"),
        ("Razão social", _e(lead.razao_social) or "—"),
        ("Situação cadastral", _e(lead.situacao_cadastral) or "—"),
        ("CNAE", _e(lead.cnae) or "—"),
        ("Porte", _e(lead.porte) or "—"),
        ("Site no ar", sn(d.site_no_ar) + (f" (HTTP {d.status_http})" if d.status_http else "")),
        ("HTTPS", sn(d.https)),
        ("Responsivo", sn(d.responsivo)),
        ("Tempo de resposta", f"{d.tempo_resposta_ms} ms" if d.tempo_resposta_ms else "—"),
        ("GTM", sn(d.tem_gtm)),
        ("Meta Pixel", sn(d.tem_meta_pixel)),
        ("GA4", "encontrado" if d.tem_ga4 else "não verificável pelo HTML"),
        ("Política LGPD", "link quebrado" if d.politica_quebrada else sn(d.tem_politica_privacidade)),
        ("Formulário", sn(d.tem_formulario)),
        ("Sitemap", sn(d.tem_sitemap)),
        ("CMS", _e(f"{d.cms or ''} {d.cms_versao or ''}".strip()) or "—"),
        ("Endereço", _e(lead.endereco) or "—"),
    ]
    return "".join(f'<div class="campo"><span>{k}</span>{v}</div>' for k, v in itens)


def gerar(leads: list[Lead], destino: str | Path, titulo: str, subtitulo: str) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    faixas = {f: sum(1 for l in leads if l.faixa == f) for f in ("quente", "morno", "frio", "fraco")}
    com_wa = sum(1 for l in leads if l.contatos.whatsapp)
    com_mail = sum(1 for l in leads if l.contatos.emails)
    com_ig = sum(1 for l in leads if l.redes.instagram)

    blocos = []
    for lead in leads:
        principais = [s for s in lead.sinais if s.pontos > 0][:4]
        tags = "".join(
            f'<span class="tag {_e(s.severidade)}">{_e(s.titulo)}</span>' for s in principais
        )
        achados = "".join(
            f'<div class="achado"><span class="pts">+{s.pontos}</span>'
            f'<b>{_e(s.titulo)}</b><p>{_e(s.evidencia)}</p></div>'
            for s in lead.sinais if s.pontos > 0
        ) or '<p style="color:var(--fraco);font-size:13px">Nenhum problema encontrado nas checagens públicas.</p>'

        viab = next((s for s in lead.sinais if s.chave == "viabilidade"), None)
        viab_html = f'<h3>Como abordar</h3><p style="font-size:13.5px;margin:0">{_e(viab.evidencia)}</p>' if viab else ""

        chave_busca = " ".join(filter(None, [
            lead.nome, lead.municipio, lead.nicho, lead.site,
            lead.redes.instagram, lead.cnpj, lead.razao_social,
            " ".join(lead.contatos.emails),
            " ".join(s.titulo for s in lead.sinais),
        ])).lower()

        blocos.append(f"""
<article class="lead" data-faixa="{_e(lead.faixa)}" data-busca="{_e(chave_busca)}">
 <div class="topo">
  <div class="score"><b>{lead.score}</b><span>{_e(lead.faixa)}</span></div>
  <div class="info">
   <h2>{_e(lead.nome)}</h2>
   <div class="meta">{_e(lead.categoria or lead.nicho or '')} · {_e(lead.municipio or '')}{('/' + _e(lead.uf)) if lead.uf else ''}{(' · ' + _e(lead.site)) if lead.site else ' · sem site'}</div>
   <div class="tags">{tags}</div>
  </div>
  <div class="canais">{_canais(lead)}</div>
 </div>
 <div class="detalhe">
  <h3>Achados ({len([s for s in lead.sinais if s.pontos > 0])})</h3>
  {achados}
  {viab_html}
  <h3>Dados</h3>
  <div class="grade">{_campos(lead)}</div>
 </div>
</article>""")

    doc = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(titulo)}</title><style>{CSS}</style></head><body>
<div class="wrap">
<header><h1>{_e(titulo)}</h1><p>{_e(subtitulo)}</p></header>
<div class="kpis">
 <div class="kpi"><b>{len(leads)}</b><span>leads</span></div>
 <div class="kpi"><b style="color:var(--quente)">{faixas['quente']}</b><span>quentes</span></div>
 <div class="kpi"><b style="color:var(--morno)">{faixas['morno']}</b><span>mornos</span></div>
 <div class="kpi"><b>{com_wa}</b><span>com WhatsApp</span></div>
 <div class="kpi"><b>{com_mail}</b><span>com e-mail</span></div>
 <div class="kpi"><b>{com_ig}</b><span>com Instagram</span></div>
</div>
<div class="barra">
 <input type="search" id="busca" placeholder="Buscar por empresa, cidade, achado, e-mail, @…">
 <button class="chip on" data-faixa="todos">Todos</button>
 <button class="chip" data-faixa="quente">Quentes</button>
 <button class="chip" data-faixa="morno">Mornos</button>
 <button class="chip" data-faixa="frio">Frios</button>
 <span style="font-size:12px;color:var(--fraco)"><b id="contador">{len(leads)}</b> exibindo</span>
</div>
{''.join(blocos)}
<div class="vazio" id="vazio" style="display:none">Nenhum lead com esse filtro.</div>
<div class="rodape">
<b>Antes de usar qualquer achado numa proposta:</b> reconfira a alegação em pelo menos duas janelas de tempo diferentes. Site que responde erro numa checagem e carrega na seguinte é instabilidade intermitente, não site fora do ar — e mandar isso numa proposta queima credibilidade no primeiro contato.<br>
<b>GA4 nunca é afirmado como ausente.</b> A ferramenta lê o HTML servido, onde tags injetadas por gerenciador não aparecem. GTM e Meta Pixel aparecem no &lt;noscript&gt; — ausência ali é evidência boa. GA4 não. Escreva "não identifiquei no código público", nunca "vocês não têm".<br>
<b>Seguidores de Instagram e TikTok</b> não são coletados automaticamente: a ferramenta entrega o perfil, e os números você levanta no HypeAuditor só nos leads que forem para a fila.
</div>
</div>
<script>{JS}</script></body></html>"""

    destino.write_text(doc, encoding="utf-8")
    return destino
