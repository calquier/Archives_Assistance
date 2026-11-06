"""Recherche par mots-clés, rubriques et dates.

Syntaxe d'une requête :
  facture orange          tous les mots (préfixes acceptés, accents ignorés)
  "lettre de mission"     expression exacte
  -brouillon              exclure un mot
  rubrique:Missions       filtre sur la rubrique (sous-chaîne ; guillemets si espaces)
  ext:pdf                 filtre sur l'extension
  depuis:2023-01-01       date du document à partir de
  jusqua:2024-12-31       date du document jusqu'à
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

_RE_JETON = re.compile(r'(\w+):"([^"]+)"|(-?)"([^"]+)"|(\S+)')
_FILTRES = {"rubrique", "ext", "depuis", "jusqua", "jusqu'a", "jusqu'à"}


@dataclass
class Requete:
    mots: list[str] = field(default_factory=list)
    exclus: list[str] = field(default_factory=list)
    rubrique: str | None = None
    ext: str | None = None
    depuis: str | None = None
    jusqua: str | None = None


def analyser(texte: str) -> Requete:
    r = Requete()
    for m in _RE_JETON.finditer(texte):
        if m.group(1) is not None:
            jeton = f"{m.group(1)}:{m.group(2)}"
        elif m.group(4) is not None:
            (r.exclus if m.group(3) else r.mots).append(m.group(4))
            continue
        else:
            jeton = m.group(5)
        if ":" in jeton:
            cle, _, valeur = jeton.partition(":")
            cle = cle.lower()
            if cle in _FILTRES and valeur:
                if cle == "rubrique":
                    r.rubrique = valeur
                elif cle == "ext":
                    r.ext = "." + valeur.lower().lstrip(".")
                elif cle == "depuis":
                    r.depuis = valeur
                else:
                    r.jusqua = valeur
                continue
        if jeton.startswith("-") and len(jeton) > 1:
            r.exclus.append(jeton[1:])
        else:
            r.mots.append(jeton)
    return r


def _terme(mot: str, prefixe: bool) -> str:
    propre = mot.replace('"', "")
    return f'"{propre}"' + ("*" if prefixe and " " not in propre else "")


def expression_fts(r: Requete) -> str | None:
    if not r.mots:
        return None
    expr = " AND ".join(_terme(m, True) for m in r.mots)
    for e in r.exclus:
        expr += " NOT " + _terme(e, False)
    return expr


def chercher(conn: sqlite3.Connection, texte: str, limite: int = 100, tri: str = "pertinence") -> list[dict]:
    r = analyser(texte)
    conditions: list[str] = []
    params: list = []
    if r.rubrique:
        conditions.append("d.rubrique LIKE ?")
        params.append(f"%{r.rubrique}%")
    if r.ext:
        conditions.append("d.extension = ?")
        params.append(r.ext)
    if r.depuis:
        conditions.append("d.date_doc >= ?")
        params.append(r.depuis)
    if r.jusqua:
        conditions.append("d.date_doc <= ?")
        params.append(r.jusqua)

    fts = expression_fts(r)
    colonnes = (
        "d.id, d.chemin, d.relatif, d.nom, d.extension, d.taille, d.date_doc, "
        "d.date_source, d.rubrique, d.racine"
    )
    if fts:
        sql = (
            f"SELECT {colonnes}, snippet(documents_fts, 2, '[', ']', ' … ', 16) AS extrait, "
            "bm25(documents_fts, 10.0, 3.0, 1.0) AS score "
            "FROM documents_fts JOIN documents d ON d.id = documents_fts.rowid "
            "WHERE documents_fts MATCH ?"
        )
        params.insert(0, fts)
    else:
        sql = f"SELECT {colonnes}, '' AS extrait, 0 AS score FROM documents d WHERE 1=1"
        for e in r.exclus:
            conditions.append("d.nom NOT LIKE ?")
            params.append(f"%{e}%")
    for c in conditions:
        sql += f" AND {c}"
    ordre = "d.date_doc DESC" if (tri == "date" or not fts) else "score"
    sql += f" ORDER BY {ordre} LIMIT ?"
    params.append(limite)
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    except sqlite3.OperationalError:
        return []
