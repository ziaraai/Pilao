import type { Metadata } from "next";

import { Fact, LegalPage, List, Section } from "@/components/legal";
import { LEGAL, RETENTION, fact } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Accord de traitement des données — Pilao",
};

export default function ProcessingAgreement() {
  const publisher = fact(LEGAL.publisher.name, "raison sociale de l'éditeur");
  return (
    <LegalPage
      title="Accord de traitement des données"
      intro="Cet accord fait partie des conditions d'utilisation. Il fixe, conformément à l'article 28 du RGPD, ce que Pilao peut faire des données personnelles que le client lui confie."
    >
      <Section title="1. Parties et rôles">
        <p>
          Le client (l&apos;entreprise titulaire du compte) est{" "}
          <strong>responsable de traitement</strong>. <Fact>{publisher}</Fact>,
          éditeur de Pilao, est <strong>sous-traitant</strong> : il traite ces
          données pour le compte du client, uniquement pour lui rendre le
          service.
        </p>
      </Section>

      <Section title="2. Objet, nature et finalité">
        <p>
          Héberger les documents et données du client ; analyser ses dossiers de
          consultation ; rédiger des brouillons de mémoires et de documents ;
          les exporter ; envoyer les alertes. Ces opérations comprennent la
          conservation, la lecture automatique (y compris par des modèles
          d&apos;intelligence artificielle), la recherche, la mise en forme et
          l&apos;effacement.
        </p>
      </Section>

      <Section title="3. Données et personnes concernées">
        <List>
          <li>
            Salariés et dirigeants du client : nom, qualification, expérience,
            CV éventuels, signataire des formulaires.
          </li>
          <li>
            Contacts présents dans les documents déposés : interlocuteurs des
            acheteurs publics dans les DCE, clients cités dans les références.
          </li>
          <li>
            Le client ne dépose pas de données sensibles au sens de
            l&apos;article 9 du RGPD (santé, opinions…), qui ne sont pas
            nécessaires au service.
          </li>
        </List>
      </Section>

      <Section title="4. Durée">
        <p>
          Pendant toute la durée du compte, puis jusqu&apos;à l&apos;effacement
          décrit à l&apos;article 10.
        </p>
      </Section>

      <Section title="5. Instructions du client">
        <p>
          Le sous-traitant ne traite les données que sur les instructions
          documentées du client : les présentes conditions et les actions que le
          client fait dans Pilao. Il n&apos;utilise jamais les données d&apos;un
          client pour un autre client, ni pour entraîner des modèles
          d&apos;intelligence artificielle. S&apos;il estime qu&apos;une
          instruction est contraire au RGPD, il en informe le client.
        </p>
      </Section>

      <Section title="6. Confidentialité et sécurité">
        <List>
          <li>
            Les personnes autorisées à accéder aux données sont tenues à la
            confidentialité, et n&apos;y accèdent que pour le support demandé
            par le client ou la sécurité du service.
          </li>
          <li>
            Mesures de sécurité : cloisonnement des données par entreprise à
            chaque requête, chiffrement des échanges (HTTPS), mots de passe
            hachés, liens de téléchargement temporaires, analyse antivirus des
            fichiers, journal des actions, hébergement dans l&apos;Union
            européenne, sauvegardes.
          </li>
        </List>
      </Section>

      <Section title="7. Sous-traitants ultérieurs">
        <p>
          Le client autorise le recours aux sous-traitants suivants. Le
          sous-traitant informe le client par e-mail de tout ajout ou
          remplacement au moins 30 jours à l&apos;avance ; le client peut
          s&apos;y opposer en mettant fin à son compte. Chaque sous-traitant
          ultérieur est tenu aux mêmes obligations.
        </p>
        <List>
          <li>
            Hébergement (serveurs, base, fichiers), Union européenne :{" "}
            <Fact>{fact(LEGAL.host.name, "hébergeur")}</Fact>.
          </li>
          <li>
            Accès aux modèles d&apos;IA : OpenRouter, Inc. (États-Unis), limité
            aux fournisseurs qui ne conservent pas les requêtes et ne s&apos;en
            servent pas pour entraîner leurs modèles. Garanties du transfert :{" "}
            <Fact>
              {
                "[À COMPLÉTER : clauses contractuelles types ou Data Privacy Framework]"
              }
            </Fact>
            .
          </li>
          <li>
            E-mails transactionnels :{" "}
            <Fact>
              {fact(
                LEGAL.emailProvider,
                "fournisseur d'e-mails transactionnels",
              )}
            </Fact>
            .
          </li>
        </List>
      </Section>

      <Section title="8. Assistance au client">
        <p>
          Le sous-traitant aide le client à répondre aux demandes des personnes
          (accès, rectification, effacement, portabilité) : l&apos;export
          complet et l&apos;effacement sont disponibles pour un administrateur
          dans Profil &gt; Vos données. Il aide aussi le client pour ses
          analyses d&apos;impact et la sécurité, dans la mesure des informations
          dont il dispose.
        </p>
      </Section>

      <Section title="9. Violation de données">
        <p>
          Le sous-traitant notifie au client toute violation de données
          personnelles dans les meilleurs délais, et au plus tard 48 heures
          après en avoir pris connaissance, avec les informations utiles pour
          que le client puisse, le cas échéant, la notifier à la CNIL et aux
          personnes concernées.
        </p>
      </Section>

      <Section title="10. Fin du traitement">
        <p>
          À la demande d&apos;un administrateur, ou à la fin du compte, toutes
          les données du client sont effacées {RETENTION.deletionGraceDays}{" "}
          jours après la demande (délai pendant lequel le client peut annuler et
          exporter ses données) : base, fichiers et index de recherche. Il ne
          reste qu&apos;un reçu sans donnée personnelle. Les sauvegardes
          s&apos;effacent à leur expiration (
          <Fact>
            {fact(
              LEGAL.backupRetention,
              "durée de conservation des sauvegardes",
            )}
          </Fact>
          ).
        </p>
      </Section>

      <Section title="11. Audit">
        <p>
          Le sous-traitant met à disposition du client les informations
          nécessaires pour démontrer le respect de ses obligations, et permet
          des audits, menés par le client ou un auditeur qu&apos;il mandate,
          tenu à la confidentialité, sur préavis de 30 jours et au plus une fois
          par an, sauf violation de données.
        </p>
      </Section>
    </LegalPage>
  );
}
