import React from 'react';
import { X, CheckCircle, AlertTriangle, ShieldCheck, Truck, DollarSign, Info } from 'lucide-react';

const REASON_METADATA = {
  LOW_COVER: {
    label: 'Low Cover (<2.0 Days)',
    color: 'bg-red-50 text-red-700 border-red-200',
    description: 'Store on-hand stock is dangerously low relative to forward demand.',
  },
  EXPIRY_FIRST: {
    label: 'FEFO Shelf-Life Priority',
    color: 'bg-purple-50 text-purple-700 border-purple-200',
    description: 'Dispatched earlier-expiring warehouse batch first to prevent wastage.',
  },
  LOWEST_COST_SOURCE: {
    label: 'Lowest Cost Lane',
    color: 'bg-sky-50 text-sky-700 border-sky-200',
    description: 'Selected the warehouse with minimum road transportation cost per unit.',
  },
  CAPACITY_LIMITED: {
    label: 'Store Capacity Capped',
    color: 'bg-amber-50 text-amber-800 border-amber-200',
    description: 'Shipment bounded by the physical volumetric storage constraint (C3).',
  },
  SCARCE_PRIORITY: {
    label: 'High-Margin Scarcity Priority',
    color: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    description: 'Prioritized this location due to superior product margin contribution.',
  },
  REPLENISH_TO_TARGET: {
    label: 'Target Replenishment',
    color: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    description: 'Standard optimal dispatch to satisfy the Newsvendor quantile target.',
  },
  NEXT_BEST: {
    label: 'Next-Best Alternate Depot',
    color: 'bg-amber-50 text-amber-700 border-amber-200',
    description: 'Primary warehouse exhausted; diverted dispatch to secondary depot.',
  },
};

export default function ReasonModal({ line, isOpen, onClose }) {
  if (!isOpen || !line) return null;

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs transition-opacity duration-200"
      role="dialog"
      aria-modal="true"
    >
      <div 
        className="relative w-full max-w-lg bg-white rounded-xl border border-slate-200 shadow-xl overflow-hidden p-6 space-y-5 animate-in fade-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center space-x-2">
              <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-indigo-50 text-indigo-700 border border-indigo-100">
                Line #{line.line_no}
              </span>
              <span className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase ${
                line.priority === 'URGENT' 
                  ? 'bg-red-50 text-red-700 border border-red-200' 
                  : line.priority === 'HIGH'
                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                  : 'bg-slate-100 text-slate-700 border border-slate-200'
              }`}>
                {line.priority} Priority
              </span>
            </div>
            <h3 className="text-base font-bold text-slate-900 mt-1 font-display">
              Explainability & Decision Audit
            </h3>
            <p className="text-xs text-slate-500">
              {line.sku_name} ({line.sku_id})
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Route Snapshot */}
        <div className="grid grid-cols-2 gap-3 p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono">
          <div>
            <span className="text-slate-400 block text-[10px] uppercase">Origin Warehouse</span>
            <span className="text-slate-800 font-semibold">{line.warehouse_name} ({line.warehouse_id})</span>
          </div>
          <div>
            <span className="text-slate-400 block text-[10px] uppercase">Destination Store</span>
            <span className="text-slate-800 font-semibold">{line.store_name} ({line.store_id})</span>
          </div>
          <div>
            <span className="text-slate-400 block text-[10px] uppercase">Dispatched Volume</span>
            <span className="text-emerald-700 font-bold">{line.qty.toLocaleString()} units</span>
          </div>
          <div>
            <span className="text-slate-400 block text-[10px] uppercase">Allocated Transport</span>
            <span className="text-slate-800 font-semibold">₹{line.line_cost_inr.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-slate-400 block text-[10px] uppercase">Assigned Batch</span>
            <span className="text-slate-700 font-mono">{line.batch_id}</span>
          </div>
          <div>
            <span className="text-slate-400 block text-[10px] uppercase">Batch Expiry Day</span>
            <span className="text-amber-700 font-mono font-semibold">Day {line.batch_expiry_day}</span>
          </div>
        </div>

        {/* Reason Codes with Mathematical Evidence */}
        <div className="space-y-3">
          <h4 className="text-xs font-semibold uppercase text-slate-500 tracking-wider">
            Decision Reason Codes & Evidence
          </h4>

          {line.reason_codes && line.reason_codes.length > 0 ? (
            <div className="space-y-2">
              {line.reason_codes.map((rc, idx) => {
                const meta = REASON_METADATA[rc.code] || {
                  label: rc.code,
                  color: 'bg-slate-50 text-slate-700 border-slate-200',
                  description: 'Solver optimized constraint criterion.',
                };
                return (
                  <div 
                    key={idx}
                    className={`p-3 rounded-lg border ${meta.color} space-y-1`}
                  >
                    <div className="flex items-center justify-between text-xs font-bold">
                      <span>{meta.label}</span>
                      <span className="font-mono text-[10px] opacity-75">{rc.code}</span>
                    </div>
                    <p className="text-[11px] opacity-90 leading-relaxed">
                      {meta.description}
                    </p>

                    {/* Evidence dictionary rendered cleanly */}
                    {rc.evidence && Object.keys(rc.evidence).length > 0 && (
                      <div className="pt-2 mt-1 border-t border-slate-200/60 grid grid-cols-2 gap-1 text-[11px] font-mono">
                        {Object.entries(rc.evidence).map(([key, val]) => (
                          <div key={key} className="flex items-center space-x-1">
                            <span className="text-slate-500">{key}:</span>
                            <span className="font-semibold text-slate-800">
                              {typeof val === 'number' ? (Number.isInteger(val) ? val : val.toFixed(2)) : String(val)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-xs text-slate-400 italic p-3 rounded-lg bg-slate-50 border border-slate-200">
              No specific reason codes attached. Standard optimal replenishment path.
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="pt-2 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition"
          >
            Close Audit
          </button>
        </div>
      </div>
    </div>
  );
}
