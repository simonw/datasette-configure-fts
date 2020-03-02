from setuptools import setup
import os

VERSION = "0.1.1a"


def get_long_description():
    with open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        encoding="utf8",
    ) as fp:
        return fp.read()


setup(
    name="datasette-configure-fts",
    description="Datasette plugin for enabling full-text search against selected table columns",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="Simon Willison",
    url="https://github.com/simonw/datasette-configure-fts",
    license="Apache License, Version 2.0",
    version=VERSION,
    packages=["datasette_configure_fts"],
    entry_points={"datasette": ["configure_fts = datasette_configure_fts"]},
    install_requires=[
        "datasette",
        "sqlite-utils",
        "starlette",
        "python-multipart",
        "asgi-csrf~=0.2.2a0",
    ],
    extras_require={"test": ["pytest", "pytest-asyncio", "httpx"]},
    tests_require=["datasette-configure-fts[test]"],
    package_data={"datasette_configure_fts": ["templates/*.html"]},
)
