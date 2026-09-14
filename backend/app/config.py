import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Search for .env in current directory, parent directory, and backend directory
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

env_paths = [
    ROOT_DIR / ".env",
    BASE_DIR / ".env",
    Path.cwd() / ".env"
]
for p in env_paths:
    if p.exists():
        load_dotenv(p)
        break
else:
    load_dotenv()


class Settings(BaseModel):
    storage_bucket: str = os.getenv("FIREBASE_STORAGE_BUCKET", "slide-preview.firebasestorage.app")
    credentials_path: str = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
    data_dir: Path = BASE_DIR / "data"
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    frontend_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]

    def resolve_credentials_path(self) -> Path | None:
        raw_path = self.credentials_path
        if not raw_path:
            return None
        
        candidates = [
            Path(raw_path),
            BASE_DIR / raw_path,
            ROOT_DIR / raw_path,
            Path.cwd() / raw_path,
        ]
        for c in candidates:
            if c.exists() and c.is_file():
                return c.resolve()
        return None

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "temp_downloads").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "split_slides").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "previews").mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
