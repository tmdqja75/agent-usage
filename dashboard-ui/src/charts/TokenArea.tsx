import { curveMonotoneX } from "@visx/curve";
import { ParentSize } from "@visx/responsive";
import { scaleLinear, scaleTime } from "@visx/scale";
import { AreaStack } from "@visx/shape";
import { max as d3max } from "d3-array";
import { SERIES_COLORS } from "./names";

export type TokenPoint = {
  date: string;
  input: number;
  output: number;
  reasoning: number;
};

const KEYS = ["input", "output", "reasoning"] as const;
const HEIGHT = 240;
const MARGIN = { top: 12, right: 16, bottom: 28, left: 48 };

function parseDay(d: string): Date {
  const [y, m, day] = d.split("-").map(Number);
  return new Date(y, m - 1, day);
}

function Inner({ data, width }: { data: TokenPoint[]; width: number }) {
  const innerW = Math.max(0, width - MARGIN.left - MARGIN.right);
  const innerH = HEIGHT - MARGIN.top - MARGIN.bottom;

  const xScale = scaleTime({
    domain: [parseDay(data[0].date), parseDay(data[data.length - 1].date)],
    range: [0, innerW],
  });
  const yMax = d3max(data, (d) => d.input + d.output + d.reasoning) ?? 0;
  const yScale = scaleLinear({
    domain: [0, yMax || 1],
    range: [innerH, 0],
    nice: true,
  });

  return (
    <svg width={width} height={HEIGHT}>
      <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
        <AreaStack
          keys={KEYS as unknown as string[]}
          data={data}
          x={(d) => xScale(parseDay(d.data.date)) ?? 0}
          y0={(d) => yScale(d[0]) ?? 0}
          y1={(d) => yScale(d[1]) ?? 0}
          curve={curveMonotoneX}
        >
          {({ stacks, path }) =>
            stacks.map((stack) => (
              <path
                key={`stack-${stack.key}`}
                d={path(stack) || ""}
                fill={SERIES_COLORS[stack.key as keyof typeof SERIES_COLORS]}
                fillOpacity={0.85}
                stroke={SERIES_COLORS[stack.key as keyof typeof SERIES_COLORS]}
                strokeWidth={1}
              />
            ))
          }
        </AreaStack>
        <line x1={0} y1={innerH} x2={innerW} y2={innerH} stroke="#374151" />
      </g>
    </svg>
  );
}

export function TokenArea({ data }: { data: TokenPoint[] }) {
  if (data.length === 0) return <div className="empty">No token activity in this window.</div>;
  return (
    <>
      <ParentSize>{({ width }) => (width > 0 ? <Inner data={data} width={width} /> : null)}</ParentSize>
      <div className="legend">
        {KEYS.map((k) => (
          <span className="item" key={k}>
            <span className="swatch" style={{ background: SERIES_COLORS[k] }} />
            {k}
          </span>
        ))}
      </div>
    </>
  );
}
