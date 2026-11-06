"""Extraction du texte des documents et détection de la date du document."""

from __future__ import annotations

import email
import email.policy
import re
from datetime import date, datetime
from pathlib import Path

from .config import TEXTE_MAX

MOIS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}

_RE_ISO = re.compile(r"(?<!\d)(19\d{2}|20\d{2})[-_.](0[1-9]|1[0-2])[-_.](0[1-9]|[12]\d|3[01])(?!\d)")
_RE_COMPACT = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")
_RE_FR = re.compile(r"(?<!\d)(0?[1-9]|[12]\d|3[01])[/.\-](0?[1-9]|1[0-2])[/.\-](19\d{2}|20\d{2})(?!\d)")
_RE_JJMMAA = re.compile(r"(?<!\d)(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(\d{2})(?!\d)")
_RE_LITTERAL = re.compile(
    r"(?<!\d)(1er|[12]\d|3[01]|0?[1-9])\s+(" + "|".join(MOIS) + r")\s+(19\d{2}|20\d{2})(?!\d)",
    re.IGNORECASE,
)


def _valide(a: int, m: int, j: int) -> date | None:
    try:
        d = date(a, m, j)
    except ValueError:
        return None
    if d > date.today() or d.year < 1950:
        return None
    return d


def date_dans_nom(nom: str) -> date | None:
    """Date écrite dans un nom de fichier (AAAA-MM-JJ, AAAAMMJJ, JJ.MM.AAAA, JJMMAA)."""
    for rx, ordre in ((_RE_ISO, "amj"), (_RE_COMPACT, "amj"), (_RE_FR, "jma"), (_RE_JJMMAA, "jma2")):
        m = rx.search(nom)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        if ordre == "amj":
            d = _valide(g[0], g[1], g[2])
        elif ordre == "jma":
            d = _valide(g[2], g[1], g[0])
        else:
            d = _valide(2000 + g[2], g[1], g[0])
        if d:
            return d
    return None


def date_dans_texte(texte: str) -> date | None:
    """Première date plausible dans les premiers caractères du texte."""
    debut = texte[:4000]
    candidats: list[tuple[int, date]] = []
    for m in _RE_LITTERAL.finditer(debut):
        j = 1 if m.group(1).lower() == "1er" else int(m.group(1))
        d = _valide(int(m.group(3)), MOIS[m.group(2).lower()], j)
        if d:
            candidats.append((m.start(), d))
    for m in _RE_FR.finditer(debut):
        d = _valide(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            candidats.append((m.start(), d))
    for m in _RE_ISO.finditer(debut):
        d = _valide(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            candidats.append((m.start(), d))
    if not candidats:
        return None
    return min(candidats)[1]


def date_du_document(nom: str, texte: str, modifie_le: float) -> tuple[str, str]:
    """Renvoie (date ISO, source) : nom, contenu, sinon date du fichier."""
    d = date_dans_nom(nom)
    if d:
        return d.isoformat(), "nom"
    d = date_dans_texte(texte)
    if d:
        return d.isoformat(), "contenu"
    return datetime.fromtimestamp(modifie_le).date().isoformat(), "fichier"


def extraire_texte(chemin: Path) -> str:
    """Texte brut du document, ou chaîne vide si le format n'est pas lu."""
    ext = chemin.suffix.lower()
    try:
        if ext in {".txt", ".md", ".csv"}:
            texte = chemin.read_text(encoding="utf-8", errors="replace")
        elif ext == ".pdf":
            texte = _pdf(chemin)
        elif ext == ".docx":
            texte = _docx(chemin)
        elif ext in {".xlsx", ".xlsm"}:
            texte = _xlsx(chemin)
        elif ext == ".pptx":
            texte = _pptx(chemin)
        elif ext == ".eml":
            texte = _eml(chemin)
        else:
            return ""
    except Exception:
        return ""
    return re.sub(r"\s+", " ", texte).strip()[:TEXTE_MAX]


def _pdf(chemin: Path) -> str:
    from pypdf import PdfReader

    lecteur = PdfReader(str(chemin))
    return "\n".join((page.extract_text() or "") for page in lecteur.pages[:50])


def _docx(chemin: Path) -> str:
    import docx

    document = docx.Document(str(chemin))
    parties = [p.text for p in document.paragraphs]
    for table in document.tables:
        for ligne in table.rows:
            parties.extend(c.text for c in ligne.cells)
    return "\n".join(parties)


def _xlsx(chemin: Path) -> str:
    import openpyxl

    classeur = openpyxl.load_workbook(str(chemin), read_only=True, data_only=True)
    parties: list[str] = []
    for feuille in classeur.worksheets[:10]:
        parties.append(feuille.title)
        for i, ligne in enumerate(feuille.iter_rows(values_only=True)):
            if i >= 500:
                break
            parties.extend(str(v) for v in ligne if v is not None)
    classeur.close()
    return " ".join(parties)


def _pptx(chemin: Path) -> str:
    from pptx import Presentation

    pres = Presentation(str(chemin))
    parties: list[str] = []
    for diapo in pres.slides:
        for forme in diapo.shapes:
            if forme.has_text_frame:
                parties.append(forme.text_frame.text)
    return "\n".join(parties)


def _eml(chemin: Path) -> str:
    message = email.message_from_bytes(chemin.read_bytes(), policy=email.policy.default)
    entete = f"{message.get('subject', '')} {message.get('from', '')} {message.get('to', '')}"
    corps = message.get_body(preferencelist=("plain", "html"))
    return entete + "\n" + (corps.get_content() if corps else "")
