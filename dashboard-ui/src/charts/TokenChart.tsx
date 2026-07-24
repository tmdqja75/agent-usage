import { TokenArea, type TokenPoint } from "./TokenArea";
import { TokenBar } from "./TokenBar";

export function TokenChart({ data, useBarChart }: { data: TokenPoint[]; useBarChart: boolean }) {
  return useBarChart ? <TokenBar data={data} /> : <TokenArea data={data} />;
}
