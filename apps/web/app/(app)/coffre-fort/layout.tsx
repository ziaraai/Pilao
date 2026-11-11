import { ModuleGate } from "@/components/module-gate";

export default function Layout({ children }: LayoutProps<"/coffre-fort">) {
  return <ModuleGate module="reponse">{children}</ModuleGate>;
}
