/** The columns of the profile's lists: the profile page and the « Ce qu'il manque » window. */
import type { ColumnDef } from "@/components/profile/simple-list";
import { formatDate } from "@/lib/format";

export const HUMAN_RESOURCE_COLUMNS: ColumnDef[] = [
  {
    key: "qualification",
    label: "Qualification",
    required: true,
    placeholder: "ex. Agent de propreté",
  },
  {
    key: "count",
    label: "Nombre",
    type: "number",
    required: true,
    placeholder: "ex. 4",
    render: (v) => `× ${String(v)}`,
  },
  {
    key: "description",
    label: "Précisions",
    placeholder: "ex. CQP, temps partiel",
    hint: "diplômes, habilitations, temps de travail, ancienneté : Pilao les reprend dans le mémoire.",
  },
];

export const EQUIPMENT_COLUMNS: ColumnDef[] = [
  {
    key: "name",
    label: "Matériel",
    required: true,
    placeholder: "ex. Autolaveuse Nilfisk SC351",
  },
  {
    key: "category",
    label: "Type de matériel",
    placeholder: "ex. autolaveuse, monobrosse",
    hint: "sert à regrouper votre matériel par type dans la liste des moyens matériels du dossier.",
  },
  {
    key: "quantity",
    label: "Quantité",
    type: "number",
    placeholder: "ex. 2",
    render: (v) => `× ${String(v)}`,
  },
];

export const CERTIFICATION_COLUMNS: ColumnDef[] = [
  {
    key: "name",
    label: "Certification",
    required: true,
    placeholder: "ex. Qualipropre",
  },
  { key: "number", label: "Numéro", placeholder: "ex. QP-2024-0123" },
  {
    key: "valid_until",
    label: "Valable jusqu'au",
    type: "date",
    render: (v) => `jusqu'au ${formatDate(String(v))}`,
  },
];
