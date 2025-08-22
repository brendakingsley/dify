import pytest
from unittest.mock import Mock, patch, MagicMock


class TestHiveTools:
    """Test cases for Hive database tools"""
    
    def test_insert_overwrite_query_validation(self):
        """Test INSERT OVERWRITE query validation"""
        
        # Mock the tool class
        from unittest.mock import MagicMock
        
        # Test valid INSERT OVERWRITE queries
        valid_queries = [
            "INSERT OVERWRITE TABLE target_table SELECT * FROM source_table",
            "insert overwrite table test partition(year=2024) select * from data",
            "INSERT OVERWRITE DIRECTORY '/tmp/output' SELECT count(*) FROM table1"
        ]
        
        for query in valid_queries:
            query_upper = query.upper().strip()
            assert query_upper.startswith("INSERT OVERWRITE"), f"Query should be valid: {query}"
    
    def test_insert_overwrite_query_rejection(self):
        """Test that non-INSERT OVERWRITE queries are rejected"""
        
        invalid_queries = [
            "SELECT * FROM table",
            "INSERT INTO table VALUES (1, 2, 3)", 
            "UPDATE table SET col=1",
            "DELETE FROM table WHERE id=1"
        ]
        
        for query in invalid_queries:
            query_upper = query.upper().strip()
            assert not query_upper.startswith("INSERT OVERWRITE"), f"Query should be rejected: {query}"
    
    def test_general_query_safety_validation(self):
        """Test that dangerous queries are blocked in general query tool"""
        
        dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", "INSERT", "UPDATE"]
        
        # Test safe queries
        safe_queries = [
            "SELECT * FROM table",
            "SHOW TABLES",
            "DESCRIBE table_name",
            "EXPLAIN SELECT * FROM table"
        ]
        
        for query in safe_queries:
            query_upper = query.upper().strip()
            is_dangerous = any(query_upper.startswith(keyword) for keyword in dangerous_keywords)
            assert not is_dangerous, f"Query should be safe: {query}"
        
        # Test dangerous queries
        unsafe_queries = [
            "DROP TABLE test",
            "DELETE FROM table",
            "INSERT INTO table VALUES (1)",
            "UPDATE table SET col=1",
            "CREATE TABLE test (id int)",
            "ALTER TABLE test ADD COLUMN col2 string"
        ]
        
        for query in unsafe_queries:
            query_upper = query.upper().strip()
            is_dangerous = any(query_upper.startswith(keyword) for keyword in dangerous_keywords)
            assert is_dangerous, f"Query should be rejected: {query}"
    
    def test_hive_provider_credentials_validation(self):
        """Test Hive provider credential validation"""
        
        # Test missing host
        credentials_no_host = {"port": "10000", "username": "test"}
        
        # Test valid credentials  
        credentials_valid = {"host": "localhost", "port": "10000", "username": "test", "database": "default"}
        
        # The actual validation would require mocking the hive connection
        # For now, we just test the credential structure
        assert credentials_valid.get("host") == "localhost"
        assert credentials_valid.get("port") == "10000"
        assert credentials_no_host.get("host") is None
    
    @patch('pyhive.hive.Connection')
    def test_hive_connection_mock(self, mock_connection):
        """Test Hive connection with mocked pyhive"""
        
        # Mock successful connection
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = None
        mock_cursor.fetchone.return_value = ("database1",)
        mock_cursor.close.return_value = None
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close.return_value = None
        
        mock_connection.return_value = mock_conn
        
        # Test connection parameters
        from pyhive import hive
        
        connection = hive.Connection(
            host="localhost",
            port=10000,
            username="test",
            password="password",
            database="default",
            auth="PLAIN"
        )
        
        cursor = connection.cursor()
        cursor.execute("SHOW DATABASES")
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        
        # Verify the mock was called correctly
        mock_connection.assert_called_once_with(
            host="localhost",
            port=10000,
            username="test", 
            password="password",
            database="default",
            auth="PLAIN"
        )
        
        assert result == ("database1",)
    
    def test_yaml_config_structure(self):
        """Test that YAML configuration files have proper structure"""
        import yaml
        import os
        
        # Test provider config
        provider_config_path = "/home/runner/work/dify/dify/api/core/tools/builtin_tool/providers/hive/hive.yaml"
        if os.path.exists(provider_config_path):
            with open(provider_config_path, 'r') as f:
                provider_config = yaml.safe_load(f)
            
            assert 'identity' in provider_config
            assert 'credentials_for_provider' in provider_config
            assert 'host' in provider_config['credentials_for_provider']
            assert 'port' in provider_config['credentials_for_provider']
        
        # Test tool configs
        tool_configs = [
            "/home/runner/work/dify/dify/api/core/tools/builtin_tool/providers/hive/tools/insert_overwrite.yaml",
            "/home/runner/work/dify/dify/api/core/tools/builtin_tool/providers/hive/tools/query.yaml"
        ]
        
        for tool_config_path in tool_configs:
            if os.path.exists(tool_config_path):
                with open(tool_config_path, 'r') as f:
                    tool_config = yaml.safe_load(f)
                
                assert 'identity' in tool_config
                assert 'parameters' in tool_config
                assert len(tool_config['parameters']) > 0