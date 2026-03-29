import { useState, useRef } from 'react';
import { Upload, FileText, CheckCircle, AlertCircle, X, Loader2, Paperclip } from 'lucide-react';
import { uploadDocument } from '../services/api';

export default function DocumentUpload({ onUploadSuccess, variant = 'default' }) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploads, setUploads] = useState([]); // { id, name, status, chunks, error }
  const [isOpen, setIsOpen] = useState(false);
  const inputRef = useRef(null);

  const handleFiles = async (files) => {
    for (const file of files) {
      const id = Date.now() + Math.random();
      const entry = { id, name: file.name, status: 'uploading', chunks: 0, error: null };
      setUploads(prev => [entry, ...prev]);

      try {
        const result = await uploadDocument(file);
        setUploads(prev =>
          prev.map(u => u.id === id
            ? { ...u, status: 'success', chunks: result.chunks_ingested }
            : u
          )
        );
        if (onUploadSuccess) {
          onUploadSuccess({ name: file.name, chunks: result.chunks_ingested, uploadedAt: new Date().toISOString() });
        }
      } catch (err) {
        setUploads(prev =>
          prev.map(u => u.id === id
            ? { ...u, status: 'error', error: err.message }
            : u
          )
        );
      }
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  };

  const onDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const onDragLeave = () => setIsDragging(false);

  const onFileSelect = (e) => {
    if (e.target.files.length) {
      handleFiles(Array.from(e.target.files));
      e.target.value = '';
    }
  };

  if (variant === 'icon') {
    return (
      <div className="relative flex items-center">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="p-2 text-helio-text-muted hover:text-white transition-colors cursor-pointer rounded-full hover:bg-white/5"
          title="Attach Document"
        >
          <Paperclip size={20} />
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md"
          multiple
          onChange={onFileSelect}
          className="hidden"
        />
        {uploads.some(u => u.status === 'uploading') && (
           <Loader2 size={12} className="absolute top-0 right-0 text-helio-accent animate-spin" />
        )}
      </div>
    );
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 px-4 py-2 rounded-xl
                   bg-helio-surface/60 backdrop-blur-md
                   border border-white/[.06]
                   text-helio-text-muted hover:text-helio-text
                   hover:border-helio-accent/30
                   transition-all duration-200 text-sm"
      >
        <Upload size={16} />
        Upload Documents
      </button>
    );
  }

  return (
    <div className="glass-card p-5 animate-fade-in-up max-w-xl mx-auto mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-helio-text flex items-center gap-2">
          <Upload size={16} className="text-helio-accent" />
          Document Ingestion
        </h3>
        <button onClick={() => setIsOpen(false)} className="text-helio-text-muted hover:text-helio-text">
          <X size={16} />
        </button>
      </div>

      {/* Drop zone */}
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200
          ${isDragging
            ? 'border-helio-accent bg-helio-accent/[.05]'
            : 'border-white/[.08] hover:border-helio-primary/30 bg-helio-surface/30'
          }`}
      >
        <Upload size={32} className={`mx-auto mb-3 ${isDragging ? 'text-helio-accent' : 'text-helio-text-muted'}`} />
        <p className="text-sm text-helio-text-muted mb-1">
          Drag &amp; drop files here or <span className="text-helio-primary underline">browse</span>
        </p>
        <p className="text-xs text-helio-text-muted/60">
          Supports PDF, TXT, MD
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md"
          multiple
          onChange={onFileSelect}
          className="hidden"
        />
      </div>

      {/* Upload list */}
      {uploads.length > 0 && (
        <div className="mt-4 space-y-2 max-h-48 overflow-y-auto">
          {uploads.map(u => (
            <div key={u.id} className="flex items-center gap-3 p-3 rounded-lg bg-helio-surface/40 text-sm">
              <FileText size={16} className="text-helio-text-muted flex-shrink-0" />
              <span className="flex-1 truncate text-helio-text">{u.name}</span>

              {u.status === 'uploading' && (
                <Loader2 size={16} className="text-helio-accent animate-spin flex-shrink-0" />
              )}
              {u.status === 'success' && (
                <span className="flex items-center gap-1 text-xs text-green-400 flex-shrink-0">
                  <CheckCircle size={14} /> {u.chunks} chunks
                </span>
              )}
              {u.status === 'error' && (
                <span className="flex items-center gap-1 text-xs text-red-400 flex-shrink-0" title={u.error}>
                  <AlertCircle size={14} /> Failed
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
