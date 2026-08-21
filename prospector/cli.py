"""Interface de linha de comando do SoulFork Prospector."""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import webbrowser
from datetime import datetime
from pathlib import Path

from . import __version__, config, export, report
from .enrich.site import ColetorSite
from .models import Lead
from .pipeline import enriquecer, montar_lead, rodar
from .store import Banco, chave_do_lead

CORES = {"quente": "\033[91m", "morno": "\033[93m", "frio": "\033[96m",
         "fraco": "\033[90m", "descartar": "\033[90m"}
RESET = "\033[0m"
NEGRITO = "\033[1m"


def _tty() -> bool:
    return sys.stdout.isatty()


def cor(txt: str, c: str) -> str:
    return f"{c}{txt}{RESET}" if _tty() else txt


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t or "sem-nome"


def _dict_para_lead(d: dict) -> Lead:
    from .models import Contatos, Diagnostico, Redes, Sinal
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


def imprimir_lead(lead: Lead, i: int) -> None:
    c = CORES.get(lead.faixa, "")
    cabec = f"{i:>3}. {cor(f'{lead.score:>3}', c)} {NEGRITO if _tty() else ''}{lead.nome}{RESET if _tty() else ''}"
    print(cabec)
    linha2 = []
    if lead.municipio:
        linha2.append(f"{lead.municipio}/{lead.uf or ''}".rstrip("/"))
    linha2.append(lead.site or "sem site")
    if lead.nota:
        linha2.append(f"{lead.nota}★ ({lead.avaliacoes})")
    print("      " + " · ".join(linha2))
    canais = []
    if lead.contatos.whatsapp:
        canais.append(f"wa.me/{lead.contatos.whatsapp}")
    if lead.contatos.emails:
        canais.append(lead.contatos.emails[0])
    if lead.redes.instagram:
        canais.append(f"@{lead.redes.instagram}")
    if lead.redes.tiktok:
        canais.append(f"tiktok @{lead.redes.tiktok}")
    if canais:
        print("      " + " · ".join(canais))
    achados = [s.titulo for s in lead.sinais if s.pontos > 0][:3]
    if achados:
        print("      " + cor("▸ " + " · ".join(achados), "\033[90m"))
    print()


def entregar(leads: list[Lead], nome_base: str, titulo: str, subtitulo: str, abrir: bool) -> dict:
    saida = config.pasta_saida()
    csv_path = export.para_csv(leads, saida / f"{nome_base}.csv")
    xlsx_path = export.para_xlsx(leads, saida / f"{nome_base}.xlsx")
    html_path = report.gerar(leads, saida / f"{nome_base}.html", titulo, subtitulo)
    if abrir:
        try:
            webbrowser.open(html_path.resolve().as_uri())
        except Exception:
            pass
    return {"csv": csv_path, "xlsx": xlsx_path, "html": html_path}


# --------------------------------------------------------------------------- #

def cmd_nichos(args) -> int:
    nichos = config.carregar_nichos(args.nichos)
    if not nichos:
        print("Nenhum nicho configurado. Verifique o arquivo nichos.json.")
        return 1
    print(f"\n{len(nichos)} nichos configurados:\n")
    for nome, cfg in sorted(nichos.items()):
        termos = ", ".join(cfg.get("termos", [])[:3])
        extra = "…" if len(cfg.get("termos", [])) > 3 else ""
        print(f"  {nome:<16} {termos}{extra}")
    print("\nUse qualquer um deles, ou passe um termo livre entre aspas:")
    print('  prospector buscar "clínica de fisioterapia" --local "Brasília, DF"\n')
    return 0


