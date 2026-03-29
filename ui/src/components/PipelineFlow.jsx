import { useState, useEffect, useRef } from 'react';
import {
  Search, Database, GitBranch, Users, Scale, FileText, Shield,
  RotateCcw, CheckCircle2, XCircle, Loader2, Clock, ChevronDown, ChevronUp
} from 'lucide-react';

const NODE_CONFIG = [
  { key: 'cache',       label: 'Cache',         icon: Database,    color: '#06b6d4' },
  { key: 'analyzer',    label: 'Analyzer',       icon: Search,      color: '#f97316' },
  { key: 'retriever',   label: 'Retriever',      icon: GitBranch,   color: '#22c55e' },
  { key: 'workers',     label: 'Workers',        icon: Users,       color: '#a855f7' },
  { key: 'adjudicator', label: 'Adjudicator',    icon: Scale,       color: '#eab308' },
  { key: 'composer',    label: 'Composer',       icon: FileText,    color: '#78716c' },
  { key: 'critic',      label: 'Critic',         icon: Shield,      color: '#ef4444' },
];

function NodeCard({ config, stage, isActive, isComplete, index }) {
  const Icon = config.icon;
  const status = stage?.status || 'pending';

  // Determine output display
  const getOutputText = () => {
    if (!stage?.output) return null;
    const o = stage.output;
    switch (config.key) {
      case 'cache':       return o.hit ? '🟢 HIT' : '🔴 MISS';
      case 'analyzer':    return `${o.keyword_count || 0} kw · ${o.entity_count || 0} ent`;
      case 'retriever':   return `k=${o.top_k} · ${o.chunks_returned} chunks`;
      case 'workers':     return `${o.count}× ${o.parallel ? 'parallel' : 'serial'}`;
      case 'adjudicator': return `${o.claims} claims · ${o.conflicts ? '⚠️' : '✅'}`;
      case 'composer':    return `${o.answer_length} chars`;
      case 'critic':      return `${o.verdict} · ${(o.confidence * 100).toFixed(0)}%`;
      default:            return null;
    }
  };

  return (
    <div
      className={`
        relative flex flex-col items-center justify-center p-3 rounded-xl min-w-[100px]
        border transition-all duration-500 group cursor-default
        ${status === 'complete'
          ? 'border-opacity-60 bg-opacity-20'
          : isActive
            ? 'border-opacity-80 animate-pulse-glow'
            : 'border-helio-border/30 bg-helio-surface/40'}
      `}
      style={{
        borderColor: status === 'complete' || isActive ? config.color + '60' : undefined,
        backgroundColor: status === 'complete' ? config.color + '10' : isActive ? config.color + '15' : undefined,
        animationDelay: `${index * 100}ms`,
      }}
    >
      {/* Status indicator */}
      <div className="absolute -top-1.5 -right-1.5">
        {status === 'complete' && <CheckCircle2 size={14} className="text-helio-success" />}
        {isActive && <Loader2 size={14} className="text-helio-primary animate-spin" />}
      </div>

      {/* Icon */}
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center mb-1.5"
        style={{ background: config.color + '20' }}
      >
        <Icon size={18} style={{ color: config.color }} />
      </div>

      {/* Label */}
      <span className="text-[11px] font-semibold text-helio-text">{config.label}</span>

      {/* Output data */}
      {stage?.output && (
        <span className="text-[9px] text-helio-text-dim mt-0.5 font-mono text-center whitespace-nowrap">
          {getOutputText()}
        </span>
      )}

      {/* Duration */}
      {stage?.duration_ms != null && (
        <span className="text-[8px] text-helio-text-muted mt-0.5 flex items-center gap-0.5">
          <Clock size={8} /> {stage.duration_ms}ms
        </span>
      )}
    </div>
  );
}

function ConnectorArrow({ animated }) {
  return (
    <div className="flex items-center mx-1">
      <div className="relative h-0.5 w-8 bg-helio-border/40 rounded">
        {animated && (
          <div
            className="absolute top-0 left-0 h-full w-3 rounded"
            style={{
              background: 'linear-gradient(90deg, transparent, #4f6ef7, transparent)',
              animation: 'shimmer 1.5s ease-in-out infinite',
              backgroundSize: '200% 100%',
            }}
          />
        )}
      </div>
      <div className="w-0 h-0 border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[6px] border-l-helio-border/60" />
    </div>
  );
}

