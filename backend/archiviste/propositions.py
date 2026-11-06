"""Propositions de renommage et de mise à la corbeille.

Ce module ne fait que proposer : il ne touche à aucun fichier. Chaque
proposition porte une clé stable ; la décision (acceptée, refusée) est
enregistrée dans la table `decisions`.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from pathlib import PurePath

from .doublons import groupes_doublons
from .nommage import appliquer_convention, est_conforme, renommage_exclu, sans_accents

# Documents jamais proposés à la corbeille (sauf demande explicite de l'utilisateur).
RE_PROTEGE = re.compile(
    r"identit|passeport|permis|imp[oô]ts?\b|contrat|bail|acte|bulletin|salaire|facture|statuts|\bpv\b|kbis|dipl[oô]me",
    re.IGNORECASE,
)
RE_CONFLIT = re.compile(r"-(DESKTOP|LAPTOP)-[A-Z0-9]+", re.IGNORECASE)
RE_COPIE = re.compile(r"( - Copie| - Copy|\(\d+\)|\[Récupéré\])", re.IGNORECASE)
RE_TECHNIQUE_NOM = re.compile(r"^(~\$|\.~lock)|\.(tmp|temp|crdownload|part)$|^(thumbs\.db|desktop\.ini|\.ds_store)$", re.IGNORECASE)
RE_PAGE_WEB = re.compile(r"_files[\\/]|\.t[ée]l[ée]charger$", re.IGNORECASE)
RE_VERSION_NOM = re.compile(r"(?:^|[\s_\-.])v(\d{1,2})(?:[.\-_](\d{1,2}))?(?=$|[\s_\-.])", re.IGNORECASE)


def cle(*parties: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parties).encode()).hexdigest()[:24]


def protege(relatif: str) -> bool:
    return bool(RE_PROTEGE.search(sans_accents(relatif)))


def decisions(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["cle"]: r["statut"] for r in conn.execute("SELECT cle, statut FROM decisions")}


def decider(conn: sqlite3.Connection, cle_prop: str, statut: str) -> None:
    if statut == "annuler":
        conn.execute("DELETE FROM decisions WHERE cle = ?", (cle_prop,))
    else:
        conn.execute(
            "INSERT INTO decisions(cle, statut, decide_le) VALUES (?, ?, ?) "
            "ON CONFLICT(cle) DO UPDATE SET statut = excluded.statut, decide_le = excluded.decide_le",
            (cle_prop, statut, time.time()),
        )
    conn.commit()


def _doc(d: dict) -> dict:
    return {k: d[k] for k in ("id", "chemin", "racine", "relatif", "nom", "taille", "rubrique") if k in d}


# ---------------------------------------------------------------- renommage

def propositions_renommage(conn: sqlite3.Connection, limite: int = 500) -> list[dict]:
    dec = decisions(conn)
    # Un fichier proposé à la corbeille n'est pas proposé au renommage.
    a_jeter = {p["document"]["chemin"] for p in propositions_corbeille(conn)}
    resultat = []
    lignes = conn.execute(
        "SELECT id, chemin, racine, relatif, nom, extension, taille, sha256, date_doc, date_source, rubrique, "
        "substr(texte, 1, 600) AS debut FROM documents ORDER BY rubrique, relatif"
    )
    for d in map(dict, lignes):
        if d["chemin"] in a_jeter or renommage_exclu(d["relatif"], d["extension"]) or est_conforme(d["nom"]):
            continue
        nouveau = appliquer_convention(d["nom"], d["relatif"], d["date_doc"], d["extension"], d["debut"] or "")
        if nouveau == d["nom"]:
            continue
        k = cle("renommage", d["chemin"], d["sha256"], nouveau)
        statut = dec.get(k)
        if statut == "refusee":
            continue
        resultat.append(
            {
                "cle": k,
                "type": "renommage",
                "document": _doc(d),
                "nouveau_nom": nouveau,
                "date_source": d["date_source"],
                "a_verifier": d["date_source"] == "fichier",
                "statut": statut or "proposee",
            }
        )
        if len(resultat) >= limite:
            break
    return resultat


# ---------------------------------------------------------------- corbeille

def _base_version(nom: str) -> tuple[str, tuple[int, int]] | None:
    stem = PurePath(nom).stem
    m = RE_VERSION_NOM.search(stem)
    if not m:
        return None
    base = (stem[: m.start()] + stem[m.end():]).strip(" _-.").lower()
    return base, (int(m.group(1)), int(m.group(2) or 0))


def propositions_corbeille(conn: sqlite3.Connection) -> list[dict]:
    dec = decisions(conn)
    vues: dict[str, dict] = {}

    def ajouter(doc: dict, motif: str, detail: str, confiance: float, reference: dict | None = None):
        if doc["chemin"] in vues or protege(doc["relatif"]):
            return
        k = cle("corbeille", doc["chemin"], doc.get("sha256", ""), motif)
        statut = dec.get(k)
        if statut == "refusee":
            return
        vues[doc["chemin"]] = {
            "cle": k,
            "type": "corbeille",
            "document": _doc(doc),
            "motif": motif,
            "detail": detail,
            "confiance": confiance,
            "reference": _doc(reference) if reference else None,
            "statut": statut or "proposee",
        }

    docs = [dict(r) for r in conn.execute(
        "SELECT id, chemin, racine, relatif, nom, extension, taille, modifie_le, sha256, rubrique FROM documents"
    )]

    # 1. Fichiers techniques : temporaires Office, pages web enregistrées.
    for d in docs:
        if RE_TECHNIQUE_NOM.search(d["nom"]):
            ajouter(d, "technique", "Fichier temporaire ou système", 0.95)
        elif RE_PAGE_WEB.search(d["relatif"]):
            ajouter(d, "technique", "Élément d'une page web enregistrée", 0.85)

    # 2. Copies identiques (même empreinte) : on garde l'exemplaire de référence.
    for g in groupes_doublons(conn):
        ref = g["reference"]
        for c in g["copies"]:
            if RE_CONFLIT.search(c["relatif"]):
                motif, detail = "conflit", "Copie créée par un conflit de synchronisation OneDrive"
            elif RE_COPIE.search(c["nom"]):
                motif, detail = "copie", "Copie identique (« - Copie », « (1) »)"
            else:
                motif, detail = "doublon", "Contenu identique à un autre fichier"
            c = dict(c)
            c["sha256"] = g["sha256"]
            ajouter(c, motif, detail, 0.98, ref)

    # 3. Versions antérieures dans le même dossier (v1 quand v2 existe).
    par_base: dict[tuple[str, str, str], list[tuple[tuple[int, int], dict]]] = {}
    for d in docs:
        bv = _base_version(d["nom"])
        if not bv:
            continue
        dossier = str(PurePath(d["relatif"]).parent)
        par_base.setdefault((dossier, bv[0], d["extension"]), []).append((bv[1], d))
    for versions in par_base.values():
        if len(versions) < 2:
            continue
        versions.sort(key=lambda x: x[0])
        recente = versions[-1][1]
        for _, ancienne in versions[:-1]:
            ajouter(ancienne, "version", f"Version plus récente : {recente['nom']}", 0.8, recente)

    return sorted(vues.values(), key=lambda p: (p["motif"], p["document"]["relatif"]))
