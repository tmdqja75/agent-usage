import { useState } from "react";
import { PieChart } from "@/components/charts/pie-chart";
import { PieSlice } from "@/components/charts/pie-slice";
import { PieCenter } from "@/components/charts/pie-center";
import { CATEGORY_COLORS } from "./names";

export type UsageDatum = { name: string; count: number };

export function UsageDonut({ data }: { data: UsageDatum[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const active = data.filter((d) => d.count > 0);
  const total = active.reduce((sum, d) => sum + d.count, 0);
  if (total <= 0) return <div className="empty">No data yet.</div>;

  const slices = active.map((d, i) => ({
    label: d.name,
    value: d.count,
    color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
  }));

  return (
    <PieChart
      data={slices}
      size={220}
      innerRadius={64}
      padAngle={0.02}
      hoveredIndex={hoveredIndex}
      onHoverChange={setHoveredIndex}
    >
      {slices.map((_, i) => (
        <PieSlice key={i} index={i} />
      ))}
      <PieCenter defaultLabel="Total" />
    </PieChart>
  );
}
