import type { Metadata } from "next";
import Link from "next/link";

import { Fact, LegalPage, List, Section } from "@/components/legal";
import { LEGAL, RETENTION, fact } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Politique de confidentialité — Pilao",
};

export default function Privacy() {
  const publisher = fact(LEGAL.publisher.name, "raison sociale de l'éditeur");
  const contact = fact(LEGAL.publisher.email, "adresse e-mail de contact");
  return (
    <LegalPage
      title="Politique de confidentialité"
      intro="Vos mémoires techniques, vos prix et vos références sont des secrets d'affaires. Cette page dit précisément ce que Pilao fait de vos données, et ce qu'il n'en fait jamais."
    >
      <Section title="1. Qui est responsable de quoi">
        <List>
          <li>
            <strong>Les comptes des utilisateurs</strong> (nom, e-mail,
            connexions) : <Fact>{publisher}</Fact>, éditeur de Pilao, en est le{" "}
            <strong>responsable de traitement</strong>.
          </li>
          <li>
            <strong>Ce que votre entreprise dépose ou saisit</strong> (profil,
            moyens humains, références, attestations, DCE, mémoires, documents
            produits) : votre entreprise en est responsable ; Pilao agit comme{" "}
            <strong>sous-traitant</strong>, uniquement pour vous rendre le
            service, selon l&apos;
            <Link href="/accord-de-traitement" className="underline">
              accord de traitement des données
            </Link>
            .
          </li>
        </List>
      </Section>

      <Section title="2. Les données des comptes, et pourquoi">
        <List>
          <li>
            <strong>Créer et gérer votre compte</strong> : nom, e-mail
            professionnel, rôle, mot de passe (jamais stocké en clair : seule
            une empreinte Argon2id est conservée), acceptation des conditions
            (date et version). Base légale : le contrat.
          </li>
          <li>
            <strong>Sécuriser l&apos;accès</strong> : sessions de connexion
            (navigateur, adresse IP), tentatives de connexion (e-mail, adresse
            IP, date, réussite), journal des actions importantes (génération,
            export, suppression). Base légale : intérêt légitime à protéger le
            service et vos données.
          </li>
          <li>
            <strong>Vous écrire</strong> : confirmation de l&apos;adresse,
            alertes d&apos;annonces et d&apos;attestations, suppression
            programmée. Base légale : le contrat. Aucun e-mail publicitaire.
          </li>
          <li>
            <strong>Recevoir vos avis</strong> : quand vous utilisez « Votre
            avis », votre message, la page d&apos;où il part et votre e-mail
            sont transmis à l&apos;équipe Pilao pour améliorer le service. Si
            vous les renseignez, le temps passé sur un dossier et le temps
            habituel servent à mesurer le temps gagné. Base légale : intérêt
            légitime à améliorer le service. Ces éléments sont effacés avec
            l&apos;entreprise.
          </li>
          <li>
            <strong>Préremplir votre entreprise</strong> : à partir du SIRET,
            Pilao interroge l&apos;annuaire public des entreprises (raison
            sociale, adresse, activité).
          </li>
        </List>
      </Section>

      <Section title="3. L'intelligence artificielle">
        <List>
          <li>
            Pilao utilise des modèles d&apos;IA pour lire les DCE et rédiger les
            brouillons. Les extraits nécessaires (DCE, données de votre profil,
            passages de vos anciens mémoires) leur sont envoyés au moment de la
            tâche.
          </li>
          <li>
            <strong>Vos données n&apos;entraînent aucun modèle.</strong> Les
            appels passent par OpenRouter, avec une option qui écarte tout
            fournisseur d&apos;IA susceptible de conserver les requêtes ou de
            s&apos;en servir pour entraîner ses modèles. Cette option est
            appliquée par le code de Pilao à chaque appel.
          </li>
          <li>
            <strong>
              Les données d&apos;une entreprise ne servent jamais pour une autre
            </strong>{" "}
            : la recherche dans les documents et la rédaction sont isolées par
            entreprise.
          </li>
          <li>
            Pilao garde un journal de chaque appel (tâche, modèle, nombre de
            jetons, coût, durée), sans le contenu de vos documents.
          </li>
        </List>
      </Section>

      <Section title="4. Qui reçoit les données (sous-traitants)">
        <List>
          <li>
            Hébergement des serveurs, de la base et des fichiers, dans
            l&apos;Union européenne :{" "}
            <Fact>{fact(LEGAL.host.name, "hébergeur")}</Fact>.
          </li>
          <li>
            Modèles d&apos;IA : OpenRouter, Inc. (États-Unis), qui transmet la
            requête au fournisseur du modèle choisi (Anthropic, Google,
            Mistral…), selon l&apos;option ci-dessus. Ce transfert hors de
            l&apos;Union européenne est encadré par{" "}
            <Fact>
              {
                "[À COMPLÉTER : garanties du transfert — clauses contractuelles types de la Commission européenne ou adhésion au Data Privacy Framework]"
              }
            </Fact>
            .
          </li>
          <li>
            Plateformes des acheteurs publics (PLACE et plateformes Atexo) : à
            votre demande, Pilao transmet la raison sociale, le SIRET et le
            contact de votre entreprise à la plateforme de l&apos;acheteur pour
            retirer le DCE en votre nom.
          </li>
          <li>
            Envoi des e-mails :{" "}
            <Fact>
              {fact(
                LEGAL.emailProvider,
                "fournisseur d'e-mails transactionnels",
              )}
            </Fact>
            .
          </li>
        </List>
        <p>
          Aucune donnée n&apos;est vendue, louée ou utilisée à des fins
          publicitaires. La liste à jour des sous-traitants figure dans
          l&apos;accord de traitement des données.
        </p>
      </Section>

      <Section title="5. Combien de temps">
        <List>
          <li>
            Le compte et les données de l&apos;entreprise : tant que le compte
            existe. Un administrateur peut demander l&apos;effacement complet
            (Profil &gt; Vos données) : il a lieu {RETENTION.deletionGraceDays}{" "}
            jours plus tard, délai pendant lequel il peut l&apos;annuler. Tout
            est alors effacé, fichiers et index de recherche compris ; il ne
            reste qu&apos;un reçu sans donnée personnelle (dates et nombre
            d&apos;éléments effacés).
          </li>
          <li>
            Les sessions de connexion : {RETENTION.sessionDays} jours au plus,
            et effacées dès la déconnexion.
          </li>
          <li>
            Les liens de confirmation d&apos;e-mail : valables{" "}
            {RETENTION.verifyLinkHours} heures, effacés dès leur utilisation ou
            leur expiration.
          </li>
          <li>
            Les tentatives de connexion : {RETENTION.loginAttemptsDays} jours.
          </li>
          <li>
            Les sauvegardes :{" "}
            <Fact>
              {fact(
                LEGAL.backupRetention,
                "durée de conservation des sauvegardes",
              )}
            </Fact>
            . Une entreprise effacée disparaît des sauvegardes à leur
            expiration.
          </li>
        </List>
      </Section>

      <Section title="6. Cookies">
        <p>
          Pilao dépose un seul cookie, <code>pilao_session</code>, qui vous
          garde connecté ({RETENTION.sessionDays} jours au plus). Il est
          strictement nécessaire au service et n&apos;est pas lisible par les
          scripts de la page. Aucun cookie de mesure d&apos;audience ni de
          publicité : aucun consentement n&apos;est donc demandé.
        </p>
      </Section>

      <Section title="7. Sécurité">
        <List>
          <li>
            Connexion chiffrée (HTTPS), mots de passe hachés (Argon2id),
            protection contre les tentatives répétées et les requêtes venant
            d&apos;autres sites.
          </li>
          <li>
            Chaque entreprise ne voit que ses propres données : le cloisonnement
            est appliqué à chaque requête, et vérifié par des tests
            automatiques.
          </li>
          <li>
            Fichiers analysés par un antivirus au dépôt, téléchargés par des
            liens temporaires.
          </li>
        </List>
      </Section>

      <Section title="8. Vos droits">
        <p>
          Vous pouvez accéder à vos données, les rectifier, les effacer, en
          limiter l&apos;usage, vous opposer à un traitement fondé sur
          l&apos;intérêt légitime, et les récupérer dans un format ouvert : un
          administrateur télécharge l&apos;export complet de l&apos;entreprise
          (Profil &gt; Vos données). Pour toute demande : <Fact>{contact}</Fact>
          . Réponse sous un mois.
        </p>
        <p>
          Pour les données que votre entreprise a déposées (par exemple les noms
          de vos salariés dans les moyens humains), adressez-vous d&apos;abord à
          votre entreprise : Pilao l&apos;aidera à répondre.
        </p>
        <p>Vous pouvez aussi saisir la CNIL (www.cnil.fr).</p>
      </Section>
    </LegalPage>
  );
}
