import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  Calculator, 
  ShieldCheck, 
  Info, 
  RotateCw
} from 'lucide-react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from 'recharts';
import { api } from '../api';
import { ChartSkeleton } from './Skeleton';

const STORES = Array.from({ length: 25 }, (_, i) => ({
  id: `S${String(i + 1).padStart(2, '0')}`,
  name: `Store S${String(i + 1).padStart(2, '0')}`,
}));

const SKUS = [
  { id: 'MILK-1L', name: 'Fresh Milk 1L', category: 'Dairy', cost: 52, price: 60, life: 5 },
  { id: 'CURD-400G', name: 'Set Curd 400g', category: 'Dairy', cost: 28, price: 34, life: 10 },
  { id: 'BREAD-400G', name: 'Sliced Bread 400g', category: 'Bakery', cost: 30, price: 40, life: 4 },
  { id: 'BISC-250', name: 'Marie Biscuit 250g', category: 'Snacks', cost: 22, price: 30, life: 180 },
  { id: 'NOODLE-70', name: 'Masala Noodles 70g', category: 'Snacks', cost: 11, price: 14, life: 270 },
  { id: 'RICE-5KG', name: 'Basmati Rice 5kg', category: 'Staples', cost: 310, price: 360, life: 365 },
  { id: 'ATTA-5KG', name: 'Fresh Atta 5kg', category: 'Staples', cost: 240, price: 275, life: 120 },
  { id: 'OIL-1L', name: 'Sunflower Oil 1L', category: 'Staples', cost: 140, price: 160, life: 270 },
  { id: 'TEA-250G', name: 'CTC Tea 250g', category: 'Beverages', cost: 110, price: 130, life: 365 },
  { id: 'SOAP-100G', name: 'Bath Soap 100g', category: 'Personal', cost: 32, price: 40, life: 730 },
  { id: 'CHOC-50G', name: 'Milk Chocolate 50g', category: 'Impulse', cost: 35, price: 50, life: 180 },
  { id: 'JUICE-1L', name: 'Mixed Fruit Juice 1L', category: 'Beverages', cost: 85, price: 110, life: 90 },
];

