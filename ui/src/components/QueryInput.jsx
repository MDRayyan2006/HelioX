import { useState } from 'react';
import { Search, Zap, Cpu, Loader2, Sparkles } from 'lucide-react';
import DocumentUpload from './DocumentUpload';

export default function QueryInput({ onSubmit, isLoading, hideTitle = false, onUploadSuccess }) {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('auto');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;
    onSubmit(query.trim(), mode);
  };

  return (
    <div className="w-full max-w-3xl mx-auto animate-fade-in-up">
      {/* Title */}
      {!hideTitle && (
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-helio-primary via-helio-accent to-helio-accent-2 bg-clip-text text-transparent mb-2">
            HelioX
          </h1>
          <p className="text-helio-text-dim text-sm tracking-wide">
            Adaptive Multi-Agent Intelligence
          </p>
        </div>
      )}

      {/* Search Input */}
      <form onSubmit={handleSubmit} className="relative group" id="query-form">
        <div className="glass-panel p-1 glow-primary transition-all duration-300 group-focus-within:shadow-[0_0_30px_rgba(79,110,247,0.25)]">
          <div className="flex items-center">
            <div className="pl-4 pr-1 text-helio-text-muted">
              <DocumentUpload onUploadSuccess={onUploadSuccess} variant="icon" />
            </div>
            <input
              id="query-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask anything about your documents..."
              className="flex-1 bg-transparent py-4 px-2 text-helio-text placeholder:text-helio-text-muted outline-none text-base"
              disabled={isLoading}
              autoComplete="off"
              spellCheck="false"
              autoFocus
            />
            <button
              id="query-submit"
              type="submit"
              disabled={!query.trim() || isLoading}
              className="mr-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-helio-primary to-helio-accent text-white font-semibold text-sm 
                         disabled:opacity-30 disabled:cursor-not-allowed
                         hover:shadow-[0_0_20px_rgba(79,110,247,0.4)] transition-all duration-200
                         active:scale-95 cursor-pointer flex items-center gap-2"
            >
              {isLoading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Zap size={16} />
              )}
              {isLoading ? 'Reasoning...' : 'Ask'}
            </button>
          </div>
        </div>
      </form>

      {/* Mode Toggle */}
      <div className="flex justify-center mt-4 gap-2">
        <button
          id="mode-auto"
          onClick={() => setMode('auto')}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-medium transition-all duration-200 cursor-pointer
            ${mode === 'auto'
              ? 'bg-helio-success/20 text-helio-success-light border border-helio-success/40'
              : 'text-helio-text-muted hover:text-helio-text-dim border border-transparent'}`}
        >
          <Sparkles size={12} />
          Auto
        </button>
        <button
          id="mode-agent"
          onClick={() => setMode('agent')}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-medium transition-all duration-200 cursor-pointer
            ${mode === 'agent'
              ? 'bg-helio-primary/20 text-helio-primary-light border border-helio-primary/40'
              : 'text-helio-text-muted hover:text-helio-text-dim border border-transparent'}`}
        >
          <Zap size={12} />
          Multi-Agent
        </button>
        <button
          id="mode-legacy"
          onClick={() => setMode('legacy')}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-medium transition-all duration-200 cursor-pointer
            ${mode === 'legacy'
              ? 'bg-helio-accent-2/20 text-helio-accent-2 border border-helio-accent-2/40'
              : 'text-helio-text-muted hover:text-helio-text-dim border border-transparent'}`}
        >
          <Cpu size={12} />
          Legacy
        </button>
      </div>
    </div>
  );
}
