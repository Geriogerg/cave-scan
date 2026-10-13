#!/bin/bash
# La suite pytest sur la config de test COMMITÉE, même si config/maisons/
# maison_test.json a une modification locale (enregistrée depuis la page
# Configuration) : elle est mise de côté le temps des tests, puis remise
# exactement, même en cas d'interruption. Arguments : ceux de pytest.
#
#   bash docs/tests/tests.sh                    (toute la suite)
#   bash docs/tests/tests.sh tests/test_pages.py -k quantite
set -u
cd "$(dirname "$0")/../.."
CONFIG=config/maisons/maison_test.json
SAUVEGARDE=$(mktemp)
cp "$CONFIG" "$SAUVEGARDE"
remettre() { cp "$SAUVEGARDE" "$CONFIG"; rm -f "$SAUVEGARDE"; }
trap remettre EXIT
git show HEAD:"$CONFIG" > "$CONFIG"
python -m pytest -q -p no:cacheprovider "$@"
