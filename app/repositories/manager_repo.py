"""Manager repository — reads/writes the Менеджеры sheet."""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain import Manager, Role
from app.integrations.sheets_client import SheetsClient
from app.repositories.schema import HEADERS_MANAGERS, SHEET_MANAGERS


class ManagerRepository:
    """CRUD on the Managers sheet."""

    def __init__(self, sheets: SheetsClient) -> None:
        self._sheets = sheets

    async def ensure_schema(self) -> None:
        await self._sheets.ensure_sheet(SHEET_MANAGERS, HEADERS_MANAGERS)

    async def list_all(self) -> list[Manager]:
        records = await self._sheets.get_all_records(SHEET_MANAGERS)
        return [self._to_domain(r) for r in records]

    async def find_by_telegram_id(self, telegram_id: str) -> Manager | None:
        records = await self._sheets.get_all_records(SHEET_MANAGERS)
        for r in records:
            if str(r.get("Telegram_ID", "")).strip() == str(telegram_id).strip():
                return self._to_domain(r)
        return None

    async def upsert(self, telegram_id: str, name: str, role: Role = Role.MANAGER) -> Manager:
        existing = await self.find_by_telegram_id(telegram_id)
        if existing is not None:
            return existing
        await self._sheets.append_row(
            SHEET_MANAGERS,
            [
                str(telegram_id),
                name,
                role.value,
                "true",
                datetime.now(UTC).isoformat(timespec="seconds"),
            ],
        )
        return Manager(
            telegram_id=str(telegram_id),
            name=name,
            role=role,
            active=True,
            created_at=datetime.now(UTC),
        )

    async def set_role(self, telegram_id: str, role: Role) -> bool:
        return await self._sheets.update_by_id(
            SHEET_MANAGERS,
            id_column="Telegram_ID",
            id_value=str(telegram_id),
            updates={"Роль": role.value},
        )

    @staticmethod
    def _to_domain(r: dict[str, object]) -> Manager:
        role_raw = str(r.get("Роль", "manager")).strip().lower()
        try:
            role = Role(role_raw)
        except ValueError:
            # Backwards compatibility with old Cyrillic role labels.
            role_map = {"админ": Role.OWNER, "owner": Role.OWNER, "менеджер": Role.MANAGER}
            role = role_map.get(role_raw, Role.MANAGER)
        active = str(r.get("Активен", "true")).strip().lower() not in ("false", "0", "no", "нет")
        created_raw = str(r.get("Дата_создания", "")).strip()
        created_at: datetime | None
        try:
            created_at = datetime.fromisoformat(created_raw) if created_raw else None
        except ValueError:
            created_at = None
        return Manager(
            telegram_id=str(r.get("Telegram_ID", "")).strip(),
            name=str(r.get("Имя", "")).strip() or f"Менеджер #{r.get('Telegram_ID', '?')}",
            role=role,
            active=active,
            created_at=created_at,
        )
