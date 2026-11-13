import type { Metadata } from "next";

import { Fact, LegalPage, Section } from "@/components/legal";
import { LEGAL, fact } from "@/lib/legal";

export const metadata: Metadata = { title: "Mentions légales — Pilao" };

export default function LegalNotice() {
  const p = LEGAL.publisher;
  return (
    <LegalPage title="Mentions légales">
      <Section title="Éditeur du service">
        <p>
          Pilao est édité par{" "}
          <Fact>{fact(p.name, "raison sociale de la société éditrice")}</Fact>,{" "}
          <Fact>{fact(p.legalForm, "forme juridique")}</Fact> au capital de{" "}
          <Fact>{fact(p.capital, "capital social")}</Fact>, dont le siège est
          situé <Fact>{fact(p.address, "adresse du siège")}</Fact>, immatriculée
          sous le numéro{" "}
          <Fact>{fact(p.rcs, "RCS et ville d'immatriculation")}</Fact>.
        </p>
        <p>
          TVA intracommunautaire :{" "}
          <Fact>{fact(p.vat, "numéro de TVA intracommunautaire")}</Fact>.
          Contact : <Fact>{fact(p.email, "adresse e-mail de contact")}</Fact>
          {" — "}
          <Fact>{fact(p.phone, "téléphone")}</Fact>.
        </p>
        <p>
          Directeur de la publication :{" "}
          <Fact>{fact(p.director, "nom du directeur de la publication")}</Fact>.
        </p>
      </Section>
      <Section title="Hébergement">
        <p>
          Le service et les données sont hébergés dans l&apos;Union européenne
          par <Fact>{fact(LEGAL.host.name, "nom de l'hébergeur")}</Fact>,{" "}
          <Fact>{fact(LEGAL.host.address, "adresse de l'hébergeur")}</Fact>,{" "}
          <Fact>{fact(LEGAL.host.phone, "téléphone de l'hébergeur")}</Fact>.
        </p>
      </Section>
      <Section title="Propriété intellectuelle">
        <p>
          La marque Pilao, le logiciel, les textes et les éléments graphiques du
          service sont protégés. Toute reproduction sans autorisation est
          interdite. Les documents que vous déposez et ceux que Pilao produit
          pour vous restent les vôtres (voir les conditions d&apos;utilisation).
        </p>
      </Section>
      <Section title="Robot de Pilao" id="robot">
        <p>
          À la demande de ses clients, Pilao récupère les dossiers de
          consultation publiés sur les plateformes des acheteurs publics (PLACE
          et plateformes Atexo). Il se présente sous le nom « Pilao », respecte
          les règles robots.txt, ne contourne jamais une vérification anti-robot
          et ne charge pas plus d&apos;une page toutes les 10 secondes sur un
          même site. Pour toute question, ou pour demander l&apos;arrêt sur
          votre plateforme :{" "}
          <Fact>{fact(p.email, "adresse e-mail de contact")}</Fact>.
        </p>
      </Section>
      <Section title="Données personnelles">
        <p>
          Voir la politique de confidentialité et l&apos;accord de traitement
          des données.
        </p>
      </Section>
    </LegalPage>
  );
}
