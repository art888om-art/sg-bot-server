"""Async Google Sheets client with retry, backoff, TTL cache, and write-lock.

The public class :class:`SheetsClient` is the single entry point used by all
repositories. It hides synchronous gspread behind ``asyncio.to_thread`` so the
event loop is never blocked, and it serializes all *writes* through an
``asyncio.Lock`` so concurrent updates do not corrupt the sheet.

If credentials/URL are missing, the client falls back to an in-memory backend
so unit tests and local development without Sheets access still work.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

from cachetools import TTLCache

from app.config import Settings
from app.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
Row = list[Any]
RecordDict = dict[str, Any]

# ─── Formula-injection safe-prefix ───
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_cell(value: object) -> str:
    """Escape strings that could be interpreted as formulas by Sheets.

    Any value starting with one of ``=+-@`` is prefixed with a single quote so
    Sheets treats it as plain text. Non-string values are stringified.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _FORMULA_PREFIXES:
        return "'" + s
    return s


def _safe_value_for_storage(value: object) -> str:
    """For the in-memory backend: stringify but DO NOT add the apostrophe.

    Real Google Sheets strips the leading apostrophe on read, so the
    in-memory backend mimics that read-side behavior by simply not storing it.
    Tests then see the same values they would see from a real Sheets read.
    """
    if value is None:
        return ""
    return str(value)


@runtime_checkable
class _Worksheet(Protocol):
    """Minimal protocol describing the worksheet API we depend on."""

    title: str

    def get_all_records(self) -> list[RecordDict]: ...
    def row_values(self, row: int) -> list[str]: ...
    def append_row(self, values: Row, value_input_option: str = ...) -> Any: ...
    def update_cell(self, row: int, col: int, value: Any) -> Any: ...
    def find(self, query: str, in_column: int | None = ...) -> Any: ...
    def add_cols(self, n: int) -> Any: ...


