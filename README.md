# datasette-configure-fts

[![PyPI](https://img.shields.io/pypi/v/datasette-configure-fts.svg)](https://pypi.org/project/datasette-configure-fts/)
[![CircleCI](https://circleci.com/gh/simonw/datasette-configure-fts.svg?style=svg)](https://circleci.com/gh/simonw/datasette-configure-fts)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/datasette-configure-fts/blob/master/LICENSE)

Datasette plugin for enabling full-text search against selected table columns

## Installation

Install this plugin in the same environment as Datasette.

    $ pip install datasette-configure-fts

## Usage

Navigate to `/-/configure-fts` on your Datasette instance to configure FTS for tables on attached writable databases.
