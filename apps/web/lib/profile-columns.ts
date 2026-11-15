/** The columns of the profile's lists: the profile page and the « Ce qu'il manque » window. */
import type { ColumnDef } from "@/components/profile/simple-list";
import { formatDate } from "@/lib/format";

export const HUMAN_RESOURCE_COLUMNS: ColumnDef[] = [
  { key: "qualification", label: "Qualification", required: true },
  {
    key: "count",
    label: "Nombre",
    type: "number",
    required: true,
    render: (v) => `× ${String(v)}`,
  },
  { key: "description", label: "Précisions" },
];

export const EQUIPMENT_COLUMNS: ColumnDef[] = [
  { key: "name", label: "Matériel", required: true },
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
    render: (v) => `× ${String(v)}`,
  },
];

export const CERTIFICATION_COLUMNS: ColumnDef[] = [
  { key: "name", label: "Certification", required: true },
  { key: "number", label: "Numéro" },
  {
    key: "valid_until",
    label: "Valable jusqu'au",
    type: "date",
    render: (v) => `jusqu'au ${formatDate(String(v))}`,
  },
];
