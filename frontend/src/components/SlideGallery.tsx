import React, { useState, useEffect } from 'react';
import { api, StoredSlideCard } from '../api/client';
import { SlideCard } from './SlideCard';
import { SlidePreviewModal } from './SlidePreviewModal';
import { IconSearch, IconTrash, IconRefresh, IconLayers, IconAlertTriangle } from './Icons';

interface SlideGalleryProps {
  onNavigateToScraper?: () => void;
}

export const SlideGallery: React.FC<SlideGalleryProps> = ({ onNavigateToScraper }) => {
  const [slides, setSlides] = useState<StoredSlideCard[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [previewSlide, setPreviewSlide] = useState<StoredSlideCard | null>(null);

  const fetchSlides = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await api.getSlides(searchTerm);
      setSlides(data);
      // Clean up selected IDs that no longer exist
      const existingIds = new Set(data.map((d) => d.id));
      setSelectedIds((prev) => new Set([...prev].filter((id) => existingIds.has(id))));
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load slides from Firebase.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSlides();
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchSlides();
  };

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedIds.size === slides.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(slides.map((s) => s.id)));
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    const count = selectedIds.size;
    const confirmMsg = `Are you sure you want to permanently delete ${count} slide file${count > 1 ? 's' : ''} from Firebase Storage (gs://slide-preview.firebasestorage.app)?`;
    if (!window.confirm(confirmMsg)) return;

    setIsDeleting(true);
    setErrorMsg(null);
    try {
      const idsToDelete = Array.from(selectedIds);
      await api.deleteSlides(idsToDelete);
      setSelectedIds(new Set());
      await fetchSlides();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to delete selected slides.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteSingle = async (slideId: string) => {
    try {
      await api.deleteSlides([slideId]);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(slideId);
        return next;
      });
      await fetchSlides();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to delete slide.');
    }
  };

  const allSelected = slides.length > 0 && selectedIds.size === slides.length;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Gallery Header & Controls */}
      <div
        style={{
          background: '#ffffff',
          borderRadius: 'var(--radius-lg)',
          padding: '24px',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--slate-200)',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h2 style={{ fontSize: '20px', fontWeight: '800', color: 'var(--slate-900)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <IconLayers size={22} color="var(--primary)" />
              Saved Slide Gallery
            </h2>
            <p style={{ color: 'var(--slate-500)', fontSize: '14px', marginTop: '2px' }}>
              Individual slides stored in Firebase Storage (<span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '12px' }}>gs://slide-preview.firebasestorage.app</span>)
            </p>
          </div>

          {/* Action Toolbar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={fetchSlides}
              disabled={isLoading}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'var(--slate-100)',
                color: 'var(--slate-700)',
                border: '1px solid var(--slate-200)',
                padding: '8px 14px',
                borderRadius: 'var(--radius-md)',
                fontSize: '13px',
                fontWeight: '600',
              }}
            >
              <div className={isLoading ? 'animate-spin' : ''}>
                <IconRefresh size={16} />
              </div>
              <span>Refresh</span>
            </button>

            {selectedIds.size > 0 && (
              <button
                type="button"
                onClick={handleDeleteSelected}
                disabled={isDeleting}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'var(--danger)',
                  color: '#ffffff',
                  border: 'none',
                  padding: '8px 16px',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '13px',
                  fontWeight: '700',
                }}
              >
                {isDeleting ? (
                  <div className="animate-spin" style={{ width: '14px', height: '14px', border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%' }} />
                ) : (
                  <IconTrash size={16} />
                )}
                <span>Delete Selected ({selectedIds.size})</span>
              </button>
            )}
          </div>
        </div>

        {errorMsg && (
          <div
            style={{
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
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Filter Bar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: '8px', flex: 1, maxWidth: '400px' }}>
            <div style={{ position: 'relative', width: '100%' }}>
              <input
                type="text"
                placeholder="Search slides by title or deck..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px 8px 36px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--slate-300)',
                  fontSize: '13px',
                  outline: 'none',
                }}
              />
              <div style={{ position: 'absolute', left: '10px', top: '9px', color: 'var(--slate-400)' }}>
                <IconSearch size={16} />
              </div>
            </div>
            <button
              type="submit"
              style={{
                background: 'var(--primary)',
                color: '#fff',
                border: 'none',
                padding: '0 14px',
                borderRadius: 'var(--radius-md)',
                fontSize: '13px',
                fontWeight: '600',
              }}
            >
              Filter
            </button>
          </form>

          {slides.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: '600', color: 'var(--slate-700)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={handleSelectAll}
                  style={{ width: '16px', height: '16px', cursor: 'pointer', accentColor: 'var(--primary)' }}
                />
                <span>{allSelected ? 'Deselect All' : 'Select All'} ({slides.length})</span>
              </label>
            </div>
          )}
        </div>
      </div>

      {/* Slide Cards Grid */}
      {isLoading ? (
        <div style={{ padding: '64px 0', textAlign: 'center', color: 'var(--slate-400)' }}>
          <div className="animate-spin" style={{ width: '32px', height: '32px', border: '3px solid var(--primary)', borderTopColor: 'transparent', borderRadius: '50%', margin: '0 auto 16px' }} />
          <p style={{ fontSize: '14px', fontWeight: '600' }}>Loading slides from Firebase Storage...</p>
        </div>
      ) : slides.length === 0 ? (
        /* Empty State */
        <div
          style={{
            background: '#ffffff',
            borderRadius: 'var(--radius-lg)',
            padding: '64px 24px',
            textAlign: 'center',
            border: '2px dashed var(--slate-300)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
          }}
        >
          <div style={{ background: 'var(--slate-100)', color: 'var(--slate-400)', padding: '16px', borderRadius: '50%' }}>
            <IconLayers size={40} />
          </div>
          <h3 style={{ fontSize: '18px', fontWeight: '800', color: 'var(--slate-800)' }}>No PowerPoint slides found</h3>
          <p style={{ color: 'var(--slate-500)', fontSize: '14px', maxWidth: '440px' }}>
            Run the scraper on any presentation website to search for download buttons, extract slides, and save them directly here.
          </p>
          {onNavigateToScraper && (
            <button
              type="button"
              onClick={onNavigateToScraper}
              style={{
                marginTop: '12px',
                background: 'var(--primary)',
                color: '#ffffff',
                border: 'none',
                padding: '10px 24px',
                borderRadius: 'var(--radius-md)',
                fontWeight: '700',
                fontSize: '14px',
              }}
            >
              Start New Scrape
            </button>
          )}
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '20px',
          }}
        >
          {slides.map((slide) => (
            <SlideCard
              key={slide.id}
              slide={slide}
              isSelected={selectedIds.has(slide.id)}
              onToggleSelect={handleToggleSelect}
              onOpenPreview={(s) => setPreviewSlide(s)}
            />
          ))}
        </div>
      )}

      {/* Full Preview Modal */}
      <SlidePreviewModal
        slide={previewSlide}
        onClose={() => setPreviewSlide(null)}
        onDeleteSingle={handleDeleteSingle}
      />
    </div>
  );
};
