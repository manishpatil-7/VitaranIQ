import React, { useState } from 'react';
import { 
  Network, 
  Building, 
  Search
} from 'lucide-react';

const WAREHOUSES = [
  { id: 'W1', name: 'Pune Fulfillment Center', lat: 18.5204, lon: 73.8567, fleet: 30, share: '35%', region: 'Western' },
  { id: 'W2', name: 'Mumbai-Bhiwandi Hub', lat: 19.0760, lon: 72.8777, fleet: 30, share: '30%', region: 'Konkan' },
  { id: 'W3', name: 'Nashik Regional Depot', lat: 20.0000, lon: 73.7900, fleet: 30, share: '20%', region: 'Northern' },
  { id: 'W4', name: 'Kolhapur Distribution Center', lat: 16.7100, lon: 74.2400, fleet: 30, share: '15%', region: 'Southern' },
];

const STORES = [
  { id: 'S01', city: 'Pune', region: 'Western', mult: 0.5, cap: 9000 },
  { id: 'S02', city: 'Pune', region: 'Western', mult: 0.6, cap: 10800 },
  { id: 'S03', city: 'Mumbai', region: 'Konkan', mult: 0.6, cap: 10800 },
  { id: 'S04', city: 'Mumbai', region: 'Konkan', mult: 0.7, cap: 12600 },
  { id: 'S05', city: 'Thane', region: 'Konkan', mult: 0.8, cap: 14400 },
  { id: 'S06', city: 'Thane', region: 'Konkan', mult: 0.8, cap: 14400 },
  { id: 'S07', city: 'Nashik', region: 'Northern', mult: 0.9, cap: 16200 },
  { id: 'S08', city: 'Nashik', region: 'Northern', mult: 0.9, cap: 16200 },
  { id: 'S09', city: 'Kolhapur', region: 'Southern', mult: 1.0, cap: 18000 },
  { id: 'S10', city: 'Kolhapur', region: 'Southern', mult: 1.0, cap: 18000 },
  { id: 'S11', city: 'Satara', region: 'Western', mult: 1.0, cap: 18000 },
  { id: 'S12', city: 'Satara', region: 'Western', mult: 1.1, cap: 19800 },
  { id: 'S13', city: 'Sangli', region: 'Southern', mult: 1.1, cap: 19800 },
  { id: 'S14', city: 'Sangli', region: 'Southern', mult: 1.2, cap: 21600 },
  { id: 'S15', city: 'Solapur', region: 'Central', mult: 1.2, cap: 21600 },
  { id: 'S16', city: 'Solapur', region: 'Central', mult: 1.2, cap: 21600 },
  { id: 'S17', city: 'Ahmednagar', region: 'Northern', mult: 1.3, cap: 23400 },
  { id: 'S18', city: 'Ahmednagar', region: 'Northern', mult: 1.4, cap: 25200 },
  { id: 'S19', city: 'Aurangabad', region: 'Central', mult: 1.5, cap: 27000 },
  { id: 'S20', city: 'Aurangabad', region: 'Central', mult: 1.5, cap: 27000 },
  { id: 'S21', city: 'Ichalkaranji', region: 'Southern', mult: 1.6, cap: 28800 },
  { id: 'S22', city: 'Ichalkaranji', region: 'Southern', mult: 1.7, cap: 30600 },
  { id: 'S23', city: 'Karad', region: 'Western', mult: 1.8, cap: 32400 },
  { id: 'S24', city: 'Karad', region: 'Western', mult: 2.0, cap: 36000 },
  { id: 'S25', city: 'Pune Hub Store', region: 'Western', mult: 1.0, cap: 18000 },
];

const SKUS = [
  { id: 'MILK-1L', name: 'Fresh Pasteurized Milk 1L', category: 'Dairy', cost: 52, price: 60, volume: 1200, life: 5, minLife: 3, q: 'P70' },
  { id: 'CURD-400G', name: 'Set Curd 400g', category: 'Dairy', cost: 28, price: 34, volume: 500, life: 10, minLife: 5, q: 'P70' },
  { id: 'BREAD-400G', name: 'White Sliced Bread 400g', category: 'Bakery', cost: 30, price: 40, volume: 2500, life: 4, minLife: 2, q: 'P70' },
  { id: 'BISC-250', name: 'Marie Biscuit Pack 250g', category: 'Snacks', cost: 22, price: 30, volume: 800, life: 180, minLife: 72, q: 'P90' },
  { id: 'NOODLE-70', name: 'Instant Masala Noodles 70g', category: 'Snacks', cost: 11, price: 14, volume: 400, life: 270, minLife: 108, q: 'P80' },
  { id: 'RICE-5KG', name: 'Basmati Rice 5kg Bag', category: 'Staples', cost: 310, price: 360, volume: 6500, life: 365, minLife: 120, q: 'P80' },
  { id: 'ATTA-5KG', name: 'Chakki Fresh Atta 5kg', category: 'Staples', cost: 240, price: 275, volume: 6500, life: 120, minLife: 48, q: 'P80' },
  { id: 'OIL-1L', name: 'Refined Sunflower Oil 1L', category: 'Staples', cost: 140, price: 160, volume: 1100, life: 270, minLife: 108, q: 'P80' },
  { id: 'TEA-250G', name: 'Premium CTC Tea 250g', category: 'Beverages', cost: 110, price: 130, volume: 900, life: 365, minLife: 120, q: 'P80' },
  { id: 'SOAP-100G', name: 'Grade 1 Bath Soap 100g', category: 'Personal', cost: 32, price: 40, volume: 250, life: 730, minLife: 240, q: 'P90' },
  { id: 'CHOC-50G', name: 'Milk Chocolate Bar 50g', category: 'Impulse', cost: 35, price: 50, volume: 120, life: 180, minLife: 60, q: 'P90' },
  { id: 'JUICE-1L', name: 'Mixed Fruit Juice 1L', category: 'Beverages', cost: 85, price: 110, volume: 1150, life: 90, minLife: 30, q: 'P80' },
];

