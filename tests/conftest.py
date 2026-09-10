"""Rend le paquet `src` importable quand pytest est lancé depuis n'importe où.

On insère la RACINE du projet, jamais `src/` lui-même : `src/io` masquerait le
module `io` de la stdlib.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
