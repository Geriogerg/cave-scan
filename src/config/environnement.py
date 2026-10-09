"""Le fichier `.env` du projet, lu par les DEUX lignes de commande.

Il porte les clés d'API, mais aussi la base et le stockage (`.env.example`) :
si un seul script le lisait, `run_v0.py` et `inventaire.py` pourraient
travailler sur deux bases différentes sans le dire. Les SDK et
`src/donnees/base.py` ne lisent que les variables d'environnement ; ce module
les y verse, sans jamais écraser une variable déjà définie.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
FICHIER_ENV = RACINE / ".env"


def charger_env(fichier: Path = FICHIER_ENV) -> None:
    """Charge `.env` s'il existe, pour que `.env.example` dise la vérité.

    Sans ceci, un `.env` rempli consciencieusement n'aurait servi à rien, et
    l'erreur aurait été un « clé absente » incompréhensible.
    """
    if not fichier.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        print(
            f"⚠  {fichier} existe mais python-dotenv n'est pas installé : "
            f"il ne sera pas lu.\n   `pip install python-dotenv`, ou exportez "
            f"les variables dans l'environnement.",
            file=sys.stderr,
        )
        return
    load_dotenv(fichier)
