# Hive Database Tools

This directory contains the Apache Hive database tools for Dify. These tools allow users to connect to Hive databases and execute SQL queries, with a focus on supporting the INSERT OVERWRITE syntax.

## Tools Included

### 1. Insert Overwrite Tool (`insert_overwrite.py`)

Executes Hive INSERT OVERWRITE statements to replace existing data in tables or partitions.

**Features:**
- Validates that queries are INSERT OVERWRITE statements
- Supports table and partition overwriting
- Includes timeout configuration for long-running operations
- Provides execution feedback and timing information

**Example Usage:**
```sql
INSERT OVERWRITE TABLE target_table PARTITION(year=2024) 
SELECT * FROM source_table WHERE date >= '2024-01-01'
```

### 2. Query Tool (`query.py`)

Executes general Hive SQL queries for data retrieval and analysis.

**Features:**
- Supports SELECT, SHOW, DESCRIBE, and EXPLAIN queries
- Blocks dangerous operations (DROP, DELETE, etc.) for safety
- Configurable result limit to prevent overwhelming responses
- Formatted table output for SELECT queries

**Example Usage:**
```sql
SELECT * FROM sales_data LIMIT 100
SHOW TABLES
DESCRIBE customer_table
```

## Configuration

The Hive provider requires the following credentials:

- **Host**: Hive server hostname
- **Port**: Hive server port (default: 10000)  
- **Username**: Authentication username (optional)
- **Password**: Authentication password (optional)
- **Database**: Default database name (optional, defaults to "default")

## Security Features

- **Query Validation**: INSERT OVERWRITE tool only accepts INSERT OVERWRITE statements
- **Operation Restrictions**: Query tool blocks dangerous operations like DROP, DELETE, CREATE, etc.
- **Result Limits**: Configurable limits prevent excessive data retrieval
- **Connection Validation**: Credentials are validated before query execution

## Dependencies

- `pyhive>=0.7.0`: Python interface to Hive
- `sasl>=0.3.1`: SASL authentication support  
- `thrift>=0.16.0`: Thrift protocol support

## Installation

The required dependencies are included in the `tools` dependency group in `pyproject.toml`.

## Error Handling

Both tools include comprehensive error handling for:
- Connection failures
- Invalid queries
- Authentication errors
- Query execution timeouts
- Missing dependencies

## Implementation Notes

- Both tools follow the Dify builtin tool pattern
- YAML configuration files define tool parameters and descriptions
- Tools support both English and Chinese (Simplified) localization
- Connection pooling is handled per-request for simplicity
- Query execution includes timing and result metrics