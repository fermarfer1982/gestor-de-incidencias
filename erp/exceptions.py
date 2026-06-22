class ERPIntegrationError(Exception):
    """Base exception for ERP integration failures."""


class SQLServerConnectionError(ERPIntegrationError):
    """Raised when the SQL Server connection cannot be established."""


class SQLServerQueryError(ERPIntegrationError):
    """Raised when a SQL Server query fails."""
