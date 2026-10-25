import React from 'react';
import { PackageOpen } from 'lucide-react';

export default function EmptyState({
  icon: Icon = PackageOpen,
  title,
  description,
  actionLabel,
  onAction,
  isLoading = false,
}) {
  return (
    <div className="ent-card p-10 flex flex-col items-center justify-center text-center">
      <div className="p-3 rounded-xl bg-slate-100 text-slate-500 mb-3 border border-slate-200">
        <Icon className="w-6 h-6 text-slate-600" />
      </div>
      <h3 className="text-sm font-semibold text-slate-900 font-display">
        {title}
      </h3>
      <p className="text-xs text-slate-500 max-w-sm mt-1 mb-4 leading-relaxed">
        {description}
      </p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          disabled={isLoading}
          className="px-3.5 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-xs transition disabled:opacity-50"
        >
          {isLoading ? 'Processing...' : actionLabel}
        </button>
      )}
    </div>
  );
}
