import { useState } from "react";
import { TooltipContent } from "@/components/charts/tooltip/tooltip-content";
import { agentLabel, CATEGORY_COLORS } from "./names";
import { t } from "@/i18n";

export type HeatDatum = {
  date: string;
  tokens: number;
  byAgent?: { agent: string; tokens: number }[];
};

// Grayscale Less -> More (flat fills, no gradient).
const SCALE = ["#161B22", "#2D333B", "#4A5568", "#8B949E", "#E5E7EB"];

function parseDay(d: string): Date {
  const [y, m, day] = d.split("-").map(Number);
  return new Date(y, m - 1, day);
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function CalendarHeatmap({ data }: { data: HeatDatum[] }) {
  const [hover, setHover] = useState<{ x: number; y: number; datum: HeatDatum } | null>(null);

  if (data.length === 0) return <div className="empty">{t("state.noActivity")}</div>;

  const byDatum = new Map(data.map((d) => [d.date, d]));
  const byDate = new Map(data.map((d) => [d.date, d.tokens]));
  const maxTokens = Math.max(...data.map((d) => d.tokens), 1);

  const first = parseDay(data[0].date);
  const last = parseDay(data[data.length - 1].date);

  // Start on the Sunday on/before the first date.
  const start = new Date(first);
  start.setDate(start.getDate() - start.getDay());

  const weeks: Date[][] = [];
  let cursor = new Date(start);
  while (cursor <= last) {
    const week: Date[] = [];
    for (let i = 0; i < 7; i++) {
      week.push(new Date(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  }

  const bucket = (tokens: number): string => {
    if (tokens <= 0) return SCALE[0];
    const idx = 1 + Math.floor((tokens / maxTokens) * (SCALE.length - 2));
    return SCALE[Math.min(idx, SCALE.length - 1)];
  };

  return (
    <div className="cal-wrap">
      <div className="cal">
        {weeks.map((week, wi) => (
          <div className="col" key={wi}>
            {week.map((day) => {
              const key = iso(day);
              const tokens = byDate.get(key);
              const inRange = day >= first && day <= last;
              const color = inRange && tokens !== undefined ? bucket(tokens) : "transparent";
              const datum = byDatum.get(key);
              return (
                <div
                  className="cell"
                  key={key}
                  style={{ background: color }}
                  onMouseEnter={(e) => {
                    if (!inRange || !datum) return;
                    const rect = e.currentTarget.getBoundingClientRect();
                    const parentRect = e.currentTarget.closest(".cal-wrap")!.getBoundingClientRect();
                    setHover({
                      x: rect.left - parentRect.left + rect.width / 2,
                      y: rect.top - parentRect.top,
                      datum,
                    });
                  }}
                  onMouseLeave={() => setHover(null)}
                />
              );
            })}
          </div>
        ))}
      </div>
      {hover && (
        <div
          className="cal-tooltip"
          style={{ left: hover.x, top: hover.y }}
        >
          <TooltipContent
            title={hover.datum.date}
            rows={
              hover.datum.byAgent && hover.datum.byAgent.length > 0
                ? hover.datum.byAgent.map((a, i) => ({
                    label: agentLabel(a.agent),
                    color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                    value: `${Math.round((a.tokens / hover.datum.tokens) * 100)}%`,
                  }))
                : [{ label: t("heatmap.tokens"), color: SCALE[SCALE.length - 1], value: hover.datum.tokens }]
            }
          />
        </div>
      )}
      <div className="cal-scale">
        <span>{t("heatmap.less")}</span>
        {SCALE.map((c) => (
          <span className="cell" key={c} style={{ background: c }} />
        ))}
        <span>{t("heatmap.more")}</span>
      </div>
    </div>
  );
}
