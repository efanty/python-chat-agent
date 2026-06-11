"""
System upgrade utilities — backup, online/offline upgrade, version management.

All upgrade operations run in a background thread with logs streamed to
a shared buffer for real-time display in the admin UI.
"""

import os
import sys
import json
import uuid, time
import zipfile
import shutil
import threading
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.utils.time_utils import beijing_now, APP_TZ
# ── Log buffer (thread-safe append, polled by admin UI) ─────────────
_log_buffer: list = []
_log_lock = threading.Lock()


def _log(msg: str):
    ts = beijing_now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _log_lock:
        _log_buffer.append(line)


def get_logs(since: int = 0) -> list:
    """Return log lines from index `since` onward."""
    with _log_lock:
        return list(_log_buffer[since:])


def clear_logs():
    with _log_lock:
        _log_buffer.clear()


# ── Paths ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKUP_DIR = PROJECT_ROOT / "backups"
VERSION_FILE = PROJECT_ROOT / "VERSION"
EXCLUDE_DIRS = {"venv", ".venv", "backups", "instance", "__pycache__", ".git", ".idea", "node_modules"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".zip", ".gz", ".tgz", ".bak"}


# ── Version helpers ────────────────────────────────────────────────
def get_current_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "0.0.0"


def set_version(version: str):
    VERSION_FILE.write_text(version.strip(), encoding="utf-8")
    _log(f"版本已更新为 {version.strip()}")


