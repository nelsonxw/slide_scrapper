import React, { useEffect, useState, useRef } from 'react';

export interface GoogleUserProfile {
  email: string;
  name: string;
  picture: string;
  token: string;
}

interface GoogleAuthProps {
  onUserChange?: (user: GoogleUserProfile | null) => void;
}

export const GoogleAuth: React.FC<GoogleAuthProps> = ({ onUserChange }) => {
  const [clientId, setClientId] = useState<string>(() => {
    return (
      localStorage.getItem('slide_scrapper_google_client_id') ||
      (import.meta as any).env?.VITE_GOOGLE_CLIENT_ID ||
      ''
    );
  });

  const [isEditingClientId, setIsEditingClientId] = useState(false);
  const [tempClientId, setTempClientId] = useState(clientId);

  const [user, setUser] = useState<GoogleUserProfile | null>(() => {
    try {
      const saved = localStorage.getItem('slide_scrapper_google_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const buttonRef = useRef<HTMLDivElement>(null);

  const parseJwt = (token: string) => {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(
        atob(base64)
          .split('')
          .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      );
      return JSON.parse(jsonPayload);
    } catch {
      return null;
    }
  };

  const handleCredentialResponse = (response: any) => {
    if (response.credential) {
      const payload = parseJwt(response.credential);
      if (payload) {
        const newUser: GoogleUserProfile = {
          email: payload.email || '',
          name: payload.name || payload.email || 'Google User',
          picture: payload.picture || '',
          token: response.credential,
        };
        setUser(newUser);
        localStorage.setItem('slide_scrapper_google_user', JSON.stringify(newUser));
        if (onUserChange) onUserChange(newUser);
      }
    }
  };

  useEffect(() => {
    if (user && onUserChange) {
      onUserChange(user);
    }
  }, []);

  useEffect(() => {
    if (!clientId) return;

    const initGsi = () => {
      const google = (window as any).google;
      if (google && google.accounts && google.accounts.id) {
        try {
          google.accounts.id.initialize({
            client_id: clientId.trim(),
            callback: handleCredentialResponse,
            auto_select: false,
          });

          if (buttonRef.current && !user) {
            buttonRef.current.innerHTML = '';
            google.accounts.id.renderButton(buttonRef.current, {
              theme: 'outline',
              size: 'medium',
              type: 'standard',
              shape: 'pill',
              text: 'signin_with',
            });
          }
        } catch (err) {
          console.error('Google GSI initialization error:', err);
        }
      }
    };

    if ((window as any).google) {
      initGsi();
    } else {
      const interval = setInterval(() => {
        if ((window as any).google) {
          clearInterval(interval);
          initGsi();
        }
      }, 300);
      return () => clearInterval(interval);
    }
  }, [clientId, user]);

  const handleSaveClientId = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = tempClientId.trim();
    setClientId(clean);
    localStorage.setItem('slide_scrapper_google_client_id', clean);
    setIsEditingClientId(false);
  };

  const handleSignOut = () => {
    setUser(null);
    localStorage.removeItem('slide_scrapper_google_user');
    if (onUserChange) onUserChange(null);
  };

  if (user) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {user.picture ? (
          <img
            src={user.picture}
            alt={user.name}
            style={{ width: '28px', height: '28px', borderRadius: '50%', border: '1px solid #38bdf8' }}
          />
        ) : (
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: '50%',
              background: '#0672cb',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '12px',
              fontWeight: '700',
            }}
          >
            {user.name[0]}
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', textAlign: 'left' }}>
          <span style={{ fontSize: '11px', fontWeight: '700', color: '#f8fafc', lineHeight: 1.2 }}>{user.name}</span>
          <span style={{ fontSize: '10px', color: '#94a3b8', lineHeight: 1.2 }}>{user.email}</span>
        </div>
        <button
          type="button"
          onClick={handleSignOut}
          style={{
            background: 'transparent',
            border: '1px solid #475569',
            color: '#cbd5e1',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 8px',
            fontSize: '11px',
            cursor: 'pointer',
            marginLeft: '4px',
          }}
        >
          Sign Out
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      {clientId ? (
        <div ref={buttonRef} />
      ) : (
        <button
          type="button"
          onClick={() => setIsEditingClientId(true)}
          style={{
            background: '#1e293b',
            color: '#38bdf8',
            border: '1px solid #0284c7',
            borderRadius: '9999px',
            padding: '6px 14px',
            fontSize: '12px',
            fontWeight: '700',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span>🔐 Set Google Client ID</span>
        </button>
      )}

      <button
        type="button"
        title="Configure Google OAuth Client ID"
        onClick={() => {
          setTempClientId(clientId);
          setIsEditingClientId(true);
        }}
        style={{
          background: 'transparent',
          border: 'none',
          color: '#94a3b8',
          fontSize: '14px',
          cursor: 'pointer',
          padding: '4px',
        }}
      >
        ⚙️
      </button>

      {/* Google Client ID Config Modal */}
      {isEditingClientId && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            backdropFilter: 'blur(4px)',
            zIndex: 100,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
          }}
          onClick={() => setIsEditingClientId(false)}
        >
          <div
            style={{
              background: '#ffffff',
              borderRadius: 'var(--radius-lg)',
              maxWidth: '520px',
              width: '100%',
              padding: '24px',
              boxShadow: 'var(--shadow-xl)',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '16px', fontWeight: '800', color: 'var(--slate-900)' }}>
                Google OAuth Client ID Configuration
              </h3>
              <button
                type="button"
                onClick={() => setIsEditingClientId(false)}
                style={{ background: 'transparent', border: 'none', fontSize: '16px', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--slate-600)', lineHeight: '1.5' }}>
              Google Sign-In requires your Google Cloud or Firebase OAuth 2.0 Web Client ID.
            </p>

            <div
              style={{
                background: 'var(--slate-50)',
                padding: '12px 14px',
                borderRadius: 'var(--radius-md)',
                fontSize: '12px',
                color: 'var(--slate-700)',
                border: '1px solid var(--slate-200)',
                lineHeight: '1.6',
              }}
            >
              <strong>Quick Setup Steps:</strong>
              <ol style={{ paddingLeft: '18px', marginTop: '4px' }}>
                <li>Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer" style={{ color: 'var(--primary)', fontWeight: '600' }}>Google Cloud Credentials</a> (or Firebase Authentication → Sign-in method → Google).</li>
                <li>Under <strong>OAuth 2.0 Client IDs</strong>, click or create a <strong>Web application</strong> client.</li>
                <li>Add <code style={{ background: '#e2e8f0', padding: '1px 4px', borderRadius: '3px' }}>http://localhost:5173</code> to <strong>Authorized JavaScript origins</strong>.</li>
                <li>Copy the Client ID and paste it below.</li>
              </ol>
            </div>

            <form onSubmit={handleSaveClientId} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: '700', color: 'var(--slate-700)', marginBottom: '6px' }}>
                  Google OAuth 2.0 Client ID
                </label>
                <input
                  type="text"
                  placeholder="e.g. 1234567890-abcdefg.apps.googleusercontent.com"
                  value={tempClientId}
                  onChange={(e) => setTempClientId(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--slate-300)',
                    fontSize: '13px',
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                  required
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setIsEditingClientId(false)}
                  style={{
                    padding: '8px 16px',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--slate-300)',
                    background: 'transparent',
                    color: 'var(--slate-700)',
                    fontSize: '13px',
                    fontWeight: '600',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    padding: '8px 20px',
                    borderRadius: 'var(--radius-md)',
                    border: 'none',
                    background: 'var(--primary)',
                    color: '#ffffff',
                    fontSize: '13px',
                    fontWeight: '700',
                  }}
                >
                  Save & Initialize
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
