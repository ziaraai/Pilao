# « Ce qu'il manque » : guider l'entreprise pour compléter son dossier — conception

Date : 2026-11-15. Statut : à valider par Faycal (approche C et « Retirer cette phrase » choisis le 2026-11-15).

## 1. Intention

En réunion, Abdraouf (ENG PRO, l'utilisateur de référence) a vu l'analyse du DCE et le mémoire. Ce qui l'a inquiété, ce sont les **informations qui manquent** : les repères jaunes « [À COMPLÉTER : …] » éparpillés dans les chapitres, ceux du DC1/DC2, les vides du profil. Il ne sait pas combien il en reste, ni où saisir chaque donnée.

Il veut que compléter soit **le plus facile possible** : un manque sur le personnel ou le matériel doit le **guider**, en un clic, vers l'endroit où saisir cette donnée, et la donnée saisie doit servir partout, sans qu'on la lui redemande.

Succès : sur un dossier rédigé, Abdraouf voit d'un coup d'œil « il manque N informations », les remplit une par une depuis cette liste sans chercher dans les chapitres, et le mémoire se met à jour tout seul. Au dossier suivant, les données déjà saisies ne manquent plus.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Une liste unique « Ce qu'il manque » par dossier, qui regroupe les repères du mémoire et du DC1/DC2.
- Pour une donnée de l'entreprise : l'ajouter dans le profil **sans quitter le dossier**, puis Pilao complète les phrases concernées.
- Pour un détail propre à l'appel d'offres : répondre sur place.
- Prévenir les manques : avertir avant la rédaction quand le profil est vide sur le personnel, le matériel ou les références.

**Non-objectifs**
- Le cadre de réponse de l'acheteur (Q19) : chantier suivant, quand on aura un vrai fichier (Rillieux).
- Réécrire des chapitres entiers après un ajout (« Régénérer un chapitre » existe déjà).
- Ajouter des champs au profil, changer le contenu des DC1/DC2.

**Anti-objectifs** (échec même si « ça marche »)
- L'IA invente une donnée pour boucher un trou (règle absolue n° 1 du produit).
- Une complétion abîme le texte que l'utilisateur a retouché.
- La même information est demandée deux fois (dans deux chapitres, ou d'un dossier à l'autre).

## 3. Contraintes

- `CLAUDE.md` : jamais d'invention ; tout appel IA passe par `app/ai/llm.py`, est journalisé dans `ai_calls`, sortie validée par Pydantic (1 nouvelle tentative puis erreur) ; chaque prompt a un cas dans `tests/ai/` ; `org_id` partout ; migrations Alembic pour tout changement de schéma ; interface en français.
- Les chapitres restent en Markdown ; chaque changement de texte crée une révision (US-4.4 CA4) et rend la matrice de conformité « à revoir » (comportement actuel d'une modification).
- Le module « Réponse aux appels d'offres » (ADR-041) porte la fonction ; les actions IA payantes sont déclarées dans `app/modules.py` (ADR-043).
- Lisible sur téléphone, sans défilement horizontal (ADR-047).

## 4. Approches envisagées

| | Comment on remplit après le clic | Avantages | Inconvénients |
|---|---|---|---|
| A. Aller au bon endroit | Le bouton ouvre la page Profil à la bonne section ; retour au dossier ; « Mettre à jour le texte » réécrit le chapitre | Simple à construire ; réutilise les pages existantes | On quitte le dossier ; la réécriture du chapitre coûte des crédits et remplace le texte retouché |
| B. Répondre sur place | Une case à côté de chaque manque ; la réponse remplace le repère, sans IA | Rapide, gratuit, n'abîme rien | Réponses courtes seulement ; le profil n'est enrichi que si on coche une option |
| **C. Le mélange (retenu par Faycal)** | Donnée de l'entreprise : petite fenêtre avec le formulaire du profil, puis Pilao complète les phrases concernées ; détail de l'appel d'offres : réponse sur place | On reste dans le dossier ; le profil s'enrichit pour la suite ; le reste du texte ne bouge pas | Un petit appel IA par complétion ; plus de pièces à construire |

## 5. Ce qui a été décidé avec Faycal

1. **Approche C.**
2. La liste est **en haut de l'onglet Mémoire** ; l'Aperçu affiche une ligne « N informations à compléter » qui y mène.
3. Chaque manque montre une icône et un bouton selon son tiroir :

```
Ce qu'il manque : 5 informations
👥 Nombre d'agents affectés au site       [Ajouter dans Moyens humains]
🧰 Autolaveuse pour les grandes surfaces  [Ajouter dans Moyens matériels]
📜 Certification qualité                  [Ajouter dans Certifications]
✏️ Horaires d'intervention sur ce site    [ ______________ ] [OK]
🆔 SIRET (pour le DC1)                     [Compléter mon profil]
```

4. **Donnée de l'entreprise** (personnel, matériel, certification, référence, identité) : le bouton ouvre une **petite fenêtre** avec le même formulaire que le profil ; l'ajout est enregistré dans le profil ; Pilao réécrit ensuite **seulement la phrase concernée**, le reste du texte ne bouge pas.
5. **Détail propre à l'appel d'offres** : une case ; la réponse remplace le repère telle quelle, sans IA.
6. Un même manque présent dans plusieurs chapitres apparaît **une seule fois** ; sa réponse remplit tous les chapitres.
7. Les manques du **DC1/DC2** sont dans la même liste.
8. **Prévention** : avant la rédaction, si le profil n'a ni personnel ni matériel, un avertissement propose de les ajouter (ou d'importer l'Excel).
9. C'est l'IA qui indique à quel tiroir appartient chaque manque, avec des mots-clés en secours.
10. La complétion d'une phrase est une action dans l'administration, **0 crédit par défaut**, prix réglable.
11. Rien n'est inventé : si la donnée ajoutée ne suffit pas, le repère reste.
12. Quand l'entreprise n'a vraiment pas la chose demandée (pas de certification, pas de nacelle…) : un bouton **« Retirer cette phrase »** supprime la phrase qui contient le repère, sans IA ni crédit.

## 6. Conception détaillée

### 6.1 Les manques : d'où ils viennent, comment ils sont regroupés

- **Mémoire** : les repères `[À COMPLÉTER : …]` présents dans le texte actuel des chapitres de la dernière version du mémoire (regex `TO_COMPLETE` de `app/domain/memoir_checks.py`). La liste est **calculée à la lecture**, pas stockée : elle reflète toujours le texte, même après une modification à la main.
- **DC1/DC2** : la liste `to_complete` du dernier document généré de chaque type.
- **Regroupement** : clé = texte du repère normalisé (minuscules, sans accents ni ponctuation, espaces réduits). Deux repères de même clé, dans un ou plusieurs chapitres, font une seule ligne, qui indique les chapitres concernés (« dans 3 chapitres »).
- **Ordre** : les données de l'entreprise d'abord (elles servent aussi aux dossiers suivants), puis les détails de l'appel d'offres, puis le DC1/DC2 ; à l'intérieur, les manques présents dans le plus de chapitres en premier.

### 6.2 Le tiroir de chaque manque

Tiroirs : `staff` (Moyens humains), `equipment` (Moyens matériels), `certification` (Certifications), `reference` (Références), `identity` (Identité de l'entreprise : SIRET, adresse, représentant, chiffre d'affaires…), `tender` (propre à cet appel d'offres).

- Le prompt `generation_memoire_chapitre` renvoie désormais `to_complete` sous forme d'objets `{"text": "…", "kind": "staff|equipment|certification|reference|identity|tender"}` (nouvelle version du prompt). Le modèle de sortie accepte encore les simples chaînes (réponses anciennes). Le `kind` est rangé dans le signalement `to_complete` du chapitre (`flags`, JSONB : pas de migration).
- **Secours** : une fonction pure de mots-clés classe un repère sans `kind` connu (repère tapé à la main, chapitre retouché, ancien mémoire), par exemple « agent, personnel, effectif, encadrant, chef d'équipe » → `staff` ; « matériel, machine, autolaveuse, monobrosse, aspirateur, véhicule, nacelle » → `equipment` ; « certification, certificat, ISO, label, Qualipropre » → `certification` ; « référence, chantier similaire, client » → `reference` ; « SIRET, adresse du siège, représentant, chiffre d'affaires, effectif total » → `identity`. Sans correspondance : `tender` (on répond sur place, sans risque).
- Les manques du DC1/DC2 sont toujours `identity`.

### 6.3 Compléter une donnée de l'entreprise

1. Le bouton « Ajouter dans … » ouvre une fenêtre (`<dialog>` natif, comme les fenêtres de l'administration) qui contient le formulaire d'ajout de la section du profil : personnel, matériel, certification, référence ; pour `identity`, la carte Identité. Le rappel du repère est affiché en haut de la fenêtre. Un lien « Importer un fichier Excel » mène à l'import existant pour le personnel et le matériel.
2. L'enregistrement passe par les routes existantes du profil (`/profile/human-resources`, `/profile/equipment`, `/profile/certifications`, `/profile/references`, `/profile/company`).
3. Ensuite, pour un repère du mémoire, Pilao lance la **complétion** (§ 6.5) dans tous les chapitres qui contiennent ce repère. Pour un repère du DC1/DC2, Pilao régénère les DC1/DC2 concernés (gratuit, comme aujourd'hui).
4. La fenêtre permet aussi « J'ai déjà cette donnée dans mon profil » : la complétion est lancée sans ajout (cas d'une donnée saisie depuis la rédaction).

### 6.4 Répondre sur place (détail de l'appel d'offres)

- Une case et un bouton « OK ». La réponse remplace le repère, mot pour mot, dans tous les chapitres qui le contiennent. Pas d'IA, pas de crédit.
- C'est une modification par l'utilisateur : nouvelle révision d'origine `edited`, signalements recalculés comme après une modification (`flags_after_edit`), matrice « à revoir ».
- Tout repère, quel que soit son tiroir, peut aussi recevoir une réponse sur place (lien discret « Répondre directement »), pour ne jamais bloquer l'utilisateur.

### 6.4 bis Retirer cette phrase

- Sur chaque ligne, un lien « Retirer cette phrase » (avec confirmation : « La phrase sera supprimée de N chapitres ») supprime, dans tous les chapitres concernés, l'unité qui contient le repère (§ 6.5 : phrase, ligne de liste ; dans un tableau, la cellule est vidée sans supprimer la ligne). Un paragraphe ou un élément de liste devenu vide est supprimé.
- Pas d'IA, pas de crédit. Modification par l'utilisateur : révision `edited`, signalements recalculés, matrice « à revoir ». L'ancienne version reste dans l'historique du chapitre (on peut la restaurer).

### 6.5 La complétion par l'IA (une phrase)

- **Unité réécrite** : la phrase qui contient le repère ; dans une liste, la ligne ; dans un tableau, la cellule. Le serveur découpe, envoie cette unité au modèle avec le repère et les données du profil utiles à son tiroir, puis **recolle** la réponse à la place de l'unité. Le reste du chapitre est recopié tel quel par le serveur : le modèle ne peut pas le modifier.
- **Nouveau prompt** `prompts/completion_repere.md` (français) : « remplace le repère par la donnée fournie, garde le reste de la phrase ; n'utilise que `<company_data>` ; si la donnée ne suffit pas, renvoie la phrase inchangée et `filled: false` ». Sortie : `{"sentence": "…", "filled": true|false}`, validée par Pydantic (1 nouvelle tentative, puis erreur).
- **Garde-fous** : les contrôles existants des nombres et des noms (`check_chapter`) s'appliquent à la phrase produite contre les données de l'entreprise ; un nombre ou un nom absent des données est refusé (la phrase reste inchangée et le manque reste dans la liste). Une phrase où le repère n'a pas disparu compte comme `filled: false`.
- **Exécution** : en tâche de fond (worker), comme la régénération d'un chapitre ; la liste montre « Complétion en cours… » et se rafraîchit. Un chapitre en cours de rédaction est passé (il sera repris par la liste suivante).
- **Révision** : chaque chapitre modifié reçoit une nouvelle révision d'origine `generated`, avec la consigne « Complété : <repère> » et le modèle utilisé ; matrice « à revoir ». Le drapeau « retouché par l'utilisateur » d'un chapitre n'est pas changé.
- **Coût** : nouvelle action payante `marker_fill` « Compléter une information » (tâche IA `marker_fill`), 0 crédit par défaut, prix réglable dans l'administration ; débitée une fois par demande de complétion, remboursée automatiquement en cas d'échec (mécanisme existant). Journalisée dans `ai_calls`.
- **Si la donnée ne suffit pas** : le repère reste, et la ligne affiche « La donnée ajoutée ne suffit pas pour cette phrase : précisez-la ou répondez directement. »

### 6.6 Prévention avant la rédaction

Dans l'onglet Mémoire, tant que le mémoire n'est pas rédigé : si le profil n'a **aucun** moyen humain, **aucun** matériel ou **aucune** référence, une carte d'avertissement l'indique (« Votre profil n'a pas de matériel : le mémoire aura des trous ») avec, pour chaque vide, le bouton qui ouvre la même fenêtre d'ajout, et un lien vers l'import Excel. La rédaction reste possible sans les remplir.

### 6.7 Écrans

- **Onglet Mémoire** : en haut, un bloc à déplier « Ce qu'il manque » (ouvert par défaut s'il reste au moins un manque, avec le nombre dans son titre ; masqué s'il n'en reste aucun, remplacé par une ligne « Rien ne manque »). Chaque ligne : icône, texte du repère, « dans N chapitres » (lien vers le premier), bouton du tiroir ou case de réponse.
- **Aperçu** : une ligne de « À faire avant de répondre » : « N informations à compléter » → onglet Mémoire, bloc « Ce qu'il manque ».
- **Export** : la vérification avant export (déjà existante) garde la liste par chapitre et ajoute un lien « Compléter maintenant » vers le bloc.
- Téléphone : une ligne par manque, le bouton passe sous le texte.

### 6.8 API

- `GET /bids/{bid_id}/missing` → `{items: [{key, text, kind, sections: [{id, title}], documents: [kind]}], profile_gaps: {staff, equipment, references}, filling: [key]}` (filtré par `org_id`, module « Réponse »).
- `POST /bids/{bid_id}/missing/answer` `{key, answer}` → remplace le repère dans les chapitres concernés, renvoie la liste à jour.
- `POST /bids/{bid_id}/missing/remove` `{key}` → supprime la phrase qui contient le repère dans les chapitres concernés, renvoie la liste à jour.
- `POST /bids/{bid_id}/missing/fill` `{key}` → 202 ; lance la complétion (débit de l'action `marker_fill`).
- `POST /bids/{bid_id}/missing/regenerate-documents` → régénère les DC1/DC2 qui ont des manques (après une mise à jour de l'identité).
- `progress` de `GET /bids/{id}` (ADR-047) gagne `missing_count` pour l'Aperçu.

## 7. Cas limites

- Repère modifié à la main entre l'affichage et la réponse : le serveur repart du texte actuel ; si le repère n'y est plus, la ligne disparaît (réponse 200, liste à jour).
- Deux repères de textes proches mais différents (« nombre d'agents », « nombre d'agents affectés ») : deux lignes (pas de rapprochement flou, pour ne jamais mélanger deux questions).
- Mémoire en cours de rédaction : la liste est affichée mais les boutons de complétion sont grisés (« Rédaction en cours »).
- Pas de mémoire encore : seule la prévention (§ 6.6) et les manques du DC1/DC2 sont proposés.
- Plusieurs versions du mémoire : seule la dernière compte.

## 8. Laissé au constructeur

- Le découpage exact des phrases (ponctuation, abréviations courantes « M. », « n° »), tant que la phrase contenant le repère est isolée et que le reste est recopié à l'identique.
- La liste complète des mots-clés de secours (tests à l'appui).
- La mise en page de la fenêtre et des lignes, dans le style des briques existantes (`components/blocks.tsx`).
- Le contenu du cas de test du nouveau prompt (`tests/ai/`), et la mise à jour des documents : US dans `docs/04`, ADR-048 dans `docs/12`, `docs/08` (nouveau prompt), `docs/10` (feuille de route), parcours navigateur.

## 9. Choix faits par Claude (à vérifier en relisant)

- La liste est **calculée** à chaque lecture plutôt que stockée : toujours juste, pas de migration.
- Unité réécrite = phrase / ligne / cellule, recollée par le serveur : garantit que le reste du texte ne bouge pas.
- Pas de rapprochement « flou » des repères : regroupement par texte identique après normalisation.
- Liens « Répondre directement » et « Retirer cette phrase » sur toutes les lignes, pour que l'utilisateur ne soit jamais bloqué.
- Révision `generated` pour une complétion par l'IA, `edited` pour une réponse sur place (pas de nouvelle origine, pas de migration).
- Prévention sur trois vides : personnel, matériel, références (les certifications manquent souvent légitimement).
