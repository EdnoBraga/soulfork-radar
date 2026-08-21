"""Configuração: chaves, nichos e caminhos.

Dois modos de vida:
- Rodando do código-fonte: tudo mora na pasta do projeto (como sempre foi).
- Rodando instalado (PyInstaller/instalador Windows): o executável mora em
  Program Files, que não aceita escrita. Dados do usuário (.env, banco,
  exportações, nichos.json editável) vão para uma pasta própria:
  %APPDATA%/SoulForkRadar no Windows, ~/.soulfork-radar nos demais.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def congelado() -> bool:
    """True quando empacotado pelo PyInstaller."""
    return getattr(sys, "frozen", False)


def raiz_projeto() -> Path:
    """Onde moram os arquivos EMPACOTADOS (só leitura quando instalado)."""
    if congelado():
        # onedir: dados ficam ao lado do executável, em _internal
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def pasta_dados() -> Path:
    """Pasta gravável do usuário. No modo código-fonte é a própria raiz."""
    if not congelado():
        return raiz_projeto()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home())) / "SoulForkRadar"
    else:
        base = Path.home() / ".soulfork-radar"
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


def salvar_chave_places(chave: str) -> Path:
    """Grava a chave no .env do usuário e aplica no processo atual."""
    chave = (chave or "").strip().strip('"').strip("'")
    alvo = pasta_dados() / ".env"
    linhas: list[str] = []
    if alvo.exists():
        linhas = [l for l in alvo.read_text(encoding="utf-8").splitlines()
                  if not l.strip().startswith("GOOGLE_PLACES_API_KEY")]
    linhas.append(f"GOOGLE_PLACES_API_KEY={chave}")
    alvo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.environ["GOOGLE_PLACES_API_KEY"] = chave
    return alvo


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


def pasta_saida() -> Path:
    p = Path(os.environ.get("PROSPECTOR_SAIDA", pasta_dados() / "saida"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def caminho_banco() -> Path:
    return Path(os.environ.get("PROSPECTOR_BANCO", pasta_dados() / "saida" / "leads.db"))
