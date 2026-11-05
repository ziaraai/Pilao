import type { Metadata } from "next";
import Link from "next/link";

import { Fact, LegalPage, List, Section } from "@/components/legal";
import { LEGAL, RETENTION, fact } from "@/lib/legal";

export const metadata: Metadata = {
  title: "Conditions d'utilisation — Pilao",
};

export default function Terms() {
  const publisher = fact(LEGAL.publisher.name, "raison sociale de l'éditeur");
  return (
    <LegalPage
      title="Conditions générales d'utilisation"
      intro="Ces conditions régissent l'utilisation de Pilao par les entreprises. Elles sont acceptées par la personne qui crée le compte, au nom de son entreprise."
    >
      <Section title="1. Objet et acceptation">
        <p>
          Pilao est un service en ligne édité par <Fact>{publisher}</Fact> («
          l&apos;éditeur ») qui aide les entreprises à répondre aux marchés
          publics. Il est réservé aux professionnels : un compte est rattaché à
          une entreprise identifiée par son SIRET (« le client »). La personne
          qui crée le compte déclare avoir le pouvoir d&apos;engager son
          entreprise. L&apos;acceptation est enregistrée avec sa date et la
          version des conditions.
        </p>
      </Section>

      <Section title="2. Le service">
        <List>
          <li>
            Veille des annonces publiques (BOAMP, TED) avec un score
            d&apos;adéquation au profil de l&apos;entreprise.
          </li>
          <li>
            Analyse du dossier de consultation (DCE) déposé par le client :
            dates, critères, plan imposé, exigences, avec leur source.
          </li>
          <li>
            Rédaction d&apos;un brouillon de mémoire technique et de documents
            préremplis (DC1, DC2, listes de moyens et de références…), et
            matrice de conformité.
          </li>
          <li>
            Coffre-fort des attestations, avec alertes d&apos;expiration ;
            exports Word, PDF et ZIP.
          </li>
        </List>
      </Section>

      <Section title="3. Un brouillon, que le client relit et dont il reste responsable">
        <List>
          <li>
            Les textes et documents produits par Pilao, notamment par
            intelligence artificielle, sont des <strong>brouillons</strong>. Ils
            peuvent contenir des erreurs ou des oublis. Le client les relit, les
            complète (en particulier les mentions « [À COMPLÉTER] ») et les
            valide avant tout usage.
          </li>
          <li>
            Pilao <strong>ne dépose jamais d&apos;offre</strong> à la place du
            client. Le client reste seul responsable du contenu de son offre,
            des engagements qu&apos;elle contient, du respect du règlement de la
            consultation et des délais.
          </li>
          <li>
            Pilao n&apos;invente pas les données de l&apos;entreprise
            (effectifs, chiffre d&apos;affaires, références, certifications,
            matériel) : il ne reprend que celles que le client a saisies ou
            déposées, et signale ce qui manque. Le client est responsable de
            leur exactitude.
          </li>
          <li>
            Le score des annonces et l&apos;analyse du DCE sont des aides à la
            décision. Pilao ne garantit ni l&apos;exhaustivité de la veille ni
            l&apos;attribution d&apos;un marché.
          </li>
        </List>
      </Section>

      <Section title="4. Compte et accès">
        <p>
          Le client désigne au moins un administrateur, qui peut exporter ou
          faire effacer les données de l&apos;entreprise. Les identifiants sont
          personnels et confidentiels : toute action faite avec un compte est
          réputée faite par le client. Le client prévient l&apos;éditeur sans
          délai de tout accès qu&apos;il n&apos;a pas autorisé.
        </p>
      </Section>

      <Section title="5. Obligations du client">
        <List>
          <li>
            Ne déposer que des documents qu&apos;il a le droit d&apos;utiliser,
            et respecter les obligations de confidentialité fixées par les
            acheteurs.
          </li>
          <li>
            Ne déposer aucun contenu illicite ni fichier malveillant, et ne pas
            chercher à accéder aux données d&apos;autres clients ou à perturber
            le service.
          </li>
          <li>
            Informer ses salariés et les personnes citées dans ses documents
            (moyens humains, références) de l&apos;usage de leurs données.
          </li>
        </List>
      </Section>

      <Section title="6. Données et confidentialité">
        <List>
          <li>
            Le client reste propriétaire de ses données et des documents
            produits pour lui. L&apos;éditeur ne les utilise que pour lui rendre
            le service.
          </li>
          <li>
            Les données d&apos;un client ne servent <strong>jamais</strong> à
            produire des documents pour un autre client, ni à entraîner des
            modèles d&apos;intelligence artificielle.
          </li>
          <li>
            Pour les données personnelles que le client confie à Pilao,
            l&apos;éditeur agit comme sous-traitant selon l&apos;
            <Link href="/accord-de-traitement" className="underline">
              accord de traitement des données
            </Link>
            , qui fait partie des présentes conditions. Voir aussi la{" "}
            <Link href="/confidentialite" className="underline">
              politique de confidentialité
            </Link>
            .
          </li>
        </List>
      </Section>

      <Section title="7. Propriété intellectuelle">
        <p>
          Le logiciel, la marque et les contenus de Pilao restent la propriété
          de l&apos;éditeur. Le client dispose d&apos;un droit d&apos;usage
          personnel et non exclusif du service pendant la durée de son compte.
          Il concède à l&apos;éditeur le seul droit d&apos;héberger et de
          traiter ses contenus pour lui rendre le service.
        </p>
      </Section>

      <Section title="8. Disponibilité">
        <p>
          L&apos;éditeur fait ses meilleurs efforts pour que le service soit
          accessible et fiable, sans garantie de disponibilité permanente : des
          interruptions peuvent avoir lieu pour maintenance, mise à jour ou
          incident chez un fournisseur. Les services d&apos;intelligence
          artificielle peuvent être momentanément indisponibles ; la tâche est
          alors relancée ou signalée. Le client conserve une copie des documents
          importants pour ses délais de remise.
        </p>
      </Section>

      <Section title="9. Prix">
        <p>
          <Fact>
            {fact(LEGAL.pricing, "formules, prix et modalités de paiement")}
          </Fact>
        </p>
      </Section>

      <Section title="10. Durée, résiliation, suspension">
        <List>
          <li>
            Le compte est ouvert sans durée déterminée. Un administrateur peut y
            mettre fin à tout moment en demandant l&apos;effacement des données
            (Profil &gt; Vos données) : il a lieu {RETENTION.deletionGraceDays}{" "}
            jours plus tard, après un export possible, et peut être annulé
            jusque-là.
          </li>
          <li>
            En cas de manquement grave du client (usage illicite, atteinte à la
            sécurité, accès aux données d&apos;autrui), l&apos;éditeur peut
            suspendre l&apos;accès après l&apos;en avoir averti, ou sans délai
            si la sécurité du service l&apos;exige.
          </li>
        </List>
      </Section>

      <Section title="11. Responsabilité">
        <p>
          L&apos;éditeur est tenu d&apos;une obligation de moyens. Il n&apos;est
          pas responsable du contenu des offres remises par le client, du rejet
          d&apos;une candidature ou d&apos;une offre, ni des dommages indirects
          (perte de marché, de chiffre d&apos;affaires ou de chance). Sa
          responsabilité est limitée à{" "}
          <Fact>{fact(LEGAL.liabilityCap, "plafond de responsabilité")}</Fact>,
          sauf faute lourde ou intentionnelle.
        </p>
      </Section>

      <Section title="12. Modification des conditions">
        <p>
          L&apos;éditeur informe les clients par e-mail de toute modification au
          moins 30 jours avant son entrée en vigueur. La nouvelle version est
          acceptée lors de la connexion suivante ; un client qui la refuse peut
          faire effacer ses données dans les conditions de l&apos;article 10.
        </p>
      </Section>

      <Section title="13. Droit applicable et litiges">
        <p>
          Les présentes conditions sont soumises au droit français. À défaut
          d&apos;accord amiable, tout litige relève du{" "}
          <Fact>{fact(LEGAL.court, "tribunal de commerce compétent")}</Fact>.
        </p>
      </Section>
    </LegalPage>
  );
}
