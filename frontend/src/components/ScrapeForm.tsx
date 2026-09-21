import React, { useState, useEffect, useRef } from 'react';
import { api, ScrapeTaskStatus } from '../api/client';
import { IconGlobe, IconLayers, IconCheckCircle, IconAlertTriangle, IconCloud } from './Icons';

import { BrowserSessionAuth } from './BrowserSessionAuth';

interface ScrapeFormProps {
  onScrapeComplete?: () => void;
  onNavigateToGallery?: () => void;
}

const PRESET_URLS = [
  { label: 'SlidesCarnival Free Templates', url: 'https://www.slidescarnival.com/category/free-templates' },
  { label: 'Sample PowerPoint Repository', url: 'https://github.com/microsoft/PowerPoint-Add-in-Samples' },
];

export const ScrapeForm: React.FC<ScrapeFormProps> = ({ onScrapeComplete, onNavigateToGallery }) => {
  const [url, setUrl] = useState('');
  const [maxPages, setMaxPages] = useState(100);
  const [maxDepth, setMaxDepth] = useState(4);
  const [consecutiveGateThreshold, setConsecutiveGateThreshold] = useState(3);
  const [consecutiveEmptyThreshold, setConsecutiveEmptyThreshold] = useState(3);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeTask, setActiveTask] = useState<ScrapeTaskStatus | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [logsCopied, setLogsCopied] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);

  // Poll task status while running
  useEffect(() => {
    if (!activeTask || activeTask.status === 'completed' || activeTask.status === 'failed' || activeTask.status === 'cancelled') {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const updated = await api.getScrapeStatus(activeTask.task_id);
        setActiveTask(updated);
        if (updated.status === 'completed') {
          if (onScrapeComplete) onScrapeComplete();
        }
      } catch (err: any) {
        console.error('Error polling scrape task:', err);
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [activeTask, onScrapeComplete]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const task = await api.startScrape({
        url: url.trim(),
        max_pages: maxPages,
        max_depth: maxDepth,
        enable_pagination: true,
        consecutive_gate_threshold: consecutiveGateThreshold,
        consecutive_empty_threshold: consecutiveEmptyThreshold,
      });
      setActiveTask(task);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to start scraping task.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    if (!activeTask) return;
    try {
      await api.cancelScrape(activeTask.task_id);
      setActiveTask((prev) => (prev ? { ...prev, status: 'cancelling', current_step: 'Cancelling task...' } : null));
    } catch (err: any) {
      console.error('Failed to cancel task:', err);
    }
  };

  const handleCopyLogs = async () => {
    if (!activeTask?.logs.length) return;
    try {
      await navigator.clipboard.writeText(activeTask.logs.join('\\n'));
      setLogsCopied(true);
      window.setTimeout(() => setLogsCopied(false), 1600);
    } catch (err) {
      setErrorMessage(err instanceof Error ? `Unable to copy logs: ${err.message}` : 'Unable to copy logs.');
    }
  };

  const isRunning = activeTask && (activeTask.status === 'running' || activeTask.status === 'queued' || activeTask.status === 'cancelling');

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Introduction Card */}
      <div
        style={{
          background: '#ffffff',
          borderRadius: 'var(--radius-lg)',
          padding: '28px',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--slate-200)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <div
            style={{
              background: 'var(--primary-light)',
              color: 'var(--primary)',
              padding: '10px',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <IconGlobe size={24} />
          </div>
          <div>
            <h2 style={{ fontSize: '20px', fontWeight: '800', color: 'var(--slate-900)' }}>
              PowerPoint Web Scraper & Slide Processor
            </h2>
            <p style={{ color: 'var(--slate-500)', fontSize: '14px' }}>
              Enter a website URL to crawl the site & sub-pages, find download buttons, verify PowerPoint presentations, split into single-slide files, and save directly to Firebase Storage.
            </p>
          </div>
        </div>

        {errorMessage && (
          <div
            style={{
              marginTop: '16px',
              padding: '12px 16px',
              background: 'var(--danger-light)',
              color: 'var(--danger-hover)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid #fca5a5',
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <IconAlertTriangle size={18} />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Scrape Input Form */}
        <form onSubmit={handleSubmit} style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: '700', color: 'var(--slate-700)', marginBottom: '8px' }}>
              Target Website URL
            </label>
            <div style={{ display: 'flex', gap: '10px' }}>
              <div style={{ position: 'relative', flex: 1 }}>
                <input
                  type="text"
                  placeholder="https://example.com/templates or direct .pptx link"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  disabled={Boolean(isRunning)}
                  required
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--slate-300)',
                    fontSize: '14px',
                    outline: 'none',
                    background: isRunning ? 'var(--slate-100)' : '#ffffff',
                  }}
                />
              </div>

              {!isRunning ? (
                <button
                  type="submit"
                  disabled={isSubmitting || !url.trim()}
                  style={{
                    background: isSubmitting || !url.trim() ? 'var(--slate-300)' : 'var(--primary)',
                    color: '#ffffff',
                    border: 'none',
                    padding: '0 24px',
                    borderRadius: 'var(--radius-md)',
                    fontWeight: '700',
                    fontSize: '14px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: isSubmitting || !url.trim() ? 'not-allowed' : 'pointer',
                  }}
                >
                  {isSubmitting ? (
                    <>
                      <div className="animate-spin" style={{ width: '16px', height: '16px', border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%' }} />
                      Starting...
                    </>
                  ) : (
                    <>
                      <IconGlobe size={18} />
                      Start Scraping
                    </>
                  )}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleCancel}
                  style={{
                    background: 'var(--danger)',
                    color: '#ffffff',
                    border: 'none',
                    padding: '0 20px',
                    borderRadius: 'var(--radius-md)',
                    fontWeight: '700',
                    fontSize: '14px',
                    cursor: 'pointer',
                  }}
                >
                  Cancel Task
                </button>
              )}
            </div>

            {/* Quick URL Presets */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '10px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '12px', color: 'var(--slate-400)', fontWeight: '600' }}>Quick suggestions:</span>
              {PRESET_URLS.map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setUrl(p.url)}
                  disabled={Boolean(isRunning)}
                  style={{
                    background: 'var(--slate-100)',
                    color: 'var(--slate-700)',
                    border: '1px solid var(--slate-200)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '4px 10px',
                    fontSize: '12px',
                    cursor: isRunning ? 'not-allowed' : 'pointer',
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Crawl Settings */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '16px',
              padding: '16px',
              background: 'var(--slate-50)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--slate-200)',
            }}
          >
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: '700', color: 'var(--slate-700)' }}>
                  Max Sub-pages to Crawl
                </label>
                <span style={{ fontSize: '12px', fontWeight: '800', color: 'var(--primary)' }}>{maxPages} pages</span>
              </div>
              <input
                type="range"
                min={50}
                max={10000}
                step={50}
                value={maxPages}
                onChange={(e) => setMaxPages(Number(e.target.value))}
                disabled={Boolean(isRunning)}
                style={{ width: '100%', accentColor: 'var(--primary)', cursor: 'pointer' }}
              />
              <span style={{ fontSize: '11px', color: 'var(--slate-400)' }}>Limits the breadth of internal links searched</span>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: '700', color: 'var(--slate-700)' }}>
                  Crawl Depth
                </label>
                <span style={{ fontSize: '12px', fontWeight: '800', color: 'var(--primary)' }}>
                  {maxDepth === 0 ? 'Page Only (Depth 0)' : `Level ${maxDepth}`}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={10}
                value={maxDepth}
                onChange={(e) => setMaxDepth(Number(e.target.value))}
                disabled={Boolean(isRunning)}
                style={{ width: '100%', accentColor: 'var(--primary)', cursor: 'pointer' }}
              />
              <span style={{ fontSize: '11px', color: 'var(--slate-400)' }}>
                {maxDepth === 0 ? 'Exclusively searches the target page' : 'Hierarchy depth of link navigation'}
              </span>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: '700', color: 'var(--slate-700)' }}>
                  Gate Skip Threshold
                </label>
                <span style={{ fontSize: '12px', fontWeight: '800', color: 'var(--primary)' }}>
                  {consecutiveGateThreshold} pages
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={10}
                value={consecutiveGateThreshold}
                onChange={(e) => setConsecutiveGateThreshold(Number(e.target.value))}
                disabled={Boolean(isRunning)}
                style={{ width: '100%', accentColor: 'var(--primary)', cursor: 'pointer' }}
              />
              <span style={{ fontSize: '11px', color: 'var(--slate-400)' }}>
                Skip pagination after N consecutive gated pages
              </span>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: '700', color: 'var(--slate-700)' }}>
                  Empty Page Threshold
                </label>
                <span style={{ fontSize: '12px', fontWeight: '800', color: 'var(--primary)' }}>
                  {consecutiveEmptyThreshold} pages
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={10}
                value={consecutiveEmptyThreshold}
                onChange={(e) => setConsecutiveEmptyThreshold(Number(e.target.value))}
                disabled={Boolean(isRunning)}
                style={{ width: '100%', accentColor: 'var(--primary)', cursor: 'pointer' }}
              />
              <span style={{ fontSize: '11px', color: 'var(--slate-400)' }}>
                Skip pagination after N consecutive empty pages (no files found)
              </span>
            </div>
          </div>

          <BrowserSessionAuth targetUrl={url} />
        </form>
      </div>

      {/* Real-time Task Monitor */}
      {activeTask && (
        <div
          className="animate-fade-in"
          style={{
            background: '#ffffff',
            borderRadius: 'var(--radius-lg)',
            padding: '24px',
            boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--slate-200)',
            display: 'flex',
            flexDirection: 'column',
            gap: '20px',
          }}
        >
          {/* Status Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 12px',
                    borderRadius: '9999px',
                    fontSize: '12px',
                    fontWeight: '800',
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    background:
                      activeTask.status === 'running'
                        ? 'var(--primary-light)'
                        : activeTask.status === 'completed'
                        ? 'var(--success-light)'
                        : activeTask.status === 'failed'
                        ? 'var(--danger-light)'
                        : 'var(--warning-light)',
                    color:
                      activeTask.status === 'running'
                        ? 'var(--primary)'
                        : activeTask.status === 'completed'
                        ? 'var(--success)'
                        : activeTask.status === 'failed'
                        ? 'var(--danger)'
                        : 'var(--warning)',
                  }}
                >
                  {activeTask.status === 'running' && (
                    <div className="animate-spin" style={{ width: '10px', height: '10px', border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%' }} />
                  )}
                  {activeTask.status === 'completed' && <IconCheckCircle size={14} />}
                  {activeTask.status}
                </span>

                <span style={{ fontSize: '14px', fontWeight: '700', color: 'var(--slate-800)' }}>
                  {activeTask.current_step}
                </span>
              </div>
              <span style={{ fontSize: '12px', color: 'var(--slate-400)', marginTop: '4px', display: 'block' }}>
                Target: {activeTask.target_url}
              </span>
            </div>

            {activeTask.status === 'completed' && onNavigateToGallery && (
              <button
                type="button"
                onClick={onNavigateToGallery}
                style={{
                  background: 'var(--success)',
                  color: '#ffffff',
                  border: 'none',
                  padding: '8px 18px',
                  borderRadius: 'var(--radius-md)',
                  fontWeight: '700',
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <IconLayers size={16} />
                View in Slide Gallery ({activeTask.uploaded_slides_count})
              </button>
            )}
          </div>

          {/* Metric Counter Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            <div style={{ background: 'var(--slate-50)', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--slate-200)' }}>
              <span style={{ fontSize: '12px', color: 'var(--slate-500)', fontWeight: '600' }}>PPTX Files Discovered</span>
              <p style={{ fontSize: '24px', fontWeight: '800', color: 'var(--slate-900)', marginTop: '4px' }}>
                {activeTask.discovered_files_count}
              </p>
            </div>

            <div style={{ background: 'var(--slate-50)', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--slate-200)' }}>
              <span style={{ fontSize: '12px', color: 'var(--slate-500)', fontWeight: '600' }}>Split Slide Files Created</span>
              <p style={{ fontSize: '24px', fontWeight: '800', color: 'var(--primary)', marginTop: '4px' }}>
                {activeTask.total_slides_created}
              </p>
            </div>

            <div style={{ background: 'var(--slate-50)', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid var(--slate-200)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '12px', color: 'var(--slate-500)', fontWeight: '600' }}>Saved to Firebase Storage</span>
                <IconCloud size={14} color="var(--primary)" />
              </div>
              <p style={{ fontSize: '24px', fontWeight: '800', color: 'var(--success)', marginTop: '4px' }}>
                {activeTask.uploaded_slides_count}
              </p>
            </div>
          </div>

          {/* Terminal Console Logs */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', gap: '12px' }}>
              <span style={{ fontSize: '12px', fontWeight: '700', color: 'var(--slate-600)' }}>Live Pipeline Logs</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '11px', color: 'var(--slate-400)', fontFamily: 'JetBrains Mono, monospace' }}>
                  {activeTask.logs.length} events
                </span>
                <button
                  type="button"
                  onClick={handleCopyLogs}
                  disabled={!activeTask.logs.length}
                  style={{
                    background: '#ffffff',
                    color: 'var(--slate-700)',
                    border: '1px solid var(--slate-300)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '5px 10px',
                    fontSize: '11px',
                    fontWeight: 700,
                    cursor: activeTask.logs.length ? 'pointer' : 'not-allowed',
                    opacity: activeTask.logs.length ? 1 : 0.6,
                  }}
                >
                  {logsCopied ? 'Copied' : 'Copy logs'}
                </button>
              </div>
            </div>
            <div
              className="terminal-scroll"
              style={{
                background: '#0f172a',
                color: '#38bdf8',
                borderRadius: 'var(--radius-md)',
                padding: '14px 16px',
                height: '240px',
                overflowY: 'auto',
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '12px',
                lineHeight: '1.6',
                border: '1px solid #1e293b',
              }}
            >
              {activeTask.logs.map((logStr, i) => (
                <div key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: logStr.includes('Error') ? '#f87171' : logStr.includes('Saved') || logStr.includes('complete') ? '#4ade80' : '#e2e8f0' }}>
                  {logStr}
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
