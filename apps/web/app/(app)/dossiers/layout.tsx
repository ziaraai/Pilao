import { ModuleGate } from "@/components/module-gate";

export default function Layout({ children }: LayoutProps<"/dossiers">) {
  return <ModuleGate module="reponse">{children}</ModuleGate>;
}
