# Anki EDN Installer

Extension tout-en-un pour installer, configurer et utiliser le deck **Anki EDN** au quotidien sans réglage complexe.

> [!CAUTION]
> **Sauvegarde préalable obligatoire** : Avant toute configuration initiale ou modification massive, réalisez une sauvegarde complète de votre collection (`Fichier > Exporter > Collection Anki (.colpkg)` en cochant l'inclusion des médias).

---

## Bonnes Pratiques

- **Synchronisation et profil** : L'assistant applique la configuration recommandée (FSRS, limites quotidiennes, abonnement AnkiCollab) à votre profil. Vérifiez vos réglages avant de confirmer.
- **Paquets filtrés** : Videz toujours vos paquets filtrés avant de synchroniser sur AnkiWeb ou de désinstaller l'extension (`Ctrl + Alt + E`).
- **Champs personnels** : Si vous avez modifié les noms de champs protégés dans AnkiCollab, vérifiez la liste des champs protégés dans la configuration de l'extension.
- **Compatibilité** : En cas de conflit mineur avec une autre extension (raccourcis ou thèmes), testez l'extension seule ou vérifiez les raccourcis configurés.

---

## Fonctionnalités Principales

### 1. Assistant d'Installation Guidé
Accessible depuis le menu **Anki EDN**, l'assistant configure votre environnement étape par étape :
- **Synchronisation AnkiWeb préalable** pour sécuriser votre collection avant les réglages.
- **Installation en un clic** des extensions recommandées (`1957538407`, `1052724801`, `2040501954`, `1674438508`, `445658251`) et du gestionnaire de raccourcis (`353547840`).
- **Abonnement automatique AnkiCollab** dès la connexion au compte.
- **Préréglage `Anki EDN` prêt à l'emploi** : 50 nouvelles cartes/jour, révisions illimitées, FSRS activé à 88 % de rétention et seuil sangsue fixé à 12 échecs avec suspension automatique.

### 2. Déblocage Progressif d'un Item Étudié
Disponible directement sur l'écran d'accueil d'Anki, dans le générateur de paquets filtrés ou via `Ctrl + Alt + U` :
- **Recherche rapide** par numéro ou intitulé d'item (ex. `145` ou `Endocardite`).
- **3 paliers de déblocage** :
  - *Essentiel (Cartes Sommaires + Rang A)* : pour démarrer sans se noyer.
  - *Rang A complet* : l'ensemble des connaissances de rang A.
  - *Item complet (Rang A + Rang B)* : la totalité de l'item.
- **Tri « Scaffolding » et apprentissage immédiat** : ordonne automatiquement les nouvelles cartes débloquées (*Sommaire -> Définitions & Sémiologie -> Examens complémentaires -> Thérapeutique & Scores*) avec option de mise en file *Learn Now* dans le bon ordre.

### 3. Générateur Hiérarchique de Paquets Filtrés & ECOS
Accessible via `Ctrl + Alt + F` ou le bouton **Paquets Filtrés EDN** :
- Navigation structurée dans les **367 items EDN** par spécialité et par item, plus un onglet dédié aux **ECOS (`EDN::SDD`)**.
- **Actions rapides par item** : *Voir dans l'explorateur*, *Dé-suspendre rangs A* et *Dé-suspendre tout*.
- Création automatique de paquets filtrés combinant cartes à réviser et nouvelles cartes selon vos filtres.

### 4. Intégrité, Protection et Outils Quotidiens
- **Protection active** : aucune carte n'est dé-suspendue automatiquement au démarrage, vos champs personnels restent protégés lors des mises à jour collaboratives, et les identifiants des cartes liées sont vérifiés automatiquement.
- **Aide à l'édition et personnalisation** : insertion rapide de symboles médicaux et de puces dans l'éditeur, infobulles visuelles natives sur les symboles des cartes, et réglages d'affichage dédiés.
- **Suivi FSRS** : rappel mensuel d'optimisation de vos paramètres FSRS selon votre rythme de révision.

---

## Raccourcis Clavier

| Raccourci | Action |
| :--- | :--- |
| `Ctrl + Alt + U` | Débloquer un item étudié |
| `Ctrl + Alt + F` | Ouvrir le générateur de paquets filtrés EDN |
| `Ctrl + Alt + R` | Rafraîchir les paquets filtrés |
| `Ctrl + Alt + E` | Vider tous les paquets filtrés |

---

## Démarrage Rapide

1. Ouvrez Anki et cliquez sur le menu **Anki EDN** dans la barre supérieure.
2. Lancez l'assistant d'installation et suivez les étapes à l'écran.
3. Utilisez **Débloquer un item étudié** (`Ctrl + Alt + U`) après chaque item révisé pour libérer les cartes progressivement.
4. Appuyez sur `Ctrl + Alt + F` pour réviser par spécialité, par item ou préparer les ECOS.

---

## Compatibilité

- **Anki** : 23.10+, 24.x et 25.x+ (Qt6).
- **Suite Anki EDN** : conçu pour fonctionner de concert avec *Lier les cartes*, *EDN Stats* et *AnkiCollab*.
