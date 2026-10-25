import React, { useState, useEffect } from 'react';
import { 
  Truck, 
  Download, 
  Search, 
  Eye, 
  RefreshCw, 
  ChevronLeft, 
  ChevronRight
} from 'lucide-react';
import { api } from '../api';
import ReasonModal from './ReasonModal';
import { TableRowSkeleton } from './Skeleton';
import EmptyState from './EmptyState';

export default function DispatchPlanView({ latestPlan, onGeneratePlan, isGeneratingPlan }) {
  const [lines, setLines] = useState([]);
  const [totalLines, setTotalLines] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [loading, setLoading] = useState(false);

  // Filters
  const [filterWarehouse, setFilterWarehouse] = useState('');
  const [filterStore, setFilterStore] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Reason Modal
  const [selectedAuditLine, setSelectedAuditLine] = useState(null);

  const planId = latestPlan?.plan_id;

  useEffect(() => {
    if (planId) {
      loadLines(planId, page, pageSize, filterWarehouse, filterStore, filterPriority);
    }
  }, [planId, page, pageSize, filterWarehouse, filterStore, filterPriority]);

  const loadLines = async (pId, pg, pSize, wh, st, prio) => {
    setLoading(true);
    try {
      const res = await api.getPlanLines({
        planId: pId,
        page: pg,
        pageSize: pSize,
        warehouseId: wh || undefined,
        storeId: st || undefined,
        priority: prio || undefined,
      });
      setLines(res.lines || []);
      setTotalLines(res.total_lines || 0);
    } catch (err) {
      console.error('Failed to load plan lines:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleExportCsv = () => {
    if (!planId) return;
    const url = api.getPlanExportUrl(planId);
    window.open(url, '_blank');
  };

  const filteredLines = lines.filter((l) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      l.sku_id.toLowerCase().includes(q) ||
      l.sku_name.toLowerCase().includes(q) ||
      l.warehouse_id.toLowerCase().includes(q) ||
      l.store_id.toLowerCase().includes(q)
    );
  });

  const totalPages = Math.ceil(totalLines / pageSize) || 1;

  if (!planId && !isGeneratingPlan) {
    return (
      <EmptyState
        icon={Truck}
        title="No Dispatch Plan Generated"
        description="Run the optimization engine to compute vehicle allocations, FEFO batch repairs, and cost-optimal delivery schedules."
        actionLabel="Generate Dispatch Plan"
        onAction={() => onGeneratePlan({ asOfDay: 703, supplyScenario: 'normal' })}
        isLoading={isGeneratingPlan}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Plan Header Card */}
      <div className="ent-card p-6 space-y-4">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <div className="p-1.5 rounded-md bg-indigo-50 text-indigo-600">
                <Truck className="w-4 h-4" />
              </div>
              <h2 className="text-base font-bold text-slate-900 font-display">
                Weekly Dispatch Recommendations & Manifest
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-2.5 mt-1 text-xs text-slate-500">
              <span className="font-mono text-slate-700 font-semibold">Plan ID: {planId || 'Generating...'}</span>
              <span>•</span>
              <span>As-Of Day: {latestPlan?.as_of_day || 703}</span>
              <span>•</span>
              <span>Supply: {latestPlan?.supply_scenario || 'Normal'}</span>
              <span>•</span>
              <span className="text-emerald-700 font-semibold">
                Status: {latestPlan?.checker?.status || 'PASS'}
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleExportCsv}
              disabled={!planId}
              className="px-3.5 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition flex items-center space-x-1.5 shadow-2xs disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5 text-slate-500" />
              <span>Export CSV</span>
            </button>
            <button
              onClick={() => onGeneratePlan({ asOfDay: 703, supplyScenario: 'normal' })}
              disabled={isGeneratingPlan}
              className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-xs transition flex items-center space-x-1.5 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isGeneratingPlan ? 'animate-spin' : ''}`} />
              <span>{isGeneratingPlan ? 'Re-optimizing...' : 'Re-Run Optimization'}</span>
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            {/* Search */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search SKU or ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 pr-3 py-1.5 rounded-lg bg-white border border-slate-300 text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs w-48 font-mono"
              />
            </div>

            {/* Warehouse Filter */}
            <select
              value={filterWarehouse}
              onChange={(e) => { setFilterWarehouse(e.target.value); setPage(1); }}
              className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 text-slate-700 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs"
            >
              <option value="">All Warehouses</option>
              <option value="W1">W1 - Pune</option>
              <option value="W2">W2 - Mumbai</option>
              <option value="W3">W3 - Nashik</option>
              <option value="W4">W4 - Kolhapur</option>
            </select>

            {/* Priority Filter */}
            <select
              value={filterPriority}
              onChange={(e) => { setFilterPriority(e.target.value); setPage(1); }}
              className="px-2.5 py-1.5 rounded-lg bg-white border border-slate-300 text-slate-700 font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 text-xs"
            >
              <option value="">All Priorities</option>
              <option value="URGENT">URGENT</option>
              <option value="HIGH">HIGH</option>
              <option value="NORMAL">NORMAL</option>
            </select>
          </div>

          <div className="text-slate-500 font-mono text-[11px]">
            Showing {filteredLines.length} of {totalLines} records
          </div>
        </div>
      </div>

      {/* Recommendations Table */}
      <div className="ent-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-mono uppercase text-[11px]">
                <th className="py-3 px-4">Line</th>
                <th className="py-3 px-3">Priority</th>
                <th className="py-3 px-4">SKU / Product</th>
                <th className="py-3 px-3">Route</th>
                <th className="py-3 px-3">Batch & Expiry</th>
                <th className="py-3 px-3 text-right">Units</th>
                <th className="py-3 px-3 text-right">Trucks</th>
                <th className="py-3 px-3 text-right">Cost (INR)</th>
                <th className="py-3 px-4">Reason Codes</th>
                <th className="py-3 px-3 text-center">Audit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRowSkeleton key={i} cols={10} />
                ))
              ) : filteredLines.length > 0 ? (
                filteredLines.map((line) => (
                  <tr key={`${line.line_no}-${line.sku_id}`} className="hover:bg-slate-50/60 transition">
                    <td className="py-3 px-4 font-mono text-slate-500">#{line.line_no}</td>
                    <td className="py-3 px-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                        line.priority === 'URGENT'
                          ? 'bg-red-50 text-red-700 border border-red-200'
                          : line.priority === 'HIGH'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200'
                          : 'bg-slate-100 text-slate-600'
                      }`}>
                        {line.priority}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <div className="font-semibold text-slate-900">{line.sku_name}</div>
                      <div className="text-[11px] font-mono text-slate-400">{line.sku_id}</div>
                    </td>
                    <td className="py-3 px-3 font-mono">
                      <span className="text-indigo-700 font-medium">{line.warehouse_id}</span>
                      <span className="text-slate-400 mx-1">&rarr;</span>
                      <span className="text-slate-800 font-medium">{line.store_id}</span>
                    </td>
                    <td className="py-3 px-3 font-mono text-[11px]">
                      <div className="text-slate-700">{line.batch_id}</div>
                      <div className="text-amber-700 font-medium text-[10px]">Exp: Day {line.batch_expiry_day}</div>
                    </td>
                    <td className="py-3 px-3 text-right font-mono font-bold text-emerald-700">
                      {line.qty.toLocaleString()}
                    </td>
                    <td className="py-3 px-3 text-right font-mono text-slate-700">
                      {line.trucks_on_lane}
                    </td>
                    <td className="py-3 px-3 text-right font-mono text-slate-900 font-medium">
                      ₹{line.line_cost_inr.toFixed(2)}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1 max-w-xs">
                        {line.reason_codes && line.reason_codes.map((rc, rIdx) => (
                          <span
                            key={rIdx}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-50 text-indigo-700 border border-indigo-100"
                            title={JSON.stringify(rc.evidence)}
                          >
                            {rc.code}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 px-3 text-center">
                      <button
                        onClick={() => setSelectedAuditLine(line)}
                        className="p-1.5 rounded-md bg-white border border-slate-200 text-slate-600 hover:text-indigo-600 hover:border-indigo-300 transition"
                        title="Audit Reasoning & Constraints"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="10" className="py-10 text-center text-slate-400 text-xs italic">
                    No dispatch lines match current filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div className="p-3.5 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs font-mono">
          <span className="text-slate-500">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center space-x-1.5">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-md bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-40 transition"
              aria-label="Previous page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="p-1.5 rounded-md bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-40 transition"
              aria-label="Next page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Audit Modal */}
      <ReasonModal
        line={selectedAuditLine}
        isOpen={Boolean(selectedAuditLine)}
        onClose={() => setSelectedAuditLine(null)}
      />
    </div>
  );
}
