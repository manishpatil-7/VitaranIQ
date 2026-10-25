import React from 'react';
import { 
  LayoutDashboard, 
  TrendingUp, 
  Truck, 
  AlertTriangle, 
  GitCompare, 
  Network, 
  ChevronLeft, 
  ChevronRight,
  Boxes,
  Sparkles,
  X
} from 'lucide-react';

export default function Sidebar({
  activeTab,
  setActiveTab,
  isCollapsed,
  setIsCollapsed,
  isMobileOpen,
  setIsMobileOpen,
  healthStatus,
  activeDataset,
}) {
  const navItems = [
    { id: 'command', label: 'Command Center', icon: LayoutDashboard },
    { id: 'forecast', label: 'Forecast Studio', icon: TrendingUp },
    { id: 'dispatch', label: 'Dispatch Plan', icon: Truck },
    { id: 'whatif', label: 'What-If Sandbox', icon: AlertTriangle },
    { id: 'backtest', label: 'Backtest & Proof', icon: GitCompare },
    { id: 'network', label: 'Network & Topology', icon: Network },
  ];

  const handleSelectTab = (id) => {
    setActiveTab(id);
    if (isMobileOpen) {
      setIsMobileOpen(false);
    }
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-white border-r border-slate-200">
      {/* Brand Header */}
      <div className="h-16 px-4 flex items-center justify-between border-b border-slate-100 flex-shrink-0">
        <div className="flex items-center space-x-3 overflow-hidden">
          <div className="h-9 w-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-xs flex-shrink-0">
            <Boxes className="w-5 h-5" />
          </div>
          {!isCollapsed && (
            <div className="flex flex-col min-w-0">
              <span className="text-base font-bold text-slate-900 font-display tracking-tight truncate">
                VitaranIQ
              </span>
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider truncate">
                Distribution Intelligence
              </span>
            </div>
          )}
        </div>

        {/* Mobile close button */}
        <button
          onClick={() => setIsMobileOpen(false)}
          className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
          aria-label="Close navigation drawer"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Nav Items */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => handleSelectTab(item.id)}
              title={isCollapsed ? item.label : undefined}
              className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors text-left ${
                isActive
                  ? 'bg-indigo-50 text-indigo-700 font-semibold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-indigo-600' : 'text-slate-500'}`} />
              {!isCollapsed && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Bottom Metadata & System Status */}
      <div className="p-3 border-t border-slate-100 bg-slate-50/70 flex-shrink-0 space-y-2">
        {!isCollapsed && (
          <>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-500 font-medium">Dataset:</span>
              <span className="font-mono text-slate-700 font-semibold">{activeDataset || 'ds_seed42'}</span>
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-500 font-medium">Model:</span>
              <span className="font-mono text-slate-700">lgb_q4</span>
            </div>
          </>
        )}

        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center space-x-2">
            <span className="relative flex h-2 w-2 flex-shrink-0">
              {healthStatus === 'ok' ? (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-600"></span>
                </>
              ) : (
                <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
              )}
            </span>
            {!isCollapsed && (
              <span className="text-[11px] font-medium text-slate-700">
                {healthStatus === 'ok' ? 'System Online' : 'Connecting...'}
              </span>
            )}
          </div>

          {/* Desktop collapse toggle */}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="hidden lg:flex p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition"
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        className={`hidden lg:block fixed inset-y-0 left-0 z-30 transition-all duration-200 ease-in-out ${
          isCollapsed ? 'w-18' : 'w-64'
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile Drawer Backdrop */}
      {isMobileOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-xs transition-opacity"
          onClick={() => setIsMobileOpen(false)}
        />
      )}

      {/* Mobile Drawer Content */}
      <div
        className={`lg:hidden fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-200 ease-in-out ${
          isMobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {sidebarContent}
      </div>
    </>
  );
}
