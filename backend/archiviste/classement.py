"""Propositions de classement : où ranger chaque dossier et chaque fichier.

Le plan de classement est un fichier JSON propre à chaque utilisateur (il
contient les noms de ses dossiers) : `plan_classement.json` à la racine du
projet, ou le chemin donné par ARCHIVISTE_PLAN. Voir
`plan_classement.exemple.json`.

Deux sortes de propositions, jamais appliquées sans validation :
- dossier : déplacer un dossier existant dans sa rubrique cible ;
- fichier : ranger un fichier isolé (à la racine d'un espace, dans un dossier
  au nom vague, ou n'importe où dans un dossier de passage comme Téléchargements,
  c'est-à-dire une racine sans rubrique propre) dans la rubrique dont les mots-clés correspondent le mieux à son
  nom et à son contenu.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path, PurePath

from .nommage import sans_accents
from .propositions import cle, decisions

RACINE_PROJET = Path(__file__).resolve().parent.parent.parent
RE_DOSSIER_VAGUE = re.compile(r"^(nouveau dossier|new folder|divers|a trier|à trier|temp|tmp)\b", re.IGNORECASE)


def chemin_plan() -> Path:
    return Path(os.environ.get("ARCHIVISTE_PLAN", RACINE_PROJET / "plan_classement.json")).expanduser()


def charger_plan(chemin: Path | None = None) -> dict:
    chemin = chemin or chemin_plan()
    if not chemin.is_file():
        return {"dossiers": [], "rubriques": []}
    plan = json.loads(chemin.read_text(encoding="utf-8"))
    plan.setdefault("dossiers", [])
    plan.setdefault("rubriques", [])
    return plan


def _norm(p: str) -> str:
    return p.replace("\\", "/").strip("/")


def _racines_par_nom(racines: list[Path]) -> dict[str, Path]:
    return {r.resolve().name: r.resolve() for r in racines}


def _absolu(logique: str, racines: dict[str, Path]) -> Path | None:
    """« ESPACE PERSO/Banque » -> chemin réel, à partir du nom de la racine."""
    parties = _norm(logique).split("/")
    racine = racines.get(parties[0])
    return racine.joinpath(*parties[1:]) if racine else None


def _taille_dossier(dossier: Path) -> tuple[int, int]:
    n = t = 0
    for base, _, noms in os.walk(dossier):
        for nom in noms:
            try:
                t += os.stat(os.path.join(base, nom)).st_size
                n += 1
            except OSError:
                pass
    return n, t


# ------------------------------------------------------------ dossiers

def propositions_dossiers(plan: dict, racines: list[Path], dec: dict[str, str]) -> list[dict]:
    par_nom = _racines_par_nom(racines)
    resultat = []
    for regle in plan["dossiers"]:
        source, cible = _norm(regle["source"]), _norm(regle["cible"])
        src = _absolu(source, par_nom)
        if src is None or not src.exists():
            continue  # déjà rangé, ou absent de ce poste
        k = cle("classement", source, cible)
        statut = dec.get(k)
        if statut == "refusee":
            continue
        fichiers, taille = _taille_dossier(src) if src.is_dir() else (1, src.stat().st_size)
        resultat.append({
            "cle": k,
            "type": "classement",
            "portee": "dossier" if src.is_dir() else "fichier",
            "source": source,
            "cible": cible,
            "fusion": bool(_absolu(cible, par_nom) and _absolu(cible, par_nom).exists()),
            "fichiers": fichiers,
            "taille": taille,
            "motif": regle.get("motif", ""),
            "confiance": regle.get("confiance", 0.9),
            "statut": statut or "proposee",
        })
    return resultat


# ------------------------------------------------------------ fichiers isolés

def _score(texte: str, mots: list[str]) -> int:
    return sum(texte.count(m) for m in mots)


def meilleure_rubrique(nom: str, texte: str, rubriques: list[dict], espace: str | None = None) -> tuple[dict, float] | None:
    """Rubrique dont les mots-clés apparaissent le plus (nom ×3, contenu ×1), avec un indice de confiance."""
    nom_n = " " + sans_accents(nom).lower().replace("_", " ").replace("-", " ") + " "
    texte_n = " " + sans_accents(texte[:20000]).lower() + " "
    scores = []
    for r in rubriques:
        if espace and not _norm(r["chemin"]).startswith(espace + "/"):
            continue
        mots = [" " + sans_accents(m).lower() for m in r.get("mots_cles", [])]
        s = 3 * _score(nom_n, mots) + _score(texte_n, mots)
        if s:
            scores.append((s, r))
    if not scores:
        return None
    scores.sort(key=lambda x: -x[0])
    meilleur = scores[0][0]
    second = scores[1][0] if len(scores) > 1 else 0
    return scores[0][1], round(meilleur / (meilleur + second + 1), 2)


def est_isole(relatif: str) -> bool:
    """Fichier à la racine d'un espace, ou dans un dossier au nom vague."""
    parties = PurePath(_norm(relatif)).parts
    if len(parties) == 1:
        return True
    return any(RE_DOSSIER_VAGUE.match(p) for p in parties[:-1])


def propositions_fichiers(conn: sqlite3.Connection, plan: dict, dec: dict[str, str], deja: set[str]) -> list[dict]:
    if not plan["rubriques"]:
        return []
    resultat = []
    espaces_ranges = {_norm(r["chemin"]).split("/")[0] for r in plan["rubriques"]}
    lignes = conn.execute(
        "SELECT id, chemin, racine, relatif, nom, taille, sha256, substr(texte, 1, 20000) AS texte FROM documents"
    )
    for d in map(dict, lignes):
        espace = Path(d["racine"]).name
        de_passage = espace not in espaces_ranges  # ex. Téléchargements : tout y est à classer
        if not de_passage and not est_isole(d["relatif"]):
            continue
        source = f"{espace}/{_norm(d['relatif'])}"
        if any(source.startswith(s + "/") or source == s for s in deja):
            continue  # couvert par une proposition de dossier
        trouve = meilleure_rubrique(d["nom"], d["texte"] or "", plan["rubriques"], None if de_passage else espace)
        if not trouve:
            continue
        rubrique, confiance = trouve
        cible = f"{_norm(rubrique['chemin'])}/{d['nom']}"
        k = cle("classement", d["chemin"], d["sha256"], cible)
        statut = dec.get(k)
        if statut == "refusee":
            continue
        resultat.append({
            "cle": k,
            "type": "classement",
            "portee": "fichier",
            "document": {"id": d["id"], "chemin": d["chemin"], "nom": d["nom"]},
            "source": source,
            "cible": cible,
            "fusion": False,
            "fichiers": 1,
            "taille": d["taille"],
            "motif": f"Mots-clés de la rubrique « {PurePath(_norm(rubrique['chemin'])).name} »",
            "confiance": confiance,
            "statut": statut or "proposee",
        })
    return resultat


def propositions_classement(conn: sqlite3.Connection, racines: list[Path], plan: dict | None = None) -> dict:
    plan = plan if plan is not None else charger_plan()
    dec = decisions(conn)
    dossiers = propositions_dossiers(plan, racines, dec)
    fichiers = propositions_fichiers(conn, plan, dec, {p["source"] for p in dossiers})
    return {
        "plan_present": bool(plan["dossiers"] or plan["rubriques"]),
        "rubriques": [r["chemin"] for r in plan["rubriques"]],
        "propositions": dossiers + sorted(fichiers, key=lambda p: -p["confiance"]),
    }
