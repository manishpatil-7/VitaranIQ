import React, { useState, useEffect } from 'react';
import { api } from './api';
import Sidebar from './components/Sidebar';
import TopHeader from './components/TopHeader';
import ConfirmModal from './components/ConfirmModal';
import CommandCenterView from './components/CommandCenterView';
import ForecastStudioView from './components/ForecastStudioView';
import DispatchPlanView from './components/DispatchPlanView';
import WhatIfSandboxView from './components/WhatIfSandboxView';
import BacktestView from './components/BacktestView';
import NetworkTopologyView from './components/NetworkTopologyView';
import { CheckCircle2, AlertCircle, X } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('command');
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isReseedModalOpen, setIsReseedModalOpen] = useState(false);

  const [healthStatus, setHealthStatus] = useState('loading');
  const [summaryData, setSummaryData] = useState(null);
  const [latestPlan, setLatestPlan] = useState(null);

  // Loading states
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false);
  const [isTrainingForecast, setIsTrainingForecast] = useState(false);
  const [isGeneratingData, setIsGeneratingData] = useState(false);

  // Cross-tab navigation state
  const [forecastSelection, setForecastSelection] = useState({ store: 'S01', sku: 'MILK-1L' });

  // Toast notifications
  const [toasts, setToasts] = useState([]);

  const addToast = (message, type = 'success') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  };

  const removeToast = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  useEffect(() => {
    initApp();
  }, []);

  const initApp = async () => {
    try {
      const health = await api.getHealth();
      setHealthStatus(health.status || 'ok');

      // Fetch Data Summary
      try {
        const sum = await api.getDataSummary();
        setSummaryData(sum);
      } catch (e) {
        console.warn('No summary found, seeding data might be needed');
      }

      // Automatically generate or fetch baseline plan for day 703
      try {
        const plan = await api.generatePlan({ asOfDay: 703, supplyScenario: 'normal', workers: 4 });
        setLatestPlan(plan);
      } catch (e) {
        console.warn('Initial plan generation deferred:', e);
      }
    } catch (err) {
      console.error('API health check failed:', err);
      setHealthStatus('error');
    }
  };

  const handleGeneratePlan = async ({ asOfDay = 703, supplyScenario = 'normal' } = {}) => {
    setIsGeneratingPlan(true);
    try {
      const plan = await api.generatePlan({ asOfDay, supplyScenario, workers: 4 });
      setLatestPlan(plan);
      addToast(`Plan ${plan.plan_id.slice(0, 16)} generated successfully! Audit: ${plan.checker?.status || 'PASS'}`, 'success');
    } catch (err) {
      console.error('Plan generation error:', err);
      addToast(`Optimization failed: ${err.message}`, 'error');
    } finally {
      setIsGeneratingPlan(false);
    }
  };

  const handleTrainForecast = async (seed = 42) => {
    setIsTrainingForecast(true);
    try {
      const res = await api.trainForecast(seed);
      addToast(`Model ${res.model_version} trained with 4-quantile LightGBM!`, 'success');
      // Refresh plan
      handleGeneratePlan({ asOfDay: 703, supplyScenario: 'normal' });
    } catch (err) {
      console.error('Training error:', err);
      addToast(`Training failed: ${err.message}`, 'error');
    } finally {
      setIsTrainingForecast(false);
    }
  };

  const handleConfirmReseed = async () => {
    setIsGeneratingData(true);
    try {
      const res = await api.generateData(42);
      addToast(`Dataset ${res.dataset_id} seeded with 219k synthetic FMCG sales records!`, 'success');
      const sum = await api.getDataSummary();
      setSummaryData(sum);
      setIsReseedModalOpen(false);
      // Retrain models
      handleTrainForecast(42);
    } catch (err) {
      console.error('Data generation error:', err);
      addToast(`Data seeding failed: ${err.message}`, 'error');
    } finally {
      setIsGeneratingData(false);
    }
  };

  const handleNavigateToTab = (tabId, params = {}) => {
    if (tabId === 'forecast' && params.store && params.sku) {
      setForecastSelection({ store: params.store, sku: params.sku });
    }
    setActiveTab(tabId);
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 flex flex-col font-sans selection:bg-indigo-50 selection:text-indigo-700">
      {/* Collapsible Sidebar */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isCollapsed={isCollapsed}
        setIsCollapsed={setIsCollapsed}
        isMobileOpen={isMobileOpen}
        setIsMobileOpen={setIsMobileOpen}
        healthStatus={healthStatus}
        activeDataset={summaryData?.dataset_id || 'ds_seed42'}
      />

      {/* Main Container offset by sidebar width */}
      <div 
        className={`flex-1 flex flex-col transition-all duration-200 ease-in-out ${
          isCollapsed ? 'lg:pl-18' : 'lg:pl-64'
        }`}
      >
        {/* Top Header */}
        <TopHeader
          activeTab={activeTab}
          onOpenMobileNav={() => setIsMobileOpen(true)}
          onGeneratePlan={handleGeneratePlan}
          isGeneratingPlan={isGeneratingPlan}
          onTrainForecast={handleTrainForecast}
          isTrainingForecast={isTrainingForecast}
          onOpenReseedModal={() => setIsReseedModalOpen(true)}
          isGeneratingData={isGeneratingData}
          asOfDay={703}
        />

        {/* View Content */}
        <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {activeTab === 'command' && (
            <CommandCenterView
              summaryData={summaryData}
              latestPlan={latestPlan}
              onGeneratePlan={handleGeneratePlan}
              onTrainForecast={handleTrainForecast}
              onGenerateData={() => setIsReseedModalOpen(true)}
              isGeneratingPlan={isGeneratingPlan}
              isTrainingForecast={isTrainingForecast}
              isGeneratingData={isGeneratingData}
              onNavigateToTab={handleNavigateToTab}
            />
          )}

          {activeTab === 'forecast' && (
            <ForecastStudioView
              initialStore={forecastSelection.store}
              initialSku={forecastSelection.sku}
            />
          )}

          {activeTab === 'dispatch' && (
            <DispatchPlanView
              latestPlan={latestPlan}
              onGeneratePlan={handleGeneratePlan}
              isGeneratingPlan={isGeneratingPlan}
            />
          )}

          {activeTab === 'whatif' && (
            <WhatIfSandboxView 
              latestPlan={latestPlan} 
              onGeneratePlan={handleGeneratePlan}
            />
          )}

          {activeTab === 'backtest' && (
            <BacktestView />
          )}

          {activeTab === 'network' && (
            <NetworkTopologyView />
          )}
        </main>

        {/* Executive Enterprise Footer */}
        <footer className="border-t border-slate-200 bg-white py-4 text-xs text-slate-500">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center space-x-2">
              <span className="font-semibold text-slate-800 font-display">VitaranIQ Engine</span>
              <span>•</span>
              <span>Enterprise Distribution Intelligence</span>
              <span>•</span>
              <span className="text-slate-600">Team: Innovate-x</span>
            </div>
            <div className="font-mono text-[11px] text-slate-500">
              LightGBM Q4 + Newsvendor CR + OR-Tools CP-SAT + FEFO Ledger Invariants
            </div>
          </div>
        </footer>
      </div>

      {/* Confirmation Modal for Reseed Data */}
      <ConfirmModal
        isOpen={isReseedModalOpen}
        title="Reseed Canonical Supply Chain Dataset?"
        message="This action will regenerate 219,000 synthetic transaction records for 25 stores and 12 SKUs (seed=42) and re-initialize the baseline inventory. Existing plan history will be refreshed."
        confirmLabel="Reseed Dataset"
        cancelLabel="Cancel"
        isDestructive={true}
        isLoading={isGeneratingData}
        onConfirm={handleConfirmReseed}
        onClose={() => !isGeneratingData && setIsReseedModalOpen(false)}
      />

      {/* Toast Notifications */}
      <div className="fixed bottom-5 right-5 z-50 space-y-2 max-w-sm w-full pointer-events-none">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`p-3.5 rounded-xl border shadow-lg pointer-events-auto flex items-start space-x-2.5 text-xs font-medium animate-in slide-in-from-bottom-2 ${
              toast.type === 'error'
                ? 'bg-red-50 text-red-900 border-red-200'
                : 'bg-white text-slate-900 border-slate-200'
            }`}
          >
            {toast.type === 'error' ? (
              <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 leading-snug">{toast.message}</div>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-slate-400 hover:text-slate-600"
              aria-label="Dismiss notification"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
