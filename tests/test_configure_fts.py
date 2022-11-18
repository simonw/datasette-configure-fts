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
    ds = Datasette([db_path])
    response = await ds.client.get("/data.json")
    assert response.status_code == 200
    tables = json.loads(response.content)["tables"]
    assert len(tables) == 1


@pytest.mark.parametrize("path", ["/-/configure-fts", "/-/configure-fts/data"])
@pytest.mark.asyncio
async def test_permissions(db_path, path):
    ds = Datasette([db_path])
    response = await ds.client.get(path)
    response.status_code == 403
    # Now try with a root actor
    response2 = await ds.client.get(
        path,
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    assert response2.status_code != 403


@pytest.mark.asyncio
async def test_redirects_to_database_if_only_one(db_path):
    ds = Datasette([db_path])
    response = await ds.client.get(
        "/-/configure-fts",
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/-/configure-fts/data"


@pytest.mark.asyncio
async def test_database_page_sets_cookie(db_path):
    ds = Datasette([db_path])
    response = await ds.client.get(
        "/-/configure-fts/data",
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    assert "ds_csrftoken" in response.cookies


@pytest.mark.asyncio
async def test_lists_databases_if_more_than_one(db_path, db_path2):
    ds = Datasette([db_path, db_path2])
    response = await ds.client.get(
        "/-/configure-fts",
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    assert response.status_code == 200
    assert '<a href="/-/configure-fts/data">data</a>' in response.text
    assert '<a href="/-/configure-fts/data2">data2</a>' in response.text


@pytest.mark.asyncio
async def test_lists_tables_in_database(db_path2):
    ds = Datasette([db_path2])
    response = await ds.client.get(
        "/-/configure-fts/data2",
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    assert response.status_code == 200
    assert "<h2>creatures</h2>" in response.text
    assert "<h2>dogs</h2>" in response.text
    assert "<h2>mammals</h2>" in response.text
    # If we select just two tables, only those two
    response2 = await ds.client.get(
        "/-/configure-fts/data2?table=dogs&table=mammals",
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    assert "<h2>creatures</h2>" not in response2.text
    assert "<h2>dogs</h2>" in response2.text
    assert "<h2>mammals</h2>" in response2.text


@pytest.mark.asyncio
async def test_text_columns_only(db_path):
    ds = Datasette([db_path])
    sqlite_utils.Database(db_path)["mixed_types"].insert(
        {
            "name": "text",
            "age": 5,
            "height": 1.4,
            "description": "description",
        }
    )
    response = await ds.client.get(
        "/-/configure-fts/data?table=mixed_types",
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    assert response.status_code == 200
    content = response.text
    assert 'name="column.name"' in content
    assert 'name="column.age"' not in content
    assert 'name="column.height"' not in content
    assert 'name="column.description"' in content


@pytest.mark.asyncio
async def test_make_table_searchable(db_path):
    ds = Datasette([db_path])
    response1 = await ds.client.get(
        "/-/configure-fts/data",
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    csrftoken = response1.cookies["ds_csrftoken"]
    response2 = await ds.client.post(
        "/-/configure-fts/data",
        data={
            "csrftoken": csrftoken,
            "table": "creatures",
            "column.name": "on",
            "column.description": "on",
        },
        cookies={
            "ds_actor": ds.sign({"a": {"id": "root"}}, "actor"),
            "ds_csrftoken": csrftoken,
        },
    )
    assert response2.status_code == 302
    assert response2.headers["location"] == "/data/creatures"
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
    assert rows == [("creatures_ad",), ("creatures_ai",), ("creatures_au",)]


@pytest.mark.asyncio
async def test_uncheck_all_columns(db_path):
    ds = Datasette([db_path])
    db = sqlite_utils.Database(db_path)
    db["creatures"].enable_fts(["name"])
    response1 = await ds.client.get(
        "/-/configure-fts/data",
        cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
    )
    csrftoken = response1.cookies["ds_csrftoken"]
    response2 = await ds.client.post(
        "/-/configure-fts/data",
        data={
            "csrftoken": csrftoken,
            "table": "creatures",
        },
        cookies={
            "ds_actor": ds.sign({"a": {"id": "root"}}, "actor"),
            "ds_csrftoken": csrftoken,
        },
    )
    assert response2.status_code == 302
    assert response2.headers["location"] == "/data/creatures"
    db = sqlite_utils.Database(db_path)
    assert db.table_names() == ["creatures"]


@pytest.mark.parametrize("authenticate", [True, False])
@pytest.mark.asyncio
async def test_table_actions(db_path, authenticate):
    ds = Datasette([db_path])
    cookies = None
    if authenticate:
        cookies = {"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")}
    response = await ds.client.get("/data/creatures", cookies=cookies)
    assert response.status_code == 200
    fragment = '<li><a href="/-/configure-fts/data?table=creatures">Configure full-text search</a></li>'
    if authenticate:
        # Should have column actions
        assert fragment in response.text
    else:
        assert fragment not in response.text
