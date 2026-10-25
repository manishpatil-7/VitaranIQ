/**
 * VitaranIQ Frontend API Client
 * Connects directly to FastAPI backend via relative `/api/v1` routes.
 */

const API_BASE = '/api/v1';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    let errorDetail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      errorDetail = data.detail || JSON.stringify(data);
    } catch {
      errorDetail = await res.text();
    }
    throw new Error(errorDetail);
  }
  return res.json();
}

export const api = {
  // Health
  getHealth: () => request('/health'),

  // Data
  getDataSummary: () => request('/data/summary'),
  generateData: (seed = 42) =>
    request('/data/generate', {
      method: 'POST',
      body: JSON.stringify({ seed }),
    }),

  // Forecast
  trainForecast: (seed = 42) =>
    request('/forecast/train', {
      method: 'POST',
      body: JSON.stringify({ seed }),
    }),
  getForecastAccuracy: () => request('/forecast/accuracy'),
  getForecastSeries: (storeId, skuId) =>
    request(`/forecast/series?store_id=${encodeURIComponent(storeId)}&sku_id=${encodeURIComponent(skuId)}`),

  // Plan
  generatePlan: ({ asOfDay = 703, supplyScenario = 'normal', workers = 4 } = {}) =>
    request('/plan', {
      method: 'POST',
      body: JSON.stringify({
        as_of_day: asOfDay,
        supply_scenario: supplyScenario,
        workers,
      }),
    }),
  getPlanLines: ({ planId, page = 1, pageSize = 20, storeId, warehouseId, priority } = {}) => {
    const params = new URLSearchParams({ page, page_size: pageSize });
    if (storeId) params.append('store_id', storeId);
    if (warehouseId) params.append('warehouse_id', warehouseId);
    if (priority) params.append('priority', priority);
    return request(`/plan/${planId}/lines?${params.toString()}`);
  },
  getPlanExportUrl: (planId) => `${API_BASE}/plan/${planId}/export`,

  // What-If
  runWhatifOutage: ({ basePlanId, outageWarehouseId, workers = 4 }) =>
    request('/whatif', {
      method: 'POST',
      body: JSON.stringify({
        base_plan_id: basePlanId,
        outage_warehouse_id: outageWarehouseId,
        workers,
      }),
    }),

  // Backtest
  startBacktest: ({ seeds = [11], scenarios = ['normal', 'scarcity'], policies = ['B1', 'B2', 'O_MA', 'VITARANIQ'] } = {}) =>
    request('/backtest', {
      method: 'POST',
      body: JSON.stringify({ seeds, scenarios, policies }),
    }),
  getBacktestRun: (runId) => request(`/backtest/${runId}`),
};
