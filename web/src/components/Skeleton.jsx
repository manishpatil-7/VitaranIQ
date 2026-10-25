import React from 'react';

export function KpiSkeleton() {
  return (
    <div className="ent-card-static p-5 space-y-3" aria-busy="true" aria-label="Loading metric">
      <div className="flex items-center justify-between">
        <div className="h-3 w-28 rounded bg-slate-200 animate-shimmer" />
        <div className="h-8 w-8 rounded-lg bg-slate-100 animate-shimmer" />
      </div>
      <div className="h-8 w-36 rounded bg-slate-200 animate-shimmer" />
      <div className="h-3.5 w-44 rounded bg-slate-100 animate-shimmer" />
    </div>
  );
}

export function TableRowSkeleton({ cols = 6 }) {
  return (
    <tr className="border-b border-slate-100" aria-busy="true">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="py-3 px-4">
          <div className="h-4 rounded bg-slate-200 animate-shimmer" style={{ width: `${60 + (i % 3) * 15}%` }} />
        </td>
      ))}
    </tr>
  );
}

export function ChartSkeleton({ height = 'h-72' }) {
  return (
    <div className={`w-full ${height} rounded-xl bg-slate-50 border border-slate-200 p-6 flex flex-col justify-end space-y-3`} aria-busy="true" aria-label="Loading chart data">
      <div className="flex items-end justify-between space-x-2 h-44">
        {Array.from({ length: 12 }).map((_, i) => {
          const heights = ['h-16', 'h-24', 'h-32', 'h-20', 'h-36', 'h-28', 'h-40', 'h-24', 'h-32', 'h-20', 'h-28', 'h-36'];
          return (
            <div key={i} className={`flex-1 rounded-t ${heights[i % heights.length]} bg-slate-200 animate-shimmer`} />
          );
        })}
      </div>
      <div className="h-3 w-full rounded bg-slate-200 animate-shimmer" />
    </div>
  );
}

export function HeatmapSkeleton() {
  return (
    <div className="w-full space-y-2 p-4 rounded-xl bg-slate-50 border border-slate-200" aria-busy="true">
      <div className="h-4 w-48 rounded bg-slate-200 animate-shimmer mb-3" />
      {Array.from({ length: 10 }).map((_, r) => (
        <div key={r} className="flex space-x-1.5">
          <div className="w-12 h-5 rounded bg-slate-200 animate-shimmer" />
          {Array.from({ length: 12 }).map((_, c) => (
            <div key={c} className="flex-1 h-5 rounded bg-slate-200 animate-shimmer" />
          ))}
        </div>
      ))}
    </div>
  );
}
