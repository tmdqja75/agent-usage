import { useEffect, useState } from "react";
import { AgentRing } from "./charts/AgentRing";
import { CalendarHeatmap } from "./charts/CalendarHeatmap";
import { TokenArea } from "./charts/TokenArea";
import { UsageDonut } from "./charts/UsageDonut";

type Data = {
  window: { start: string; end: string };
  tokens: { date: string; input: number; output: number; reasoning: number }[];
  agents: { agent: string; tokens: number }[];
  skills: { name: string; count: number }[];
  mcp: { name: string; count: number }[];
  heatmap: { date: string; tokens: number }[];
};

export default function App() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("data.json")
      .then((r) => r.json())
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="dashboard empty">Failed to load data: {error}</div>;
  if (!data) return <div className="dashboard empty">Loading…</div>;

  return (
    <div className="dashboard">
      <section className="block">
        <h2>
          Total Token Usage{" "}
          <span className="window">
            {data.window.start} → {data.window.end}
          </span>
        </h2>
        <TokenArea data={data.tokens} />
      </section>
      <section className="block">
        <h2>Usage by Agent</h2>
        <AgentRing data={data.agents} />
      </section>
      <div className="row-two">
        <section className="block">
          <h2>Skill Usage</h2>
          <UsageDonut data={data.skills} />
        </section>
        <section className="block">
          <h2>MCP Usage</h2>
          <UsageDonut data={data.mcp} />
        </section>
      </div>
      <section className="block">
        <h2>Activity</h2>
        <CalendarHeatmap data={data.heatmap} />
      </section>
    </div>
  );
}