class SheetsClient:
    """High-level async wrapper around a Google Sheets workbook.

    Parameters
    ----------
    settings:
        Application settings. ``google_sheet_url`` and
        ``google_credentials_file`` are read from here.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._cache: TTLCache[str, Any] = TTLCache(
            maxsize=256, ttl=settings.sheets_cache_ttl_seconds
        )
        self._wb: Any = None  # gspread.Spreadsheet — typed loosely on purpose
        self._fallback: _InMemoryBackend | None = None
        self._connected = False

    # ─────────────────────────── connection ───────────────────────────
    async def connect(self) -> None:
        """Lazily open the workbook. Safe to call multiple times."""
        if self._connected:
            return

        creds_path = Path(self._settings.google_credentials_file)
        if not self._settings.google_sheet_url or not creds_path.exists():
            logger.warning(
                "sheets.fallback_in_memory",
                reason="missing credentials or sheet URL",
                creds_exists=creds_path.exists(),
                sheet_url_set=bool(self._settings.google_sheet_url),
            )
            self._fallback = _InMemoryBackend()
            self._connected = True
            return

        def _open() -> Any:
            import gspread  # imported lazily
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(creds_path), scopes=scopes)  # type: ignore[no-untyped-call]
            client = gspread.authorize(creds)
            return client.open_by_url(self._settings.google_sheet_url)

        self._wb = await asyncio.to_thread(_open)
        self._connected = True
        logger.info("sheets.connected", sheet=self._wb.title if self._wb else "?")

    @property
    def in_memory(self) -> bool:
        return self._fallback is not None

    # ─────────────────────────── retry helper ───────────────────────────
    async def _retry(
        self,
        func: Callable[[], T],
        *,
        op: str,
        attempts: int = 3,
    ) -> T:
        """Run *sync* gspread call in a thread with exponential backoff."""
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.to_thread(func)
            except Exception as exc:  # gspread.exceptions.APIError, network, etc.
                last_exc = exc
                msg = str(exc).lower()
                # On 429 quota, back off longer
                if "429" in msg or "rate" in msg or "quota" in msg:
                    delay = min(30.0, 5.0 * attempt + random.uniform(0, 1))
                else:
                    delay = (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.warning(
                    "sheets.retry",
                    op=op,
                    attempt=attempt,
                    error=str(exc),
                    sleep_seconds=round(delay, 2),
                )
                if attempt < attempts:
                    await asyncio.sleep(delay)
        assert last_exc is not None
        logger.error("sheets.give_up", op=op, error=str(last_exc))
        raise last_exc

    # ─────────────────────────── worksheet ops ───────────────────────────
    async def ensure_sheet(self, title: str, headers: list[str]) -> None:
        """Make sure a worksheet exists and has all required headers.

        Adds missing columns *softly* — never removes or reorders existing ones.
        """
        await self.connect()
        if self._fallback is not None:
            self._fallback.ensure(title, headers)
            return

        def _ensure() -> None:
            wb = self._wb
            existing = {ws.title for ws in wb.worksheets()}
            if title not in existing:
                ws = wb.add_worksheet(title=title, rows=500, cols=max(8, len(headers) + 2))
                ws.insert_row(headers, 1)
                logger.info("sheets.created_worksheet", title=title)
                return
            ws = wb.worksheet(title)
            row1 = ws.row_values(1)
            for h in headers:
                if h not in row1:
                    ws.add_cols(1)
                    ws.update_cell(1, len(row1) + 1, h)
                    row1.append(h)

        async with self._lock:
            await self._retry(_ensure, op=f"ensure_sheet:{title}")
        self._cache.clear()

    async def get_all_records(self, title: str) -> list[RecordDict]:
        """Return all rows of a worksheet as list of dicts (header → value)."""
        cache_key = f"records::{title}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [dict(r) for r in cached]

        await self.connect()
        if self._fallback is not None:
            data = self._fallback.records(title)
        else:
            data = await self._retry(
                lambda: self._wb.worksheet(title).get_all_records(),
                op=f"get_all_records:{title}",
            )
        self._cache[cache_key] = [dict(r) for r in data]
        return [dict(r) for r in data]

    async def append_row(self, title: str, row: Row) -> None:
        """Append a row. Values are auto-escaped against formula injection.

        For real Google Sheets we send the escaped values (with leading "'")
        with ``USER_ENTERED`` — Sheets stores them as plain text and strips the
        apostrophe on read. For the in-memory backend we store raw values to
        mimic that read-side behavior so tests see clean strings.
        """
        await self.connect()
        async with self._lock:
            if self._fallback is not None:
                self._fallback.append(title, [_safe_value_for_storage(v) for v in row])
            else:
                safe_row = [safe_cell(v) for v in row]
                await self._retry(
                    lambda: self._wb.worksheet(title).append_row(
                        safe_row, value_input_option="USER_ENTERED"
                    ),
                    op=f"append_row:{title}",
                )
            self._invalidate(title)

    async def update_by_id(
        self,
        title: str,
        id_column: str,
        id_value: object,
        updates: dict[str, object],
    ) -> bool:
        """Update specific columns of the row where ``id_column == id_value``.

        Returns True if a row was updated, False if not found. Values are
        auto-escaped against formula injection.
        """
        await self.connect()
        if self._fallback is not None:
            async with self._lock:
                ok = self._fallback.update(title, id_column, id_value, updates)
                if ok:
                    self._invalidate(title)
                return ok

        def _update() -> bool:
            ws = self._wb.worksheet(title)
            header = ws.row_values(1)
            try:
                id_col_idx = header.index(id_column) + 1
            except ValueError:
                return False
            try:
                cell = ws.find(str(id_value), in_column=id_col_idx)
            except Exception:  # gspread.exceptions.CellNotFound
                return False
            if cell is None:
                return False
            for col_name, value in updates.items():
                if col_name not in header:
                    continue
                col_idx = header.index(col_name) + 1
                ws.update_cell(cell.row, col_idx, safe_cell(value))
            return True

        async with self._lock:
            ok = await self._retry(_update, op=f"update_by_id:{title}")
        if ok:
            self._invalidate(title)
        return ok

    def _invalidate(self, title: str) -> None:
        keys_to_drop = [k for k in self._cache if k.endswith(title)]
        for k in keys_to_drop:
            del self._cache[k]

    # ─────────────────────────── utilities ───────────────────────────
    async def next_id(self, title: str, id_column: str = "ID") -> int:
        records = await self.get_all_records(title)
        max_id = 0
        for r in records:
            raw = str(r.get(id_column, "")).strip()
            if raw.isdigit():
                max_id = max(max_id, int(raw))
        return max_id + 1

    async def healthcheck(self) -> bool:
        """Light readiness probe used by /readyz."""
        if self._fallback is not None:
            return True
        try:
            await self._retry(lambda: self._wb.worksheets(), op="healthcheck", attempts=1)
            return True
        except Exception:
            return False


# ─────────────────────────── in-memory fallback ───────────────────────────
class _InMemoryBackend:
    """Tiny in-memory backend for tests and dev without Sheets access."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def ensure(self, title: str, headers: list[str]) -> None:
        sheet = self._data.setdefault(title, {"headers": [], "rows": []})
        for h in headers:
            if h not in sheet["headers"]:
                sheet["headers"].append(h)

    def records(self, title: str) -> list[RecordDict]:
        sheet = self._data.get(title)
        if not sheet:
            return []
        headers = sheet["headers"]
        return [dict(zip(headers, row, strict=False)) for row in sheet["rows"]]

    def append(self, title: str, row: Row) -> None:
        sheet = self._data.setdefault(title, {"headers": [], "rows": []})
        # Pad if shorter than headers
        while len(row) < len(sheet["headers"]):
            row.append("")
        sheet["rows"].append(row)

    def update(
        self, title: str, id_column: str, id_value: object, updates: dict[str, object]
    ) -> bool:
        sheet = self._data.get(title)
        if not sheet or id_column not in sheet["headers"]:
            return False
        id_idx = sheet["headers"].index(id_column)
        for row in sheet["rows"]:
            if str(row[id_idx]) == str(id_value):
                for col, value in updates.items():
                    if col in sheet["headers"]:
                        row[sheet["headers"].index(col)] = _safe_value_for_storage(value)
                return True
        return False


# ─────────────────────────── singleton getter ───────────────────────────
_client_instance: SheetsClient | None = None
_client_lock = asyncio.Lock()


async def get_sheets_client(settings: Settings | None = None) -> SheetsClient:
    """Return the application-wide SheetsClient singleton."""
    global _client_instance
    if _client_instance is not None:
        return _client_instance
    async with _client_lock:
        if _client_instance is None:
            from app.config import get_settings

            _client_instance = SheetsClient(settings or get_settings())
            await _client_instance.connect()
    return _client_instance


def reset_sheets_client_for_tests() -> None:
    """Reset the singleton — test helper only."""
    global _client_instance
    _client_instance = None


# Suppress unused-but-imported warning for `time` if optimizers strip it; we
# may use it again for backoff tweaks.
_ = time
