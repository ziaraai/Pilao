import { ModuleGate } from "@/components/module-gate";

export default function Layout({ children }: LayoutProps<"/documents">) {
  return <ModuleGate module="reponse">{children}</ModuleGate>;
}
