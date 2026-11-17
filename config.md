# Configuration — Anki EDN Installer & Setup

Cet add-on installe, configure et maintient l'environnement complet du paquet collaboratif Anki EDN (greffons requis, abonnement AnkiCollab automatique dès la connexion, préréglage FSRS, réparation des NID, paquets filtrés, infobulles symboles et protection des champs).

## Paramètres d'installation et du paquet

- `deck_name` (`chaîne`, par défaut `"Anki EDN"`) : nom du paquet principal AnkiCollab dans votre collection Anki.
- `share_code` (`chaîne`, par défaut `"mango-may-georgia-eleven-moon-orange"`) : code de partage officiel AnkiCollab utilisé pour abonner automatiquement le profil après connexion (et copié dans le presse-papiers en secours).
- `addons` (`liste d'entiers`, par défaut `[1957538407, 1052724801, 2040501954, 1674438508, 445658251]`) : identifiants AnkiWeb des greffons requis à vérifier et installer automatiquement (AnkiCollab, BetterSearch, Symbols As You Type, EDN Stat, Lier les cartes).
- `preset_name` (`chaîne`, par défaut `"Anki EDN"`) : nom du préréglage d'options de révision créé et assigné aux paquets EDN.

## Options du préréglage de révision (`options`)

- `options.new_per_day` (`entier`, par défaut `50`) : plafond quotidien de nouvelles cartes par jour appliqué au préréglage `Anki EDN`.
- `options.reviews_per_day` (`entier`, par défaut `9999`) : plafond quotidien de révisions pour ne masquer aucune carte due.
- `options.desired_retention` (`nombre décimal`, par défaut `0.88`) : taux de rétention cible FSRS (valeurs admissibles : `0.70` à `0.97`, recommandé : `0.88`).
- `options.leech_threshold` (`entier`, par défaut `12`) : seuil d'échecs avant qu'une carte soit classée comme sangsue (*leech*), avec action par défaut réglée sur **Suspendre** (`leechAction = 0`).

## Modules fonctionnels (`modules`) et préférences cartes (`edn_card_prefs.json`)

- `modules.fsrs_checker` (`booléen`, par défaut `true`) : active la surveillance périodique de l'optimisation des paramètres FSRS au démarrage d'Anki (rappel standard toutes les 3 semaines, ou 1 semaine si les paramètres étaient déjà optimaux lors du dernier calcul).
- `modules.filtered_decks` (`booléen`, par défaut `true`) : active le générateur de paquets filtrés hiérarchiques et l'action « Débloquer un item étudié... » (`Ctrl + Alt + U`, également accessible depuis l'écran d'accueil d'Anki et le générateur de paquets filtrés avec 3 modes progressifs et tri Scaffolding natif).
- `shortcuts.unlock_studied_item` (`chaîne`, par défaut `"Ctrl+Alt+U"`) : raccourci clavier global configuré dans `Paramètres EDN` pour ouvrir l'outil « Débloquer un item étudié ».
- `modules.history` (`booléen`, par défaut `true`) : active la journalisation locale des opérations de l'assistant EDN.
- `showSymbolTooltips` (`booléen`, par défaut `true`, modifiable dans `Paramètres EDN > Réglages Cartes`) : entoure les symboles et abréviations médicales (Léo Picat) d'une infobulle native explicative au survol pendant la révision.
- `showTombeStars` (`booléen`, par défaut `true`, modifiable dans `Paramètres EDN > Réglages Cartes`) : affiche en haut à gauche des cartes (recto et verso) sur ordinateur autant d'étoiles que d'occurrences d'annales où la carte est tombée (tag `tombé::X-fois`, maximum 5 ; sources détaillées dans le champ `References` / `Références`).
- `showTombeStarsMobile` (`booléen`, par défaut `true`, modifiable dans `Paramètres EDN > Réglages Cartes`) : active l'affichage des étoiles « tombé » lors des révisions sur mobile.
