import React, { useState } from 'react';
import { StoredSlideCard } from '../api/client';
import { IconDownload, IconEye, IconExternalLink, IconLayers } from './Icons';

interface SlideCardProps {
  slide: StoredSlideCard;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  onOpenPreview: (slide: StoredSlideCard) => void;
}

export const SlideCard: React.FC<SlideCardProps> = ({
  slide,
  isSelected,
  onToggleSelect,
  onOpenPreview,
}) => {
  const [imgError, setImgError] = useState(false);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 KB';
    const k = 1024;
    return `${(bytes / k).toFixed(1)} KB`;
  };

  return (
    <div
      style={{
        background: '#ffffff',
        borderRadius: 'var(--radius-md)',
        border: isSelected ? '2px solid var(--primary)' : '1px solid var(--slate-200)',
        boxShadow: isSelected ? '0 0 0 3px var(--primary-light)' : 'var(--shadow-sm)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        transition: 'all 0.15s ease',
        position: 'relative',
      }}
    >
      {/* Top Slide Preview Thumbnail */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          paddingTop: '56.25%', // 16:9 Aspect Ratio
          background: 'var(--slate-100)',
          cursor: 'pointer',
          overflow: 'hidden',
        }}
        onClick={() => onOpenPreview(slide)}
      >
        {!imgError ? (
          <img
            src={slide.preview_url}
            alt={slide.title}
            onError={() => setImgError(true)}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              transition: 'transform 0.2s ease',
            }}
          />
        ) : (
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--slate-400)',
              gap: '6px',
            }}
          >
            <IconLayers size={32} />
            <span style={{ fontSize: '11px', fontWeight: '600' }}>PowerPoint Slide</span>
          </div>
        )}

        {/* Slide Number Badge */}
        <span
          style={{
            position: 'absolute',
            bottom: '8px',
            right: '8px',
            background: 'rgba(15, 23, 42, 0.85)',
            color: '#ffffff',
            padding: '2px 8px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            fontWeight: '700',
            backdropFilter: 'blur(4px)',
          }}
        >
          Slide {slide.slide_index + 1} of {slide.total_slides}
        </span>
      </div>

      {/* Card Selection Checkbox overlay */}
      <div
        style={{
          position: 'absolute',
          top: '8px',
          left: '8px',
          zIndex: 2,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(slide.id)}
          style={{
            width: '18px',
            height: '18px',
            cursor: 'pointer',
            accentColor: 'var(--primary)',
            borderRadius: '4px',
          }}
        />
      </div>

      {/* Card Body Details */}
      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', flex: 1, gap: '8px' }}>
        <h4
          title={slide.title}
          style={{
            fontSize: '14px',
            fontWeight: '700',
            color: 'var(--slate-800)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {slide.title}
        </h4>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
          <span
            title={slide.original_presentation_name}
            style={{
              fontSize: '12px',
              color: 'var(--slate-500)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            Deck: {slide.original_presentation_name}
          </span>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '4px' }}>
            <span style={{ fontSize: '11px', color: 'var(--slate-400)', fontWeight: '600' }}>
              {formatBytes(slide.file_size)}
            </span>

            {slide.original_source_url && (
              <a
                href={slide.original_source_url}
                target="_blank"
                rel="noreferrer"
                title="View original download link"
                style={{
                  color: 'var(--primary)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '11px',
                  textDecoration: 'none',
                  fontWeight: '600',
                }}
              >
                <span>Source</span>
                <IconExternalLink size={12} />
              </a>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: 'auto', paddingTop: '10px', borderTop: '1px solid var(--slate-100)' }}>
          <button
            type="button"
            onClick={() => onOpenPreview(slide)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              background: 'var(--slate-100)',
              color: 'var(--slate-700)',
              border: 'none',
              padding: '6px 10px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              fontWeight: '600',
            }}
          >
            <IconEye size={14} />
            <span>Preview</span>
          </button>

          <a
            href={slide.pptx_url}
            download={slide.slide_filename}
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              background: 'var(--primary-light)',
              color: 'var(--primary)',
              textDecoration: 'none',
              padding: '6px 10px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              fontWeight: '600',
            }}
          >
            <IconDownload size={14} />
            <span>.pptx</span>
          </a>
        </div>
      </div>
    </div>
  );
};
