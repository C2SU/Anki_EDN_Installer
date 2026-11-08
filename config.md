# Configuration — Anki EDN Installer & Setup

Cet add-on installe, configure et maintient l'environnement complet du paquet collaboratif Anki EDN (greffons requis, abonnement AnkiCollab, préréglage FSRS, réparation des NID, paquets filtrés et protection des champs).

## Paramètres d'installation et du paquet

- `deck_name` (`chaîne`, par défaut `"Anki EDN"`) : nom du paquet principal AnkiCollab dans votre collection Anki.
- `share_code` (`chaîne`, par défaut `"mango-may-georgia-eleven-moon-orange"`) : code de partage officiel AnkiCollab copié dans le presse-papiers lors de l'étape d'abonnement.
- `addons` (`liste d'entiers`, par défaut `[1957538407, 1052724801, 1762336370, 1201122026, 445658251]`) : identifiants AnkiWeb des greffons requis à vérifier et installer automatiquement.
- `preset_name` (`chaîne`, par défaut `"Anki EDN"`) : nom du préréglage d'options de révision créé et assigné aux paquets EDN.

## Options du préréglage de révision (`options`)

- `options.new_per_day` (`entier`, par défaut `30`) : nombre maximal de nouvelles cartes par jour appliqué au préréglage `Anki EDN` (valeurs recommandées : 25 à 50).
- `options.reviews_per_day` (`entier`, par défaut `9999`) : plafond quotidien de révisions pour ne masquer aucune carte due.
- `options.desired_retention` (`nombre décimal`, par défaut `0.88`) : taux de rétention cible FSRS (valeurs admissibles : `0.70` à `0.97`, recommandé : `0.88`).
- `options.leech_threshold` (`entier`, par défaut `20`) : seuil d'échecs avant qu'une carte soit marquée comme sangsue (*leech*).

## Modules fonctionnels (`modules`)

- `modules.fsrs_checker` (`booléen`, par défaut `true`) : active la surveillance périodique de l'optimisation des paramètres FSRS au démarrage d'Anki (rappel standard toutes les 3 semaines, ou 1 semaine si les paramètres étaient déjà optimaux lors du dernier calcul).
- `modules.history` (`booléen`, par défaut `true`) : active la journalisation locale des opérations de l'assistant EDN.
