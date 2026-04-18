"""Game result CRUD service backed by MongoDB (motor)."""

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.app.models.schemas import GameRecord, PaginatedResponse
from backend.app.services.db_utils import with_mongo_retry


class GameService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._col = db["games"]

    async def save_game(self, record: GameRecord) -> str:
        doc = record.model_dump(by_alias=True, exclude_none=True)

        async def _insert():
            result = await self._col.insert_one(doc)
            return str(result.inserted_id)

        return await with_mongo_retry(_insert, op_name="save_game")

    async def get_games(
        self,
        page: int = 1,
        limit: int = 20,
        *,
        title: str | None = None,
    ) -> PaginatedResponse:
        """List games; ``title`` (BE-T5) is an optional equality filter.

        None (default) — no filter, original behavior. The literal
        ``"untitled"`` collapses to rows where ``title`` is null or
        missing so the FE drill-down has a stable bucket for legacy
        records.
        """
        skip = (page - 1) * limit

        async def _fetch():
            query: dict = {}
            if title == "untitled":
                query["$or"] = [
                    {"title": {"$exists": False}},
                    {"title": None},
                ]
            elif title is not None:
                query["title"] = title
            total = await self._col.count_documents(query)
            cursor = (
                self._col.find(query)
                .sort("timestamp", -1)
                .skip(skip)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            for d in docs:
                d["_id"] = str(d["_id"])
            return PaginatedResponse(data=docs, total=total, page=page, limit=limit)

        return await with_mongo_retry(_fetch, op_name="get_games")

    async def aggregate_by_title(
        self, page: int = 1, limit: int = 20
    ) -> PaginatedResponse:
        """Group ``games`` by title → per-run summary (BE-T4).

        Each output entry:

          {
            "title":            str,   # "untitled" for null/missing
            "experiment_id":    str,   # most recent match's exp id
            "started_at":       iso,   # earliest timestamp in group
            "ended_at":         iso,   # latest timestamp in group
            "total_games":      int,
            "win_rate":         float in [0, 1],   # player1 win rate
            "avg_rally_length": float,
            "status":           "done",  # overlayed with "running" at route layer
          }

        Sorted by ``started_at`` desc. Null / missing titles bucket
        under "untitled" so the FE drill-down has a stable group for
        pre-title records.
        """
        skip = (page - 1) * limit

        async def _fetch() -> PaginatedResponse:
            group_key = {"$ifNull": ["$title", "untitled"]}

            total_docs = await self._col.aggregate(
                [{"$group": {"_id": group_key}}, {"$count": "total"}]
            ).to_list(length=1)
            total = int(total_docs[0]["total"]) if total_docs else 0

            pipeline = [
                {
                    "$group": {
                        "_id": group_key,
                        "title": {"$first": group_key},
                        "experiment_id": {"$last": "$experiment_id"},
                        "started_at": {"$min": "$timestamp"},
                        "ended_at": {"$max": "$timestamp"},
                        "total_games": {"$sum": 1},
                        "wins": {
                            "$sum": {"$cond": [{"$eq": ["$winner", 1]}, 1, 0]}
                        },
                        "avg_rally_length": {"$avg": "$rally_count"},
                    }
                },
                {"$sort": {"started_at": -1}},
                {"$skip": skip},
                {"$limit": limit},
                {
                    "$project": {
                        "_id": 0,
                        "title": 1,
                        "experiment_id": 1,
                        "started_at": 1,
                        "ended_at": 1,
                        "total_games": 1,
                        "wins": 1,
                        "avg_rally_length": 1,
                    }
                },
            ]
            raw = await self._col.aggregate(pipeline).to_list(length=limit)
            entries: list[dict] = []
            for doc in raw:
                total_games = int(doc.get("total_games", 0))
                wins = int(doc.get("wins", 0))
                win_rate = (wins / total_games) if total_games else 0.0
                started_at = doc.get("started_at")
                ended_at = doc.get("ended_at")
                entries.append({
                    "title": doc.get("title") or "untitled",
                    "experiment_id": doc.get("experiment_id"),
                    "started_at": (
                        started_at.isoformat()
                        if started_at is not None
                        and hasattr(started_at, "isoformat")
                        else started_at
                    ),
                    "ended_at": (
                        ended_at.isoformat()
                        if ended_at is not None and hasattr(ended_at, "isoformat")
                        else ended_at
                    ),
                    "total_games": total_games,
                    "win_rate": win_rate,
                    "avg_rally_length": float(doc.get("avg_rally_length") or 0.0),
                    # Route layer overlays "running" when the manager's
                    # current title matches this row.
                    "status": "done",
                })
            return PaginatedResponse(
                data=entries, total=total, page=page, limit=limit
            )

        return await with_mongo_retry(_fetch, op_name="aggregate_by_title")

    async def get_game(self, game_id: str) -> dict | None:
        from bson import ObjectId
        from bson.errors import InvalidId

        try:
            oid = ObjectId(game_id)
        except (InvalidId, TypeError):
            return None

        async def _fetch():
            doc = await self._col.find_one({"_id": oid})
            if doc is None:
                return None
            doc["_id"] = str(doc["_id"])
            return doc

        return await with_mongo_retry(_fetch, op_name="get_game")

    async def get_game_by_game_id(self, game_id: str) -> dict | None:
        """Look up a game by its uuid4 game_id field."""

        async def _fetch():
            doc = await self._col.find_one({"game_id": game_id})
            if doc is None:
                return None
            doc["_id"] = str(doc["_id"])
            return doc

        return await with_mongo_retry(_fetch, op_name="get_game_by_game_id")
