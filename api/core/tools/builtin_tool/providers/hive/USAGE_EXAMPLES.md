# Hive INSERT OVERWRITE Usage Examples

This document provides practical examples of how to use the Hive database tools in Dify workflows.

## Setup

1. **Configure Hive Provider**
   - Go to Tools section in Dify
   - Add Hive Database provider
   - Configure connection settings:
     - Host: `your-hive-server.company.com`
     - Port: `10000` 
     - Username: `your-username`
     - Password: `your-password`
     - Database: `your-database`

## INSERT OVERWRITE Examples

### Example 1: Daily Data Refresh
```sql
INSERT OVERWRITE TABLE daily_summary PARTITION(date='2024-12-19')
SELECT 
    product_id,
    COUNT(*) as order_count,
    SUM(amount) as total_revenue,
    AVG(amount) as avg_order_value
FROM raw_orders 
WHERE order_date = '2024-12-19'
GROUP BY product_id
```

### Example 2: Monthly Aggregation
```sql
INSERT OVERWRITE TABLE monthly_sales PARTITION(year=2024, month=12)
SELECT 
    region,
    category,
    SUM(sales_amount) as total_sales,
    COUNT(DISTINCT customer_id) as unique_customers
FROM daily_sales 
WHERE year = 2024 AND month = 12
GROUP BY region, category
```

### Example 3: Data Migration
```sql
INSERT OVERWRITE TABLE customer_master
SELECT 
    customer_id,
    first_name,
    last_name,
    email,
    registration_date,
    CASE 
        WHEN total_orders > 10 THEN 'VIP'
        WHEN total_orders > 5 THEN 'Regular'
        ELSE 'New'
    END as customer_tier
FROM customer_raw_data c
LEFT JOIN (
    SELECT customer_id, COUNT(*) as total_orders
    FROM orders 
    GROUP BY customer_id
) o ON c.customer_id = o.customer_id
```

## Query Tool Examples

### Example 1: Data Exploration
```sql
-- Check available tables
SHOW TABLES

-- Examine table structure  
DESCRIBE sales_data

-- Sample data review
SELECT * FROM customer_orders LIMIT 20
```

### Example 2: Data Analysis
```sql
-- Sales performance analysis
SELECT 
    product_category,
    SUM(sales_amount) as total_sales,
    COUNT(*) as transaction_count
FROM sales_data 
WHERE sales_date >= '2024-01-01'
GROUP BY product_category
ORDER BY total_sales DESC
LIMIT 10
```

### Example 3: Data Quality Checks
```sql
-- Check for null values
SELECT 
    COUNT(*) as total_records,
    COUNT(customer_id) as valid_customer_ids,
    COUNT(order_date) as valid_dates
FROM orders
WHERE order_date >= '2024-12-01'

-- Identify duplicates
SELECT customer_email, COUNT(*) as duplicate_count
FROM customers
GROUP BY customer_email
HAVING COUNT(*) > 1
```

## Workflow Integration

### Use Case 1: Automated ETL Pipeline
1. **Extract**: Use query tool to validate source data
2. **Transform**: Process data using business logic
3. **Load**: Use INSERT OVERWRITE to refresh target tables

### Use Case 2: Report Generation
1. **Data Preparation**: Use INSERT OVERWRITE to create reporting tables
2. **Analysis**: Use query tool to generate insights
3. **Export**: Extract final results for reporting

### Use Case 3: Data Validation
1. **Quality Check**: Use query tool to check data quality
2. **Correction**: Apply data corrections
3. **Refresh**: Use INSERT OVERWRITE to update clean datasets

## Best Practices

### Security
- ✅ Always validate data sources before INSERT OVERWRITE
- ✅ Use partition-specific overwriting when possible
- ✅ Test queries on small datasets first
- ❌ Never run INSERT OVERWRITE without backup plans

### Performance
- ✅ Use partitioned tables for large datasets
- ✅ Include appropriate WHERE clauses to limit data
- ✅ Set reasonable timeouts for long-running operations
- ✅ Monitor query execution times

### Data Integrity
- ✅ Verify row counts before and after operations
- ✅ Check data types and formats
- ✅ Validate business logic in transformations
- ✅ Maintain audit logs of data changes

## Error Handling

### Common Issues and Solutions

1. **Connection Timeout**
   - Increase timeout parameter
   - Check network connectivity
   - Verify Hive server status

2. **Permission Denied**
   - Verify username/password
   - Check database access permissions
   - Confirm table-level permissions

3. **Query Syntax Error**
   - Validate SQL syntax
   - Check table and column names
   - Verify partition specifications

4. **Performance Issues**
   - Add WHERE clauses to limit data
   - Use appropriate partitioning
   - Consider query optimization

## Integration with Dify Workflows

### Example Workflow: Daily Sales Processing
```
1. Trigger: Daily schedule (every morning at 6 AM)
2. Query Tool: Check if yesterday's data is available
3. INSERT OVERWRITE: Refresh daily sales summary
4. Query Tool: Validate updated data
5. Notification: Send completion status
```

### Example Workflow: Customer Segmentation
```
1. Trigger: Weekly schedule
2. Query Tool: Analyze customer behavior patterns
3. INSERT OVERWRITE: Update customer segments table
4. Query Tool: Generate segment statistics
5. Export: Create reports for marketing team
```

This comprehensive set of tools enables robust data processing workflows with Apache Hive, specifically supporting the INSERT OVERWRITE syntax that was requested.