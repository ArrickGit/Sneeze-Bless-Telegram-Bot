from __future__ import annotations

from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient

from blessyou_bot.constants import DEFAULT_RULES
from blessyou_bot.models import Actor, Participant


class MongoStorage:
    def __init__(self, uri: str, database_name: str) -> None:
        self._client = AsyncMongoClient(uri)
        self._db = self._client[database_name]
        self.scores = self._db["scores"]
        self.events = self._db["events"]
        self.rules = self._db["rules"]
        self.known_users = self._db["known_users"]

    async def connect(self) -> None:
        await self._client.admin.command("ping")

    async def close(self) -> None:
        await self._client.close()

    async def ensure_indexes(self) -> None:
        await self.scores.create_index([("chat_id", ASCENDING), ("points", DESCENDING)])
        await self.scores.create_index([("chat_id", ASCENDING), ("user_key", ASCENDING)], unique=True)
        await self.events.create_index([("chat_id", ASCENDING), ("created_at", DESCENDING)])
        await self.known_users.create_index([("username", ASCENDING)])
        await self.known_users.create_index([("updated_at", DESCENDING)])

    async def ensure_rules(self, chat_id: int) -> list[str]:
        await self.rules.update_one(
            {"_id": chat_id},
            {
                "$setOnInsert": {
                    "chat_id": chat_id,
                    "rules": DEFAULT_RULES,
                    "created_at": self._now(),
                }
            },
            upsert=True,
        )
        document = await self.rules.find_one({"_id": chat_id})
        return list(document["rules"]) if document else list(DEFAULT_RULES)

    async def list_rules(self, chat_id: int) -> list[str]:
        return await self.ensure_rules(chat_id)

    async def add_rule(self, chat_id: int, text: str) -> list[str]:
        rules = await self.ensure_rules(chat_id)
        rules.append(text.strip())
        await self.rules.update_one(
            {"_id": chat_id},
            {"$set": {"rules": rules, "updated_at": self._now()}},
            upsert=True,
        )
        return rules

    async def remove_rule(self, chat_id: int, index: int) -> list[str]:
        rules = await self.ensure_rules(chat_id)
        if index < 0 or index >= len(rules):
            raise IndexError("Rule index out of range")
        del rules[index]
        await self.rules.update_one(
            {"_id": chat_id},
            {"$set": {"rules": rules, "updated_at": self._now()}},
            upsert=True,
        )
        return rules

    async def bless(
        self,
        chat_id: int,
        participants: list[Participant],
        amount: int,
        actor: Actor,
    ) -> list[dict]:
        return await self._apply_score_change(
            chat_id=chat_id,
            participants=participants,
            delta=amount,
            event_type="bless",
            actor=actor,
            reason=None,
        )

    async def unbless(
        self,
        chat_id: int,
        participant: Participant,
        amount: int,
        actor: Actor,
        reason: str | None,
    ) -> dict:
        results = await self._apply_score_change(
            chat_id=chat_id,
            participants=[participant],
            delta=-amount,
            event_type="unbless",
            actor=actor,
            reason=reason,
        )
        return results[0]

    async def get_scoreboard(self, chat_id: int, limit: int) -> list[dict]:
        cursor = (
            self.scores.find({"chat_id": chat_id})
            .sort([("points", DESCENDING), ("handle", ASCENDING)])
            .limit(limit)
        )
        results = []
        async for document in cursor:
            results.append(
                {
                    "handle": document["handle"],
                    "points": document["points"],
                }
            )
        return results

    async def hard_reset(self) -> dict[str, int]:
        scores_result = await self.scores.delete_many({})
        events_result = await self.events.delete_many({})
        rules_result = await self.rules.delete_many({})
        return {
            "scores": scores_result.deleted_count,
            "events": events_result.deleted_count,
            "rules": rules_result.deleted_count,
        }

    async def remember_user(self, user_id: int, username: str | None, full_name: str) -> None:
        await self.known_users.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "username": username.lower() if username else None,
                    "full_name": full_name,
                    "updated_at": self._now(),
                },
                "$setOnInsert": {"created_at": self._now()},
            },
            upsert=True,
        )

    async def find_user_by_username(self, username: str) -> dict | None:
        return await self.known_users.find_one(
            {"username": username.lower()},
            sort=[("updated_at", DESCENDING)],
        )

    async def _apply_score_change(
        self,
        chat_id: int,
        participants: list[Participant],
        delta: int,
        event_type: str,
        actor: Actor,
        reason: str | None,
    ) -> list[dict]:
        timestamp = self._now()

        for participant in participants:
            await self.scores.update_one(
                {"chat_id": chat_id, "user_key": participant.key},
                {
                    "$inc": {"points": delta},
                    "$set": {
                        "handle": participant.handle,
                        "updated_at": timestamp,
                        "last_actor_id": actor.user_id,
                        "last_actor_username": actor.username,
                    },
                    "$setOnInsert": {
                        "chat_id": chat_id,
                        "user_key": participant.key,
                        "created_at": timestamp,
                    },
                },
                upsert=True,
            )

        await self.events.insert_one(
            {
                "chat_id": chat_id,
                "event_type": event_type,
                "participants": [
                    {"user_key": participant.key, "handle": participant.handle} for participant in participants
                ],
                "delta": delta,
                "reason": reason,
                "actor": {
                    "user_id": actor.user_id,
                    "username": actor.username,
                    "full_name": actor.full_name,
                },
                "created_at": timestamp,
            }
        )

        return await self._fetch_scores(chat_id, participants)

    async def _fetch_scores(self, chat_id: int, participants: list[Participant]) -> list[dict]:
        keys = [participant.key for participant in participants]
        docs = {}
        cursor = self.scores.find({"chat_id": chat_id, "user_key": {"$in": keys}})
        async for document in cursor:
            docs[document["user_key"]] = document

        results = []
        for participant in participants:
            document = docs[participant.key]
            results.append({"handle": document["handle"], "points": document["points"]})
        return results

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
