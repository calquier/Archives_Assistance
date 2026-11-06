# Archiviste

Application locale qui indexe les archives personnelles et professionnelles (ESPACE PERSO, ESPACE PRO), permet de les retrouver par mots-clés et par dates, repère les doublons et propose des renommages et des mises à la corbeille.

**Rien n'est déplacé, renommé ni supprimé** : le scan ne fait que lire, et les propositions attendent une validation. L'application des changements validés, avec journal et annulation, est la prochaine étape.

L'interface reprend la charte de la Console personnelle (rail de modules, bandeau, accents or).

## Installation (Windows, une fois)

Prérequis : Python 3.11 ou plus récent.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\installer.ps1
```

Vérifiez ensuite les dossiers indexés dans `.env` (variable `ARCHIVISTE_RACINES`, chemins séparés par `;`).

## Utilisation

```powershell
powershell -ExecutionPolicy Bypass -File scripts\lancer.ps1
```

L'interface s'ouvre sur http://127.0.0.1:8765. Cliquez sur « Mettre à jour l'index » pour le premier scan.

| Module | Contenu |
| --- | --- |
| Accueil | Nombre de documents, volume, doublons, documents par rubrique |
| Recherche | Mots-clés dans le nom et le contenu (PDF, Word, Excel, PowerPoint, texte, emails .eml), filtres par rubrique, type et dates |
| Doublons | Groupes de fichiers identiques, avec l'exemplaire à garder |
| Propositions | Renommage selon la convention `AAAA-MM-JJ_Type_Tiers_Précision_vNN.ext`, et mise à la corbeille (copies, conflits OneDrive, versions antérieures, fichiers techniques) |
| Réglages | Dossiers indexés, syntaxe de recherche |

Syntaxe de recherche : `facture orange`, `"lettre de mission"`, `-brouillon`, `rubrique:Missions` (ou `rubrique:"ESPACE PRO/[2] Missions"`), `ext:pdf`, `depuis:2023-01-01`, `jusqua:2024-12-31`.

Ligne de commande : `python -m archiviste scanner | chercher <requête> | doublons | plan | serveur`.

## Mise à jour automatique

```powershell
powershell -ExecutionPolicy Bypass -File scripts\installer-tache.ps1
```

Crée une tâche Windows qui met l'index à jour chaque dimanche à 20 h.

## Protections

- Les pièces d'identité, impôts, contrats, baux, bulletins, factures, statuts, PV, Kbis et diplômes ne sont jamais proposés à la corbeille.
- Le code (`[7] Python`, `[80] Dev`), les sauvegardes brutes (`Carte SD MC`) et les pages web enregistrées ne sont pas renommés.
- Une proposition refusée n'est plus présentée tant que le fichier ne change pas.

## Développement

```bash
cd backend
pip install -e ".[dev]"
pytest
```

| Fichier | Rôle |
| --- | --- |
| `backend/archiviste/scanner.py` | Parcours incrémental des dossiers, empreintes SHA-256 |
| `backend/archiviste/extraction.py` | Texte des documents, date du document (nom, contenu, sinon fichier) |
| `backend/archiviste/db.py` | Index SQLite avec recherche plein texte FTS5 |
| `backend/archiviste/recherche.py` | Analyse des requêtes et recherche |
| `backend/archiviste/doublons.py` | Groupes de doublons exacts |
| `backend/archiviste/nommage.py` | Convention de nommage |
| `backend/archiviste/propositions.py` | Propositions de renommage et de corbeille, décisions |
| `backend/archiviste/api.py` | API web et service de l'interface |
| `web/` | Interface (HTML, CSS, JavaScript sans compilation) |
