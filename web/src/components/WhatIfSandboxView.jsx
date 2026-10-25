import React, { useState } from 'react';
import { 
  AlertTriangle, 
  Truck, 
  TrendingUp, 
  ShieldAlert, 
  CheckCircle2, 
  Zap,
  Building2,
  MapPin,
  RefreshCw
} from 'lucide-react';
import { api } from '../api';
import { KpiSkeleton } from './Skeleton';
import EmptyState from './EmptyState';

const WAREHOUSES = [
  { id: 'W1', name: 'Pune Fulfillment Center', volumeShare: '35%', fleet: 30 },
  { id: 'W2', name: 'Mumbai-Bhiwandi Hub', volumeShare: '30%', fleet: 30 },
  { id: 'W3', name: 'Nashik Regional Depot', volumeShare: '20%', fleet: 30 },
  { id: 'W4', name: 'Kolhapur Distribution Center', volumeShare: '15%', fleet: 30 },
];

export default function WhatIfSandboxView({ latestPlan, onGeneratePlan }) {
  const [selectedWarehouse, setSelectedWarehouse] = useState('W1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [whatifResult, setWhatifResult] = useState(null);

  const basePlanId = latestPlan?.plan_id;

  const handleRunSimulation = async () => {
    if (!basePlanId) {
      setError('Please generate a base plan first before running disruption simulations.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.runWhatifOutage({
        basePlanId,
        outageWarehouseId: selectedWarehouse,
        workers: 4,
      });
      setWhatifResult(res);
    } catch (err) {
      console.error('What-If run failed:', err);
      setError(err.message || 'Simulation failed.');
    } finally {
      setLoading(false);
    }
  };

  const comp = whatifResult?.comparison;
  const displacedStores = whatifResult?.displaced_stores || [];
  const newRoutes = whatifResult?.new_routes || [];

  return (
    <div className="space-y-6">
      {/* Sandbox Control Card */}
      <div className="ent-card p-6 border-l-4 border-l-amber-500">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="p-1.5 rounded-lg bg-amber-50 text-amber-700 border border-amber-200">
                <AlertTriangle className="w-4 h-4" />
              </span>
              <h2 className="text-lg font-bold text-slate-900 font-display">
                What-If Supply Chain Disruption Sandbox
              </h2>
            </div>
            <p className="text-xs text-slate-500 mt-1.5 max-w-2xl leading-relaxed">
              Stress-test network resilience: instantly simulate sudden warehouse outages (floods, labor halts) and let the integer solver re-route emergency supply across eligible alternate depots while respecting capacity constraints.
            </p>
          </div>

          {/* Outage Selector & Trigger */}
          <div className="flex flex-wrap items-center gap-2.5">
            <label className="text-xs font-medium text-slate-600 hidden sm:inline">
              Simulate Outage:
            </label>
            <select
              value={selectedWarehouse}
              onChange={(e) => setSelectedWarehouse(e.target.value)}
              className="px-3 py-2 rounded-lg bg-white border border-slate-300 text-xs font-mono text-slate-800 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            >
              {WAREHOUSES.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.id} — {w.name} ({w.volumeShare} Inbound)
                </option>
              ))}
            </select>

            <button
              onClick={handleRunSimulation}
              disabled={loading || !basePlanId}
              className="px-4 py-2 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-700 text-white shadow-xs transition flex items-center space-x-1.5 disabled:opacity-50"
            >
              {loading ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Zap className="w-3.5 h-3.5" />
              )}
              <span>{loading ? 'Re-solving CP-SAT...' : 'Simulate Outage'}</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* When no base plan is present */}
      {!basePlanId && !loading && (
        <EmptyState
          icon={AlertTriangle}
          title="No Base Dispatch Plan Available"
          description="A baseline dispatch plan is required to benchmark the network against simulated warehouse outages."
          actionLabel="Generate Base Plan (Day 703)"
          onAction={onGeneratePlan ? () => onGeneratePlan({ asOfDay: 703 }) : undefined}
        />
      )}

      {/* Loading Skeletons */}
      {loading && (
        <div className="space-y-6">
          <KpiSkeleton count={4} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="ent-card p-6 h-64 animate-pulse bg-slate-100" />
            <div className="ent-card p-6 h-64 animate-pulse bg-slate-100" />
          </div>
        </div>
      )}

      {/* Delta Comparison KPI Cards */}
      {whatifResult && comp && !loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Delta Transport Cost */}
          <div className="ent-card p-5">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Transport Cost Surge</span>
              <div className="p-2 rounded-lg bg-amber-50 text-amber-700 border border-amber-200">
                <TrendingUp className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold font-display text-amber-700">
              +₹{comp.delta_transport_inr?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
            <div className="flex items-center space-x-1 mt-1 text-xs text-slate-500 font-mono">
              <span>Base: ₹{comp.base_transport_inr?.toFixed(0)}</span>
              <span>&rarr;</span>
              <span className="text-slate-800 font-semibold">New: ₹{comp.new_transport_inr?.toFixed(0)}</span>
            </div>
          </div>

          {/* Card 2: Stockout Absorption */}
          <div className="ent-card p-5">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Unmet Demand Impact</span>
              <div className="p-2 rounded-lg bg-red-50 text-red-700 border border-red-200">
                <ShieldAlert className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold font-display text-red-700">
              +{comp.delta_unmet_units || 0} units
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Absorbed {((1 - (comp.delta_unmet_units || 0) / 12000) * 100).toFixed(1)}% through backup hubs
            </div>
          </div>

          {/* Card 3: Additional Fleet Deployed */}
          <div className="ent-card p-5">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Emergency Fleet Shift</span>
              <div className="p-2 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200">
                <Truck className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold font-display text-slate-900">
              {comp.delta_trucks >= 0 ? `+${comp.delta_trucks}` : comp.delta_trucks} Trucks
            </div>
            <div className="text-xs text-emerald-700 mt-1 flex items-center space-x-1 font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Within remaining fleet cap</span>
            </div>
          </div>

          {/* Card 4: Displaced Stores */}
          <div className="ent-card p-5">
            <div className="flex items-center justify-between text-slate-500 mb-2">
              <span className="text-xs font-semibold uppercase tracking-wider">Displaced Locations</span>
              <div className="p-2 rounded-lg bg-teal-50 text-teal-700 border border-teal-200">
                <MapPin className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-bold font-display text-teal-700">
              {comp.affected_stores_count || displacedStores.length} Stores
            </div>
            <div className="text-xs text-slate-500 mt-1 font-mono">
              Diverted from {comp.outage_warehouse_id}
            </div>
          </div>
        </div>
      )}

      {/* Displaced Stores & Alternate Lanes Breakdown */}
      {whatifResult && !loading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: Displaced Stores List */}
          <div className="ent-card p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900 font-display flex items-center space-x-2">
                <Building2 className="w-4 h-4 text-amber-600" />
                <span>Displaced Retail Stores & Backup Depots</span>
              </h3>
              <span className="text-xs font-mono text-slate-500">
                {displacedStores.length} Stores Diverted
              </span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              Stores previously reliant on <strong className="text-slate-700">{selectedWarehouse}</strong> now fulfilled by neighboring regional hubs:
            </p>

            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {displacedStores.length > 0 ? (
                displacedStores.map((ds, idx) => (
                  <div 
                    key={idx}
                    className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center space-x-2">
                      <span className="px-2 py-0.5 rounded font-mono font-bold bg-white text-slate-800 border border-slate-300">
                        {ds.store_id}
                      </span>
                      <span className="text-slate-500 font-mono text-[11px]">
                        Prev: <span className="line-through text-red-600">{ds.previous_warehouse}</span>
                      </span>
                    </div>

                    <div className="flex items-center space-x-1.5 font-mono">
                      <span className="text-slate-400">&rarr;</span>
                      {ds.new_warehouses && ds.new_warehouses.length > 0 ? (
                        ds.new_warehouses.map((nw, i) => (
                          <span key={i} className="px-2 py-0.5 rounded font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {nw}
                          </span>
                        ))
                      ) : (
                        <span className="px-2 py-0.5 rounded text-red-700 bg-red-50 border border-red-200 text-[11px] font-semibold">
                          Stocked Out
                        </span>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-slate-400 italic py-6 text-center">
                  No stores required diversion for this warehouse.
                </div>
              )}
            </div>
          </div>

          {/* Right: New Emergency Routes */}
          <div className="ent-card p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900 font-display flex items-center space-x-2">
                <Truck className="w-4 h-4 text-indigo-600" />
                <span>New Emergency Lanes Activated</span>
              </h3>
              <span className="text-xs font-mono text-slate-500">
                {newRoutes.length} Corridors
              </span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              Lanes newly established or expanded to bridge regional supply gaps:
            </p>

            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {newRoutes.length > 0 ? (
                newRoutes.map((nr, idx) => (
                  <div 
                    key={idx}
                    className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between text-xs font-mono"
                  >
                    <div className="flex items-center space-x-2">
                      <span className="text-indigo-700 font-bold bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-200">
                        {nr.warehouse_id}
                      </span>
                      <span className="text-slate-400">&rarr;</span>
                      <span className="text-slate-800 font-bold bg-white px-1.5 py-0.5 rounded border border-slate-200">
                        {nr.store_id}
                      </span>
                    </div>

                    <div className="flex items-center space-x-3 text-slate-700">
                      <span className="text-slate-600">{nr.trucks} Trucks</span>
                      <span className="text-emerald-700 font-bold">₹{nr.cost_inr?.toFixed(2)}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-slate-400 italic py-6 text-center">
                  Emergency shipments consolidated onto existing transport corridors.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
