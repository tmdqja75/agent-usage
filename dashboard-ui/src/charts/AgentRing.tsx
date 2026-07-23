import { Donut } from "./Donut";
import { agentLabel } from "./names";

export type AgentDatum = { agent: string; tokens: number };

export function AgentRing({ data }: { data: AgentDatum[] }) {
  const slices = data
    .filter((d) => d.tokens > 0)
    .map((d) => ({ label: agentLabel(d.agent), value: d.tokens }));
  return <Donut slices={slices} />;
}
