"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Price history chart. connectNulls={false} — a line drawn across a 6-week hole
 * is a lie in SVG, and the fixture plants exactly such a hole to test this. */
export default function PriceChart({
  history,
  unit,
}: {
  history: { week_ending: string; price_avg: number | null }[];
  unit: string;
}) {
  const data = history.map((h) => ({
    week: h.week_ending.slice(0, 7),
    price: h.price_avg,
  }));
  return (
    <div className="h-64 w-full" dir="ltr">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="week" tick={{ fontSize: 11 }} />
          <YAxis
            tick={{ fontSize: 11 }}
            width={70}
            tickFormatter={(v: number) => v.toLocaleString("en-PK")}
            domain={["auto", "auto"]}
          />
          <Tooltip
            formatter={(v) =>
              v == null ? "not surveyed" : `Rs ${Number(v).toLocaleString("en-PK")}`
            }
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke="#065f46"
            strokeWidth={2}
            fill="#a7f3d0"
            connectNulls={false}
            dot={false}
            name={unit}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
