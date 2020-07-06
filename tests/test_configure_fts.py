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
    db["dogs"].insert({"name": "Pancakes"})
    db["mammals"].insert({"name": "Pancakes"})
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


@pytest.mark.asyncio
async def test_database_page_sets_cookie(db_path):
    app = Datasette([db_path]).app()
    async with httpx.AsyncClient(app=app) as client:
        response = await client.get("http://localhost/-/configure-fts/data")
    assert "ds_csrftoken" in response.cookies


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
async def test_lists_tables_in_database(db_path2):
    app = Datasette([db_path2]).app()
    async with httpx.AsyncClient(app=app) as client:
        response = await client.get(
            "http://localhost/-/configure-fts/data2", allow_redirects=False
        )
    assert 200 == response.status_code
    assert b"<h2>creatures</h2>" in response.content
    assert b"<h2>dogs</h2>" in response.content
    assert b"<h2>mammals</h2>" in response.content
    # If we select just two tables, only those two
    async with httpx.AsyncClient(app=app) as client:
        response2 = await client.get(
            "http://localhost/-/configure-fts/data2?table=dogs&table=mammals",
            allow_redirects=False,
        )
    assert b"<h2>creatures</h2>" not in response2.content
    assert b"<h2>dogs</h2>" in response2.content
    assert b"<h2>mammals</h2>" in response2.content


@pytest.mark.asyncio
async def test_text_columns_only(db_path):
    app = Datasette([db_path]).app()
    sqlite_utils.Database(db_path)["mixed_types"].insert(
        {"name": "text", "age": 5, "height": 1.4, "description": "description",}
    )
    async with httpx.AsyncClient(app=app) as client:
        response = await client.get(
            "http://localhost/-/configure-fts/data?table=mixed_types",
            allow_redirects=False,
        )
    assert 200 == response.status_code
    content = response.content.decode("utf-8")
    assert 'name="column.name"' in content
    assert 'name="column.age"' not in content
    assert 'name="column.height"' not in content
    assert 'name="column.description"' in content


@pytest.mark.asyncio
async def test_make_table_searchable(db_path):
    app = Datasette([db_path]).app()
    async with httpx.AsyncClient(app=app) as client:
        response1 = await client.get("http://localhost/-/configure-fts/data")
        csrftoken = response1.cookies["ds_csrftoken"]
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


@pytest.mark.asyncio
async def test_uncheck_all_columns(db_path):
    app = Datasette([db_path]).app()
    db = sqlite_utils.Database(db_path)
    db["creatures"].enable_fts(["name"])
    async with httpx.AsyncClient(app=app) as client:
        response1 = await client.get("http://localhost/-/configure-fts/data")
        csrftoken = response1.cookies["csrftoken"]
        response2 = await client.post(
            "http://localhost/-/configure-fts/data",
            data={
                "csrftoken": csrftoken,
                "table": "creatures",
            },
            allow_redirects=False,
        )
    assert 302 == response2.status_code
    assert "/data/creatures" == response2.headers["location"]
    db = sqlite_utils.Database(db_path)
    assert ["creatures"] == db.table_names()