export default function PipelineFlow({ trace }) {
  const [showRetry, setShowRetry] = useState(false);
  const [animatedIndex, setAnimatedIndex] = useState(-1);

  // Animate nodes sequentially on mount
  useEffect(() => {
    if (!trace) return;
    let i = 0;
    const timer = setInterval(() => {
      setAnimatedIndex(i);
      i++;
      if (i >= trace.stages.length) clearInterval(timer);
    }, 300);
    return () => clearInterval(timer);
  }, [trace]);

  if (!trace) return null;

  const retryTrace = trace.retry_trace;
  const totalDuration = trace.stages.reduce((sum, s) => sum + (s.duration_ms || 0), 0);

  return (
    <div className="w-full animate-fade-in-up">
      <div className="glass-panel p-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <GitBranch size={16} className="text-helio-primary-light" />
            <span className="text-xs font-semibold uppercase tracking-wider text-helio-primary-light">
              Pipeline Flow
            </span>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-helio-text-muted">
            <span className="flex items-center gap-1">
              <Clock size={11} /> {totalDuration}ms total
            </span>
            {retryTrace && (
              <span className="flex items-center gap-1">
                <RotateCcw size={11} /> {retryTrace.total_attempts} attempt{retryTrace.total_attempts > 1 ? 's' : ''}
              </span>
            )}
            {trace.cache_hit && (
              <span className="px-2 py-0.5 rounded-full bg-helio-success/15 text-helio-success font-medium">
                CACHED
              </span>
            )}
          </div>
        </div>

        {/* Node Graph — horizontal n8n-style flow */}
        <div className="overflow-x-auto pb-2">
          <div className="flex items-center justify-center min-w-fit py-3">
            {NODE_CONFIG.map((config, index) => {
              const stage = trace.stages.find(s => s.key === config.key || s.name === config.key);
              const isActive = index === animatedIndex && stage?.status !== 'complete';
              const isComplete = index <= animatedIndex;
              return (
                <div key={config.key} className="flex items-center">
                  {index > 0 && <ConnectorArrow animated={isComplete} />}
                  <NodeCard
                    config={config}
                    stage={stage}
                    isActive={isActive}
                    isComplete={isComplete}
                    index={index}
                  />
                </div>
              );
            })}
          </div>
        </div>

        {/* Retry Loop Indicator */}
        {retryTrace && retryTrace.total_attempts > 1 && (
          <div className="mt-3 border-t border-helio-border/30 pt-3">
            <button
              onClick={() => setShowRetry(!showRetry)}
              className="flex items-center gap-2 text-[11px] text-helio-text-dim hover:text-helio-text transition-colors cursor-pointer w-full"
            >
              <RotateCcw size={12} className="text-node-retry" />
              <span className="font-medium">
                Retry Loop: {retryTrace.total_attempts} attempts
                {retryTrace.improved && (
                  <span className="ml-2 text-helio-success">
                    ↗ +{(retryTrace.confidence_delta * 100).toFixed(1)}% confidence
                  </span>
                )}
              </span>
              {showRetry ? <ChevronUp size={12} className="ml-auto" /> : <ChevronDown size={12} className="ml-auto" />}
            </button>

            {showRetry && (
              <div className="mt-3 space-y-2 animate-fade-in-up">
                {retryTrace.attempts.map((attempt, i) => (
                  <div
                    key={i}
                    className={`flex items-start gap-3 p-3 rounded-lg border text-[11px] ${
                      i === retryTrace.best_attempt
                        ? 'border-helio-success/30 bg-helio-success/5'
                        : 'border-helio-border/20 bg-helio-surface/30'
                    }`}
                  >
                    {/* Attempt number */}
                    <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                      attempt.verdict === 'PASS'
                        ? 'bg-helio-success/20 text-helio-success'
                        : attempt.verdict === 'PARTIAL'
                          ? 'bg-helio-warning/20 text-helio-warning'
                          : 'bg-helio-danger/20 text-helio-danger'
                    }`}>
                      {attempt.attempt}
                    </div>

                    <div className="flex-1 min-w-0">
                      {/* Query */}
                      <p className="text-helio-text-dim font-mono truncate">
                        "{attempt.query_used}"
                      </p>
                      <div className="flex items-center gap-3 mt-1">
                        <span className={`font-semibold ${
                          attempt.verdict === 'PASS' ? 'text-helio-success'
                            : attempt.verdict === 'PARTIAL' ? 'text-helio-warning'
                              : 'text-helio-danger'
                        }`}>
                          {attempt.verdict}
                        </span>
                        <span className="text-helio-text-muted font-mono">
                          conf: {(attempt.confidence * 100).toFixed(0)}%
                        </span>
                        <span className="text-helio-text-muted">
                          {attempt.chunk_ids.length} chunks
                        </span>
                      </div>
                      {/* Issues */}
                      {attempt.issues.length > 0 && (
                        <div className="mt-1.5 space-y-0.5">
                          {attempt.issues.map((issue, j) => (
                            <p key={j} className="text-helio-danger/80 text-[10px]">⚠ {issue}</p>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Best badge */}
                    {i === retryTrace.best_attempt && (
                      <span className="flex-shrink-0 text-[9px] px-2 py-0.5 rounded-full bg-helio-success/15 text-helio-success font-semibold">
                        BEST
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
