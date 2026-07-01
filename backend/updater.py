"""Update mechanism: version check and patch application."""
import json
import os
import shutil
import zipfile
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime


def _get_version_path() -> str:
    root = os.environ.get("FINANCE_ROOT", "")
    if root:
        return os.path.join(root, "version.json")
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "version.json")


def _get_app_root() -> str:
    root = os.environ.get("FINANCE_ROOT", "")
    if root:
        return root
    return os.path.dirname(os.path.dirname(__file__))


def read_local_version() -> dict:
    """Read the local version.json file."""
    path = _get_version_path()
    if not os.path.exists(path):
        return {"version": "0.0.0", "build": 0, "error": "version.json not found"}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"version": "0.0.0", "build": 0, "error": str(e)}


def compare_versions(local: str, remote: str) -> bool:
    """Return True if remote version is newer than local."""
    def parse(v: str):
        try:
            return tuple(int(x) for x in v.split("."))
        except ValueError:
            return (0, 0, 0)

    return parse(remote) > parse(local)


async def check_update(update_url: str | None = None) -> dict:
    """Check for available updates by fetching remote version.json."""
    local = read_local_version()

    url = update_url or local.get("update_url", "")
    if not url:
        return {
            "has_update": False,
            "current_version": local.get("version", "0.0.0"),
            "error": "未配置更新地址",
        }

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url.rstrip("/") + "/version.json")
            resp.raise_for_status()
            remote = resp.json()
    except Exception as e:
        return {
            "has_update": False,
            "current_version": local.get("version", "0.0.0"),
            "error": f"检查更新失败: {e}",
        }

    has = compare_versions(local.get("version", "0.0.0"), remote.get("version", "0.0.0"))

    return {
        "has_update": has,
        "current_version": local.get("version", "0.0.0"),
        "latest_version": remote.get("version"),
        "build": remote.get("build"),
        "release_date": remote.get("release_date"),
        "changelog": remote.get("changelog", ""),
        "download_url": remote.get("download_url", ""),
        "size": remote.get("size", 0),
    }


async def apply_patch(patch_path: str) -> dict:
    """Apply a patch zip file. Structure: patch zip contains files to replace.

    Expected zip structure:
        patch/
            files/        - files to replace (relative to app root)
            manifest.json - list of files with sha256 checksums
    """
    app_root = _get_app_root()
    backup_dir = os.path.join(app_root, "data", "patches_backup")

    if not zipfile.is_zipfile(patch_path):
        return {"success": False, "error": "补丁文件格式错误"}

    extract_dir = None
    try:
        extract_dir = tempfile.mkdtemp(prefix="patch_")
        with zipfile.ZipFile(patch_path, "r") as zf:
            zf.extractall(extract_dir)

        manifest_path = os.path.join(extract_dir, "patch", "manifest.json")
        if not os.path.exists(manifest_path):
            return {"success": False, "error": "补丁缺少 manifest.json"}

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        files_to_patch = manifest.get("files", [])
        if not files_to_patch:
            return {"success": False, "error": "补丁清单为空"}

        # Validate target version
        target = manifest.get("target_version", "")
        current = read_local_version().get("version", "0.0.0")
        if target and target != current:
            return {
                "success": False,
                "error": f"补丁目标版本 {target} 与当前版本 {current} 不匹配",
            }

        # Backup and apply each file
        os.makedirs(backup_dir, exist_ok=True)
        applied = []
        for file_info in files_to_patch:
            rel_path = file_info.get("path", "")
            expected_checksum = file_info.get("checksum", "")
            source = os.path.join(extract_dir, "patch", "files", rel_path)

            if not os.path.exists(source):
                return {"success": False, "error": f"补丁缺少文件: {rel_path}"}

            # Verify checksum
            if expected_checksum:
                with open(source, "rb") as sf:
                    actual = hashlib.sha256(sf.read()).hexdigest()
                if actual != expected_checksum:
                    return {
                        "success": False,
                        "error": f"文件校验失败: {rel_path}",
                    }

            target_path = os.path.join(app_root, rel_path)
            target_dir = os.path.dirname(target_path)

            # Backup existing file
            if os.path.exists(target_path):
                backup_target = os.path.join(backup_dir, rel_path.replace("\\", "/"))
                os.makedirs(os.path.dirname(backup_target), exist_ok=True)
                shutil.copy2(target_path, backup_target)

            # Apply
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(source, target_path)
            applied.append(rel_path)

        # Update version.json
        new_version = manifest.get("new_version", "")
        if new_version:
            vp = _get_version_path()
            try:
                with open(vp, encoding="utf-8") as f:
                    vdata = json.load(f)
                vdata["version"] = new_version
                vdata["build"] = manifest.get("new_build", vdata.get("build", 0))
                vdata["updated_at"] = datetime.now().isoformat()
                with open(vp, "w", encoding="utf-8") as f:
                    json.dump(vdata, f, ensure_ascii=False, indent=2)
            except OSError:
                pass

        return {
            "success": True,
            "applied": len(applied),
            "files": applied,
            "new_version": new_version,
        }

    except Exception as e:
        return {"success": False, "error": f"补丁应用失败: {e}"}
    finally:
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
