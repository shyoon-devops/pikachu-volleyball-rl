"""Minimal in-memory async fake of the motor collection API.

Exists only to test the EvaluationRepository and routers without
requiring a running MongoDB. Implements just enough of the API that
EvaluationCollection depends on: insert_one, find (with sort/limit/async
iteration), find_one.
"""

from __future__ import annotations

from typing import Any


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)

    def sort(self, key: str, direction: int = 1) -> "_Cursor":
        reverse = direction == -1
        self._docs.sort(key=lambda d: d.get(key, ""), reverse=reverse)
        return self

    def limit(self, n: int) -> "_Cursor":
        self._docs = self._docs[:n]
        return self

    def __aiter__(self) -> "_Cursor":
        self._iter = iter(self._docs)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeInsertResult:
    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class FakeCollection:
    """In-memory async stand-in for AsyncIOMotorCollection."""

    def __init__(self) -> None:
        self._docs: list[dict[str, Any]] = []
        self._counter = 0

    async def insert_one(self, document: dict[str, Any]) -> FakeInsertResult:
        doc = dict(document)
        self._counter += 1
        if "_id" not in doc:
            doc["_id"] = f"fake-oid-{self._counter}"
        self._docs.append(doc)
        return FakeInsertResult(doc["_id"])

    def find(self, filter: dict[str, Any] | None = None) -> _Cursor:
        filter = filter or {}
        matched = [d for d in self._docs if self._matches(d, filter)]
        return _Cursor(matched)

    async def find_one(
        self, filter: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        filter = filter or {}
        for d in self._docs:
            if self._matches(d, filter):
                return dict(d)
        return None

    async def delete_one(self, filter: dict[str, Any]) -> int:
        """Delete first matching document. Returns count removed (0 or 1)."""
        for i, d in enumerate(self._docs):
            if self._matches(d, filter):
                del self._docs[i]
                return 1
        return 0

    @staticmethod
    def _matches(doc: dict[str, Any], filter: dict[str, Any]) -> bool:
        for k, v in filter.items():
            if isinstance(v, dict):
                # Support only the $gte operator we actually use.
                if "$gte" in v and str(doc.get(k, "")) < str(v["$gte"]):
                    return False
            else:
                if doc.get(k) != v:
                    return False
        return True


__all__ = ["FakeCollection", "FakeInsertResult"]