def cmd_buscar(args) -> int:
    config.carregar_env(args.env)
    chave = config.chave_places()
    if not chave:
        print("\n✗ Falta a chave da Google Places API.\n")
        print("  1. console.cloud.google.com → crie um projeto")
        print("  2. Ative 'Places API (New)' e ligue o faturamento")
        print("  3. Credenciais → Criar chave de API")
        print("  4. Copie .env.example para .env e cole a chave lá\n")
        return 1

    nichos = config.carregar_nichos(args.nichos)
    alvo = args.nicho
    if alvo in nichos:
        termos = nichos[alvo].get("termos") or [alvo]
        tipo = nichos[alvo].get("tipo")
        nome_nicho = alvo
    else:
        termos = [alvo]
        tipo = None
        nome_nicho = alvo
        print(f"(‘{alvo}’ não está em nichos.json — usando como termo de busca livre)")

    if args.termo:
        termos = args.termo

    print(f"\n{NEGRITO if _tty() else ''}SoulFork Prospector{RESET if _tty() else ''} — "
          f"{nome_nicho} em {args.local}\n")

    def log(msg: str) -> None:
        print("  " + msg, flush=True)

    try:
        leads = rodar(
            nome_nicho, termos, args.local,
            chave_places=chave,
            max_por_termo=args.max_por_termo,
            tipo=tipo,
            paralelismo=args.paralelismo,
            consultar_cnpj=not args.sem_cnpj,
            respeitar_robots=not args.ignorar_robots,
            progresso=log,
        )
    except Exception as e:
        print(f"\n✗ {e}\n")
        return 1

    if not leads:
        print("\nNenhum resultado. Tente outro termo ou amplie a localização.\n")
        return 1

    if args.minimo:
        leads = [l for l in leads if l.score >= args.minimo]
    if args.limite:
        leads = leads[: args.limite]

    banco = Banco(config.caminho_banco())
    novos = sum(1 for l in leads if banco.salvar(l))
    banco.registrar_rodada(nome_nicho, args.local, len(leads), novos)
    banco.fechar()

    print(f"\n{'─' * 60}")
    print(f"{len(leads)} leads · {novos} inéditos · "
          f"{sum(1 for l in leads if l.faixa == 'quente')} quentes")
    print(f"{'─' * 60}\n")

    for i, lead in enumerate(leads[: args.mostrar], 1):
        imprimir_lead(lead, i)

    if len(leads) > args.mostrar:
        print(f"      … e mais {len(leads) - args.mostrar}. Tudo está nos arquivos abaixo.\n")

    base = f"{slug(nome_nicho)}-{slug(args.local)}-{datetime.now():%Y%m%d-%H%M}"
    arquivos = entregar(
        leads, base,
        f"{nome_nicho.capitalize()} · {args.local}",
        f"{len(leads)} leads · rodada de {datetime.now():%d/%m/%Y %H:%M} · "
        f"score = quanto vale abordar (0–100)",
        abrir=not args.nao_abrir,
    )
    print("Arquivos gerados:")
    for k, v in arquivos.items():
        if v:
            print(f"  {k.upper():<5} {v}")
    print()
    return 0


