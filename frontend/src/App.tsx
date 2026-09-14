import React, { useState, useEffect } from 'react';
import { ScrapeForm } from './components/ScrapeForm';
import { SlideGallery } from './components/SlideGallery';
import { GoogleAuth, GoogleUserProfile } from './components/GoogleAuth';
import { api, StorageStatus } from './api/client';
import { IconGlobe, IconLayers, IconCloud } from './components/Icons';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'scrape' | 'gallery'>('scrape');
  const [storageStatus, setStorageStatus] = useState<StorageStatus | null>(null);
  const [slideCount, setSlideCount] = useState<number>(0);
  const [googleUser, setGoogleUser] = useState<GoogleUserProfile | null>(null);

  const fetchStatusAndCount = async () => {
    try {
      const status = await api.getStorageStatus();
      setStorageStatus(status);
    } catch {
      // Ignore
    }

    try {
      const slides = await api.getSlides();
      setSlideCount(slides.length);
    } catch {
      // Ignore
    }
  };

  useEffect(() => {
    fetchStatusAndCount();
  }, [activeTab]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--slate-50)' }}>
      {/* Top Navbar */}
      <header
        style={{
          background: '#0f172a',
          color: '#ffffff',
          padding: '0 28px',
          height: '64px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid #1e293b',
          position: 'sticky',
          top: 0,
          zIndex: 40,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: 'var(--radius-sm)',
              background: 'linear-gradient(135deg, #0672cb, #38bdf8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: '800',
              fontSize: '18px',
              color: '#ffffff',
              boxShadow: '0 2px 8px rgba(6, 114, 203, 0.4)',
            }}
          >
            P
          </div>
          <div>
            <h1 style={{ fontSize: '16px', fontWeight: '800', letterSpacing: '-0.2px' }}>
              Slide Scrapper
            </h1>
            <span style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginTop: '-2px' }}>
              PowerPoint Web Scraper & Firebase Storage Studio
            </span>
          </div>
        </div>

        {/* Center Navigation Tabs */}
        <nav style={{ display: 'flex', gap: '6px', background: '#1e293b', padding: '4px', borderRadius: 'var(--radius-md)' }}>
          <button
            type="button"
            onClick={() => setActiveTab('scrape')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 18px',
              borderRadius: 'var(--radius-sm)',
              background: activeTab === 'scrape' ? 'var(--primary)' : 'transparent',
              color: activeTab === 'scrape' ? '#ffffff' : '#94a3b8',
              border: 'none',
              fontWeight: '700',
              fontSize: '13px',
            }}
          >
            <IconGlobe size={16} />
            <span>1. Scrape & Discover</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('gallery')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 18px',
              borderRadius: 'var(--radius-sm)',
              background: activeTab === 'gallery' ? 'var(--primary)' : 'transparent',
              color: activeTab === 'gallery' ? '#ffffff' : '#94a3b8',
              border: 'none',
              fontWeight: '700',
              fontSize: '13px',
            }}
          >
            <IconLayers size={16} />
            <span>2. Slide Gallery</span>
            {slideCount > 0 && (
              <span
                style={{
                  background: activeTab === 'gallery' ? 'rgba(255,255,255,0.25)' : '#334155',
                  color: '#ffffff',
                  padding: '1px 7px',
                  borderRadius: '9999px',
                  fontSize: '11px',
                  fontWeight: '800',
                }}
              >
                {slideCount}
              </span>
            )}
          </button>
        </nav>

        {/* Header Right Side: Firebase Storage Badge & Google Sign-In */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: 'var(--radius-md)',
              background: '#1e293b',
              border: '1px solid #334155',
              fontSize: '12px',
              color: '#e2e8f0',
            }}
          >
            <IconCloud size={14} color="#38bdf8" />
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '11px', color: '#94a3b8' }}>gs://</span>
            <span style={{ fontWeight: '700', color: '#38bdf8' }}>slide-preview.firebasestorage.app</span>
            {storageStatus?.is_connected ? (
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#4ade80' }} title="Firebase Storage Ready" />
            ) : (
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#f59e0b' }} title="Storage Config Active" />
            )}
          </div>

          <div style={{ borderLeft: '1px solid #334155', paddingLeft: '12px' }}>
            <GoogleAuth onUserChange={setGoogleUser} />
          </div>
        </div>
      </header>

      {/* Main Page Area */}
      <main style={{ flex: 1, padding: '32px 24px' }}>
        {activeTab === 'scrape' && (
          <ScrapeForm
            onScrapeComplete={fetchStatusAndCount}
            onNavigateToGallery={() => setActiveTab('gallery')}
            googleUser={googleUser}
          />
        )}
        {activeTab === 'gallery' && (
          <SlideGallery
            onNavigateToScraper={() => setActiveTab('scrape')}
          />
        )}
      </main>
    </div>
  );
};
