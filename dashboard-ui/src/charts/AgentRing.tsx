import { useState } from "react";
import { RingChart } from "@/components/charts/ring-chart";
import { Ring } from "@/components/charts/ring";
import { RingCenter } from "@/components/charts/ring-center";
import {
  Legend,
  LegendItem,
  LegendLabel,
  LegendMarker,
  LegendProgress,
  LegendValue,
} from "@/components/charts/legend";
import { agentLabel, CATEGORY_COLORS } from "./names";

export type AgentDatum = { agent: string; tokens: number };

export function AgentRing({ data }: { data: AgentDatum[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const active = data.filter((d) => d.tokens > 0);
  const total = active.reduce((sum, d) => sum + d.tokens, 0);
  if (total <= 0) return <div className="empty">No agent activity yet.</div>;

  const items = active.map((d, i) => ({
    label: agentLabel(d.agent),
    value: d.tokens,
    maxValue: total,
    color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
  }));

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row",
        gap: 32,
        alignItems: "center",
        justifyContent: "center",
        flexWrap: "wrap",
      }}
    >
      <RingChart
        data={items}
        size={200}
        hoveredIndex={hoveredIndex}
        onHoverChange={setHoveredIndex}
      >
        {items.map((_, i) => (
          <Ring key={i} index={i} />
        ))}
        <RingCenter
          defaultLabel="Total tokens"
          formatOptions={{ notation: "compact", maximumFractionDigits: 1 }}
        />
      </RingChart>
      <Legend items={items} hoveredIndex={hoveredIndex} onHoverChange={setHoveredIndex}>
        <LegendItem>
          <LegendMarker />
          <LegendLabel />
          <LegendValue showPercentage />
          <LegendProgress />
        </LegendItem>
      </Legend>
    </div>
  );
}
