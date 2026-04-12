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

    async def get_games(self, page: int = 1, limit: int = 20) -> PaginatedResponse:
        skip = (page - 1) * limit

        async def _fetch():
            total = await self._col.count_documents({})
            cursor = self._col.find().sort("timestamp", -1).skip(skip).limit(limit)
            docs = await cursor.to_list(length=limit)
            for d in docs:
                d["_id"] = str(d["_id"])
            return PaginatedResponse(data=docs, total=total, page=page, limit=limit)

        return await with_mongo_retry(_fetch, op_name="get_games")

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