export default function NetworkTopologyView() {
  const [activeSection, setActiveSection] = useState('warehouses');
  const [skuSearch, setSkuSearch] = useState('');

  const filteredSkus = SKUS.filter(
    (p) =>
      p.name.toLowerCase().includes(skuSearch.toLowerCase()) ||
      p.id.toLowerCase().includes(skuSearch.toLowerCase()) ||
      p.category.toLowerCase().includes(skuSearch.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="ent-card p-6 border-l-4 border-l-indigo-600">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="p-1.5 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200">
                <Network className="w-4 h-4" />
              </span>
              <h2 className="text-lg font-bold text-slate-900 font-display">
                Maharashtra Supply Chain Network Topology
              </h2>
            </div>
            <p className="text-xs text-slate-500 mt-1.5 max-w-2xl leading-relaxed">
              Configured master parameters (params.yaml): 4 regional fulfillment centers, 25 retail destinations, 12 SKU profiles, and dedicated 120-truck logistics fleet with exact transport tariffs.
            </p>
          </div>

          {/* Sub-tabs */}
          <div className="p-1 rounded-lg bg-slate-100 border border-slate-200 flex items-center space-x-1 text-xs">
            <button
              onClick={() => setActiveSection('warehouses')}
              className={`px-3 py-1.5 rounded-md font-medium transition ${
                activeSection === 'warehouses'
                  ? 'bg-white text-indigo-700 font-semibold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Warehouses (4)
            </button>
            <button
              onClick={() => setActiveSection('stores')}
              className={`px-3 py-1.5 rounded-md font-medium transition ${
                activeSection === 'stores'
                  ? 'bg-white text-indigo-700 font-semibold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Stores (25)
            </button>
            <button
              onClick={() => setActiveSection('products')}
              className={`px-3 py-1.5 rounded-md font-medium transition ${
                activeSection === 'products'
                  ? 'bg-white text-indigo-700 font-semibold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Products (12)
            </button>
          </div>
        </div>
      </div>

      {/* Fleet & Lane Parameters Card */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="ent-card p-4">
          <span className="text-slate-500 uppercase tracking-wider block text-[10px] font-semibold">Standard Truck Fleet</span>
          <span className="text-lg font-bold text-slate-900 font-display mt-0.5 block">4,000 Litres</span>
          <span className="text-slate-500 block mt-0.5 font-mono text-[11px]">4,000,000 ml payload</span>
        </div>
        <div className="ent-card p-4">
          <span className="text-slate-500 uppercase tracking-wider block text-[10px] font-semibold">Fixed Truck Dispatch</span>
          <span className="text-lg font-bold text-slate-900 font-display mt-0.5 block">₹800 / Truck</span>
          <span className="text-slate-500 block mt-0.5 font-mono text-[11px]">80,000 paise base fee</span>
        </div>
        <div className="ent-card p-4">
          <span className="text-slate-500 uppercase tracking-wider block text-[10px] font-semibold">Variable Mileage</span>
          <span className="text-lg font-bold text-emerald-700 font-display mt-0.5 block">₹14.00 / km</span>
          <span className="text-slate-500 block mt-0.5 font-mono text-[11px]">1,400 paise/km</span>
        </div>
        <div className="ent-card p-4">
          <span className="text-slate-500 uppercase tracking-wider block text-[10px] font-semibold">Lane Restrictions</span>
          <span className="text-lg font-bold text-indigo-700 font-display mt-0.5 block">≤ 450 km</span>
          <span className="text-slate-500 block mt-0.5 font-mono text-[11px]">1.30× Haversine factor</span>
        </div>
      </div>

      {/* Section 1: Warehouses */}
      {activeSection === 'warehouses' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {WAREHOUSES.map((w) => (
            <div key={w.id} className="ent-card p-5 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                    {w.id}
                  </span>
                  <h3 className="text-sm font-bold text-slate-900 mt-1.5 font-display">{w.name}</h3>
                </div>
                <div className="p-2 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-100">
                  <Building className="w-4 h-4" />
                </div>
              </div>

              <div className="space-y-1.5 text-xs font-mono pt-3 border-t border-slate-100">
                <div className="flex justify-between text-slate-500">
                  <span>Region:</span>
                  <span className="text-slate-800 font-medium">{w.region}</span>
                </div>
                <div className="flex justify-between text-slate-500">
                  <span>Coordinates:</span>
                  <span className="text-slate-700">{w.lat.toFixed(2)}°N, {w.lon.toFixed(2)}°E</span>
                </div>
                <div className="flex justify-between text-slate-500">
                  <span>Fleet Quota:</span>
                  <span className="text-emerald-700 font-bold">{w.fleet} Trucks</span>
                </div>
                <div className="flex justify-between text-slate-500">
                  <span>Inbound Inflow:</span>
                  <span className="text-indigo-700 font-bold">{w.share} of total</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Section 2: Stores */}
      {activeSection === 'stores' && (
        <div className="ent-card overflow-hidden">
          <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs">
            <h3 className="font-bold text-slate-900 font-display">25 Supermarket & Retail Store Nodes</h3>
            <span className="text-slate-500 font-mono">18,000 Litres Base Capacity × Size Multiplier</span>
          </div>
          <div className="overflow-x-auto max-h-96">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="sticky top-0 bg-slate-100 border-b border-slate-200 text-slate-500 font-mono uppercase text-[11px]">
                <tr>
                  <th className="py-2.5 px-4">Store ID</th>
                  <th className="py-2.5 px-4">Anchor City</th>
                  <th className="py-2.5 px-4">Region</th>
                  <th className="py-2.5 px-4 text-right">Size Factor</th>
                  <th className="py-2.5 px-4 text-right">Storage Volume (L)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {STORES.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2.5 px-4 font-mono font-bold text-indigo-700">{s.id}</td>
                    <td className="py-2.5 px-4 text-slate-800 font-medium">{s.city}</td>
                    <td className="py-2.5 px-4 text-slate-500 font-mono text-[11px]">{s.region}</td>
                    <td className="py-2.5 px-4 text-right font-mono text-slate-700">{s.mult}x</td>
                    <td className="py-2.5 px-4 text-right font-mono font-bold text-emerald-700">
                      {s.cap.toLocaleString()} L
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Section 3: Products */}
      {activeSection === 'products' && (
        <div className="ent-card overflow-hidden space-y-3">
          <div className="p-4 bg-slate-50 border-b border-slate-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <h3 className="font-bold text-slate-900 font-display text-xs">12 High-Velocity FMCG Product SKUs</h3>
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search SKU..."
                value={skuSearch}
                onChange={(e) => setSkuSearch(e.target.value)}
                className="pl-8 pr-3 py-1 rounded-lg bg-white border border-slate-300 text-xs font-mono text-slate-800 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 w-48"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50/50 border-b border-slate-200 text-slate-500 font-mono uppercase text-[11px]">
                  <th className="py-2.5 px-4">SKU ID</th>
                  <th className="py-2.5 px-4">Product Name</th>
                  <th className="py-2.5 px-3">Category</th>
                  <th className="py-2.5 px-3 text-right">Cost (₹)</th>
                  <th className="py-2.5 px-3 text-right">Price (₹)</th>
                  <th className="py-2.5 px-3 text-right">Margin (%)</th>
                  <th className="py-2.5 px-3 text-right">Shelf Life</th>
                  <th className="py-2.5 px-3 text-right">Min Life (Arrival)</th>
                  <th className="py-2.5 px-3 text-center">Quantile</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredSkus.map((sku) => {
                  const marginPct = Math.round(((sku.price - sku.cost) / sku.price) * 100);
                  const isShortLife = sku.life <= 10;
                  return (
                    <tr key={sku.id} className="hover:bg-slate-50 transition-colors">
                      <td className="py-2.5 px-4 font-mono font-bold text-indigo-700">{sku.id}</td>
                      <td className="py-2.5 px-4 text-slate-800 font-medium">{sku.name}</td>
                      <td className="py-2.5 px-3 text-slate-500 font-mono text-[11px]">{sku.category}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-slate-700">₹{sku.cost.toFixed(2)}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-slate-900 font-semibold">₹{sku.price.toFixed(2)}</td>
                      <td className="py-2.5 px-3 text-right font-mono font-bold text-emerald-700">{marginPct}%</td>
                      <td className="py-2.5 px-3 text-right font-mono">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                          isShortLife ? 'bg-red-50 text-red-700 border border-red-200 font-bold' : 'text-slate-600'
                        }`}>
                          {sku.life} Days
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-slate-500">{sku.minLife} Days</td>
                      <td className="py-2.5 px-3 text-center">
                        <span className="px-2 py-0.5 rounded font-mono font-bold text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-200">
                          {sku.q}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
