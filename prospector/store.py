"""Banco local SQLite — histórico e deduplicação entre rodadas."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Lead

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leads (
    chave            TEXT PRIMARY KEY,
    place_id         TEXT,
    nome             TEXT,
    site             TEXT,
    municipio        TEXT,
    uf               TEXT,
    nicho            TEXT,
    score            INTEGER,
    faixa            TEXT,
    status           TEXT DEFAULT 'novo',
    primeira_vez_em  TEXT,
    atualizado_em    TEXT,
    dados            TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_nicho ON leads(nicho);
CREATE TABLE IF NOT EXISTS posicoes (
    chave     TEXT,
    busca     TEXT,
    posicao   INTEGER,
    medido_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_pos ON posicoes(busca, medido_em);
CREATE TABLE IF NOT EXISTS rodadas (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nicho     TEXT,
    local     TEXT,
    total     INTEGER,
    novos     INTEGER,
    criada_em TEXT
);
"""


def _agora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def chave_do_lead(lead: Lead) -> str:
    if lead.place_id:
        return f"place:{lead.place_id}"
    if lead.site:
        return "site:" + lead.site.lower().replace("https://", "").replace("http://", "").rstrip("/")
    return f"nome:{(lead.nome or '').lower()}|{(lead.municipio or '').lower()}"


class Banco:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.caminho)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self.con.commit()

    def ja_visto(self, chave: str) -> bool:
        cur = self.con.execute("SELECT 1 FROM leads WHERE chave = ?", (chave,))
        return cur.fetchone() is not None

    def salvar(self, lead: Lead) -> bool:
        """Devolve True se é lead novo. Upsert atômico: duas buscas simultâneas
        não quebram no UNIQUE constraint."""
        chave = chave_do_lead(lead)
        novo = not self.ja_visto(chave)
        agora = _agora()
        payload = json.dumps(lead.to_dict(), ensure_ascii=False)
        self.con.execute(
            "INSERT INTO leads (chave, place_id, nome, site, municipio, uf, nicho,"
            " score, faixa, primeira_vez_em, atualizado_em, dados)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(chave) DO UPDATE SET"
            " nome=excluded.nome, site=excluded.site, score=excluded.score,"
            " faixa=excluded.faixa, atualizado_em=excluded.atualizado_em,"
            " dados=excluded.dados",
            (chave, lead.place_id, lead.nome, lead.site, lead.municipio, lead.uf,
             lead.nicho, lead.score, lead.faixa, agora, agora, payload),
        )
        self.con.commit()
        return novo

    def registrar_posicoes(self, busca: str, leads: list[Lead]) -> None:
        agora = _agora()
        self.con.executemany(
            "INSERT INTO posicoes (chave, busca, posicao, medido_em) VALUES (?,?,?,?)",
            [((l.place_id or l.nome), busca, l.posicao_maps, agora)
             for l in leads if l.posicao_maps],
        )
        self.con.commit()

    def posicoes_anteriores(self, busca: str) -> dict[str, int]:
        """Última medição ANTERIOR à mais recente, para comparar subiu/caiu."""
        datas = [r[0] for r in self.con.execute(
            "SELECT DISTINCT medido_em FROM posicoes WHERE busca=? ORDER BY medido_em DESC LIMIT 2",
            (busca,))]
        if len(datas) < 2:
            return {}
        anterior = datas[1]
        return {r["chave"]: r["posicao"] for r in self.con.execute(
            "SELECT chave, posicao FROM posicoes WHERE busca=? AND medido_em=?",
            (busca, anterior))}

    def registrar_rodada(self, nicho: str, local: str, total: int, novos: int) -> None:
        self.con.execute(
            "INSERT INTO rodadas (nicho, local, total, novos, criada_em) VALUES (?,?,?,?,?)",
            (nicho, local, total, novos, _agora()),
        )
        self.con.commit()

    def listar(self, nicho: str | None = None, minimo: int = 0, limite: int = 500) -> list[dict]:
        sql = "SELECT dados, status, primeira_vez_em FROM leads WHERE score >= ?"
        args: list = [minimo]
        if nicho:
            sql += " AND nicho = ?"
            args.append(nicho)
        sql += " ORDER BY score DESC LIMIT ?"
        args.append(limite)
        saida = []
        for r in self.con.execute(sql, args):
            d = json.loads(r["dados"])
            d["_status"] = r["status"]
            d["_primeira_vez_em"] = r["primeira_vez_em"]
            saida.append(d)
        return saida

    def marcar(self, chave: str, status: str) -> None:
        self.con.execute("UPDATE leads SET status=?, atualizado_em=? WHERE chave=?",
                         (status, _agora(), chave))
        self.con.commit()

    def resumo(self) -> dict:
        cur = self.con.execute(
            "SELECT COUNT(*) t, SUM(faixa='quente') q, SUM(faixa='morno') m,"
            " SUM(status='novo') n FROM leads"
        ).fetchone()
        return {"total": cur["t"] or 0, "quentes": cur["q"] or 0,
                "mornos": cur["m"] or 0, "novos": cur["n"] or 0}

    def fechar(self) -> None:
        self.con.close()
