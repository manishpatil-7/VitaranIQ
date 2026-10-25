import React from 'react';
import { 
  Activity, 
  Layers, 
  BarChart3, 
  Truck, 
  AlertTriangle, 
  GitCompare, 
  Network, 
  RefreshCw,
  Sparkles
} from 'lucide-react';

export default function Navbar({ 
  activeTab, 
  setActiveTab, 
  healthStatus, 
  activeDataset, 
  activeModel, 
  onQuickGenerate, 
  isGeneratingPlan 
}) {
  const tabs = [
    { id: 'command', label: 'Command Center', icon: Activity },
    { id: 'forecast', label: 'Forecast Studio', icon: BarChart3 },
    { id: 'dispatch', label: 'Dispatch Plan', icon: Truck },
    { id: 'whatif', label: 'What-If Sandbox', icon: AlertTriangle },
    { id: 'backtest', label: 'Backtest & Proof', icon: GitCompare },
    { id: 'network', label: 'Network & Topology', icon: Network },
  ];

  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-slate-800 bg-slate-950/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Tag */}
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-violet-600 to-fuchsia-500 flex items-center justify-center shadow-lg shadow-indigo-500/25 ring-1 ring-white/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xl font-extrabold tracking-tight font-display bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                  VitaranIQ
                </span>
                <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 tracking-wider">
                  Engine v1.0
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">AI-Powered FMCG Distribution Intelligence</p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="hidden lg:flex items-center space-x-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-indigo-600/15 text-indigo-300 border border-indigo-500/30 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-400' : 'text-slate-400'}`} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>

          {/* System Status & Quick Plan */}
          <div className="flex items-center space-x-3">
            {/* Status Indicator */}
            <div className="flex items-center space-x-2 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs">
              <span className="relative flex h-2 w-2">
                {healthStatus === 'ok' ? (
                  <>
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </>
                ) : (
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                )}
              </span>
              <span className="text-slate-300 font-mono text-[11px]">
                {healthStatus === 'ok' ? 'ONLINE' : 'CONNECTING'}
              </span>
            </div>

            {/* Quick Plan Button */}
            <button
              onClick={onQuickGenerate}
              disabled={isGeneratingPlan}
              className="flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-white shadow-md shadow-indigo-500/20 border border-indigo-400/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isGeneratingPlan ? 'animate-spin' : ''}`} />
              <span>{isGeneratingPlan ? 'Optimizing...' : 'New Plan'}</span>
            </button>
          </div>
        </div>

        {/* Mobile Tab Scroller */}
        <div className="flex lg:hidden overflow-x-auto space-x-1 py-2 border-t border-slate-800/60 no-scrollbar">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                  isActive
                    ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/30'
                    : 'text-slate-400 hover:bg-slate-800/40 border border-transparent'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
}
