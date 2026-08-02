"""資料存取層。

本層是唯一接觸資料庫的位置，使兩項規則有單一的強制點（plan.md 結構決策）：

1. **JWT 轉發**——內部使用者的請求以其自身 JWT 建立連線，RLS 依
   `auth.jwt()` 的自訂 claim 判定權限，後端無從偽造（research.md R-002）。
2. **`service_role` 不得用於處理使用者請求**——以 `assert_not_service_role`
   在建立連線時強制，並由 `tests/unit/test_service_role_guard.py` 守護。

`DataStore` 是資料庫這個外部服務的可替換介面（憲章「外部服務隔離」）。
正式實作為 `SupabaseDataStore`；離線測試以 `memory_store.InMemoryDataStore`
取代，後者同時模擬 RLS 政策矩陣，使權限行為在離線套件中仍可被斷言。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from backend.src.config import Settings

# 依 request.jwt.claims 判定權限時使用的角色值
ROLE_HR = "HR"
ROLE_MANAGER = "MANAGER"
ROLE_CANDIDATE = "CANDIDATE"
ROLE_SYSTEM = "SYSTEM"

# 唯附加資料表：0011_append_only.sql 撤銷 UPDATE 與 DELETE（FR-078）
APPEND_ONLY_TABLES = frozenset(
    {"execution_records", "ai_reports", "manager_decisions", "audit_logs"}
)


class DataAccessError(RuntimeError):
    """資料存取失敗。"""


class ServiceRoleMisuseError(DataAccessError):
    """service_role 金鑰被用於處理使用者請求（research.md R-002 明令禁止）。"""


@dataclass(frozen=True)
class RequestContext:
    """一次請求的身分。

    `jwt` 為內部使用者的 Supabase Auth token，會原樣轉發給 PostgREST；
    應徵者沒有 JWT，其 `role` 為 CANDIDATE，只能走 SECURITY DEFINER 函式。
    """

    role: str
    auth_user_id: str | None = None
    internal_user_id: str | None = None
    dept_id: str | None = None
    jwt: str | None = None

    @property
    def is_hr(self) -> bool:
        return self.role == ROLE_HR

    @property
    def is_manager(self) -> bool:
        return self.role == ROLE_MANAGER


ANON_CONTEXT = RequestContext(role=ROLE_CANDIDATE)
SYSTEM_CONTEXT = RequestContext(role=ROLE_SYSTEM)


@runtime_checkable
class DataStore(Protocol):
    """資料庫存取介面。篩選條件以欄位對應值表示。

    值可為純量（等值比對）或 `(運算子, 值)`，運算子支援
    `eq`、`neq`、`in`、`ilike`、`is`、`lt`、`gt`。
    """

    def select(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...

    def update(
        self, table: str, values: dict[str, Any], *, filters: dict[str, Any]
    ) -> list[dict[str, Any]]: ...

    def rpc(self, function: str, params: dict[str, Any]) -> Any: ...


def assert_not_service_role(key: str | None, settings: Settings) -> None:
    """拒絕以 service_role 金鑰處理使用者請求。

    service_role 會完全繞過 RLS，一旦用於使用者請求，資料庫層的權限政策
    形同不存在（research.md R-002）。這裡寧可讓請求失敗，也不要靜默地
    取得全表存取權。
    """
    service_key = settings.supabase.service_role_key
    if key and service_key and key == service_key:
        raise ServiceRoleMisuseError(
            "service_role 金鑰僅限資料庫遷移與維護作業，不得用於處理使用者請求"
        )


class SupabaseDataStore:
    """以請求者 JWT 建立的 Supabase 連線（research.md R-002）。"""

    _OPERATORS = ("eq", "neq", "in", "ilike", "is", "lt", "gt")

    def __init__(self, client: Any, context: RequestContext) -> None:
        self._client = client
        self._context = context

    @property
    def context(self) -> RequestContext:
        return self._context

    def _query(self, table: str, filters: dict[str, Any] | None):
        query = self._client.table(table)
        return query

    @staticmethod
    def _apply(query, filters: dict[str, Any] | None):
        for column, condition in (filters or {}).items():
            operator, value = _split_condition(condition)
            if operator not in SupabaseDataStore._OPERATORS:
                raise DataAccessError(f"不支援的篩選運算子：{operator}")
            query = getattr(query, operator)(column, value)
        return query

    def select(
        self,
        table: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = self._apply(self._query(table, filters).select("*"), filters)
        if order_by:
            query = query.order(order_by, desc=descending)
        if limit is not None:
            query = query.limit(limit)
        return list(query.execute().data or [])

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        data = self._client.table(table).insert(row).execute().data or []
        return dict(data[0]) if data else dict(row)

    def update(
        self, table: str, values: dict[str, Any], *, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if table in APPEND_ONLY_TABLES:
            raise DataAccessError(f"{table} 為唯附加資料表，不接受 UPDATE（FR-078）")
        query = self._apply(self._client.table(table).update(values), filters)
        return list(query.execute().data or [])

    def rpc(self, function: str, params: dict[str, Any]) -> Any:
        return self._client.rpc(function, params).execute().data


def _split_condition(condition: Any) -> tuple[str, Any]:
    if isinstance(condition, tuple) and len(condition) == 2:
        return str(condition[0]), condition[1]
    return "eq", condition


def create_supabase_store(settings: Settings, context: RequestContext) -> SupabaseDataStore:
    """建立正式的 Supabase 連線。

    內部使用者：以其 JWT 授權，RLS 依 JWT claim 判定。
    應徵者／系統：以 anon 金鑰連線，底層資料表對 anon 未開放，
    只能呼叫 0010 授權的 SECURITY DEFINER 函式。
    """
    # 守護先於任何相依載入：即使 supabase 套件不存在，誤用 service_role
    # 仍必須以 ServiceRoleMisuseError 失敗，而非以 ImportError 混淆原因。
    assert_not_service_role(context.jwt, settings)

    from supabase import create_client  # 延後匯入：離線測試不需要此相依

    client = create_client(settings.supabase.url, settings.supabase.anon_key)
    if context.jwt:
        client.postgrest.auth(context.jwt)
    return SupabaseDataStore(client, context)
