import { ModuleGate } from "@/components/module-gate";

export default function Layout({ children }: LayoutProps<"/annonces">) {
  return <ModuleGate module="veille">{children}</ModuleGate>;
}
