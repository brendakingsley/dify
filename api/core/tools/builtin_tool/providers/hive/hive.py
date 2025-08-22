from typing import Any

from core.tools.builtin_tool.provider import BuiltinToolProviderController


class HiveToolProvider(BuiltinToolProviderController):
    def _validate_credentials(self, user_id: str, credentials: dict[str, Any]) -> None:
        """
        Validate the credentials for Hive connection
        """
        try:
            from pyhive import hive
            
            host = credentials.get("host")
            port = int(credentials.get("port", 10000))
            username = credentials.get("username")
            password = credentials.get("password")
            database = credentials.get("database", "default")
            
            if not host:
                raise ValueError("Host is required")
            
            # Test connection
            connection = hive.Connection(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                auth="PLAIN" if username else "NONE"
            )
            
            # Try a simple query to validate connection
            cursor = connection.cursor()
            cursor.execute("SHOW DATABASES")
            cursor.fetchone()
            cursor.close()
            connection.close()
            
        except ImportError:
            raise ValueError("PyHive is not installed. Please install it to use Hive tools.")
        except Exception as e:
            raise ValueError(f"Failed to connect to Hive: {str(e)}")