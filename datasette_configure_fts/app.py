from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Router, Route
from starlette.endpoints import HTTPEndpoint
from starlette.exceptions import HTTPException
from urllib.parse import quote_plus
from asgi_csrf import asgi_csrf
import sqlite_utils


def configure_fts_app(datasette):
    ConfigureFtsIndex, ConfigureFtsDatabase = get_classes(datasette)
    return asgi_csrf(
        Router(
            routes=[
                Route("/-/configure-fts", endpoint=ConfigureFtsIndex),
                Route("/-/configure-fts/{database}", endpoint=ConfigureFtsDatabase),
            ]
        )
    )


def get_classes(datasette):
    class ConfigureFtsIndex(HTTPEndpoint):
        def get_databases(self):
            return [db for db in datasette.databases.values() if db.is_mutable]

        async def get(self, request):
            databases = self.get_databases()
            if 1 == len(databases):
                return RedirectResponse(
                    url="/-/configure-fts/{}".format(quote_plus(databases[0].name)),
                    status_code=302,
                )
            return HTMLResponse(
                await datasette.render_template(
                    "configure_fts_index.html", {"databases": databases}
                )
            )

    class ConfigureFtsDatabase(ConfigureFtsIndex):
        async def get(self, request):
            databases = self.get_databases()
            database_name = request.path_params["database"]
            just_these_tables = set(request.query_params.getlist("table"))
            try:
                database = [db for db in databases if db.name == database_name][0]
            except IndexError:
                raise HTTPException(status_code=404, detail="Database not found")
            tables = []
            hidden_tables = set(await database.hidden_table_names())
            for table_name in await database.table_names():
                if just_these_tables and table_name not in just_these_tables:
                    continue
                if table_name in hidden_tables:
                    continue
                # Only text columns
                def find_text_columns(conn):
                    columns_and_types = sqlite_utils.Database(conn)[
                        table_name
                    ].columns_dict
                    return [
                        column
                        for column, dtype in columns_and_types.items()
                        if dtype is str
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
            return HTMLResponse(
                await datasette.render_template(
                    "configure_fts_database.html",
                    {
                        "database": database,
                        "tables": tables,
                        "csrftoken": request.scope.get("csrftoken", ""),
                    },
                )
            )

        async def post(self, request):
            formdata = await request.form()
            database_name = request.path_params["database"]
            columns = [
                c.split(".", 1)[1] for c in formdata.keys() if c.startswith("column.")
            ]
            table = formdata["table"]

            def enable_fts(conn):
                db = sqlite_utils.Database(conn)
                db[table].disable_fts()
                db[table].enable_fts(columns, create_triggers=True)

            await datasette.databases[database_name].execute_write_fn(
                enable_fts, block=True
            )

            return RedirectResponse(
                "/{}/{}".format(quote_plus(database_name), quote_plus(table)),
                status_code=302,
            )

    return ConfigureFtsIndex, ConfigureFtsDatabase
