import React from 'react';
import { 
  Menu, 
  RefreshCw, 
  Database, 
  Cpu, 
  Calendar, 
  ShieldCheck,
  Zap
} from 'lucide-react';

const TAB_TITLES = {
  command: { title: 'Command Center', section: 'Operations' },
  forecast: { title: 'Forecast Studio', section: 'Demand Intelligence' },
  dispatch: { title: 'Dispatch Plan', section: 'Fulfillment & Logistics' },
  whatif: { title: 'What-If Disruption Sandbox', section: 'Resilience Engineering' },
  backtest: { title: 'Backtest & Proof Matrix', section: 'Simulation & Benchmarks' },
  network: { title: 'Network & Topology', section: 'Master Parameters' },
};

export default function TopHeader({
  activeTab,
  onOpenMobileNav,
  onGeneratePlan,
  isGeneratingPlan,
  onTrainForecast,
  isTrainingForecast,
  onOpenReseedModal,
  isGeneratingData,
  asOfDay = 703,
}) {
  const current = TAB_TITLES[activeTab] || TAB_TITLES.command;

  return (
    <header className="sticky top-0 z-20 h-16 bg-white border-b border-slate-200 px-4 sm:px-6 lg:px-8 flex items-center justify-between shadow-2xs">
      <div className="flex items-center space-x-3">
        {/* Mobile menu toggle */}
        <button
          onClick={onOpenMobileNav}
          className="lg:hidden p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition"
          aria-label="Open navigation menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Breadcrumb & Section */}
        <div>
          <div className="flex items-center space-x-1.5 text-xs text-slate-500 font-medium">
            <span>{current.section}</span>
            <span>/</span>
            <span className="text-slate-900 font-semibold">{current.title}</span>
          </div>
          <div className="flex items-center space-x-2 mt-0.5">
            <span className="text-xs font-mono font-medium text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">
              Cycle #{asOfDay}
            </span>
            <span className="text-xs text-slate-500 hidden sm:inline">
              9-Day Horizon
            </span>
          </div>
        </div>
      </div>

      {/* Action Cluster */}
      <div className="flex items-center space-x-2">
        {/* Secondary: Retrain Models */}
        <button
          onClick={() => onTrainForecast(42)}
          disabled={isTrainingForecast}
          className="hidden sm:flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition disabled:opacity-50"
          title="Retrain LightGBM 4-quantile model on historical window"
        >
          <Cpu className={`w-3.5 h-3.5 text-slate-500 ${isTrainingForecast ? 'animate-spin' : ''}`} />
          <span>{isTrainingForecast ? 'Training...' : 'Retrain'}</span>
        </button>

        {/* Secondary: Reseed Data (Confirmation Modal trigger) */}
        <button
          onClick={onOpenReseedModal}
          disabled={isGeneratingData}
          className="hidden sm:flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition disabled:opacity-50"
          title="Reseed canonical dataset (seed=42, 219k records)"
        >
          <Database className={`w-3.5 h-3.5 text-slate-500 ${isGeneratingData ? 'animate-spin' : ''}`} />
          <span>{isGeneratingData ? 'Seeding...' : 'Reseed'}</span>
        </button>

        {/* Primary CTA: Generate Dispatch Plan */}
        <button
          onClick={() => onGeneratePlan({ asOfDay, supplyScenario: 'normal' })}
          disabled={isGeneratingPlan}
          className="flex items-center space-x-1.5 px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-xs transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isGeneratingPlan ? 'animate-spin' : ''}`} />
          <span>{isGeneratingPlan ? 'Optimizing...' : 'Generate Plan'}</span>
        </button>
      </div>
    </header>
  );
}