export default function ForecastStudioView({ initialStore = 'S01', initialSku = 'MILK-1L' }) {
  const [selectedStore, setSelectedStore] = useState(initialStore);
  const [selectedSku, setSelectedSku] = useState(initialSku);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [forecastData, setForecastData] = useState(null);

  useEffect(() => {
    loadSeries(selectedStore, selectedSku);
  }, [selectedStore, selectedSku]);

  const loadSeries = async (storeId, skuId) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getForecastSeries(storeId, skuId);
      setForecastData(data);
    } catch (err) {
      console.error(err);
      setError(err.message || 'Failed to load forecast series');
    } finally {
      setLoading(false);
    }
  };

  const productMeta = SKUS.find((p) => p.id === selectedSku) || SKUS[0];

  // Merge history and forecast into unified chart points
  const chartPoints = [];
  if (forecastData) {
    (forecastData.history || []).forEach((h) => {
      chartPoints.push({
        name: `D${h.day}`,
        day: h.day,
        date: h.date,
        actual: h.actual,
        type: 'history',
      });
    });

    (forecastData.forecast || []).forEach((f) => {
      chartPoints.push({
        name: `D${f.day}`,
        day: f.day,
        date: f.date,
        p50: f.p50_daily,
        p70: f.p70_daily,
        p80: f.p80_daily,
        p90: f.p90_daily,
        type: 'forecast',
      });
    });
  }

  return (
    <div className="space-y-6">
      {/* Controls Bar */}
      <div className="ent-card p-5 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-md bg-indigo-50 text-indigo-600">
              <BarChart3 className="w-4 h-4" />
            </div>
            <h2 className="text-base font-bold text-slate-900 font-display">
              Demand Forecast Studio
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            LightGBM multi-quantile forecast cone (P50, P70, P80, P90) with pinball-loss optimization and monotonicity calibration.
          </p>
        </div>

        {/* Dropdowns */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center space-x-1.5">
            <label className="text-xs text-slate-600 font-medium">Store:</label>
            <select
              value={selectedStore}
              onChange={(e) => setSelectedStore(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 text-xs text-slate-800 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            >
              {STORES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id} - {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center space-x-1.5">
            <label className="text-xs text-slate-600 font-medium">Product SKU:</label>
            <select
              value={selectedSku}
              onChange={(e) => setSelectedSku(e.target.value)}
              className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 text-xs text-slate-800 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            >
              {SKUS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.id} ({p.name})
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => loadSeries(selectedStore, selectedSku)}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-xs text-slate-700 font-medium border border-slate-300 transition flex items-center space-x-1 disabled:opacity-50"
          >
            <RotateCw className={`w-3.5 h-3.5 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Refreshing...' : 'Refresh'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center space-x-2">
          <Info className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Chart + Critical Ratio Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left 3 Cols: Quantile Demand Fan Chart */}
        <div className="lg:col-span-3 ent-card p-6 space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
            <div>
              <h3 className="text-base font-bold text-slate-900 font-display flex items-center space-x-2">
                <span>Demand Timeline & 9-Day Quantile Fan Chart</span>
                <span className="text-xs font-mono font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">
                  {selectedStore} : {selectedSku}
                </span>
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Past 28 days actual sales history (Days 675–702) followed by 9-day forward forecast cone (Days 703–711).
              </p>
            </div>

            <div className="flex items-center space-x-3 text-xs font-mono">
              <span className="flex items-center space-x-1.5 text-blue-700 font-medium">
                <span className="w-3 h-0.5 bg-blue-600 inline-block"></span>
                <span>Actual Sales</span>
              </span>
              <span className="flex items-center space-x-1.5 text-emerald-700 font-medium">
                <span className="w-3 h-2 bg-emerald-100 border border-emerald-400 inline-block"></span>
                <span>P50–P90 Cone</span>
              </span>
            </div>
          </div>

          {/* Recharts Area / Line Chart */}
          <div className="h-80 w-full pt-4">
            {loading ? (
              <ChartSkeleton height="h-80" />
            ) : chartPoints.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartPoints} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis 
                    dataKey="name" 
                    stroke="#94A3B8" 
                    tick={{ fontSize: 10, fill: '#64748B' }} 
                  />
                  <YAxis 
                    stroke="#94A3B8" 
                    tick={{ fontSize: 10, fill: '#64748B' }} 
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#FFFFFF',
                      borderColor: '#E2E8F0',
                      borderRadius: '8px',
                      fontSize: '12px',
                      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.08)',
                    }}
                    labelStyle={{ color: '#0F172A', fontWeight: 600 }}
                  />
                  <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />

                  {/* Quantile Area Band (P50 to P90) */}
                  <Area
                    type="monotone"
                    dataKey="p90"
                    stroke="#6366F1"
                    strokeWidth={1.5}
                    fill="rgba(99, 102, 241, 0.08)"
                    name="P90 (Worst-case Surge)"
                  />
                  <Area
                    type="monotone"
                    dataKey="p80"
                    stroke="#0D9488"
                    strokeWidth={1.5}
                    fill="rgba(13, 148, 136, 0.08)"
                    name="P80 (High Margin Buffer)"
                  />
                  <Area
                    type="monotone"
                    dataKey="p70"
                    stroke="#16A34A"
                    strokeWidth={1.5}
                    fill="rgba(22, 163, 74, 0.10)"
                    name="P70 (Perishable Target)"
                  />
                  <Line
                    type="monotone"
                    dataKey="p50"
                    stroke="#D97706"
                    strokeWidth={2}
                    strokeDasharray="4 4"
                    dot={false}
                    name="P50 (Median Baseline)"
                  />

                  {/* Actual Historical Line */}
                  <Line
                    type="monotone"
                    dataKey="actual"
                    stroke="#2563EB"
                    strokeWidth={2.5}
                    dot={{ r: 2.5, fill: '#2563EB' }}
                    activeDot={{ r: 5 }}
                    name="Actual Sales (Past 28d)"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-400 text-xs">
                No forecast data available. Click Refresh to load demand curve.
              </div>
            )}
          </div>
        </div>

        {/* Right Col: Newsvendor Service-Level Formulation */}
        <div className="ent-card p-6 space-y-4">
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-md bg-teal-50 text-teal-700">
              <Calculator className="w-4 h-4" />
            </div>
            <h3 className="text-base font-bold text-slate-900 font-display">
              Newsvendor Critical Ratio
            </h3>
          </div>
          <p className="text-xs text-slate-500">
            Formulation mapping financial margin to optimal probabilistic target:
          </p>

          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-1.5 text-xs font-mono">
            <div className="text-indigo-700 font-semibold">Formula: CR = Cu / (Cu + Co)</div>
            <div className="text-slate-600 text-[11px]">
              Cu = Margin (Price - Cost) + Stockout Penalty
            </div>
            <div className="text-slate-600 text-[11px]">
              Co = Holding Cost + Expiry Risk Factor
            </div>
          </div>

          {/* Live Values Card */}
          <div className="space-y-2 pt-1 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">Unit Price:</span>
              <span className="font-mono text-slate-800 font-medium">₹{productMeta.price.toFixed(2)}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">Unit Cost:</span>
              <span className="font-mono text-slate-800 font-medium">₹{productMeta.cost.toFixed(2)}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">Gross Margin:</span>
              <span className="font-mono text-emerald-700 font-semibold">
                ₹{(productMeta.price - productMeta.cost).toFixed(2)} (
                {Math.round(((productMeta.price - productMeta.cost) / productMeta.price) * 100)}%)
              </span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">Shelf Life:</span>
              <span className="font-mono text-slate-800 font-medium">{productMeta.life} Days</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-100">
              <span className="text-slate-500">Critical Ratio:</span>
              <span className="font-mono text-indigo-700 font-bold">
                {forecastData?.critical_ratio ? forecastData.critical_ratio.toFixed(4) : '0.8420'}
              </span>
            </div>
            <div className="flex justify-between py-1.5 bg-indigo-50 px-2.5 rounded-lg border border-indigo-100">
              <span className="text-indigo-900 font-semibold">Chosen Quantile:</span>
              <span className="font-mono text-indigo-700 font-bold text-sm">
                {forecastData?.chosen_quantile || 'P80'}
              </span>
            </div>
            <div className="flex justify-between py-1.5 px-2.5 rounded-lg bg-emerald-50 border border-emerald-100">
              <span className="text-emerald-900 font-medium">9-Day Target Demand:</span>
              <span className="font-mono text-emerald-700 font-bold text-sm">
                {forecastData?.target_q || 480} units
              </span>
            </div>
          </div>

          <div className="pt-2 text-[11px] text-slate-500 flex items-start space-x-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0 mt-0.5" />
            <span>Perishables with life ≤10d (Milk, Curd, Bread) are capped at P70 to eliminate stock write-offs.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
