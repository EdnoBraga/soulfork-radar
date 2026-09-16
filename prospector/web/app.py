"""Interface web do SoulFork Find. Local: python -m prospector.web · servidor: wsgi.py"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from .. import config, export
from ..analise import comparar_posicoes, resumir
from ..frases import rotulo_faixa
from ..models import Lead
from ..pipeline import rodar
from ..store import STATUS, Banco, chave_do_lead
from ..sugestoes import CIDADES, SUGESTOES, UFS

app = Flask(__name__)
config.carregar_env()
# sem FIND_SECRET_KEY (só no uso local) a sessão vale até o processo reiniciar
app.secret_key = os.environ.get("FIND_SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(days=7))

# Senha única de administrador. Sem FIND_SENHA o app fica aberto — só serve
# para rodar na própria máquina; o wsgi.py de produção se recusa a subir assim.
ROTAS_PUBLICAS = {"login", "saude", "static"}


@app.before_request
def exigir_login():
    senha = os.environ.get("FIND_SENHA", "")
    if not senha or request.endpoint in ROTAS_PUBLICAS or session.get("logado"):
        return None
    if request.path.startswith(("/lead/", "/rodada/")) and request.method == "POST":
        return jsonify(ok=False, erro="sessão expirada, entre de novo"), 401
    return redirect(url_for("login", proximo=request.full_path.rstrip("?")))


@app.route("/entrar", methods=["GET", "POST"], endpoint="login")
def entrar():
    erro = None
    proximo = request.values.get("proximo") or "/"
    if not proximo.startswith("/") or proximo.startswith("//"):
        proximo = "/"   # nada de redirecionar para fora do site
    if request.method == "POST":
        digitada = (request.form.get("senha") or "").encode()
        if hmac.compare_digest(digitada, os.environ.get("FIND_SENHA", "").encode()):
            session.clear()
            session["logado"] = True
            session.permanent = True
            return redirect(proximo)
        time.sleep(1)   # ponytail: freio simples contra força bruta; limite por IP se virar alvo
        erro = "Senha incorreta."
    return render_template("login.html", erro=erro, proximo=proximo)


@app.get("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))


@app.get("/saude")
def saude():
    return "ok"

# rodadas em andamento nesta sessão; as concluídas também ficam no banco
RODADAS: dict[str, dict] = {}

# Text Search da Places API (New), tabela de ago/2026 do LEIA-ME
PRECO_CHAMADA_USD = 0.032
ROTULO_STATUS = dict(STATUS)


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
                "Falta a chave da Google Places API — cadastre em Configuração."
            )
        grupo, termos, tipo = config.termos_do_nicho(nicho)
        if len(termos) > 1:
            log(f"nicho '{grupo}': {len(termos)} variações de busca")
        elif quantidade > 60:
            log("o Google entrega no máximo 60 empresas por termo — "
                "busque pelo nome do nicho para usar as variações")
        stats: dict = {}
        leads = rodar(
            nicho, termos, local,
            chave_places=chave,
            max_por_termo=min(quantidade, 60),
            tipo=tipo,
            progresso=log,
            limite_total=quantidade,
            stats=stats,
        )[:quantidade]

        banco = Banco(config.caminho_banco())
        busca_id = f"{nicho}|{local}".lower()
        novos = set()
        for lead in leads:
            if banco.salvar(lead):
                novos.add(chave_do_lead(lead))
        banco.registrar_posicoes(busca_id, leads)
        anteriores = banco.posicoes_anteriores(busca_id)
        terminou = datetime.now().astimezone().isoformat(timespec="seconds")
        extra = {"novos": sorted(novos), "anteriores": anteriores,
                 "chamadas": stats.get("chamadas", 0), "quantidade": quantidade,
                 "terminou_em": terminou}
        banco.registrar_rodada(nicho, local, len(leads), len(novos), rid=rid,
                               dados={**extra, "chaves": [chave_do_lead(l) for l in leads]})
        banco.fechar()

        r.update(status="pronta", leads=[l.to_dict() for l in leads], **extra)
    except Exception as e:
        r.update(status="erro", erro=str(e))


def _rodada(rid: str) -> dict | None:
    """Memória primeiro; se o servidor reiniciou, reabre do banco."""
    r = RODADAS.get(rid)
    if r is None:
        banco = Banco(config.caminho_banco())
        r = banco.carregar_rodada(rid)
        banco.fechar()
        if r is not None:
            RODADAS[rid] = r
    return r


def _leads_da_rodada(rid: str) -> tuple[dict, list[Lead]]:
    r = _rodada(rid)
    if not r or r.get("status") != "pronta":
        abort(404)
    return r, [_dict_para_lead(d) for d in r["leads"]]


# ----------------------------------------------------------------------------- #

@app.route("/configuracao", methods=["GET", "POST"])
def configuracao():
    msg = erro = None
    if request.method == "POST" and request.form.get("token") is not None:
        from ..sources import instagram as ig
        token = (request.form.get("token") or "").strip()
        if not token:
            erro = "Cole o token antes de salvar."
        else:
            try:
                iguid, usuario = ig.descobrir_conta(token)
                config.salvar_token_instagram(token, iguid)
                msg = f"Token salvo e ligado à conta @{usuario}." if usuario \
                    else "Token salvo."
            except (ig.InstagramError, ig.IndisponivelError) as e:
                erro = str(e)
    elif request.method == "POST":
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
                           tem_token=bool(config.token_instagram() and config.ig_user_id()),
                           pasta=str(config.pasta_dados()), msg=msg, erro=erro)


@app.get("/")
def inicio():
    banco = Banco(config.caminho_banco())
    resumo = banco.resumo()
    salvas = banco.listar_rodadas(limite=8)
    banco.fechar()
    historico = {s["rid"]: {"id": s["rid"], "nicho": s["nicho"], "local": s["local"],
                            "status": "pronta", "total": s["total"], "criada_em": s["criada_em"]}
                 for s in salvas}
    for rid, r in RODADAS.items():   # em andamento ou com erro ainda não estão no banco
        historico.setdefault(rid, {"id": rid, "nicho": r["nicho"], "local": r["local"],
                                   "status": r["status"], "total": len(r.get("leads", [])),
                                   "criada_em": r["criada_em"]})
    historico = sorted(historico.values(), key=lambda h: h["criada_em"], reverse=True)
    nichos = [("Nicho completo — busca todas as variações", sorted(config.carregar_nichos()))]
    return render_template(
        "busca.html", sugestoes=nichos + SUGESTOES, ufs=UFS,
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
    r = _rodada(rid)
    if not r:
        abort(404)
    if r["status"] == "pronta":
        return redirect(url_for("leads", rid=rid))
    return render_template("aguardando.html", rid=rid, r=r)


@app.get("/rodada/<rid>/status")
def status(rid):
    r = _rodada(rid)
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
    andamento = request.args.get("s", "")
    banco = Banco(config.caminho_banco())
    status_map = banco.status_de([chave_do_lead(l) for l in ls])
    banco.fechar()

    def passa(l: Lead) -> bool:
        ch = chave_do_lead(l)
        if andamento and status_map.get(ch, "novo") != andamento:
            return False
        if filtro == "novos" and ch not in novos:
            return False
        if filtro == "vistos" and ch in novos:
            return False
        if presenca == "sem-site" and l.site:
            return False
        if presenca == "sem-instagram" and not any(s.chave == "sem_instagram" for s in l.sinais):
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
        andamento=andamento, status_map=status_map, STATUS=STATUS,
        n_novos=sum(1 for l in ls if chave_do_lead(l) in novos),
        custo_usd=(r.get("chamadas") or 0) * PRECO_CHAMADA_USD,
    )


@app.post("/lead/status")
def mudar_status():
    d = request.get_json(silent=True) or {}
    chave, novo = (d.get("chave") or "").strip(), d.get("status")
    if not chave or novo not in ROTULO_STATUS:
        return jsonify(ok=False, erro="status inválido"), 400
    banco = Banco(config.caminho_banco())
    existe = banco.ja_visto(chave)
    if existe:
        banco.marcar(chave, novo)
    banco.fechar()
    if not existe:
        return jsonify(ok=False, erro="lead não encontrado"), 404
    return jsonify(ok=True, status=novo, rotulo=ROTULO_STATUS[novo])


@app.post("/rodada/<rid>/instagram")
def instagram(rid):
    """Seguidores de UM lead, sob demanda. Nunca roda na varredura:
    a Meta libera ~200 chamadas por hora."""
    from ..sources import instagram as ig

    token, iguid = config.token_instagram(), config.ig_user_id()
    if not (token and iguid):
        return jsonify(ok=False, erro="Configure o token da Meta primeiro."), 400
    usuario = ((request.get_json(silent=True) or {}).get("usuario") or "").strip()
    try:
        dados = ig.consultar(usuario, token, iguid)
    except ig.IndisponivelError as e:
        return jsonify(ok=False, indisponivel=True, erro=str(e)), 200
    except ig.InstagramError as e:
        return jsonify(ok=False, erro=str(e)), 200

    r = _rodada(rid)
    banco = Banco(config.caminho_banco())
    for d in (r or {}).get("leads", []):
        if ((d.get("redes") or {}).get("instagram") or "").lower() != usuario.lower():
            continue
        d["redes"]["instagram_seguidores"] = dados["seguidores"]
        d["redes"]["instagram_ultima_publicacao"] = dados["ultima_publicacao"]
        banco.salvar(_dict_para_lead(d))
    banco.fechar()
    return jsonify(ok=True, **dados)


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
    tmp = Path(tempfile.gettempdir()) / f"find-{rid}"
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
    andamento = request.args.get("s", "")
    status_map = {chave_do_lead(l): d.get("_status") or "novo" for l, d in zip(ls, dados)}
    if andamento:
        ls = [l for l in ls if status_map[chave_do_lead(l)] == andamento]
    return render_template("banco.html", leads=ls, resumo=resumo,
                           rotulo_faixa=rotulo_faixa, chave_do_lead=chave_do_lead,
                           status_map=status_map, STATUS=STATUS, andamento=andamento)


def main():
    import webbrowser
    porta = 8760
    print(f"\n  SoulFork Find → http://localhost:{porta}\n")
    try:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{porta}")).start()
    except Exception:
        pass
    app.run(host="127.0.0.1", port=porta, debug=False)


if __name__ == "__main__":
    main()
