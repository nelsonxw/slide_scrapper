import React, { useEffect, useState } from 'react';
import { StoredSlideCard } from '../api/client';
import { IconX, IconDownload, IconTrash, IconExternalLink, IconCloud, IconEye } from './Icons';

interface SlidePreviewModalProps {
  slide: StoredSlideCard | null;
  onClose: () => void;
  onDeleteSingle: (slideId: string) => void;
}

export const SlidePreviewModal: React.FC<SlidePreviewModalProps> = ({
  slide,
  onClose,
  onDeleteSingle,
}) => {
  const [viewMode, setViewMode] = useState<'image' | 'pptx'>('pptx');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!slide) return null;

  const officeViewerUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(slide.pptx_url)}`;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(4px)',
        zIndex: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}
      onClick={onClose}
    >
      <div
        className="animate-fade-in"
        style={{
          background: '#ffffff',
          borderRadius: 'var(--radius-lg)',
          maxWidth: '1000px',
          width: '100%',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: 'var(--shadow-xl)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '16px 24px',
            borderBottom: '1px solid var(--slate-200)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: '800', color: 'var(--slate-900)' }}>
              {slide.title}
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--slate-500)' }}>
              Presentation: {slide.original_presentation_name} (Slide {slide.slide_index + 1} of {slide.total_slides})
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ display: 'flex', background: 'var(--slate-100)', borderRadius: 'var(--radius-sm)', padding: '3px' }}>
              <button
                type="button"
                onClick={() => setViewMode('pptx')}
                style={{
                  background: viewMode === 'pptx' ? '#ffffff' : 'transparent',
                  color: viewMode === 'pptx' ? 'var(--slate-900)' : 'var(--slate-500)',
                  border: 'none',
                  padding: '6px 12px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <IconEye size={14} />
                <span>PowerPoint</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode('image')}
                style={{
                  background: viewMode === 'image' ? '#ffffff' : 'transparent',
                  color: viewMode === 'image' ? 'var(--slate-900)' : 'var(--slate-500)',
                  border: 'none',
                  padding: '6px 12px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                }}
              >
                <span>Image</span>
              </button>
            </div>

            <button
              type="button"
              onClick={onClose}
              style={{
                background: 'var(--slate-100)',
                border: 'none',
                borderRadius: '50%',
                width: '32px',
                height: '32px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--slate-600)',
              }}
            >
              <IconX size={18} />
            </button>
          </div>
        </div>

        {/* Modal Body: PowerPoint Viewer or Preview Image */}
        <div
          style={{
            padding: '0',
            background: 'var(--slate-900)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
            flex: 1,
          }}
        >
          {viewMode === 'pptx' ? (
            <iframe
              src={officeViewerUrl}
              title="PowerPoint Viewer"
              style={{
                width: '100%',
                height: '100%',
                border: 'none',
              }}
              sandbox="allow-scripts allow-same-origin allow-popups"
            />
          ) : (
            <div
              style={{
                padding: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '100%',
                height: '100%',
                overflow: 'auto',
              }}
            >
              <img
                src={slide.preview_url}
                alt={slide.title}
                style={{
                  maxWidth: '100%',
                  maxHeight: '100%',
                  objectFit: 'contain',
                  borderRadius: 'var(--radius-sm)',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                }}
              />
            </div>
          )}
        </div>

        {/* Modal Footer: Metadata & Actions */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid var(--slate-200)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
            background: 'var(--slate-50)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <IconCloud size={14} color="var(--primary)" />
              <span style={{ fontSize: '11px', color: 'var(--slate-500)', fontFamily: 'JetBrains Mono, monospace' }}>
                Firebase: {slide.storage_pptx_path}
              </span>
            </div>
            {slide.original_source_url && (
              <a
                href={slide.original_source_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  color: 'var(--primary)',
                  fontSize: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  textDecoration: 'none',
                }}
              >
                <span>Original source page</span>
                <IconExternalLink size={12} />
              </a>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              type="button"
              onClick={() => {
                if (confirm(`Delete slide '${slide.title}' from Firebase Storage?`)) {
                  onDeleteSingle(slide.id);
                  onClose();
                }
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'var(--danger-light)',
                color: 'var(--danger-hover)',
                border: '1px solid #fca5a5',
                padding: '8px 14px',
                borderRadius: 'var(--radius-md)',
                fontSize: '13px',
                fontWeight: '700',
              }}
            >
              <IconTrash size={16} />
              <span>Delete from Firebase</span>
            </button>

            <a
              href={slide.pptx_url}
              download={slide.slide_filename}
              target="_blank"
              rel="noreferrer"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'var(--primary)',
                color: '#ffffff',
                textDecoration: 'none',
                padding: '8px 18px',
                borderRadius: 'var(--radius-md)',
                fontSize: '13px',
                fontWeight: '700',
              }}
            >
              <IconDownload size={16} />
              <span>Download .pptx</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};
