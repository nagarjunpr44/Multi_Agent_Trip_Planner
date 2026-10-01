from trip_planner import store


async def test_store_roundtrip(tmp_path):
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await store.upsert_trip({"id": "t1", "title": "Lisbon", "status": "planning"})
        await store.upsert_trip({"id": "t1", "title": "Lisbon 4d", "status": "planning"})
        assert [t["title"] for t in await store.list_trips()] == ["Lisbon 4d"]
        assert (await store.get_trip("t1"))["trip"]["title"] == "Lisbon 4d"

        await store.set_preference("diet", "vegetarian")
        await store.set_preference("diet", "vegan")
        assert await store.get_preferences() == {"diet": "vegan"}

        await store.cache_set("k", {"a": 1})
        assert await store.cache_get("k") == {"a": 1}
        await store.cache_set("old", 1, ttl_hours=-1)
        assert await store.cache_get("old") is None

        assert await store.delete_trip("t1") is True
        assert await store.get_trip("t1") is None
    finally:
        await store.close_db()
