"""Interface web do SoulFork Radar — roda local: python -m prospector.web"""
from __future__ import annotations

import io
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, send_file, url_for)

from .. import config, export
from ..analise import comparar_posicoes, resumir
from ..frases import rotulo_faixa
from ..models import Lead
from ..pipeline import rodar
from ..store import Banco, chave_do_lead
from ..sugestoes import CIDADES, SUGESTOES, UFS

app = Flask(__name__)
config.carregar_env()

# rodadas em andamento e concluídas nesta sessão do servidor
RODADAS: dict[str, dict] = {}


def _dict_para_lead(d: dict) -> Lead:
    from ..models import Contatos, Diagnostico, Redes, Sinal
    lead = Lead()
    for k, v in d.items():
        if k.startswith("_"):
            continue
        if k == "contatos":
            lead.contatos = Contatos(**v)
        elif k == "redes":
            lead.redes = Redes(**v)
        elif k == "diagnostico":
            lead.diagnostico = Diagnostico(**v)
        elif k == "sinais":
            lead.sinais = [Sinal(**s) for s in v]
        elif hasattr(lead, k):
            setattr(lead, k, v)
    return lead


def _executar_busca(rid: str, nicho: str, local: str, quantidade: int) -> None:
    r = RODADAS[rid]

    def log(msg: str) -> None:
        r["log"].append(msg)

    try:
        chave = config.chave_places()
        if not chave:
            raise RuntimeError(
                "Falta a chave da Google Places API. Copie .env.example para .env, "
                "cole a chave e reinicie o servidor."
            )
        leads = rodar(
            nicho, [nicho], local,
            chave_places=chave,
            max_por_termo=min(quantidade, 60),
            progresso=log,
        )
        # quantidade acima de 60: completa com variações do termo
        if quantidade > 60 and len(leads) < quantidade:
            extras = rodar(
                nicho, [f"{nicho} perto de", f"melhor {nicho}"], local,
                chave_places=chave,
                max_por_termo=60,
                progresso=log,
            )
            vistos = {l.place_id for l in leads if l.place_id}
            for l in extras:
                if l.place_id not in vistos and len(leads) < quantidade:
                    leads.append(l)
        leads = leads[:quantidade]

        banco = Banco(config.caminho_banco())
        busca_id = f"{nicho}|{local}".lower()
        anteriores = {}
        novos = set()
        for lead in leads:
            if banco.salvar(lead):
                novos.add(chave_do_lead(lead))
        banco.registrar_posicoes(busca_id, leads)
        anteriores = banco.posicoes_anteriores(busca_id)
        banco.registrar_rodada(nicho, local, len(leads), len(novos))
        banco.fechar()

        r.update(
            status="pronta",
            leads=[l.to_dict() for l in leads],
            novos=sorted(novos),
            anteriores=anteriores,
            terminou_em=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
    except Exception as e:
        r.update(status="erro", erro=str(e))


def _leads_da_rodada(rid: str) -> tuple[dict, list[Lead]]:
    r = RODADAS.get(rid)
    if not r or r.get("status") != "pronta":
        abort(404)
    return r, [_dict_para_lead(d) for d in r["leads"]]


# ----------------------------------------------------------------------------- #

@app.route("/configuracao", methods=["GET", "POST"])
def configuracao():
    msg = erro = None
    if request.method == "POST":
        chave = (request.form.get("chave") or "").strip()
        if not chave:
            erro = "Cole a chave antes de salvar."
        elif not chave.startswith("AIza") or len(chave) < 30:
            erro = ("Isso não parece uma chave do Google (elas começam com \"AIza\"). "
                    "Confira se copiou a chave inteira.")
        else:
            # testa a chave com a requisição mais barata possível
            import requests as _rq
            try:
                resp = _rq.post(
                    "https://places.googleapis.com/v1/places:searchText",
                    json={"textQuery": "padaria em São Paulo", "pageSize": 1},
                    headers={"Content-Type": "application/json",
                             "X-Goog-Api-Key": chave,
                             "X-Goog-FieldMask": "places.id"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    config.salvar_chave_places(chave)
                    msg = "Chave testada e salva. Pode buscar."
                elif resp.status_code in (401, 403):
                    erro = ("O Google recusou a chave (HTTP %d). Verifique se a "
                            "\"Places API (New)\" está ativada no projeto e se o "
                            "faturamento está ligado." % resp.status_code)
                else:
                    erro = f"O Google respondeu HTTP {resp.status_code}. Tente de novo."
            except Exception as e:
                erro = f"Não consegui falar com o Google: {e}"
    return render_template("configuracao.html", pagina="config",
                           tem_chave=bool(config.chave_places()),
                           pasta=str(config.pasta_dados()), msg=msg, erro=erro)


@app.get("/")
def inicio():
    banco = Banco(config.caminho_banco())
    resumo = banco.resumo()
    banco.fechar()
    historico = [
        {"id": rid, **{k: r[k] for k in ("nicho", "local", "status") if k in r},
         "total": len(r.get("leads", []))}
        for rid, r in sorted(RODADAS.items(), key=lambda kv: kv[1]["criada_em"], reverse=True)
    ]
    return render_template(
        "busca.html", sugestoes=SUGESTOES, ufs=UFS,
        cidades_json=json.dumps(CIDADES, ensure_ascii=False),
        resumo=resumo, historico=historico[:8],
        tem_chave=bool(config.chave_places()),
    )


@app.post("/buscar")
def buscar():
    nicho = (request.form.get("nicho") or "").strip()
    uf = (request.form.get("uf") or "").strip()
    cidade = (request.form.get("cidade") or "").strip()
    quantidade = max(1, min(int(request.form.get("quantidade") or 20), 120))
    if not nicho or not uf:
        return redirect(url_for("inicio"))
    local = f"{cidade}, {uf}" if cidade else uf

    # teto de memória: mantém só as 20 rodadas mais recentes
    if len(RODADAS) > 20:
        for velho in sorted(RODADAS, key=lambda k: RODADAS[k]["criada_em"])[:len(RODADAS) - 20]:
            RODADAS.pop(velho, None)

    rid = uuid.uuid4().hex[:10]
    RODADAS[rid] = {
        "status": "rodando", "nicho": nicho, "local": local,
        "quantidade": quantidade, "log": [],
        "criada_em": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    threading.Thread(target=_executar_busca, args=(rid, nicho, local, quantidade),
                     daemon=True).start()
    return redirect(url_for("aguardando", rid=rid))


@app.get("/rodada/<rid>/aguardando")
def aguardando(rid):
    r = RODADAS.get(rid)
    if not r:
        abort(404)
    if r["status"] == "pronta":
        return redirect(url_for("leads", rid=rid))
    return render_template("aguardando.html", rid=rid, r=r)


@app.get("/rodada/<rid>/status")
def status(rid):
    r = RODADAS.get(rid)
    if not r:
        abort(404)
    return jsonify(status=r["status"], log=r["log"][-12:], erro=r.get("erro"))


@app.get("/rodada/<rid>/leads")
def leads(rid):
    r, ls = _leads_da_rodada(rid)
    novos = set(r.get("novos") or [])
    filtro = request.args.get("f", "todos")
    presenca = request.args.get("p", "")
    contato = request.args.get("c", "")

    def passa(l: Lead) -> bool:
        ch = chave_do_lead(l)
        if filtro == "novos" and ch not in novos:
            return False
        if filtro == "vistos" and ch in novos:
            return False
        if presenca == "sem-site" and l.site:
            return False
        if presenca == "sem-instagram" and l.redes.instagram:
            return False
        if presenca == "site-quebrado" and l.diagnostico.site_no_ar is not False:
            return False
        if presenca == "sem-medicao" and not (
            l.diagnostico.tem_gtm is False and l.diagnostico.tem_meta_pixel is False
        ):
            return False
        if presenca == "lgpd" and not (
            l.diagnostico.politica_quebrada
            or (l.diagnostico.tem_politica_privacidade is False and l.diagnostico.tem_formulario)
            or l.diagnostico.coleta_dado_sensivel
        ):
            return False
        if contato == "whatsapp" and not l.contatos.whatsapp:
            return False
        if contato == "email" and not l.contatos.emails:
            return False
        if contato == "telefone" and not l.contatos.telefone:
            return False
        return True

    ordem = request.args.get("o", "score")
    filtrados = [l for l in ls if passa(l)]
    if ordem == "maps":
        filtrados.sort(key=lambda l: l.posicao_maps or 999)
    elif ordem == "avaliacoes":
        filtrados.sort(key=lambda l: -(l.avaliacoes or 0))
    else:
        filtrados.sort(key=lambda l: -l.score)

    return render_template(
        "leads.html", rid=rid, r=r, leads=filtrados, total=len(ls),
        novos=novos, chave_do_lead=chave_do_lead, rotulo_faixa=rotulo_faixa,
        filtro=filtro, presenca=presenca, contato=contato, ordem=ordem,
        n_novos=sum(1 for l in ls if chave_do_lead(l) in novos),
    )


@app.get("/rodada/<rid>/analises")
def analises(rid):
    r, ls = _leads_da_rodada(rid)
    novos = set(r.get("novos") or [])
    dados = resumir(ls, {chave_do_lead(l) for l in ls if chave_do_lead(l) in novos})
    movimento = comparar_posicoes(ls, r.get("anteriores") or {})
    return render_template("analises.html", rid=rid, r=r, d=dados, mov=movimento,
                           rotulo_faixa=rotulo_faixa)


@app.get("/rodada/<rid>/exportar/<formato>")
def exportar(rid, formato):
    r, ls = _leads_da_rodada(rid)
    base = f"leads-{r['nicho']}-{r['local']}".replace(",", "").replace(" ", "-").lower()
    tmp = Path("/tmp") / f"radar-{rid}"
    tmp.mkdir(exist_ok=True)
    if formato == "csv":
        p = export.para_csv(ls, tmp / f"{base}.csv")
        return send_file(p, as_attachment=True, download_name=p.name)
    if formato == "xlsx":
        p = export.para_xlsx(ls, tmp / f"{base}.xlsx")
        if not p:
            abort(500)
        return send_file(p, as_attachment=True, download_name=p.name)
    if formato == "pdf":
        from .pdf import gerar_pdf
        novos = set(r.get("novos") or [])
        dados = resumir(ls, {chave_do_lead(l) for l in ls if chave_do_lead(l) in novos})
        p = gerar_pdf(ls, dados, r, tmp / f"resumo-{base}.pdf")
        return send_file(p, as_attachment=True, download_name=p.name)
    abort(404)


@app.get("/banco")
def banco_view():
    banco = Banco(config.caminho_banco())
    dados = banco.listar(limite=1000)
    resumo = banco.resumo()
    banco.fechar()
    ls = [_dict_para_lead(d) for d in dados]
    return render_template("banco.html", leads=ls, resumo=resumo,
                           rotulo_faixa=rotulo_faixa, chave_do_lead=chave_do_lead,
                           status_map={d.get("place_id") or "": d.get("_status") for d in dados})


def main():
    import webbrowser
    porta = 8760
    print(f"\n  SoulFork Radar → http://localhost:{porta}\n")
    try:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{porta}")).start()
    except Exception:
        pass
    app.run(host="127.0.0.1", port=porta, debug=False)


if __name__ == "__main__":
    main()
