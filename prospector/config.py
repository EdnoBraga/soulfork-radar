"""Configuração: chaves, nichos e caminhos.

Dados graváveis (.env, banco, exportações, nichos.json editável) moram em
FIND_DADOS — no servidor, um volume persistente. Sem a variável, na pasta
do projeto (desenvolvimento local).
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def raiz_projeto() -> Path:
    """Onde mora o código (e o nichos.json padrão)."""
    return Path(__file__).resolve().parent.parent


def pasta_dados() -> Path:
    base = Path(os.environ.get("FIND_DADOS") or raiz_projeto())
    base.mkdir(parents=True, exist_ok=True)
    return base


def carregar_env(caminho: str | Path | None = None) -> None:
    """Lê um .env simples (CHAVE=valor) sem depender de biblioteca externa."""
    alvo = Path(caminho) if caminho else pasta_dados() / ".env"
    if not alvo.exists():
        return
    for linha in alvo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor


def chave_places() -> str:
    return os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()


def _gravar_env(**pares: str) -> Path:
    """Grava chaves no .env do usuário e aplica no processo atual."""
    alvo = pasta_dados() / ".env"
    linhas: list[str] = []
    if alvo.exists():
        linhas = [l for l in alvo.read_text(encoding="utf-8").splitlines()
                  if not any(l.strip().startswith(k) for k in pares)]
    for chave, valor in pares.items():
        valor = (valor or "").strip().strip('"').strip("'")
        linhas.append(f"{chave}={valor}")
        os.environ[chave] = valor
    alvo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return alvo


def salvar_chave_places(chave: str) -> Path:
    return _gravar_env(GOOGLE_PLACES_API_KEY=chave)


def token_instagram() -> str:
    return os.environ.get("META_IG_TOKEN", "").strip()


def ig_user_id() -> str:
    return os.environ.get("META_IG_USER_ID", "").strip()


def salvar_token_instagram(token: str, user_id: str) -> Path:
    return _gravar_env(META_IG_TOKEN=token, META_IG_USER_ID=user_id)


def carregar_nichos(caminho: str | Path | None = None) -> dict:
    """Lê nichos.json da pasta do usuário; se não existir lá, copia o embutido."""
    if caminho:
        alvo = Path(caminho)
    else:
        alvo = pasta_dados() / "nichos.json"
        embutido = raiz_projeto() / "nichos.json"
        if not alvo.exists() and embutido.exists():
            try:
                shutil.copy(embutido, alvo)
            except OSError:
                alvo = embutido
    if not alvo.exists():
        return {}
    dados = json.loads(alvo.read_text(encoding="utf-8"))
    return {k: v for k, v in dados.items() if not k.startswith("_")}


def _normal(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", texto.lower().strip())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t[:-1] if t.endswith("s") else t   # "dentistas" == "dentista"


def termos_do_nicho(texto: str, nichos: dict | None = None) -> tuple[str | None, list[str], str | None]:
    """Casa o que o usuário digitou com o nichos.json. Devolve (nicho, termos, tipo).

    - Nome do nicho ("odontologia") -> todos os termos do grupo.
    - Um dos termos ("pizzaria") -> só ele, com o tipo do grupo. Os grupos
      misturam sub-nichos (pizzaria e hamburgueria em "restaurante"); completar
      uma busca de pizzaria com hamburgueria seria lixo.
    - Nada casou -> termo livre, sem tipo."""
    alvo = _normal(texto)
    for nome, cfg in (carregar_nichos() if nichos is None else nichos).items():
        termos = cfg.get("termos") or [nome]
        if alvo == _normal(nome):
            return nome, termos, cfg.get("tipo")
        if alvo in {_normal(t) for t in termos}:
            return nome, [texto], cfg.get("tipo")
    return None, [texto], None


def pasta_saida() -> Path:
    p = Path(os.environ.get("PROSPECTOR_SAIDA", pasta_dados() / "saida"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def caminho_banco() -> Path:
    return Path(os.environ.get("PROSPECTOR_BANCO", pasta_dados() / "saida" / "leads.db"))
