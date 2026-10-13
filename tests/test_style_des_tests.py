"""Les tests ne s'accrochent pas à la phrase exacte (recommandation R3).

Une assertion qui compare une longue phrase d'interface casse à chaque
reformulation : on finit par modifier les tests à tout propos, et un test
modifié trop facilement ne garantit plus rien. Les tests vérifient donc un
élément, un rôle ou un mot-clé — au plus 40 caractères de texte.

Exceptions (liste blanche ci-dessous) : les messages qui PORTENT une contrainte
dure de CLAUDE.md, dont la formulation fait partie de la garantie ; et ce qui
n'est pas une phrase d'interface (SQL, adresse, balisage, donnée).
"""

from __future__ import annotations

import ast
from pathlib import Path

DOSSIER = Path(__file__).parent
LONGUEUR_MAX = 40

# (fichier, début de la chaîne) -> raison. Un début suffit à reconnaître la chaîne.
LISTE_BLANCHE: dict[tuple[str, str], str] = {
    ("test_inventaire_cli.py", "Rossignol-Trapet"): "donnée : les valeurs d'une bouteille, pas une phrase",
    ("test_inventaires.py", "1_etiquette.jpg"): "donnée : des noms de fichiers",
    ("test_regroupement.py", "Première description."): "donnée : deux descriptions saisies, réunies à l'export",
}

NON_PHRASE = ("SELECT ", "select ", "INSERT ", "/app/", "/inventaires/", "<", "http", "\\")


def chaines_longues(fichier: Path) -> list[tuple[int, str]]:
    """Les constantes texte de plus de LONGUEUR_MAX caractères comparées dans un
    `assert`, passées à `match=`, ou en 4e argument de `verifier_erreur`."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    trouvees: list[tuple[int, str]] = []

    def relever(noeud: ast.AST) -> None:
        for sous in ast.walk(noeud):
            if isinstance(sous, ast.Constant) and isinstance(sous.value, str) and len(sous.value) > LONGUEUR_MAX:
                trouvees.append((sous.lineno, sous.value))

    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assert):
            relever(noeud.test)
        elif isinstance(noeud, ast.Call):
            for mot in noeud.keywords:
                if mot.arg == "match":
                    relever(mot.value)
            nom = getattr(noeud.func, "id", None) or getattr(noeud.func, "attr", None)
            if nom == "verifier_erreur" and len(noeud.args) >= 4:
                relever(noeud.args[3])
    return trouvees


def est_exemptee(fichier: str, chaine: str) -> bool:
    if chaine.lstrip().startswith(NON_PHRASE) or " FROM " in chaine or '="' in chaine:  # SQL, balisage
        return True
    return any(fichier == f and chaine.startswith(debut) for f, debut in LISTE_BLANCHE)


def test_aucune_assertion_sur_une_longue_phrase():
    fautives = [
        f"{fichier.name}:{ligne} « {chaine[:70]} »"
        for fichier in sorted(DOSSIER.glob("test_*.py"))
        if fichier.name != Path(__file__).name
        for ligne, chaine in chaines_longues(fichier)
        if not est_exemptee(fichier.name, chaine)
    ]
    assert not fautives, (
        f"{len(fautives)} assertion(s) sur une phrase de plus de {LONGUEUR_MAX} caractères : vérifier un "
        f"mot-clé ou l'élément, ou justifier l'exception dans LISTE_BLANCHE.\n" + "\n".join(fautives)
    )
