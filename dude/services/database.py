"""Shared connection settings without importing vector/embedding services."""

from psycopg.conninfo import make_conninfo


def build_connection_string(config):
    return make_conninfo(host=config.pg_host, port=config.pg_port,
                         dbname=config.pg_database, user=config.pg_user,
                         password=config.pg_password, connect_timeout=10)
