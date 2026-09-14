import React, { useEffect, useState } from 'react';
import { api, BrowserSessionStatus } from '../api/client';

interface BrowserSessionAuthProps {
  targetUrl: string;
}

const initialStatus: BrowserSessionStatus = {
  status: 'not_connected',
  site: null,
  message: 'No saved browser session.',
};

export const BrowserSessionAuth: React.FC<BrowserSessionAuthProps> = ({ targetUrl }) => {
  const [session, setSession] = useState<BrowserSessionStatus>(initialStatus);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const refreshSession = async () => {
      try {
        const currentSession = await api.getBrowserSession();
        if (isMounted) setSession(currentSession);
      } catch {
        return;
      }
    };

    refreshSession();
    const interval = window.setInterval(refreshSession, 2000);
    return () => {
      isMounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const connectSession = async () => {
    const loginUrl = targetUrl.trim() || 'https://www.slidemodel.com/account/login/';
    setIsLoading(true);
    setError(null);
    setSession({ status: 'connecting', site: loginUrl, message: 'Complete login in the visible browser window, then close it.' });

    try {
      const result = await api.openBrowserLogin(loginUrl);
      setSession(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to open the browser session.');
      setSession({ status: 'error', site: loginUrl, message: 'The browser session could not be opened.' });
    } finally {
      setIsLoading(false);
    }
  };

  const completeSession = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setSession(await api.completeBrowserSession());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to complete the browser session.');
    } finally {
      setIsLoading(false);
    }
  };

  const clearSession = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setSession(await api.clearBrowserSession());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to clear the browser session.');
    } finally {
      setIsLoading(false);
    }
  };

  const isConnected = session.status === 'authenticated';
  const isBrowserOpen = session.status === 'browser_open';
  const isConnecting = session.status === 'connecting' || isLoading;

  return (
    <section
      style={{
        padding: '16px',
        background: 'var(--slate-50)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--slate-200)',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center' }}>
        <div>
          <strong style={{ display: 'block', fontSize: '13px', color: 'var(--slate-800)' }}>Protected-site session</strong>
          <span style={{ fontSize: '11px', color: 'var(--slate-500)' }}>
            The exact target page opens in one persistent Chrome session. Complete any Google or site sign-in prompt there.
          </span>
        </div>
        <span
          style={{
            padding: '4px 8px',
            borderRadius: '9999px',
            fontSize: '11px',
            fontWeight: 700,
            color: isConnected ? 'var(--success)' : isConnecting || isBrowserOpen ? 'var(--warning)' : 'var(--slate-600)',
            background: isConnected ? 'var(--success-light)' : isConnecting || isBrowserOpen ? 'var(--warning-light)' : 'var(--slate-200)',
            whiteSpace: 'nowrap',
          }}
        >
          {isConnected ? 'Connected' : isBrowserOpen ? 'Chrome is open' : isConnecting ? 'Starting Chrome' : 'Not connected'}
        </span>
      </div>

      <span style={{ fontSize: '12px', color: 'var(--slate-600)' }}>{session.message}</span>
      {session.site && <span style={{ fontSize: '11px', color: 'var(--slate-400)' }}>Site: {session.site}</span>}
      {error && <span style={{ fontSize: '12px', color: 'var(--danger)' }}>{error}</span>}

      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={isBrowserOpen ? completeSession : connectSession}
          disabled={isConnecting}
          style={{
            background: isConnecting ? 'var(--slate-300)' : 'var(--primary)',
            color: '#ffffff',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            padding: '7px 12px',
            fontSize: '12px',
            fontWeight: 700,
          }}
        >
          {isConnecting ? 'Starting Chrome...' : isBrowserOpen ? 'Mark login complete' : isConnected ? 'Reopen Chrome session' : 'Open target in Chrome'}
        </button>
        {isConnected && (
          <button
            type="button"
            onClick={clearSession}
            disabled={isLoading}
            style={{
              background: '#ffffff',
              color: 'var(--slate-700)',
              border: '1px solid var(--slate-300)',
              borderRadius: 'var(--radius-sm)',
              padding: '7px 12px',
              fontSize: '12px',
              fontWeight: 700,
            }}
          >
            Clear saved session
          </button>
        )}
      </div>
    </section>
  );
};
