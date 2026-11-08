# Anki EDN Installer & Assistant de Configuration

Module central d'installation, d'orchestration et de gestion avancee pour l'ecosysteme Anki EDN (DFASM / ECN).

> [!CAUTION]
> **Avertissement - Version de Test (BETA)**
> Cet add-on applique des modifications automatiques aux preferences globales de profil Anki, orchestre des paquets filtres a grande echelle et injecte des mecanismes de protection sur les transactions locales.
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

- **Assistant d'Installation et de Configuration Unifié :**
  - Parcours guidé en 3 étapes dynamiques : installation automatique des extensions requises, abonnement AnkiCollab surveillé en direct, puis application des réglages en un clic.
  - Synchronisation AnkiWeb préalable pour éviter tout conflit appareil / AnkiWeb.
  - Détection et téléchargement en 1 clic des extensions requises (AnkiCollab `1957538407`, BetterSearch `1052724801`, Symboles `1762336370`, Statistiques EDN `1201122026`, Lier les cartes `445658251`).
  - Guidage d'abonnement au paquet AnkiCollab avec copie automatique de la clé de partage et détection en temps réel de l'arrivée du paquet `Anki EDN`.
  - Application du préréglage de révision recommandé (`Anki EDN` : 30 nouvelles cartes/jour, 9999 révisions/jour, FSRS 88 %, seuil sangsue 20 échecs) et suspension initiale intelligente (distinction automatique entre nouveau profil et progression existante).
- **Intégrité et Respect des Révisions de l'Étudiant :**
  - Aucune désuspension intempestive de cartes au démarrage : l'étudiant reste maître du déblocage progressif de ses items et de ses rangs (A/B).
  - Suppression des popups intrusifs de vérification automatique au lancement.
- **Reparation des NID (Linked Cards) :** Analyse et resolution des identifiants uniques de notes pour maintenir l'integrite des renvois croises entre fiches medicales.
- **Protection Active des Champs Utilisateur :** Empeche les fusions collaboratives d'ecraser vos annotations et notes personnelles (`Notes personnelles`, `Moyens mnémotechniques`), avec empreinte locale de securite.
- **Generateur Hierarchique de Paquets Filtres & Deck ECOS :** Creation automatisee de paquets filtres organises par specialite et par item (367 items EDN couverts), ainsi que generation dediee du paquet filtré ECOS regroupant l'ensemble des Situations de Depart (balises EDN::SDD).
- **Actions Rapides sur Paquets Filtres (Page d'aperçu) :** Encart d'actions directes integre a chaque paquet filtre feuille :
  - *Voir dans l'explorateur* : ouvre l'explorateur cible sur toutes les cartes de l'item / volet (actives et suspendues).
  - *Dé-suspendre rangs A* : reactive en 1 clic les cartes de rang A restantes (avec compteur dynamique) et regenere le paquet.
  - *Dé-suspendre tout* : reactive toutes les cartes suspendues de l'item et regenere le paquet.
- **Outils d'Edition et de Revision Medicale :**
  - **Guide Rédactionnel & Puces :** Normalisation typographique medicale et insertion de listes hierarchiques.
  - **Importateur de Symboles :** Raccourcis de remplacement automatique (`->`, `>=`, `+-`, etc.) dans l'editeur.
  - **Ajout d'Etiquette a la Volee (`Shift + T`) :** Edition rapide des tags de la note en cours de revision.
  - **Reglages Visuels des Cartes :** Personnalisation de la police, de la taille et de l'affichage des bandeaux sur les cartes EDN.
  - **Rappel d'Optimisation FSRS :** Suivi mensuel de l'optimisation des parametres FSRS.
- **Raccourcis Clavier Dedies & Actions :**
  - `Ctrl + Alt + F` : Ouvrir l'interface du generateur de paquets filtres.
  - `Génération du Deck ECOS (SDD)` : Bouton dédié et sélection au contact des matières dans le générateur de paquets filtrés.
  - `Ctrl + Alt + R` : Lancer la regeneration complete des paquets filtres EDN.
  - `Ctrl + Alt + E` : Vider integralement tous les paquets filtres EDN.
  - `Shift + T` : Ouvrir l'outil d'ajout d'etiquette a la volee pendant la revision.

---

## Utilisation

1. Ouvrez Anki, puis rendez-vous dans le menu **Anki EDN > Rétablir les réglages du tuto...** pour lancer l'assistant d'installation et de diagnostic.
2. Pour verifier les cartes ajoutees ou modifiees apres une synchronisation AnkiCollab, cliquez sur **Anki EDN > Vérifier les nouveautés du paquet**.
3. Pour reviser un sous-ensemble precis du programme, ouvrez le generateur via **Anki EDN > Paquets Filtrés > Générateur de paquets filtrés...** (`Ctrl + Alt + F`).
4. Pour configurer les modules, les champs proteges, les styles de cartes ou les raccourcis, ouvrez **Anki EDN > Paramètres EDN...**.

---

## Compatibilite

- Anki 23.10+, Anki 24.x, Anki 25.x+
- PyQt6 / Qt6
- Fonctionne en synergie avec la suite officielle : Lier les cartes, EDN Stats, NID, AnkiCollab
