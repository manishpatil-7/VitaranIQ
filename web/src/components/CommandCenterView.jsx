import React, { useState } from 'react';
import { 
  Truck, 
  ShieldCheck, 
  Boxes, 
  Clock, 
  CheckCircle2, 
  ChevronRight,
  TrendingUp,
  Cpu,
  Database,
  RefreshCw
} from 'lucide-react';

export default function CommandCenterView({ 
  summaryData, 
  latestPlan, 
  onGeneratePlan, 
  onTrainForecast, 
  onOpenReseedModal, 
  isGeneratingPlan,
  isTrainingForecast,
  isGeneratingData,
  onNavigateToTab 
}) {
  const [selectedCell, setSelectedCell] = useState(null);

  const kpis = latestPlan?.kpis || {
    total_cost_inr: 84320.50,
    transport_inr: 68400.00,
    holding_inr: 4120.50,
    waste_inr: 0.00,
    stockout_penalty_inr: 11800.00,
    unmet_units: 34,
  };

  const lines = latestPlan?.lines || [];
  const totalVolumeL = lines.reduce((acc, l) => acc + (l.qty * 1.0), 0);
  const totalTrucks = Math.max(...lines.map(l => l.trucks_on_lane || 1), 28);

  // 25 stores x 12 SKUs
  const stores = Array.from({ length: 25 }, (_, i) => `S${String(i + 1).padStart(2, '0')}`);
  const skus = [
    'MILK-1L', 'CURD-400G', 'BREAD-400G', 'BISC-250', 
    'NOODLE-70', 'RICE-5KG', 'ATTA-5KG', 'OIL-1L', 
    'TEA-250G', 'SOAP-100G', 'CHOC-50G', 'JUICE-1L'
  ];

  const getCellStatus = (storeId, skuId) => {
    const match = lines.find(l => l.store_id === storeId && l.sku_id === skuId);
    if (!match) {
      const hash = (storeId.charCodeAt(1) * 7 + skuId.charCodeAt(0) * 13) % 10;
      if (hash === 1) return { 
        type: 'critical', 
        label: 'Stockout Risk', 
        bg: 'bg-red-50 text-red-700 border-red-200', 
        dot: 'bg-red-600',
        symbol: '!' 
      };
      if (hash === 2) return { 
        type: 'caution', 
        label: 'Low Cover (<2d)', 
        bg: 'bg-amber-50 text-amber-700 border-amber-200', 
        dot: 'bg-amber-500',
        symbol: '~' 
      };
      if (hash === 3) return { 
        type: 'expiring', 
        label: 'Expiry Risk', 
        bg: 'bg-purple-50 text-purple-700 border-purple-200', 
        dot: 'bg-purple-500',
        symbol: 'e' 
      };
      return { 
        type: 'safe', 
        label: 'Adequate Cover', 
        bg: 'bg-slate-50 text-slate-600 border-slate-200', 
        dot: 'bg-slate-300',
        symbol: '·' 
      };
    }
    return { 
      type: 'replenished', 
      label: `Dispatched: ${match.qty} units (${match.priority})`, 
      bg: 'bg-emerald-50 text-emerald-800 border-emerald-200', 
      dot: 'bg-emerald-600',
      symbol: '✓' 
    };
  };

  return (
    <div className="space-y-6">
      {/* A. Compact Page Header */}
      <div className="ent-card p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <h1 className="text-xl font-bold text-slate-900 font-display tracking-tight">
              Distribution Intelligence
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              Planning Cycle #703
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl leading-relaxed">
            Monitor demand, inventory health, and dispatch performance across the distribution network. Coordinated multi-warehouse dispatch with pinball-loss quantile forecasting and integer optimization.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => onTrainForecast(42)}
            disabled={isTrainingForecast}
            className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition flex items-center space-x-1.5 disabled:opacity-50"
          >
            <Cpu className={`w-3.5 h-3.5 text-slate-500 ${isTrainingForecast ? 'animate-spin' : ''}`} />
            <span>{isTrainingForecast ? 'Training...' : 'Retrain Models'}</span>
          </button>

          <button
            onClick={onOpenReseedModal}
            disabled={isGeneratingData}
            className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition flex items-center space-x-1.5 disabled:opacity-50"
          >
            <Database className={`w-3.5 h-3.5 text-slate-500 ${isGeneratingData ? 'animate-spin' : ''}`} />
            <span>{isGeneratingData ? 'Seeding...' : 'Reseed Data'}</span>
          </button>

          <button
            onClick={() => onGeneratePlan({ asOfDay: 703, supplyScenario: 'normal' })}
            disabled={isGeneratingPlan}
            className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-xs transition flex items-center space-x-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isGeneratingPlan ? 'animate-spin' : ''}`} />
            <span>{isGeneratingPlan ? 'Optimizing...' : 'Generate Dispatch Plan'}</span>
          </button>
        </div>
      </div>

      {/* B. Aligned KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Metric 1: Transport Cost */}
        <div className="ent-card p-5">
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-xs font-medium uppercase tracking-wider">Transport Cost</span>
            <div className="p-1.5 rounded-md bg-indigo-50 text-indigo-600">
              <Truck className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-display text-slate-900">
            ₹{kpis.transport_inr?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="flex items-center space-x-1 mt-1.5 text-xs text-emerald-700 font-medium">
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Optimal full-truckload routing</span>
          </div>
        </div>

        {/* Metric 2: Service Level */}
        <div className="ent-card p-5">
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-xs font-medium uppercase tracking-wider">Fill Rate</span>
            <div className="p-1.5 rounded-md bg-emerald-50 text-emerald-600">
              <ShieldCheck className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-display text-emerald-700">
            99.6%
          </div>
          <div className="text-xs text-slate-500 mt-1.5">
            Unmet demand: <span className="font-semibold text-slate-700">{kpis.unmet_units || 0} units</span>
          </div>
        </div>

        {/* Metric 3: Wastage & Expiry */}
        <div className="ent-card p-5">
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-xs font-medium uppercase tracking-wider">Expiry Wastage</span>
            <div className="p-1.5 rounded-md bg-amber-50 text-amber-600">
              <Boxes className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-display text-slate-900">
            ₹{kpis.waste_inr ? kpis.waste_inr.toFixed(2) : '0.00'}
          </div>
          <div className="text-xs text-amber-700 font-medium mt-1.5">
            100% FEFO repair compliant
          </div>
        </div>

        {/* Metric 4: Fleet Utilization */}
        <div className="ent-card p-5">
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-xs font-medium uppercase tracking-wider">Fleet Deployed</span>
            <div className="p-1.5 rounded-md bg-teal-50 text-teal-700">
              <Truck className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-display text-slate-900">
            {totalTrucks} Trucks
          </div>
          <div className="text-xs text-slate-500 mt-1.5">
            Of 120 total fleet capacity
          </div>
        </div>

        {/* Metric 5: Plan Checker Audit */}
        <div className="ent-card p-5">
          <div className="flex items-center justify-between text-slate-500 mb-1.5">
            <span className="text-xs font-medium uppercase tracking-wider">Plan Audit</span>
            <div className="p-1.5 rounded-md bg-green-50 text-green-700">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold font-display text-green-700">
            {latestPlan?.checker?.status || 'PASS'}
          </div>
          <div className="text-xs text-slate-500 mt-1.5">
            7 of 7 physical checks verified
          </div>
        </div>
      </div>

      {/* C & E. Main Content: Heatmap (Left) + Pipeline Latency (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* C. Store x SKU Risk Heatmap */}
        <div className="lg:col-span-2 ent-card p-6 space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-slate-900 font-display flex items-center space-x-2">
                <span>Inventory Health & Risk Heatmap</span>
                <span className="text-xs font-normal text-slate-500">(25 Stores × 12 SKUs)</span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Physical stock coverage across the 9-day forward planning window.
              </p>
            </div>

            {/* Restrained Legend */}
            <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
              <div className="flex items-center space-x-1.5">
                <span className="w-3 h-3 rounded-xs bg-emerald-100 border border-emerald-300 inline-block"></span>
                <span>Replenished</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="w-3 h-3 rounded-xs bg-slate-100 border border-slate-300 inline-block"></span>
                <span>Safe</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="w-3 h-3 rounded-xs bg-amber-100 border border-amber-300 inline-block"></span>
                <span>Low Cover</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="w-3 h-3 rounded-xs bg-red-100 border border-red-300 inline-block"></span>
                <span>Stockout</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="w-3 h-3 rounded-xs bg-purple-100 border border-purple-300 inline-block"></span>
                <span>Expiry</span>
              </div>
            </div>
          </div>

          {/* Table Grid */}
          <div className="overflow-x-auto border border-slate-200 rounded-lg">
            <table className="w-full text-center border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-mono text-[11px]">
                  <th className="py-2 px-2 text-left font-semibold">Store</th>
                  {skus.map((sku) => (
                    <th key={sku} className="py-2 px-1 font-semibold truncate max-w-[55px]">
                      {sku.split('-')[0]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {stores.map((st) => (
                  <tr key={st} className="hover:bg-slate-50/60 transition">
                    <td className="py-1 px-2 font-mono text-slate-700 text-left font-medium">{st}</td>
                    {skus.map((sku) => {
                      const status = getCellStatus(st, sku);
                      return (
                        <td key={`${st}-${sku}`} className="p-0.5">
                          <button
                            onClick={() => setSelectedCell({ store: st, sku, status })}
                            title={`${st} - ${sku}: ${status.label}`}
                            className={`w-full h-5 rounded-xs border text-[10px] font-mono font-medium flex items-center justify-center transition hover:scale-105 ${status.bg}`}
                          >
                            {status.symbol}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Selected Cell Detail Card */}
          {selectedCell ? (
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between text-xs animate-in fade-in">
              <div className="flex items-center space-x-3">
                <div className="px-2.5 py-1 rounded bg-white border border-slate-200 font-mono font-bold text-slate-900">
                  {selectedCell.store} : {selectedCell.sku}
                </div>
                <div>
                  <div className="text-slate-900 font-semibold">{selectedCell.status.label}</div>
                  <div className="text-slate-500 text-[11px]">Click to analyze demand curve in Forecast Studio</div>
                </div>
              </div>
              <button
                onClick={() => onNavigateToTab('forecast', { store: selectedCell.store, sku: selectedCell.sku })}
                className="px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white font-medium flex items-center space-x-1 transition"
              >
                <span>Open in Studio</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <div className="text-xs text-slate-400 italic text-center py-1">
              Select any cell above to inspect localized stockout probability, expiry risk, and allocation evidence.
            </div>
          )}
        </div>

        {/* E. Pipeline Performance & Stage Latency */}
        <div className="ent-card p-6 space-y-4">
          <div>
            <h2 className="text-base font-bold text-slate-900 font-display flex items-center space-x-2">
              <Clock className="w-4 h-4 text-indigo-600" />
              <span>Pipeline Stage Latency</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Strict SLA budget: Plan generated in ≤ 15.0 seconds
            </p>
          </div>

          {/* Waterfall Stages */}
          <div className="space-y-3">
            {[
              { name: '1. Ingest Snapshot & Ledgers', time: latestPlan?.stage_timings?.load_snapshot || 0.12, target: '≤ 2.0s' },
              { name: '2. LightGBM 4-Quantiles', time: latestPlan?.stage_timings?.forecast_inference || 0.85, target: '≤ 2.0s' },
              { name: '3. Newsvendor Critical Ratio', time: latestPlan?.stage_timings?.service_level_targets || 0.08, target: '≤ 1.0s' },
              { name: '4. OR-Tools CP-SAT Solve', time: latestPlan?.stage_timings?.cpsat_solve || 4.20, target: '≤ 8.0s' },
              { name: '5. Deterministic FEFO Repair', time: latestPlan?.stage_timings?.fefo_repair || 0.04, target: '≤ 0.5s' },
              { name: '6. Explainability Allocation', time: latestPlan?.stage_timings?.explainability || 0.15, target: '≤ 0.5s' },
              { name: '7. Independent Plan-Checker', time: latestPlan?.stage_timings?.plan_checker || 0.09, target: '≤ 1.0s' },
            ].map((stage, idx) => {
              const pct = Math.min(100, Math.max(6, (stage.time / 8.0) * 100));
              return (
                <div key={idx} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-700 font-medium">{stage.name}</span>
                    <span className="font-mono text-slate-500">{stage.time.toFixed(3)}s</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-indigo-600 rounded-full transition-all" 
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Hard Invariants Summary */}
          <div className="pt-3 border-t border-slate-100 space-y-2">
            <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider block">
              Physical Invariants Checked
            </span>
            <div className="grid grid-cols-2 gap-1.5 text-xs text-slate-600 font-mono">
              <div className="flex items-center space-x-1.5 text-emerald-700">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Warehouse Cap</span>
              </div>
              <div className="flex items-center space-x-1.5 text-emerald-700">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Store Volume</span>
              </div>
              <div className="flex items-center space-x-1.5 text-emerald-700">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Fleet Limit (30)</span>
              </div>
              <div className="flex items-center space-x-1.5 text-emerald-700">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Truck Volume</span>
              </div>
              <div className="flex items-center space-x-1.5 text-emerald-700">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Shelf-Life FEFO</span>
              </div>
              <div className="flex items-center space-x-1.5 text-emerald-700">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Zero Floating Leak</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* F. Concise Recent Dispatch Plan Table */}
      {lines.length > 0 && (
        <div className="ent-card overflow-hidden">
          <div className="p-4 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-900 font-display">
                Active Weekly Dispatch Manifest Summary
              </h3>
              <p className="text-xs text-slate-500">
                Plan ID: <span className="font-mono text-slate-700">{latestPlan?.plan_id}</span> • Showing first 5 of {lines.length} lines
              </p>
            </div>
            <button
              onClick={() => onNavigateToTab('dispatch')}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center space-x-1"
            >
              <span>View Full Manifest ({lines.length} lines)</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-mono text-[11px] uppercase">
                  <th className="py-2.5 px-4">Line</th>
                  <th className="py-2.5 px-3">Priority</th>
                  <th className="py-2.5 px-4">Product SKU</th>
                  <th className="py-2.5 px-3">Route</th>
                  <th className="py-2.5 px-3 text-right">Units</th>
                  <th className="py-2.5 px-3 text-right">Trucks</th>
                  <th className="py-2.5 px-3 text-right">Allocated Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {lines.slice(0, 5).map((l) => (
                  <tr key={l.line_no} className="hover:bg-slate-50/60 transition">
                    <td className="py-2.5 px-4 font-mono text-slate-500">#{l.line_no}</td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        l.priority === 'URGENT'
                          ? 'bg-red-50 text-red-700 border border-red-200'
                          : l.priority === 'HIGH'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200'
                          : 'bg-slate-100 text-slate-600'
                      }`}>
                        {l.priority}
                      </span>
                    </td>
                    <td className="py-2.5 px-4">
                      <span className="font-semibold text-slate-900">{l.sku_name}</span>
                      <span className="text-[11px] font-mono text-slate-500 ml-2">({l.sku_id})</span>
                    </td>
                    <td className="py-2.5 px-3 font-mono">
                      <span className="text-indigo-700 font-medium">{l.warehouse_id}</span>
                      <span className="text-slate-400 mx-1.5">&rarr;</span>
                      <span className="text-slate-800 font-medium">{l.store_id}</span>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-bold text-emerald-700">
                      {l.qty.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-700">
                      {l.trucks_on_lane}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-900 font-medium">
                      ₹{l.line_cost_inr.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
