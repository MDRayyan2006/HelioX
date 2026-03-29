import { useState, useEffect, useRef } from 'react';
import { Copy, Check, BookOpen, ThumbsUp, ThumbsDown } from 'lucide-react';

export default function AnswerDisplay({ answer, citations, isStreaming, queryText }) {
  const [displayedText, setDisplayedText] = useState('');
  const [copied, setCopied] = useState(false);
  const [ratedScore, setRatedScore] = useState(0);
  const containerRef = useRef(null);

  // Simulated streaming effect
  useEffect(() => {
    if (!answer) { setDisplayedText(''); return; }
    if (!isStreaming) { setDisplayedText(answer); return; }

    let idx = 0;
    const speed = 8; // chars per tick
    const timer = setInterval(() => {
      idx += speed;
      if (idx >= answer.length) {
        setDisplayedText(answer);
        clearInterval(timer);
      } else {
        setDisplayedText(answer.slice(0, idx));
      }
    }, 16);
    return () => clearInterval(timer);
  }, [answer, isStreaming]);

  const handleCopy = () => {
    navigator.clipboard.writeText(answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Reset rating on new answer
  useEffect(() => {
    setRatedScore(0);
  }, [answer]);

  const handleFeedback = async (score) => {
    if (ratedScore !== 0) return;
    setRatedScore(score);
    try {
      await fetch('http://localhost:8000/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query_text: queryText, score })
      });
    } catch (e) {
      console.error("Feedback error:", e);
    }
  };

  if (!answer) return null;

  // Basic markdown-to-HTML (bold, code, lists)
  const renderMarkdown = (text) => {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong class="text-helio-text font-semibold">$1</strong>')
      .replace(/`(.*?)`/g, '<code class="px-1.5 py-0.5 rounded bg-helio-surface-3 text-helio-accent text-sm font-mono">$1</code>')
      .replace(/^\d+\.\s+/gm, (match) => `<span class="text-helio-primary font-semibold">${match}</span>`)
      .replace(/\n\n/g, '</p><p class="mb-3">')
      .replace(/\n/g, '<br/>');
  };

  return (
    <div className="w-full max-w-3xl mx-auto mt-6 animate-fade-in-up" ref={containerRef}>
      {/* Answer Card */}
      <div className="glass-panel p-6 relative">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-helio-primary-light">
            <BookOpen size={16} />
            <span className="text-xs font-semibold uppercase tracking-wider">Answer</span>
          </div>
          <button
            onClick={handleCopy}
            className="p-2 rounded-lg hover:bg-helio-surface-3 text-helio-text-muted hover:text-helio-text transition-colors cursor-pointer"
            title="Copy answer"
          >
            {copied ? <Check size={14} className="text-helio-success" /> : <Copy size={14} />}
          </button>
        </div>

        {/* Answer Text */}
        <div
          className="text-helio-text/90 leading-relaxed text-[15px]"
          dangerouslySetInnerHTML={{ __html: '<p class="mb-3">' + renderMarkdown(displayedText) + '</p>' }}
        />

        {/* Streaming cursor */}
        {isStreaming && displayedText.length < answer.length && (
          <span className="inline-block w-2 h-5 bg-helio-primary animate-pulse ml-0.5 rounded-sm" />
        )}

        {/* Feedback Widget */}
        {queryText && !isStreaming && (
          <div className="mt-6 pt-4 border-t border-white/5 flex items-center gap-3">
            <span className="text-[10px] text-helio-text-muted font-bold uppercase tracking-widest mr-2">Rate Answer</span>
            <button 
              onClick={() => handleFeedback(1)}
              disabled={ratedScore !== 0}
              className={`p-1.5 rounded-md transition-all ${ratedScore === 1 ? 'bg-helio-success/20 text-helio-success' : 'hover:bg-white/10 text-helio-text-muted hover:text-helio-success'} disabled:cursor-not-allowed`}
              title="Helpful"
            >
              <ThumbsUp size={14} className={ratedScore === 1 ? 'fill-helio-success' : ''} />
            </button>
            <button 
              onClick={() => handleFeedback(-1)}
              disabled={ratedScore !== 0}
              className={`p-1.5 rounded-md transition-all ${ratedScore === -1 ? 'bg-red-500/20 text-red-400' : 'hover:bg-white/10 text-helio-text-muted hover:text-red-400'} disabled:cursor-not-allowed`}
              title="Unhelpful"
            >
              <ThumbsDown size={14} className={ratedScore === -1 ? 'fill-red-400' : ''} />
            </button>
            {ratedScore === 1 && <span className="text-xs text-helio-success ml-2 animate-fade-in">Feedback saved!</span>}
            {ratedScore === -1 && <span className="text-xs text-red-400 ml-2 animate-fade-in">Noted! Tuning parameters for next time...</span>}
          </div>
        )}
      </div>

      {/* Citations */}
      {citations && citations.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-xs font-semibold text-helio-text-muted uppercase tracking-wider px-1 mb-2">
            Sources ({citations.length})
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {citations.map((cite, i) => (
              <div
                key={cite.chunk_id || i}
                className="glass-card p-3 hover:border-helio-primary/40 transition-all duration-200 cursor-pointer group"
              >
                <div className="flex items-start gap-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-helio-primary/20 text-helio-primary-light flex items-center justify-center text-[10px] font-bold">
                    {i + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-helio-text truncate group-hover:text-helio-primary-light transition-colors">
                      {cite.source}
                    </p>
                    <p className="text-[11px] text-helio-text-muted mt-0.5 line-clamp-2">
                      {(cite.text || '').slice(0, 100)}...
                    </p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-helio-success/10 text-helio-success">
                        {(cite.score * 100).toFixed(0)}%
                      </span>
                      {cite.page && (
                        <span className="text-[10px] text-helio-text-muted">
                          p.{cite.page}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
