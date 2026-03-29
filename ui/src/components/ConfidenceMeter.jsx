import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

export default function ConfidenceMeter({ confidence, breakdown }) {
  const [expanded, setExpanded] = useState(false);

  const pct = Math.round(confidence * 100);
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (confidence * circumference);

  const getColor = (val) => {
    if (val >= 0.7) return 'text-confidence-high';
    if (val >= 0.4) return 'text-confidence-mid';
    return 'text-confidence-low';
  };

  const getStrokeColor = (val) => {
    if (val >= 0.7) return '#34d399';
    if (val >= 0.4) return '#fbbf24';
    return '#f87171';
  };

  const breakdownItems = breakdown ? [
    { label: 'Retrieval', key: 'retrieval_quality', icon: '🔍' },
    { label: 'Adjudication', key: 'adjudication_score', icon: '⚖️' },
    { label: 'Critic', key: 'critic_confidence', icon: '🧪' },
    { label: 'Agreement', key: 'agreement_score', icon: '🤝' },
  ] : [];

  return (
    <div className="glass-card p-4 flex flex-col items-center">
      {/* Radial Gauge */}
      <div className="relative w-28 h-28">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          {/* Background ring */}
          <circle cx="50" cy="50" r={radius} fill="none" stroke="rgba(42,53,80,0.5)" strokeWidth="6" />
          {/* Confidence arc */}
          <circle
            cx="50" cy="50" r={radius}
            fill="none"
            stroke={getStrokeColor(confidence)}
            strokeWidth="6"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            className="transition-all duration-1000 ease-out"
            style={{
              filter: `drop-shadow(0 0 6px ${getStrokeColor(confidence)}40)`,
              animation: 'confidence-fill 1.2s ease-out',
            }}
          />
        </svg>
        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-2xl font-bold ${getColor(confidence)}`}>
            {pct}%
          </span>
          <span className="text-[9px] text-helio-text-muted uppercase tracking-wider">
            Confidence
          </span>
        </div>
      </div>

      {/* Expand breakdown */}
      {breakdown && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 flex items-center gap-1 text-[11px] text-helio-text-muted hover:text-helio-text-dim transition-colors cursor-pointer"
        >
          {expanded ? 'Hide' : 'Breakdown'}
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      )}

      {/* Breakdown bars */}
      {expanded && breakdown && (
        <div className="w-full mt-3 space-y-2 animate-fade-in-up">
          {breakdownItems.map(({ label, key, icon }) => {
            const val = breakdown[key] || 0;
            return (
              <div key={key}>
                <div className="flex items-center justify-between text-[10px] mb-0.5">
                  <span className="text-helio-text-dim">{icon} {label}</span>
                  <span className={`font-mono font-medium ${getColor(val)}`}>
                    {(val * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="h-1.5 bg-helio-surface-3 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{
                      width: `${val * 100}%`,
                      background: getStrokeColor(val),
                      boxShadow: `0 0 6px ${getStrokeColor(val)}40`,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
