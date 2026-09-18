import React, { useEffect, useState } from 'react';
import { StoredSlideCard } from '../api/client';
import { IconX, IconDownload, IconTrash, IconExternalLink, IconCloud, IconEye, IconLayers } from './Icons';

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
  const [viewMode, setViewMode] = useState<'image' | 'pptx'>('image');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    setViewMode('image');
  }, [slide?.id]);

  if (!slide) return null;

  const pptxPublicUrl = slide.public_pptx_url || (slide.pptx_url.startsWith('http') ? slide.pptx_url : `${window.location.origin}${slide.pptx_url}`);
  const officeViewerUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(pptxPublicUrl)}`;

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
            gap: '12px',
          }}
        >
          <div style={{ overflow: 'hidden' }}>
            <h3 style={{ fontSize: '16px', fontWeight: '800', color: 'var(--slate-900)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
              {slide.title}
            </h3>
            <span style={{ fontSize: '12px', color: 'var(--slate-500)' }}>
              Presentation: {slide.original_presentation_name} (Slide {slide.slide_index + 1} of {slide.total_slides})
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
            {/* View Mode Toggle */}
            <div style={{ display: 'flex', background: 'var(--slate-100)', borderRadius: 'var(--radius-sm)', padding: '3px' }}>
              <button
                type="button"
                onClick={() => setViewMode('pptx')}
                style={{
                  background: viewMode === 'pptx' ? '#ffffff' : 'transparent',
                  color: viewMode === 'pptx' ? 'var(--slate-900)' : 'var(--slate-500)',
                  border: 'none',
                  padding: '5px 12px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  boxShadow: viewMode === 'pptx' ? 'var(--shadow-sm)' : 'none',
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
                  padding: '5px 12px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  boxShadow: viewMode === 'image' ? 'var(--shadow-sm)' : 'none',
                }}
              >
                <IconLayers size={14} />
                <span>Slide Image</span>
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
                cursor: 'pointer',
              }}
            >
              <IconX size={18} />
            </button>
          </div>
        </div>

        {/* Modal Body: PowerPoint Viewer or Slide Image */}
        <div
          style={{
            padding: '0',
            background: 'var(--slate-900)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
            flex: 1,
            position: 'relative',
            minHeight: '480px',
          }}
        >
          {viewMode === 'pptx' ? (
            <>
              <iframe
                src={officeViewerUrl}
                title="PowerPoint Viewer"
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                  flex: 1,
                }}
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-presentation"
                allowFullScreen
              />
              <div
                style={{
                  padding: '8px 16px',
                  background: 'rgba(15, 23, 42, 0.95)',
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  borderTop: '1px solid rgba(255, 255, 255, 0.1)',
                  fontSize: '12px',
                  color: 'var(--slate-300)',
                }}
              >
                <span>If PowerPoint Online shows a license error or is blocked by your network:</span>
                <button
                  type="button"
                  onClick={() => setViewMode('image')}
                  style={{
                    background: 'var(--primary)',
                    color: '#ffffff',
                    border: 'none',
                    padding: '4px 10px',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '11px',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  View Slide Image Preview
                </button>
              </div>
            </>
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
                  maxHeight: '65vh',
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
                cursor: 'pointer',
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
