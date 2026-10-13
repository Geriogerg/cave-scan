#!/bin/bash
# La suite pytest. Les tests ont leur propre configuration figée
# (tests/fixtures/maison_test.json, recommandation R2) : modifier celle de
# l'application (config/maisons/) ne les touche plus. Arguments : ceux de pytest.
#
#   bash docs/tests/tests.sh                    (toute la suite)
#   bash docs/tests/tests.sh tests/test_pages.py -k quantite
set -u
cd "$(dirname "$0")/../.."
python -m pytest -q -p no:cacheprovider "$@"
