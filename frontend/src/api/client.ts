export interface ScrapeTaskStatus {
  task_id: string;
  target_url: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'cancelling';
  current_step: string;
  discovered_files_count: number;
  total_slides_created: number;
  uploaded_slides_count: number;
  logs: string[];
  created_at: string;
  updated_at: string;
  error?: string | null;
  saved_slides: Array<{
    id: string;
    title: string;
    slide_filename: string;
    preview_url: string;
    pptx_url: string;
  }>;
}

export interface StoredSlideCard {
  id: string;
  slide_filename: string;
  preview_filename: string;
  storage_pptx_path: string;
  storage_preview_path: string;
  pptx_url: string;
  preview_url: string;
  public_pptx_url: string;
  title: string;
  original_presentation_name: string;
  original_source_url: string;
  slide_index: number;
  total_slides: number;
  file_size: number;
  uploaded_at: string;
}

export interface StorageStatus {
  bucket_name: string;
  is_connected: boolean;
  credentials_found: boolean;
  credentials_path: string;
  error?: string | null;
}

export interface BrowserSessionStatus {
  status: 'not_connected' | 'connecting' | 'browser_open' | 'authenticated' | 'not_authenticated' | 'timeout' | 'error';
  site: string | null;
  message: string;
  debug_logs: string[];
}

export interface DeleteSlidesResponse {
  deleted_count: number;
  success: boolean;
  errors: string[];
}

const API_BASE = '/api';

export const api = {
  async startScrape(params: {
    url: string;
    max_pages?: number;
    max_depth?: number;
  }): Promise<ScrapeTaskStatus> {
    const res = await fetch(`${API_BASE}/scrape/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: params.url,
        max_pages: params.max_pages ?? 25,
        max_depth: params.max_depth ?? 2,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to start scrape task' }));
      throw new Error(err.detail || 'Failed to start scrape task');
    }
    return res.json();
  },

  async getScrapeStatus(taskId: string): Promise<ScrapeTaskStatus> {
    const res = await fetch(`${API_BASE}/scrape/status/${taskId}`);
    if (!res.ok) {
      throw new Error('Failed to fetch scrape task status');
    }
    return res.json();
  },

  async cancelScrape(taskId: string): Promise<void> {
    await fetch(`${API_BASE}/scrape/cancel/${taskId}`, { method: 'POST' });
  },

  async getBrowserSession(): Promise<BrowserSessionStatus> {
    const res = await fetch(`${API_BASE}/scrape/session`);
    if (!res.ok) {
      throw new Error('Failed to get browser session status');
    }
    return res.json();
  },

  async openBrowserLogin(url: string): Promise<BrowserSessionStatus> {
    const res = await fetch(`${API_BASE}/scrape/open-browser-login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      throw new Error('Failed to open browser session');
    }
    return res.json();
  },

  async verifyBrowserSession(): Promise<BrowserSessionStatus> {
    const res = await fetch(`${API_BASE}/scrape/session/verify`, { method: 'POST' });
    if (!res.ok) {
      throw new Error('Failed to verify the open browser session');
    }
    return res.json();
  },

  async completeBrowserSession(): Promise<BrowserSessionStatus> {
    const res = await fetch(`${API_BASE}/scrape/session/complete`, { method: 'POST' });
    if (!res.ok) {
      throw new Error('Failed to complete browser session');
    }
    return res.json();
  },

  async closeBrowserSession(): Promise<BrowserSessionStatus> {
    const res = await fetch(`${API_BASE}/scrape/session/close`, { method: 'POST' });
    if (!res.ok) {
      throw new Error('Failed to close scraper browser');
    }
    return res.json();
  },

  async clearBrowserSession(): Promise<BrowserSessionStatus> {
    const res = await fetch(`${API_BASE}/scrape/session`, { method: 'DELETE' });
    if (!res.ok) {
      throw new Error('Failed to clear browser session');
    }
    return res.json();
  },

  async getSlides(search?: string): Promise<StoredSlideCard[]> {
    const url = search ? `${API_BASE}/slides?search=${encodeURIComponent(search)}` : `${API_BASE}/slides`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new Error('Failed to fetch slides');
    }
    return res.json();
  },

  async deleteSlides(slideIds: string[]): Promise<DeleteSlidesResponse> {
    const res = await fetch(`${API_BASE}/slides`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slide_ids: slideIds }),
    });
    if (!res.ok) {
      throw new Error('Failed to delete slides');
    }
    return res.json();
  },

  async getStorageStatus(): Promise<StorageStatus> {
    const res = await fetch(`${API_BASE}/slides/storage-status`);
    if (!res.ok) {
      throw new Error('Failed to get storage status');
    }
    return res.json();
  },
};
