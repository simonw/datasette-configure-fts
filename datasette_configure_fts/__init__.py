from datasette import hookimpl
from .app import configure_fts_app


@hookimpl
def asgi_wrapper(datasette):
    def wrap_with_configure_fts(app):
        async def wrapped_app(scope, receive, send):
            path = scope["path"]
            if path == "/-/configure-fts" or path.startswith("/-/configure-fts/"):
                await (configure_fts_app(datasette))(scope, receive, send)
            else:
                await app(scope, receive, send)

        return wrapped_app

    return wrap_with_configure_fts
