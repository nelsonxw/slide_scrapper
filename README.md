# PowerPoint Web Scraper & Slide Studio

A standalone full-stack web application that crawls websites and their sub-pages to search for download buttons, verifies PowerPoint presentations, splits them into individual single-slide `.pptx` files, uploads them to Firebase Storage (`gs://slide-preview.firebasestorage.app`), and provides a visual gallery for previewing and batch-deleting slides from Firebase Storage.

---

## 🌟 Key Features

1. **Intelligent Web & Sub-site Crawler (`backend/app/scraper/`)**:
   - Breadth-first crawler traversing target domain and internal sub-pages.
   - Detects download buttons, links (`<a>`, `<button>`, forms, data-attributes), and `.pptx`/`.ppt` download endpoints.
   - Verifies Content-Type headers and OOXML/ZIP binary magic bytes (`PK\x03\x04` for PPTX, OLE Compound for legacy PPT) to ensure files are genuine PowerPoint decks.

2. **PowerPoint Slide Splitter & Preview Generator (`backend/app/ppt/`)**:
   - Parses multi-slide presentations and cleanly isolates each slide into its own standalone 1-slide `.pptx` file.
   - Preserves slide layouts, themes, color palettes, shapes, images, and text formats.
   - Generates high-resolution PNG thumbnail previews using PowerPoint COM automation on Windows with a fallback PIL graphical renderer.

3. **Firebase Storage Integration (`backend/app/firebase/`)**:
   - Configured for `gs://slide-preview.firebasestorage.app`.
   - Automatically uploads each single-slide `.pptx` and its thumbnail preview image.
   - Attaches structured metadata (presentation name, slide index, total slides, original site source URL, timestamp).
   - Real-time batch deletion removes selected files directly from Firebase Storage.

4. **Modern Responsive React Frontend (`frontend/`)**:
   - **Tab 1: Scrape & Discover**: Enter target site URL, adjust max sub-pages and crawl depth, with live progress logs and metric counters.
   - **Tab 2: Slide Gallery & Preview**: Card grid of all uploaded slides, slide number badges, full-screen lightbox preview modal, search filtering, multi-select checkboxes, Select All, and **"Delete Selected"** action from Firebase Storage.
   - **Browser-Based Login**: Click "🌐 Open Browser for Google Login" to open a visible browser window for manual authentication on gated sites (e.g., SlideModel). The session is preserved for all future automated scrapes.

---

## 🚀 Quick Start

### 1. One-Click Launch (Windows)
Double-click `run_app.bat` or run:
```bat
run_app.bat
```
This automatically starts both the FastAPI backend (`http://localhost:8000`) and the React frontend (`http://localhost:5173`).

### 2. Manual Startup

**Backend:**
```bash
cd slide_scrapper/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Frontend:**
```bash
cd slide_scrapper/frontend
npm.cmd run dev
```

---

## ⚙️ Configuration (.env)

Create or edit `.env` in `slide_scrapper/` or `slide_scrapper/backend/`:
```env
# Firebase Storage Bucket
FIREBASE_STORAGE_BUCKET=slide-preview.firebasestorage.app

# Path to your Firebase service account key JSON (optional / for authenticated production uploads)
FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json

# Server settings
HOST=0.0.0.0
PORT=8000
```

> **Note**: If `serviceAccountKey.json` is not yet placed in the project folder, the app automatically activates fallback local storage sync so all scraping, splitting, previewing, and batch-deleting features function locally and upload to Firebase as soon as credentials are provided.

---

## 🔐 Browser-Based Login for Gated Sites

For websites that require user authentication (e.g., SlideModel free templates):

**Why Google One-Tap doesn't work in automated browsers:**
Google has anti-automation protections that detect when a browser is controlled by automation tools (like Playwright) and blocks Google One-Tap to prevent fraud. This is why the automated browser cannot show Google One-Tap.

**Solution: Automatic Cookie Extraction**

1. In the **Scrape & Discover** tab, click **"🌐 Auto-Extract Cookies After Login"** in the Advanced section.
2. A browser window will open with two tabs:
   - **Tab 1**: Google login page - sign in with your Google account
   - **Tab 2**: SlideModel login page - complete Google One-Tap authentication
3. **Close the browser window** when finished - cookies are automatically extracted and filled in the Session Cookies field
4. All future scrapes will use these cookies to download gated content without additional login prompts

This approach is completely automatic - no manual cookie copying required!

---

## 🧪 Running Automated Tests

Run backend unit and integration tests:
```bash
set PYTHONPATH=C:\Users\tiger\Windsurf projects\slide_scrapper\backend
python -m unittest discover -s slide_scrapper/backend/tests
```

Build and type-check frontend:
```bash
npm.cmd --prefix slide_scrapper/frontend run build
```
