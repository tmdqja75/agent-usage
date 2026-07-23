import { Group } from "@visx/group";
import { Pie } from "@visx/shape";
import { CATEGORY_COLORS } from "./names";

export type Slice = { label: string; value: number };

const SIZE = 220;
const THICKNESS = 34;

export function Donut({ slices }: { slices: Slice[] }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (total <= 0) return <div className="empty">No data yet.</div>;

  const radius = SIZE / 2;

  return (
    <>
      <svg width={SIZE} height={SIZE} style={{ display: "block", margin: "0 auto" }}>
        <Group top={radius} left={radius}>
          <Pie
            data={slices}
            pieValue={(d) => d.value}
            outerRadius={radius}
            innerRadius={radius - THICKNESS}
            padAngle={0.01}
          >
            {(pie) =>
              pie.arcs.map((arc, i) => (
                <path
                  key={arc.data.label}
                  d={pie.path(arc) || ""}
                  fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]}
                />
              ))
            }
          </Pie>
        </Group>
      </svg>
      <div className="legend">
        {slices.map((s, i) => (
          <span className="item" key={s.label}>
            <span
              className="swatch"
              style={{ background: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}
            />
            {s.label} ({s.value})
          </span>
        ))}
      </div>
    </>
  );
}
