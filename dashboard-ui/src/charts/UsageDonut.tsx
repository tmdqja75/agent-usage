import { Donut } from "./Donut";

export type UsageDatum = { name: string; count: number };

export function UsageDonut({ data }: { data: UsageDatum[] }) {
  const slices = data.map((d) => ({ label: d.name, value: d.count }));
  return <Donut slices={slices} />;
}
