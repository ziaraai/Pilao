# 13 — Questions ouvertes

| # | Question | Qui | Statut |
|---|---|---|---|
| Q1 | Recevoir le plan type des mémoires et 3 vrais DCE d'Abdraouf | Abdraouf | En attente |
| Q2 | Les acheteurs acceptent-ils l'attestation RNE à la place du Kbis ? | Faycal / Abdraouf | À vérifier |
| Q3 | Prix de l'abonnement et formules | Faycal + Abdraouf | Après les tests |
| Q4 | Nom définitif « Pilao » : marque INPI (classes 9, 35, 42) et domaines .fr/.com | Faycal | À vérifier |
| Q5 | Société qui porte le projet et forme du partenariat (associés / prestation / mixte) | Faycal + Abdraouf | À décider |
| Q6 | Quelles plateformes d'acheteurs Abdraouf utilise le plus (priorité V2 du téléchargement automatique) ? | Abdraouf | À demander |
| Q7 | Hébergeur de production (Scaleway, OVHcloud…). Pilote : VPS Contabo géré par Plesk, `app.pilao.pro` (ADR-033) ; vérifier que la région du VPS est dans l'UE | Faycal | Pilote décidé, production à décider |
| Q8 | Format de mise en page Word attendu (charte, page de garde). Par défaut : page de garde avec logo, sommaire, titres à la couleur de l'entreprise, Arial (ADR-022) | Abdraouf | À demander |
| Q9 | Vérifier l'API Recherche d'entreprises sur un appel réel (domaine `recherche-entreprises.api.gouv.fr` à autoriser dans le réseau de l'environnement de développement) | Faycal | À faire |
| Q10 | Politique de blocage des connexions : aujourd'hui 5 échecs en 15 min bloquent l'e-mail, même pour son vrai titulaire, et un tiers peut bloquer un compte connu. Remettre le compteur à zéro après une connexion réussie ? Bloquer par couple e-mail + IP ? Ajouter un CAPTCHA ? | Faycal | À décider |
| Q11 | Fournisseur d'e-mails transactionnels (UE). Pilote : messagerie Plesk du serveur (`noreply@pilao.pro`, ADR-032) ; pour la production, un service à bonne délivrabilité (Brevo, Scaleway TEM) : il suffit de changer `SMTP_HOST` | Faycal | Pilote décidé |
| Q12 | DC1 et DC2 générés sur la trame des formulaires de la DAJ (rubriques, articles L. 2141-1 à L. 2141-5, L. 2141-7 à L. 2141-11 du code de la commande publique et L. 5212-1 à L. 5212-11 du code du travail) : à comparer aux modèles officiels en vigueur sur economie.gouv.fr, ainsi que la mention « annexe 7 » de la convention collective de la propreté dans la trame de planning | Faycal / Abdraouf | À vérifier |
| Q13 | Éditeur : barre de mise en forme et aperçu sur un texte Markdown (ADR-020). Suffisant pour une secrétaire, ou faut-il un éditeur visuel (WYSIWYG) ? | Abdraouf | À tester |
| Q14 | Ouvrir l'accès réseau de l'environnement cloud à `boamp-datadila.opendatasoft.com`, `api.ted.europa.eu` et `recherche-entreprises.api.gouv.fr` (débloque P1-INT-01, P3-01, P3-02, P3-INT-02 et Q9). La proposition automatique n'a pas pu s'afficher dans l'application mobile : la refaire depuis claude.ai sur ordinateur, ou ajouter ces hôtes dans les réglages de l'environnement | Faycal | À faire |
| Q15 | Durées de conservation : 30 jours avant l'effacement après la demande (ADR-026), et durée de conservation des sauvegardes chez l'hébergeur, à écrire dans la politique de confidentialité | Faycal | À décider |
| Q16 | Relecture juridique des pages légales (mentions, confidentialité, CGU, accord de traitement), garanties du transfert vers OpenRouter (clauses contractuelles types ou Data Privacy Framework, et contrat de sous-traitance d'OpenRouter), plafond de responsabilité et tribunal compétent. Les éléments à fournir sont dans `apps/web/lib/legal.ts` | Faycal + juriste | À faire |
