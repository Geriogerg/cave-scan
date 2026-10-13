"""Lance l'application (API + écrans + worker, extracteur factice) entièrement
isolée, pour l'agent testeur-web : base, stockage et configs dans un dossier
temporaire. Rien n'est écrit dans data/ ni dans config/maisons/.

    python docs/tests/lancer_appli_isolee.py DOSSIER_TEMPORAIRE [--port N]

Le dossier est créé s'il n'existe pas ; les configs de config/maisons/ y sont
COPIÉES (la page Configuration écrit dans la copie). Aucune clé API n'est lue.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    dossier = Path(sys.argv[1]).resolve()
    reste = sys.argv[2:]
    configs = dossier / "configs"
    if not configs.exists():
        shutil.copytree(RACINE / "config" / "maisons", configs)
    (dossier / "stockage").mkdir(parents=True, exist_ok=True)

    os.environ["CAVE_SCAN_STOCKAGE"] = str(dossier / "stockage")
    os.environ["CAVE_SCAN_AUTEUR"] = "Testeur"
    for variable in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "CAVE_SCAN_DB"):
        os.environ.pop(variable, None)

    from src.config import environnement

    environnement.charger_env = lambda *a, **k: None  # ne jamais lire .env (clé réelle)

    import src.api.app as application

    creer_app = application.creer_app
    application.creer_app = lambda url, **options: creer_app(url, configs=configs, **options)

    import dev

    return dev.main(["--backend", "factice", "--base", str(dossier / "test.db"), *reste])


if __name__ == "__main__":
    raise SystemExit(main())
