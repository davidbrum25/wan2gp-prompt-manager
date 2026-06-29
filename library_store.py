import json
import os
import uuid
from datetime import datetime


def library_file_path(plugin_dir: str) -> str:
    return os.path.join(plugin_dir, "prompts_library.json")


def load_library(plugin_dir: str) -> list[dict]:
    path = library_file_path(plugin_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as reader:
            payload = json.load(reader)
        if isinstance(payload, list):
            return [entry for entry in payload if isinstance(entry, dict)]
    except Exception as exc:
        print(f"[Prompt Manager] Could not read library file: {exc}")
    return []


def save_library(plugin_dir: str, entries: list[dict]) -> None:
    path = library_file_path(plugin_dir)
    os.makedirs(plugin_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as writer:
        json.dump(entries, writer, indent=2, ensure_ascii=False)


def find_by_source_path(entries: list[dict], source_path: str) -> dict | None:
    normalized = os.path.abspath(source_path)
    for entry in entries:
        if os.path.abspath(entry.get("source_path", "")) == normalized:
            return entry
    return None


def find_by_id(entries: list[dict], entry_id: str) -> dict | None:
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry
    return None


def remove_by_id(plugin_dir: str, entry_id: str) -> bool:
    entries = load_library(plugin_dir)
    new_entries = [entry for entry in entries if entry.get("id") != entry_id]
    if len(new_entries) == len(entries):
        return False
    save_library(plugin_dir, new_entries)
    return True


def upsert_entry(plugin_dir: str, entry: dict) -> dict:
    entries = load_library(plugin_dir)
    source_path = entry.get("source_path", "")
    existing = find_by_source_path(entries, source_path) if source_path else None
    if existing:
        entry["id"] = existing["id"]
        entry["saved_at"] = existing.get("saved_at", entry.get("saved_at"))
        entries = [entry if item.get("id") == existing["id"] else item for item in entries]
    else:
        entry.setdefault("id", str(uuid.uuid4()))
        entry.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))
        entries.insert(0, entry)
    save_library(plugin_dir, entries)
    return entry


def export_library_json(plugin_dir: str) -> str:
    return json.dumps(load_library(plugin_dir), indent=2, ensure_ascii=False)


def import_library_entries(plugin_dir: str, payload, merge: bool = True) -> tuple[int, int]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, list):
        raise ValueError("Library import must be a JSON array.")

    incoming = [entry for entry in payload if isinstance(entry, dict)]
    if not merge:
        save_library(plugin_dir, incoming)
        return len(incoming), 0

    existing = load_library(plugin_dir)
    existing_ids = {entry.get("id") for entry in existing if entry.get("id")}
    existing_sources = {
        os.path.abspath(entry.get("source_path", ""))
        for entry in existing
        if entry.get("source_path")
    }
    added = 0
    skipped = 0
    for entry in incoming:
        source_path = entry.get("source_path", "")
        entry_id = entry.get("id")
        if entry_id and entry_id in existing_ids:
            skipped += 1
            continue
        if source_path and os.path.abspath(source_path) in existing_sources:
            skipped += 1
            continue
        entry.setdefault("id", str(uuid.uuid4()))
        entry.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))
        existing.insert(0, entry)
        existing_ids.add(entry["id"])
        if source_path:
            existing_sources.add(os.path.abspath(source_path))
        added += 1
    save_library(plugin_dir, existing)
    return added, skipped


def library_entry_to_grid_entry(entry: dict) -> dict:
    source_path = entry.get("source_path", "")
    file_exists = bool(source_path and os.path.isfile(source_path))
    created_ts = entry.get("created", 0) or 0
    return {
        "path": f"lib://{entry['id']}",
        "basename": entry.get("basename") or "Saved prompt",
        "model": entry.get("model") or "Unknown model",
        "prompt": entry.get("prompt") or "",
        "search_text": entry.get("search_text") or "",
        "created": created_ts,
        "created_label": entry.get("created_label") or entry.get("saved_at", "")[:16],
        "is_video": bool(entry.get("is_video")),
        "is_image": bool(entry.get("is_image")),
        "has_metadata": True,
        "is_library": True,
        "is_saved": True,
        "library_id": entry.get("id"),
        "source_path": source_path,
        "file_exists": file_exists,
        "tags": entry.get("tags") or [],
    }