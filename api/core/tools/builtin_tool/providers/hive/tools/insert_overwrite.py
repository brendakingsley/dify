from collections.abc import Generator
from typing import Any, Optional
import time

from core.tools.builtin_tool.tool import BuiltinTool
from core.tools.entities.tool_entities import ToolInvokeMessage


class InsertOverwriteTool(BuiltinTool):
    def _invoke(
        self,
        user_id: str,
        tool_parameters: dict[str, Any],
        conversation_id: Optional[str] = None,
        app_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke Hive INSERT OVERWRITE tool
        """
        try:
            from pyhive import hive
        except ImportError:
            yield self.create_text_message("PyHive is not installed. Please install it to use Hive tools.")
            return
        
        query = tool_parameters.get("query", "").strip()
        timeout = tool_parameters.get("timeout", 300)
        
        if not query:
            yield self.create_text_message("Query is required")
            return
        
        # Validate that this is an INSERT OVERWRITE query
        query_upper = query.upper().strip()
        if not query_upper.startswith("INSERT OVERWRITE"):
            yield self.create_text_message("Query must be an INSERT OVERWRITE statement")
            return
        
        # Get credentials
        credentials = self.get_credentials()
        host = credentials.get("host")
        port = int(credentials.get("port", 10000))
        username = credentials.get("username")
        password = credentials.get("password")
        database = credentials.get("database", "default")
        
        try:
            # Connect to Hive
            connection = hive.Connection(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                auth="PLAIN" if username else "NONE"
            )
            
            cursor = connection.cursor()
            
            # Execute the INSERT OVERWRITE query
            start_time = time.time()
            yield self.create_text_message(f"Executing INSERT OVERWRITE query...")
            
            cursor.execute(query)
            
            # Wait for completion with timeout
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                cursor.close()
                connection.close()
                yield self.create_text_message(f"Query execution timeout after {timeout} seconds")
                return
            
            # Get affected rows count if available
            try:
                # For INSERT OVERWRITE, we may not get row count, but we can check if it completed
                affected_rows = cursor.rowcount if cursor.rowcount >= 0 else "Unknown"
            except:
                affected_rows = "Unknown"
            
            execution_time = time.time() - start_time
            
            cursor.close()
            connection.close()
            
            result_message = f"""INSERT OVERWRITE query executed successfully!

Query: {query}

Execution time: {execution_time:.2f} seconds
Affected rows: {affected_rows}

Note: INSERT OVERWRITE replaces existing data in the target table/partition."""
            
            yield self.create_text_message(result_message)
            
        except Exception as e:
            yield self.create_text_message(f"Error executing INSERT OVERWRITE query: {str(e)}")