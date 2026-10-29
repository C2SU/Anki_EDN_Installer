# Anki EDN Installer & Assistant de Configuration

Module central d'installation, d'orchestration et de gestion avancee pour l'ecosysteme Anki EDN (DFASM / ECN).

> [!CAUTION]
> **Avertissement - Version de Test (BETA)**
> Cet add-on est actuellement en version de test. Il applique des modifications automatiques aux preferences globales de profil Anki, orchestre des paquets filtres a grande echelle et injecte des mecanismes de protection sur les transactions locales.
> **Une sauvegarde complete de votre profil Anki (export .colpkg avec medias) est imperative avant toute manipulation.**

---

## Risques Encourus et Bonnes Pratiques

L'utilisation de ce module d'automatisation implique la prise en compte des points suivants :

1. **Reconfiguration automatique des options globales :** L'assistant met a jour vos reglages AnkiWeb (synchronisation a l'ouverture et fermeture, synchronisation automatique des medias) et AnkiCollab. Pensez a verifier ces options apres execution.
2. **Impact sur les files d'attente (Paquets Filtres) :** La creation et la regeneration de paquets filtres deplacent temporairement les cartes hors de leurs paquets d'origine. Si vous devez synchroniser votre profil ou desactiver l'add-on, utilisez prealablement le raccourci `Ctrl + Alt + E` pour vider tous les paquets filtres et restituer les cartes.
3. **Protection des champs personnalises :** La protection contre l'ecrasement s'appuie sur les noms de champs definis dans les modeles de notes. Si vous renommez manuellement ces champs, mettez a jour la configuration dans les reglages EDN.
4. **Interactions entre extensions :** L'add-on intercepte et securise plusieurs composants de l'interface (WebEngine, boites de dialogue). Des incompatibilites mineures peuvent survenir avec d'autres extensions modifiant les menus ou l'interface d'Anki.

---

## Fonctionnalites Principales

- **Assistant de Configuration en 1 Clic :** Diagnostic automatique de l'installation et reglage instantane des options de synchronisation critiques AnkiCollab et AnkiWeb.
- **Reparation des NID (Linked Cards) :** Analyse et resolution des identifiants uniques de notes pour maintenir l'integrite des renvois croises entre fiches medicales.
- **Protection Active des Champs Utilisateur :** Empeche les fusions collaboratives d'effacer vos annotations et notes personnelles.
- **Generateur Hierarchique de Paquets Filtres :** Creation automatisee de paquets filtres organises par matiere et par item (367 items EDN couverts).
- **Raccourcis Clavier Dedies :**
  - `Ctrl + Alt + F` : Ouvrir l'interface du generateur de paquets filtres.
  - `Ctrl + Alt + R` : Lancer la regeneration complete des paquets filtres EDN.
  - `Ctrl + Alt + E` : Vider integralement tous les paquets filtres EDN.
- **Menu Centralise EDN :** Acces rapide et sobre a l'ensemble des modules, guides et preferences de la suite medicale.
- **Gardes-Fous de Stabilite :** Mesures de securite logicielles pour prevenir les plantages lors des manipulations multi-fenetres.

---

## Utilisation

1. Ouvrez Anki, puis rendez-vous dans le menu **EDN > Assistant de configuration EDN...**
2. Cliquez sur les boutons de verification / configuration pour initialiser vos parametres globaux et securiser vos notes.
3. Pour reviser un sous-ensemble precis du programme, ouvrez le generateur via **EDN > Paquets Filtrés > Générateur de paquets filtrés...** (`Ctrl + Alt + F`).
4. Avant chaque synchronisation importante, assurez-vous de vider les paquets filtres via `Ctrl + Alt + E`.

---

## Compatibilite

- Anki 23.10+, Anki 24.x, Anki 25.x+
- PyQt6 / Qt6
- Fonctionne en synergie avec la suite officielle : Lier les cartes, EDN Stats, NID, AnkiCollab
