"""Convention de nommage : AAAA-MM-JJ_Type_Tiers[_Precision][_vNN].ext"""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath

TYPES = {
    # mot-clé (sans accent, minuscule) -> Type normalisé
    "facture": "Facture", "invoice": "Facture",
    "devis": "Devis", "propale": "Devis", "proposition commerciale": "Devis",
    "contrat": "Contrat", "convention": "Contrat",
    "avenant": "Avenant",
    "bail": "Bail",
    "releve": "Releve",
    "avis": "Avis",
    "attestation": "Attestation", "certificat": "Attestation", "justificatif": "Attestation",
    "courrier": "Courrier", "lettre": "Courrier",
    "compte rendu": "CR", "compte-rendu": "CR", "cr ": "CR",
    "pv": "PV", "proces verbal": "PV", "proces-verbal": "PV",
    "statuts": "Statuts",
    "bulletin": "Bulletin", "fiche de paie": "Bulletin",
    "presentation": "Presentation",
    "note": "Note",
    "modele": "Modele", "template": "Modele",
    "business plan": "BP", "bp ": "BP", "budget": "BP",
    "stock": "Etat", "etat": "Etat", "reporting": "Etat", "tableau de bord": "Etat",
}
EXT_PHOTO = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".tif", ".tiff"}
EXT_PRESENTATION = {".pptx", ".ppt"}
MOTS_VIDES = {"et", "de", "du", "la", "le", "les", "des", "d", "l", "a", "au", "aux", "en", "pour", "sur", "un", "une"}
EXT_EXCLUES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".css", ".html", ".bat", ".ps1",
    ".ini", ".lnk", ".url", ".db", ".sqlite3", ".exe", ".dll", ".msi",
}
DOSSIERS_EXCLUS = re.compile(r"python|\bdev\b|carte sd|\.vscode|_files", re.IGNORECASE)

RE_CONFORME = re.compile(r"^\d{4}(-\d{2}){0,2}_[A-Z][A-Za-z]+_[A-Za-z0-9-]+(_[A-Za-z0-9-]+)?(_v\d{2})?$")
RE_VERSION = re.compile(r"(?:^|[\s_\-.])v(\d{1,2})(?:[.\-_](\d{1,2}))?(?=$|[\s_\-.])", re.IGNORECASE)
RE_NUMERO_DOSSIER = re.compile(r"^\s*[\[(]?\d{1,3}[\])]?\s*-?\s*")
RE_COPIE = re.compile(r"\s*(- Copie|- Copy|\(\d+\)|\[Récupéré\])\s*", re.IGNORECASE)
RE_DATES = re.compile(
    r"(19|20)\d{2}[-_.]?\d{2}[-_.]?\d{2}|\d{1,2}[/.\-]\d{1,2}[/.\-](19|20)\d{2}|(?<!\d)\d{6}(?!\d)"
)


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def segment(texte: str, max_len: int = 40) -> str:
    """Mots séparés par des tirets, sans accents ni caractères spéciaux."""
    propre = sans_accents(texte)
    mots = re.findall(r"[A-Za-z0-9]+", propre)
    resultat = "-".join(mots)
    return resultat[:max_len].strip("-")


def est_conforme(nom: str) -> bool:
    return bool(RE_CONFORME.match(PurePath(nom).stem))


def detecter_type(nom: str, ext: str, texte: str = "") -> str:
    if ext in EXT_PHOTO:
        return "Photo"
    cible = " " + sans_accents(nom).lower().replace("_", " ") + " "
    for cle, valeur in TYPES.items():
        if cle in cible:
            return valeur
    if ext in EXT_PRESENTATION:
        return "Presentation"
    debut = " " + sans_accents(texte[:600]).lower() + " "
    for cle, valeur in TYPES.items():
        if len(cle) > 3 and cle in debut:
            return valeur
    return "Document"


def tiers_depuis_chemin(relatif: str) -> str:
    """Le dossier sous la rubrique (ex. [2] Missions/CLIENT/... -> CLIENT)."""
    dossiers = list(PurePath(relatif).parts[:-1])
    if len(dossiers) >= 2:
        candidat = dossiers[1]
    elif dossiers:
        candidat = dossiers[0]
    else:
        return ""
    return segment(RE_NUMERO_DOSSIER.sub("", candidat), 30)


def version(nom: str) -> str:
    m = RE_VERSION.search(PurePath(nom).stem)
    if not m:
        return ""
    return f"v{int(m.group(1)):02d}"


def precision(nom: str, type_doc: str, tiers: str) -> str:
    base = PurePath(nom).stem
    base = RE_COPIE.sub(" ", base)
    base = RE_VERSION.sub(" ", base)
    base = RE_DATES.sub(" ", base)
    mots = re.findall(r"[A-Za-z0-9]+", sans_accents(base))
    a_retirer = {type_doc.lower(), *tiers.lower().split("-")}
    for cle, valeur in TYPES.items():
        if valeur == type_doc:
            a_retirer.update(cle.split())
    gardes = [m[0].upper() + m[1:] for m in mots if m.lower() not in MOTS_VIDES and m.lower() not in a_retirer]
    return segment(" ".join(gardes), 40)


def appliquer_convention(nom: str, relatif: str, date_doc: str, ext: str, texte: str = "") -> str:
    type_doc = detecter_type(nom, ext, texte)
    tiers = tiers_depuis_chemin(relatif) or "Divers"
    parties = [date_doc, type_doc, tiers]
    prec = precision(nom, type_doc, tiers)
    if prec:
        parties.append(prec)
    v = version(nom)
    if v:
        parties.append(v)
    nouveau = "_".join(parties)[:80 - len(ext)]
    return nouveau + ext.lower()


def renommage_exclu(relatif: str, ext: str) -> bool:
    return ext in EXT_EXCLUES or bool(DOSSIERS_EXCLUS.search(relatif)) or PurePath(relatif).name.startswith("~$")
