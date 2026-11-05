# Configuration — Assistant & Installateur EDN

Ce module centralise la configuration des fonctionnalités pédagogiques, la gestion des modèles de cartes et l'intégration du standard de révision EDN.

## Modules fonctionnels (`modules`)

- `modules.fsrs_checker` (booléen, par défaut `true`) : active la vérification périodique de l'optimisation des paramètres FSRS au démarrage d'Anki. Lorsque ce module est actif, un rappel sobre s'affiche si vos paramètres d'espacement méritent un recalcul.
- `modules.history` (booléen, par défaut `true`) : active l'historique et la journalisation locale des interventions de l'assistant EDN.
