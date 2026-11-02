"""Critère R1 de la boucle qualité, exécutable (T9-R3).

Pour chaque ligne « | N | … | Corrigé … » de docs/tests/journal.md, la colonne Id
est découpée sur « / » ; chaque id doit apparaître EN ENTIER dans
docs/tests/rapports/tour<N+1>.md, sur une ligne qui porte une marque (✅, ❌, ou
« non retestable »).

    python docs/tests/verifier_r1.py 7      # ids du tour 7 dans tour8.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
MARQUE = re.compile(r"✅|❌|non retestable", re.IGNORECASE)


def ids_corriges(tour: int) -> list[str]:
    ids: list[str] = []
    for ligne in (RACINE / "journal.md").read_text(encoding="utf-8").splitlines():
        colonnes = [c.strip() for c in ligne.strip().strip("|").split("|")]
        if len(colonnes) < 5 or colonnes[0] != str(tour) or not colonnes[4].startswith("Corrigé"):
            continue
        for morceau in colonnes[1].split("/"):
            identifiant = re.match(r"T\d+-[A-Z]+\d+", morceau.strip())
            if identifiant and identifiant.group(0) not in ids:
                ids.append(identifiant.group(0))
    return ids


def manquants(tour: int) -> list[str]:
    rapport = RACINE / "rapports" / f"tour{tour + 1}.md"
    lignes = rapport.read_text(encoding="utf-8").splitlines() if rapport.exists() else []
    absents = []
    for identifiant in ids_corriges(tour):
        motif = re.compile(rf"(?<![\w-]){re.escape(identifiant)}(?![\d])")
        if not any(motif.search(ligne) and MARQUE.search(ligne) for ligne in lignes):
            absents.append(identifiant)
    return absents


def main(argv: list[str]) -> int:
    tour = int(argv[1])
    absents = manquants(tour)
    print(f"Tour {tour} : {len(ids_corriges(tour))} ids « Corrigé », {len(absents)} sans marque dans tour{tour + 1}.md"
          + (f" : {', '.join(absents)}" if absents else "."))
    return 1 if absents else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