def get_version_from_zip(zip_path: str) -> str:
    """Read VERSION from inside a ZIP archive without extracting."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Try VERSION at root
            try:
                return zf.read("VERSION").decode("utf-8").strip()
            except KeyError:
                pass
            # Walk entries for version file in subdirectories
            for name in zf.namelist():
                base = Path(name).name.lower()
                if base == "version":
                    return zf.read(name).decode("utf-8").strip()
    except Exception:
        pass
    return "0.0.0"


def get_backup_list() -> list:
    """List available backups (project + db) sorted by time (newest first)."""
    if not BACKUP_DIR.exists():
        return []
    backups = []
    for f in sorted(BACKUP_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        # Project backup: backup_YYYYMMDD_HHMMSS.zip
        # DB backup: db_YYYYMMDD_HHMMSS.sqlite
        if f.suffix == ".zip" and f.name.startswith("backup_"):
            size_mb = f.stat().st_size / (1024 * 1024)
            ts = datetime.fromtimestamp(f.stat().st_mtime, tz=APP_TZ)
            backups.append({
                "name": f.name,
                "size": f"{size_mb:.1f} MB",
                "time": ts.strftime("%Y-%m-%d %H:%M"),
                "path": str(f).replace("\\", "/"),
            })
        elif f.suffix == ".sqlite" and f.name.startswith("db_"):
            size_mb = f.stat().st_size / (1024 * 1024)
            ts = datetime.fromtimestamp(f.stat().st_mtime, tz=APP_TZ)
            backups.append({
                "name": f.name,
                "size": f"{size_mb:.1f} MB",
                "time": ts.strftime("%Y-%m-%d %H:%M"),
                "path": str(f).replace("\\", "/"),
            })
    return backups


# ── Backup ─────────────────────────────────────────────────────────
def create_backup() -> Optional[str]:
    """Create a full project backup ZIP (exclude venv, data, logs).

    Returns the backup file path on success, or None on failure.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = beijing_now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}.zip"
    backup_path = BACKUP_DIR / backup_name

    _log(f"正在创建备份: {backup_name} ...")
    try:
        count = 0
        with zipfile.ZipFile(str(backup_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(str(PROJECT_ROOT)):
                # Prune excluded dirs in-place (affects os.walk)
                rel = Path(root).relative_to(PROJECT_ROOT)
                parts = set(rel.parts)
                if parts & EXCLUDE_DIRS:
                    dirs.clear()
                    continue
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in EXCLUDE_EXTS:
                        continue
                    fpath = os.path.join(root, f)
                    arcname = str(Path(fpath).relative_to(PROJECT_ROOT))
                    try:
                        zf.write(fpath, arcname)
                        count += 1
                    except Exception:
                        pass
        _log(f"备份完成: {count} 个文件, {backup_name}")
        return str(backup_path)
    except Exception as e:
        _log(f"备份失败: {e}")
        return None


def restore_backup(backup_path: str) -> bool:
    """Restore from a backup ZIP (dangerous: overwrites current files)."""
    _log(f"正在从备份恢复: {backup_path} ...")
    try:
        with zipfile.ZipFile(backup_path, "r") as zf:
            zf.extractall(str(PROJECT_ROOT))
        _log("恢复完成")
        return True
    except Exception as e:
        _log(f"恢复失败: {e}")
        return False


# ── Extract ZIP upgrade ────────────────────────────────────────────
def extract_upgrade_zip(zip_path: str) -> bool:
    """Extract a project upgrade ZIP over the current directory.

    The ZIP should contain the project files at its root (like a git repo
    checkout).  Files are extracted with .bak creation for existing files.
    """
    _log("正在解压升级包...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Security: reject path traversal
            for info in zf.infolist():
                name = info.filename
                if ".." in name or name.startswith("/") or name.startswith("\\"):
                    _log(f"非法路径已拒绝: {name}")
                    return False

            # Backup existing files before overwriting
            renamed = 0
            for info in zf.infolist():
                if info.is_dir():
                    continue
                target = PROJECT_ROOT / info.filename
                if target.exists():
                    bak = target.with_name(target.name + ".bak")
                    try:
                        shutil.move(str(target), str(bak))
                        renamed += 1
                    except Exception:
                        pass

            # Extract
            extracted = 0
            for info in zf.infolist():
                if info.is_dir():
                    continue
                target = PROJECT_ROOT / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    zf.extract(info, str(PROJECT_ROOT))
                    extracted += 1
                except Exception as e:
                    _log(f"  解压失败 {info.filename}: {e}")

            _log(f"解压完成: {extracted} 个文件已更新")
            return True
    except Exception as e:
        _log(f"解压失败: {e}")
        return False


# ── Post-upgrade steps ─────────────────────────────────────────────
def run_pip_install() -> bool:
    """Run pip install -r requirements.txt in background."""
    _log("正在安装 Python 依赖...")
    req_txt = PROJECT_ROOT / "requirements.txt"
    if not req_txt.exists():
        _log("  requirements.txt 不存在，跳过")
        return True

    python = sys.executable
    try:
        result = subprocess.run(
            [python, "-m", "pip", "install", "-r", str(req_txt), "--quiet"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            _log("  依赖安装成功")
            return True
        else:
            _log(f"  依赖安装失败 (exit {result.returncode})")
            for line in result.stderr.split("\n")[-5:]:
                if line.strip():
                    _log(f"    {line.strip()}")
            return False
    except subprocess.TimeoutExpired:
        _log("  依赖安装超时（>5分钟）")
        return False
    except Exception as e:
        _log(f"  依赖安装异常: {e}")
        return False


def run_db_migrate() -> bool:
    """Create all tables (simple migrate — Flask-Migrate would be better)."""
    _log("正在迁移数据库...")
    try:
        # Import here to avoid circular imports at module level
        from app import create_app
        upgrade_app = create_app()
        with upgrade_app.app_context():
            from app.extensions.init_sqlalchemy import db
            db.create_all()
        _log("  数据库迁移完成")
        return True
    except Exception as e:
        _log(f"  数据库迁移失败: {e}")
        return False


# ── Online upgrade ─────────────────────────────────────────────────
DOWNLOAD_DIR = PROJECT_ROOT / "downloads"


def online_upgrade(download_url: str) -> bool:
    """Download a ZIP from a URL and perform offline upgrade."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zip_name = f"upgrade_{uuid.uuid4().hex[:8]}.zip"
    zip_path = DOWNLOAD_DIR / zip_name

    _log(f"正在从远程下载: {download_url} ...")
    try:
        urllib.request.urlretrieve(download_url, str(zip_path))
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        _log(f"  下载完成 ({size_mb:.1f} MB)")
    except Exception as e:
        _log(f"  下载失败: {e}")
        return False

    # Perform upgrade from downloaded ZIP
    ok = _do_upgrade(str(zip_path))

    # Cleanup download
    try:
        zip_path.unlink()
    except Exception:
        pass

    return ok


# ── Rollback tracking (persisted to disk) ────────────────────────
_LAST_UPGRADE_FILE = BACKUP_DIR / "last_upgrade.json"
_last_upgrade_backup: Optional[str] = None


def _load_last_upgrade():
    """Load the last upgrade backup path from disk cache."""
    global _last_upgrade_backup
    if _last_upgrade_backup is not None:
        return
    try:
        if _LAST_UPGRADE_FILE.exists():
            data = json.loads(_LAST_UPGRADE_FILE.read_text(encoding="utf-8"))
            path = data.get("backup_path", "")
            if path and Path(path).exists():
                _last_upgrade_backup = path
    except Exception:
        pass


def _save_last_upgrade(backup_path: str):
    """Save the last upgrade backup path to disk cache."""
    global _last_upgrade_backup
    _last_upgrade_backup = backup_path
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        _LAST_UPGRADE_FILE.write_text(
            json.dumps({
                "backup_path": backup_path,
                "timestamp": beijing_now().strftime("%Y-%m-%d %H:%M:%S"),
            }, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def get_last_upgrade_backup() -> Optional[str]:
    """Return the backup path from the most recent upgrade.

    Falls back to the newest backup_*.zip if no upgrade backup is recorded.
    """
    _load_last_upgrade()
    if _last_upgrade_backup and Path(_last_upgrade_backup).exists():
        return _last_upgrade_backup
    # Fallback: use the newest project backup from the directory
    backups = get_backup_list()
    for b in backups:
        if b["name"].startswith("backup_"):
            return b["path"]
    return None


def rollback() -> bool:
    """One-click rollback: restore last upgrade backup → pip → migrate.

    Returns True if rollback completes successfully.
    """
    backup_path = get_last_upgrade_backup()
    if not backup_path:
        _log("没有可回滚的备份")
        return False

    _log("=" * 50)
    _log("开始一键回滚...")
    _log("=" * 50)

    ok = restore_backup(backup_path)
    if not ok:
        return False

    run_pip_install()
    run_db_migrate()

    # Re-read version from restored VERSION file
    ver = get_current_version()
    _log(f"回滚完成，当前版本: {ver}")
    _log("=" * 50)
    _log("请重启应用使更改生效")
    _log("=" * 50)
    return True


# ── Full upgrade pipeline ──────────────────────────────────────────
_upgrade_in_progress = False


def _do_upgrade(zip_path: str) -> bool:
    """Run the full upgrade pipeline: backup → extract → pip → migrate."""
    global _upgrade_in_progress, _last_upgrade_backup
    if _upgrade_in_progress:
        _log("升级任务已在运行中")
        return False
    _upgrade_in_progress = True

    try:
        # 1. Backup
        backup_path = create_backup()
        _save_last_upgrade(backup_path)  # persist for one-click rollback
        if not backup_path:
            _log("备份失败，终止升级")
            return False

        # 2. Extract
        if not extract_upgrade_zip(zip_path):
            _log("解压失败，终止升级")
            return False

        # 3. Pip install
        run_pip_install()

        # 4. DB migrate
        run_db_migrate()

        # 5. Read new version if present
        new_ver = get_current_version()
        _log(f"升级完成，当前版本: {new_ver}")

        _log("=" * 50)
        _log("请重启应用使所有更改生效")
        _log("=" * 50)
        return True
    finally:
        _upgrade_in_progress = False


def run_offline_upgrade(zip_storage) -> bool:
    """Entry point for ZIP upload upgrade.  Runs in background thread.

    `zip_storage` is a werkzeug FileStorage or any file-like object,
    or a string path to an existing ZIP file.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zip_name = f"upload_{uuid.uuid4().hex[:8]}.zip"
    zip_path = DOWNLOAD_DIR / zip_name

    if isinstance(zip_storage, str):
        shutil.copy2(zip_storage, str(zip_path))
    else:
        zip_storage.save(str(zip_path))
    _log(f"上传包已保存: {zip_name}")

    result = _do_upgrade(str(zip_path))
    try:
        zip_path.unlink()
    except Exception:
        pass
    return result


# ── Check update (compare remote version) ─────────────────────────
def check_update(version_url: str) -> dict:
    """Fetch remote version info and compare with current.

    version_url should point to a JSON endpoint returning:
      {"version": "1.2.3", "release_url": "...", "changelog": "..."}
    Or a plain text file containing just the version string.
    """
    try:
        req = urllib.request.Request(version_url, method="GET", headers={
            "User-Agent": "DeepAgent-UpgradeCheck/1.0",
        })
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read().decode("utf-8", errors="replace").strip()

        remote_version = body
        release_url = ""
        changelog = ""
        if body.startswith("{"):
            try:
                info = json.loads(body)
                remote_version = info.get("version", body)
                release_url = info.get("release_url", "")
                changelog = info.get("changelog", "")
            except json.JSONDecodeError:
                pass

        current = get_current_version()
        is_newer = _compare_versions(remote_version, current)

        return {
            "current": current,
            "remote": remote_version,
            "is_newer": is_newer,
            "release_url": release_url,
            "changelog": changelog,
        }
    except Exception as e:
        return {"error": str(e), "current": get_current_version()}


def _compare_versions(a: str, b: str) -> bool:
    """Return True if version a is newer than b (semver-like comparison)."""
    def _parse(v):
        parts = []
        for seg in v.replace("-", ".").replace("_", ".").split("."):
            try:
                parts.append(int(seg))
            except ValueError:
                parts.append(0)
        # Pad to same length
        while len(parts) < 4:
            parts.append(0)
        return tuple(parts[:4])
    return _parse(a) > _parse(b)


# ── Clean .bak files ────────────────────────────────────────────────
def count_bak_files() -> int:
    """Count .bak files left from upgrades."""
    count = 0
    for f in PROJECT_ROOT.rglob("*.bak"):
        # Skip files inside excluded dirs
        rel = f.relative_to(PROJECT_ROOT)
        if set(rel.parts) & EXCLUDE_DIRS:
            continue
        count += 1
    return count


def clean_bak_files() -> int:
    """Remove all .bak files from the project. Returns count removed."""
    removed = 0
    for f in list(PROJECT_ROOT.rglob("*.bak")):
        rel = f.relative_to(PROJECT_ROOT)
        if set(rel.parts) & EXCLUDE_DIRS:
            continue
        try:
            f.unlink()
            removed += 1
        except Exception:
            pass
    _log(f"已清理 {removed} 个 .bak 文件")
    return removed


# ── Database backup / restore ──────────────────────────────────────
def get_db_path() -> Optional[Path]:
    """Find the SQLite database file path."""
    candidates = [
        PROJECT_ROOT / "instance" / "app.db",
        PROJECT_ROOT / "app.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def db_backup() -> Optional[str]:
    """Backup the SQLite database file to backups/.

    ⚠ 先执行 WAL checkpoint 确保 app.db-wal 中的最新数据
    被合并到 app.db 主文件中，避免备份遗漏最新数据。
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = get_db_path()
    if not db_path:
        _log("未找到数据库文件")
        return None

    # ── 先执行 WAL checkpoint，将 WAL 日志合并到主文件 ──────────────
    # 后台线程没有应用上下文，需要手动创建
    try:
        from app import create_app
        _app = create_app()
        with _app.app_context():
            from app.extensions.init_sqlalchemy import db
            db.session.execute(db.text("PRAGMA wal_checkpoint(FULL)"))
            db.session.commit()
            _log("WAL checkpoint 完成，数据已合并到 app.db")
    except Exception as e:
        _log(f"WAL checkpoint 失败（不影响备份）: {e}")

    timestamp = beijing_now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"db_{timestamp}.sqlite"
    backup_path = BACKUP_DIR / backup_name

    try:
        shutil.copy2(str(db_path), str(backup_path))
        size_mb = backup_path.stat().st_size / (1024 * 1024)
        _log(f"数据库备份完成: {backup_name} ({size_mb:.1f} MB)")
        return str(backup_path)
    except Exception as e:
        _log(f"数据库备份失败: {e}")
        return None


def db_restore(backup_path: str) -> bool:
    """Restore SQLite database from a backup file. Replaces current DB."""
    _log(f"正在从数据库备份恢复: {backup_path} ...")
    db_path = get_db_path()
    if not db_path:
        _log("未找到当前数据库文件")
        return False

    src = Path(backup_path)
    if not src.exists():
        _log(f"备份文件不存在: {backup_path}")
        return False

    try:
        # Keep current DB as a safety backup
        safety = db_path.with_name(db_path.name + ".before_restore")
        if not safety.exists():
            shutil.copy2(str(db_path), str(safety))
            _log(f"当前数据库已备份到 {safety.name}")

        shutil.copy2(str(src), str(db_path))
        _log("数据库恢复完成")
        return True
    except Exception as e:
        _log(f"数据库恢复失败: {e}")
        return False


# ── Pending upgrades (version confirmation) ───────────────────────
_pending_upgrades: dict = {}
_pending_lock = threading.Lock()


def store_pending_upgrade(zip_path: str) -> str:
    """Store a pending upgrade ZIP path and return an opaque token."""
    _cleanup_old_pending()
    token = uuid.uuid4().hex
    with _pending_lock:
        _pending_upgrades[token] = {"zip_path": zip_path, "ts": time.time()}
    return token


def pop_pending_upgrade(token: str) -> Optional[str]:
    """Retrieve and remove a pending upgrade ZIP path by token."""
    with _pending_lock:
        data = _pending_upgrades.pop(token, None)
    return data["zip_path"] if data else None


def _cleanup_old_pending():
    """Remove pending upgrades older than 30 minutes."""
    now = time.time()
    with _pending_lock:
        expired = [k for k, v in _pending_upgrades.items() if now - v["ts"] > 1800]
        for k in expired:
            _pending_upgrades.pop(k, None)