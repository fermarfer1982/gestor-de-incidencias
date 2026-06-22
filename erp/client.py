import logging
from contextlib import contextmanager

import mssql_python
from django.conf import settings

from erp.exceptions import SQLServerConnectionError, SQLServerQueryError

logger = logging.getLogger(__name__)


class SQLServerClient:
    def __init__(
        self,
        connection_string=None,
        connect_timeout=None,
        query_timeout=None,
        connect_function=None,
    ):
        self.connection_string = connection_string or settings.ERP_SQLSERVER_CONNECTION_STRING
        self.connect_timeout = (
            settings.ERP_SQLSERVER_CONNECT_TIMEOUT if connect_timeout is None else connect_timeout
        )
        self.query_timeout = settings.ERP_SQLSERVER_QUERY_TIMEOUT if query_timeout is None else query_timeout
        self.connect_function = connect_function or mssql_python.connect

    @contextmanager
    def connection(self):
        if not self.connection_string:
            raise SQLServerConnectionError("ERP_SQLSERVER_CONNECTION_STRING no configurada.")

        connection = None
        try:
            logger.info("Opening SQL Server connection")
            connection = self.connect_function(
                connection_str=self.connection_string,
                timeout=self.connect_timeout,
                autocommit=True,
            )
            connection.timeout = self.query_timeout
        except Exception as exc:
            logger.exception("Error connecting to SQL Server")
            raise SQLServerConnectionError("No se pudo conectar con SQL Server.") from exc

        try:
            yield connection
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    logger.warning("Error closing SQL Server connection", exc_info=True)

    def fetch_all(self, sql, params):
        with self.connection() as connection:
            cursor = connection.cursor()
            try:
                logger.info("Executing SQL Server query")
                cursor.execute(sql, *params)
                columns = [column[0] for column in (cursor.description or [])]
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            except Exception as exc:
                logger.exception("Error executing SQL Server query")
                raise SQLServerQueryError("No se pudo ejecutar la consulta en SQL Server.") from exc
            finally:
                try:
                    cursor.close()
                except Exception:
                    logger.warning("Error closing SQL Server cursor", exc_info=True)
