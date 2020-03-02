import datasette
from datasette.app import Datasette
import sqlite_utils
import pytest
import json
import httpx
import re

whitespace = re.compile(r"\s+")


@pytest.fixture
def db_path(tmpdir):
    path = str(tmpdir / "data.db")
    db = sqlite_utils.Database(path)
    db["creatures"].insert_all(
        [
            {"name": "Cleo", "description": "A medium sized dog"},
            {"name": "Siroco", "description": "A troublesome Kakapo"},
        ]
    )
    return path


@pytest.fixture
def db_path2(tmpdir):
    path = str(tmpdir / "data2.db")
    db = sqlite_utils.Database(path)
    db["creatures"].insert({"name": "Pancakes"})
    return path


@pytest.mark.asyncio
async def test_initial_db_is_not_searchable(db_path):
    app = Datasette([db_path]).app()
    async with httpx.AsyncClient(app=app) as client:
        response = await client.get("http://localhost/data.json")
    assert 200 == response.status_code
    tables = json.loads(response.content)["tables"]
    assert 1 == len(tables)


@pytest.mark.asyncio
async def test_redirects_to_database_if_only_one(db_path):
    app = Datasette([db_path]).app()
    async with httpx.AsyncClient(app=app) as client:
        response = await client.get(
            "http://localhost/-/configure-fts", allow_redirects=False
        )
    assert 302 == response.status_code
    assert "/-/configure-fts/data" == response.headers["location"]
    # Check it sets a csrf cookie
    assert "csrftoken" in response.cookies


@pytest.mark.asyncio
async def test_lists_databases_if_more_than_one(db_path, db_path2):
    app = Datasette([db_path, db_path2]).app()
    async with httpx.AsyncClient(app=app) as client:
        response = await client.get(
            "http://localhost/-/configure-fts", allow_redirects=False
        )
    assert 200 == response.status_code
    assert b'<a href="/-/configure-fts/data">data</a>' in response.content
    assert b'<a href="/-/configure-fts/data2">data2</a>' in response.content


@pytest.mark.asyncio
async def test_make_table_searchable(db_path):
    app = Datasette([db_path]).app()
    async with httpx.AsyncClient(app=app) as client:
        response1 = await client.get("http://localhost/-/configure-fts/data")
        csrftoken = response1.cookies["csrftoken"]
        response2 = await client.post(
            "http://localhost/-/configure-fts/data",
            data={
                "csrftoken": csrftoken,
                "table": "creatures",
                "column.name": "on",
                "column.description": "on",
            },
            allow_redirects=False,
        )
    assert 302 == response2.status_code
    assert "/data/creatures" == response2.headers["location"]
    db = sqlite_utils.Database(db_path)
    assert [
        "creatures",
        "creatures_fts",
        "creatures_fts_data",
        "creatures_fts_idx",
        "creatures_fts_docsize",
        "creatures_fts_config",
    ] == db.table_names()
    assert (
        "CREATE VIRTUAL TABLE [creatures_fts] USING FTS5 ( [name], [description], content=[creatures] )"
        == whitespace.sub(" ", db["creatures_fts"].schema)
    )
    # It should have set up triggers
    rows = db.conn.execute(
        'select name from sqlite_master where type = "trigger" order by name'
    ).fetchall()
    assert [("creatures_ad",), ("creatures_ai",), ("creatures_au",)] == rows
