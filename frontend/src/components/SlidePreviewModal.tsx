import React, { useEffect } from 'react';
import { StoredSlideCard } from '../api/client';
import { IconX, IconDownload, IconTrash, IconExternalLink, IconCloud } from './Icons';

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
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!slide) return null;

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
          maxWidth: '900px',
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

        {/* Modal Body: Slide Preview Image */}
        <div
          style={{
            padding: '24px',
            background: 'var(--slate-900)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'auto',
          }}
        >
          <img
            src={slide.preview_url}
            alt={slide.title}
            style={{
              maxWidth: '100%',
              maxHeight: '52vh',
              objectFit: 'contain',
              borderRadius: 'var(--radius-sm)',
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            }}
          />
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
