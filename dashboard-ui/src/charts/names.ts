export const AGENT_NAMES: Record<string, string> = {
  hermes_agent: "Hermes",
  claude_code: "Claude Code",
  codex: "Codex",
};

export function agentLabel(agent: string): string {
  return AGENT_NAMES[agent] ?? agent;
}

// Flat categorical palette (no gradients).
export const SERIES_COLORS = {
  input: "#60A5FA",
  output: "#34D399",
  reasoning: "#A78BFA",
};

export const CATEGORY_COLORS = [
  "#60A5FA",
  "#34D399",
  "#A78BFA",
  "#F472B6",
  "#FBBF24",
  "#22D3EE",
  "#F87171",
  "#9CA3AF",
];
