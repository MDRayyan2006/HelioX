import { useState } from 'react';
import {
  Brain, Trophy, Sparkles, ChevronDown, ChevronUp, Gauge
} from 'lucide-react';

function ConceptBar({ concept, maxImportance }) {
  const [expanded, setExpanded] = useState(false);
  const pct = (concept.importance / maxImportance) * 100;

  return (
    <div className="group">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left cursor-pointer"
      >
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] font-medium text-helio-text group-hover:text-helio-primary-light transition-colors">
            {concept.name}
          </span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-helio-text-dim">
              {(concept.importance * 100).toFixed(0)}%
            </span>
            {expanded ? <ChevronUp size={10} className="text-helio-text-muted" /> : <ChevronDown size={10} className="text-helio-text-muted" />}
          </div>
        </div>
        <div className="h-1.5 bg-helio-surface-3 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${pct}%`,
              background: `linear-gradient(90deg, #4f6ef7, #22d3ee)`,
              boxShadow: '0 0 8px rgba(79, 110, 247, 0.3)',
            }}
          />
        </div>
      </button>
      {expanded && (
        <div className="mt-1.5 flex flex-wrap gap-1 animate-fade-in-up">
          {concept.members.map(m => (
            <span
              key={m}
              className="px-1.5 py-0.5 rounded text-[9px] bg-helio-primary/10 text-helio-primary-light border border-helio-primary/20"
            >
              {m}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function StrategyRow({ strategy, best }) {
  const domainColors = {
    rewrite: { bg: 'bg-node-critic/10', text: 'text-node-critic', border: 'border-node-critic/20' },
    depth: { bg: 'bg-node-retriever/10', text: 'text-node-retriever', border: 'border-node-retriever/20' },
    routing: { bg: 'bg-node-adjudicator/10', text: 'text-node-adjudicator', border: 'border-node-adjudicator/20' },
  };
  const color = domainColors[strategy.domain] || domainColors.rewrite;
  const successRate = strategy.attempts > 0 ? ((strategy.successes / strategy.attempts) * 100).toFixed(0) : '0';

  return (
    <div className={`flex items-center gap-2 p-2 rounded-lg border transition-all ${best ? 'border-helio-warning/30 bg-helio-warning/5' : 'border-helio-border/10 hover:border-helio-border/30'
      } ${strategy.disabled ? 'opacity-40' : ''}`}>
      {/* Domain tag */}
      <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium border ${color.bg} ${color.text} ${color.border}`}>
        {strategy.domain}
      </span>

      {/* Strategy name */}
      <span className="text-[11px] font-mono text-helio-text flex-1 truncate">
        {strategy.strategy}
      </span>

      {/* Score bar */}
      <div className="w-16 h-1.5 bg-helio-surface-3 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${strategy.score * 100}%`,
            background: strategy.score >= 0.7 ? '#34d399'
              : strategy.score >= 0.5 ? '#fbbf24'
                : '#f87171',
          }}
        />
      </div>

      {/* Score */}
      <span className="text-[10px] font-mono text-helio-text-dim w-10 text-right">
        {(strategy.score * 100).toFixed(0)}%
      </span>

      {/* Success rate */}
      <span className="text-[9px] text-helio-text-muted w-12 text-right">
        {strategy.successes}/{strategy.attempts}
      </span>

      {/* Best badge */}
      {best && (
        <Trophy size={11} className="text-helio-warning flex-shrink-0" />
      )}
    </div>
  );
}

export default function LearningPanel({ learning }) {
  if (!learning) return null;

  const maxImportance = Math.max(...learning.top_concepts.map(c => c.importance));

  // Find best strategy per domain
  const bestPerDomain = {};
  learning.strategy_leaderboard.forEach(s => {
    if (!bestPerDomain[s.domain] || s.score > bestPerDomain[s.domain].score) {
      bestPerDomain[s.domain] = s;
    }
  });

  // Sort leaderboard by score descending
  const sorted = [...learning.strategy_leaderboard].sort((a, b) => b.score - a.score);

  return (
    <div className="glass-panel p-5 animate-fade-in-up">
      <div className="flex items-center gap-2 mb-4">
        <Brain size={16} className="text-helio-accent-2" />
        <span className="text-xs font-semibold uppercase tracking-wider text-helio-accent-2">
          Learning Insights
        </span>
      </div>

      <div className="space-y-5">
        {/* Memory Quality */}
        <div className="flex items-center gap-3 p-3 rounded-xl bg-helio-surface/50 border border-helio-border/20">
          <Gauge size={20} className="text-helio-accent flex-shrink-0" />
          <div className="flex-1">
            <p className="text-[10px] text-helio-text-muted">Memory Quality</p>
            <div className="flex items-center gap-2 mt-0.5">
              <div className="flex-1 h-2 bg-helio-surface-3 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${learning.memory_quality * 100}%`,
                    background: 'linear-gradient(90deg, #4f6ef7, #22d3ee)',
                    boxShadow: '0 0 8px rgba(34, 211, 238, 0.3)',
                  }}
                />
              </div>
              <span className="text-sm font-mono font-bold text-helio-accent">
                {(learning.memory_quality * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>

        {/* Top Concepts */}
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <Sparkles size={12} className="text-helio-primary-light" />
            <p className="text-[10px] text-helio-text-muted uppercase tracking-wider">
              Top Discovered Concepts
            </p>
          </div>
          <div className="space-y-3">
            {learning.top_concepts.map(concept => (
              <ConceptBar
                key={concept.name}
                concept={concept}
                maxImportance={maxImportance}
              />
            ))}
          </div>
        </div>

        {/* Strategy Leaderboard */}
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <Trophy size={12} className="text-helio-warning" />
            <p className="text-[10px] text-helio-text-muted uppercase tracking-wider">
              Strategy Leaderboard
            </p>
          </div>
          <div className="space-y-1.5">
            {sorted.map((strategy, i) => {
              const isBest = bestPerDomain[strategy.domain]?.strategy === strategy.strategy;
              return (
                <StrategyRow
                  key={`${strategy.domain}-${strategy.strategy}`}
                  strategy={strategy}
                  best={isBest}
                />
              );
            })}
          </div>
        </div>

        {/* Entity Boost Cloud */}
        {learning.entity_boosts && Object.keys(learning.entity_boosts).length > 0 && (
          <div>
            <p className="text-[10px] text-helio-text-muted uppercase tracking-wider mb-2">
              Entity Boost Map
            </p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(learning.entity_boosts)
                .sort((a, b) => b[1] - a[1])
                .map(([entity, boost]) => {
                  const size = Math.max(10, Math.min(16, boost * 10));
                  const opacity = Math.max(0.4, Math.min(1, boost / 1.5));
                  return (
                    <span
                      key={entity}
                      className="px-2 py-1 rounded-lg bg-helio-accent-2/10 border border-helio-accent-2/20 font-mono"
                      style={{ fontSize: `${size}px`, opacity }}
                    >
                      <span className="text-helio-accent-2">{entity}</span>
                      <span className="text-helio-text-muted ml-1 text-[8px]">×{boost.toFixed(1)}</span>
                    </span>
                  );
                })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