def cmd_analisar(args) -> int:
    """Diagnóstico avulso de um site — sem gastar cota da Places API."""
    config.carregar_env(args.env)
    coletor = ColetorSite(respeitar_robots=not args.ignorar_robots)
    lead = montar_lead({"nome": args.url, "site": args.url}, "avulso", "análise avulsa")
    lead = enriquecer(lead, coletor, consultar_cnpj=not args.sem_cnpj)

    print()
    imprimir_lead(lead, 1)
    print(f"  Score: {lead.score}/100 ({lead.faixa})\n")
    for s in lead.sinais:
        marca = "+" if s.pontos > 0 else " "
        print(f"  {marca}{s.pontos if s.pontos else '':>3}  {s.titulo}")
        print(f"        {s.evidencia}\n")

    if args.json:
        print(json.dumps(lead.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_lista(args) -> int:
    config.carregar_env(args.env)
    banco = Banco(config.caminho_banco())
    dados = banco.listar(nicho=args.nicho, minimo=args.minimo, limite=args.limite)
    resumo = banco.resumo()
    banco.fechar()

    if not dados:
        print("\nBanco vazio. Rode `prospector buscar` primeiro.\n")
        return 1

    print(f"\nBanco: {resumo['total']} leads · {resumo['quentes']} quentes · "
          f"{resumo['mornos']} mornos\n")
    leads = [_dict_para_lead(d) for d in dados]
    for i, lead in enumerate(leads[: args.mostrar], 1):
        imprimir_lead(lead, i)

    if args.exportar:
        base = f"fila-{slug(args.nicho or 'todos')}-{datetime.now():%Y%m%d-%H%M}"
        arquivos = entregar(leads, base, "Fila de prospecção",
                            f"{len(leads)} leads do banco local", abrir=not args.nao_abrir)
        print("Arquivos gerados:")
        for k, v in arquivos.items():
            if v:
                print(f"  {k.upper():<5} {v}")
        print()
    return 0


def cmd_marcar(args) -> int:
    config.carregar_env(args.env)
    banco = Banco(config.caminho_banco())
    banco.marcar(args.chave, args.status)
    banco.fechar()
    print(f"{args.chave} → {args.status}")
    return 0


# --------------------------------------------------------------------------- #

def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prospector",
        description="SoulFork Prospector — encontra e qualifica clientes por nicho e localização.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""exemplos:
  prospector nichos
  prospector buscar fisioterapia --local "Brasília, DF"
  prospector buscar contabilidade --local "Taguatinga, DF" --minimo 45
  prospector buscar "clínica de podologia" --local "Goiânia, GO" --limite 30
  prospector analisar https://exemplo.com.br
  prospector lista --nicho fisioterapia --exportar
""",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--env", help="caminho de um .env alternativo")
    p.add_argument("--nichos", help="caminho de um nichos.json alternativo")
    sub = p.add_subparsers(dest="comando", required=True)

    b = sub.add_parser("buscar", help="roda uma prospecção completa")
    b.add_argument("nicho", help="nome de um nicho do nichos.json, ou termo livre entre aspas")
    b.add_argument("--local", required=True, help='cidade/região, ex: "Brasília, DF"')
    b.add_argument("--termo", action="append", help="sobrescreve os termos do nicho (repetível)")
    b.add_argument("--max-por-termo", type=int, default=60,
                   help="teto de resultados por termo (a API entrega no máximo 60)")
    b.add_argument("--minimo", type=int, default=0, help="descarta leads abaixo deste score")
    b.add_argument("--limite", type=int, help="mantém só os N melhores")
    b.add_argument("--mostrar", type=int, default=15, help="quantos imprimir no terminal")
    b.add_argument("--paralelismo", type=int, default=6, help="sites analisados em paralelo")
    b.add_argument("--sem-cnpj", action="store_true", help="pula a consulta à Receita")
    b.add_argument("--ignorar-robots", action="store_true",
                   help="ignora robots.txt (use com consciência)")
    b.add_argument("--nao-abrir", action="store_true", help="não abre o relatório no navegador")
    b.set_defaults(func=cmd_buscar)

    a = sub.add_parser("analisar", help="diagnostica um único site, sem usar a Places API")
    a.add_argument("url")
    a.add_argument("--json", action="store_true", help="imprime o JSON completo")
    a.add_argument("--sem-cnpj", action="store_true")
    a.add_argument("--ignorar-robots", action="store_true")
    a.set_defaults(func=cmd_analisar)

    l = sub.add_parser("lista", help="mostra os leads já salvos no banco local")
    l.add_argument("--nicho")
    l.add_argument("--minimo", type=int, default=0)
    l.add_argument("--limite", type=int, default=500)
    l.add_argument("--mostrar", type=int, default=20)
    l.add_argument("--exportar", action="store_true", help="gera CSV/XLSX/HTML da fila")
    l.add_argument("--nao-abrir", action="store_true")
    l.set_defaults(func=cmd_lista)

    n = sub.add_parser("nichos", help="lista os nichos configurados")
    n.set_defaults(func=cmd_nichos)

    m = sub.add_parser("marcar", help="muda o status de um lead (novo/abordado/reuniao/fechado/descartado)")
    m.add_argument("chave", help='ex: "place:ChIJ..."')
    m.add_argument("status")
    m.set_defaults(func=cmd_marcar)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = montar_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrompido.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
