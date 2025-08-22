from collections.abc import Generator
from typing import Any, Optional

from core.tools.builtin_tool.tool import BuiltinTool
from core.tools.entities.tool_entities import ToolInvokeMessage


class QueryTool(BuiltinTool):
    def _invoke(
        self,
        user_id: str,
        tool_parameters: dict[str, Any],
        conversation_id: Optional[str] = None,
        app_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke Hive Query tool
        """
        try:
            from pyhive import hive
        except ImportError:
            yield self.create_text_message("PyHive is not installed. Please install it to use Hive tools.")
            return
        
        query = tool_parameters.get("query", "").strip()
        limit = tool_parameters.get("limit", 100)
        
        if not query:
            yield self.create_text_message("Query is required")
            return
        
        # Validate safe query types - block potentially dangerous operations
        query_upper = query.upper().strip()
        dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", "INSERT", "UPDATE"]
        
        if any(query_upper.startswith(keyword) for keyword in dangerous_keywords):
            yield self.create_text_message(f"Query type not allowed. This tool only supports read operations like SELECT, SHOW, DESCRIBE.")
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
            
            # Execute the query
            yield self.create_text_message(f"Executing query: {query}")
            
            cursor.execute(query)
            
            # Fetch results
            if query_upper.startswith("SELECT"):
                # For SELECT queries, fetch limited results
                results = cursor.fetchmany(limit)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                
                if not results:
                    yield self.create_text_message("Query executed successfully but returned no results.")
                else:
                    # Format results as table
                    result_text = f"Query Results ({len(results)} rows):\n\n"
                    
                    # Add column headers
                    if columns:
                        result_text += " | ".join(columns) + "\n"
                        result_text += " | ".join(["-" * len(col) for col in columns]) + "\n"
                    
                    # Add data rows
                    for row in results:
                        row_data = [str(item) if item is not None else "NULL" for item in row]
                        result_text += " | ".join(row_data) + "\n"
                    
                    if len(results) == limit:
                        result_text += f"\n(Results limited to {limit} rows)"
                    
                    yield self.create_text_message(result_text)
            else:
                # For other queries (SHOW, DESCRIBE, etc.), fetch all results
                results = cursor.fetchall()
                
                if not results:
                    yield self.create_text_message("Query executed successfully.")
                else:
                    result_text = "Query Results:\n\n"
                    for row in results:
                        if isinstance(row, tuple):
                            result_text += " | ".join([str(item) if item is not None else "NULL" for item in row]) + "\n"
                        else:
                            result_text += str(row) + "\n"
                    
                    yield self.create_text_message(result_text)
            
            cursor.close()
            connection.close()
            
        except Exception as e:
            yield self.create_text_message(f"Error executing query: {str(e)}")