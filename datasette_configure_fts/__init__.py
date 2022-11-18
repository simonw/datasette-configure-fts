from datasette import hookimpl
from datasette.utils.asgi import Response, NotFound, Forbidden
import urllib
import sqlite_utils


@hookimpl
def permission_allowed(actor, action):
    if action == "configure-fts" and actor and actor.get("id") == "root":
        return True


@hookimpl
def register_routes():
    return [
        (r"^/-/configure-fts$", configure_fts_index),
        (r"^/-/configure-fts/(?P<database>.*)$", configure_fts_database),
    ]


@hookimpl
def table_actions(datasette, actor, database, table):
    async def inner():
        if not await datasette.permission_allowed(
            actor, "configure-fts", default=False
        ):
            return []
        return [
            {
                "href": datasette.urls.path(
                    "/-/configure-fts/{}?{}".format(
                        database, urllib.parse.urlencode({"table": table})
                    )
                ),
                "label": "Configure full-text search",
            }
        ]

    return inner


def get_databases(datasette):
    return [
        db
        for db in datasette.databases.values()
        if db.is_mutable and db.name != "_internal"
    ]


async def configure_fts_index(datasette, request):
    if not await datasette.permission_allowed(
        request.actor, "configure-fts", default=False
    ):
        raise Forbidden("Permission denied for configure-fts")
    databases = get_databases(datasette)
    if 1 == len(databases):
        return Response.redirect(
            "/-/configure-fts/{}".format(urllib.parse.quote_plus(databases[0].name))
        )
    return Response.html(
        await datasette.render_template(
            "configure_fts_index.html", {"databases": databases}, request=request
        )
    )


async def configure_fts_database(datasette, request):
    if not await datasette.permission_allowed(
        request.actor, "configure-fts", default=False
    ):
        raise Forbidden("Permission denied for configure-fts")
    if request.method == "POST":
        return await configure_fts_database_post(datasette, request)
    else:
        return await configure_fts_database_get(datasette, request)


async def configure_fts_database_get(datasette, request):
    databases = get_databases(datasette)
    database_name = request.url_vars["database"]
    just_these_tables = set(request.args.getlist("table"))
    try:
        database = [db for db in databases if db.name == database_name][0]
    except IndexError:
        raise NotFound("Database not found")
    tables = []
    hidden_tables = set(await database.hidden_table_names())
    for table_name in await database.table_names():
        if just_these_tables and table_name not in just_these_tables:
            continue
        if table_name in hidden_tables:
            continue
        # Only text columns
        def find_text_columns(conn):
            columns_and_types = sqlite_utils.Database(conn)[table_name].columns_dict
            return [
                column for column, dtype in columns_and_types.items() if dtype is str
            ]

        columns = await database.execute_write_fn(find_text_columns, block=True)
        fts_table = await database.fts_table(table_name)
        searchable_columns = []
        if fts_table:
            searchable_columns = await database.table_columns(fts_table)
        tables.append(
            {
                "name": table_name,
                "columns": columns,
                "searchable_columns": searchable_columns,
                "fts_table": fts_table,
            }
        )
    return Response.html(
        await datasette.render_template(
            "configure_fts_database.html",
            {
                "database": database,
                "tables": tables,
            },
            request=request,
        )
    )


async def configure_fts_database_post(datasette, request):
    formdata = await request.post_vars()
    database_name = request.url_vars["database"]
    columns = [c.split(".", 1)[1] for c in formdata.keys() if c.startswith("column.")]
    table = formdata["table"]

    def enable_fts(conn):
        db = sqlite_utils.Database(conn)
        db[table].disable_fts()
        if columns:
            db[table].enable_fts(columns, create_triggers=True)

    await datasette.databases[database_name].execute_write_fn(enable_fts, block=True)

    return Response.redirect(
        "/{}/{}".format(
            urllib.parse.quote_plus(database_name), urllib.parse.quote_plus(table)
        )
    )
