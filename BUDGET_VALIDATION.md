# Budget Validation System

This document explains how to use the UWBot's budget validation system, which checks if clients have a positive surplus (net income > expenses).

## Overview

The budget validation system allows you to:
- Retrieve budget data from the database using your exact query structure
- Calculate total net income and total expenses
- Determine if a client has a positive surplus
- Get structured results with clear PASS/NO PASS recommendations
- Integrate with both API endpoints and Microsoft Teams

## Database Schema

The system works with your existing database structure:

```sql
-- Your exact query structure
SELECT 
    contacts.id,
    contacts.acctid,
    contacts.del,
    contacts.iscoapp,
    contacts.c_type,
    contacts.leadstatus,
    sum(case when field_type = 'I' THEN field_val ELSE 0 END) AS total_net_income,
    sum(case when field_type = 'E' THEN field_val ELSE 0 END) AS total_expenses
FROM contacts
LEFT JOIN budget_data ON budget_data.contact_id = contacts.id
LEFT JOIN budget_fields ON budget_data.field_id = budget_fields.id
WHERE contacts.id = :contact_id
    AND contacts.acctid = 2996 -- to show just the cdr clients
    AND contacts.c_type = 20588 -- to include just clients in underwriting stage
    AND contacts.del = 'f' -- to exclude deleted clients
    AND contacts.iscoapp = 0 -- to exclude the co app
    AND contacts.leadstatus = 134774 -- to include just leads with Submitted status
GROUP BY contacts.id, contacts.acctid, contacts.del, contacts.iscoapp, contacts.c_type, contacts.leadstatus
```

### Required Database Tables
- `contacts`: Main contact information
- `budget_data`: Budget values linked to contacts
- `budget_fields`: Budget field definitions with type (I=Income, E=Expense)

## API Usage

### 1. Debug Endpoint (Testing)

**Endpoint:** `POST /debug/budget`

**Request Body:**
```json
{
    "contact_id": 123,
    "user_id": "test-user"
}
```

**Response:**
```json
{
    "contact_id": 123,
    "budget_info": {
        "contact_id": 123,
        "total_net_income": 5000.0,
        "total_expenses": 3500.0,
        "analysis": {
            "result": "pass",
            "confidence": 1.0,
            "reason": "Positive surplus of $1,500.00 (Income: $5,000.00, Expenses: $3,500.00)",
            "total_net_income": 5000.0,
            "total_expenses": 3500.0,
            "surplus": 1500.0
        },
        "formatted_response": "✅ Contact 123 has a positive budget surplus..."
    },
    "response": "✅ Contact 123 has a positive budget surplus...",
    "success": true,
    "processing_time": 0.15
}
```

### 2. Teams Integration

Send messages in Microsoft Teams with budget-related keywords:

- "Budget check for contact 123"
- "Check surplus for contact 456"
- "Validate budget for contact 789"
- "Income analysis for contact 101"

The bot will automatically detect budget-related keywords and perform budget analysis.

## Result Classifications

The system provides a simple pass/no-pass assessment:

### 1. **PASS** ✅
- Positive surplus (net income > expenses)
- Client can be shown to agents
- **Example:** Income $5,000, Expenses $3,500 = Surplus $1,500

### 2. **NO PASS** ❌
- Negative surplus (net income < expenses)
- Client should not be shown to agents
- **Example:** Income $3,000, Expenses $4,500 = Deficit $1,500

## Validation Criteria

The system checks the following conditions:

1. **Client Type**: Only CDR clients (acctid = 2996)
2. **Stage**: Only underwriting stage clients (c_type = 20588)
3. **Status**: Only submitted leads (leadstatus = 134774)
4. **Exclusions**: 
   - Excludes deleted clients (del = 'f')
   - Excludes co-applicants (iscoapp = 0)

## Implementation Details

### Services

1. **BudgetValidationService** (`src/uwbot/services/budget_validation_service.py`)
   - Core budget analysis logic
   - Surplus calculation
   - Response formatting

2. **ContactService** (`src/uwbot/services/contact_service.py`)
   - Database queries for budget data
   - Integration with budget validation
   - Response formatting

### Database Models

Updated models in `src/uwbot/db/models.py`:
- `BudgetData`: Budget values linked to contacts
- `BudgetFields`: Budget field definitions

### API Endpoints

- **Debug Router**: `/debug/budget` for testing
- **Teams Router**: Automatic detection and processing

## Testing

### 1. Run the Test Script

```bash
python test_budget_validation.py
```

This will test various budget scenarios and show you how the system works.

### 2. Test with Real Data

```bash
# Using curl
curl -X POST "http://localhost:3978/debug/budget" \
  -H "Content-Type: application/json" \
  -d '{"contact_id": 123, "user_id": "test-user"}'
```

### 3. Test in Teams

Send a message like: "Budget check for contact 123"

## Configuration

### Environment Variables

Ensure these are set in your environment:

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Optional: AWS Secrets Manager
USE_AWS_SECRETS=true
AWS_DB_SECRET_NAME=your_secret_name
```

### Database Setup

Make sure your database has:
1. `contacts` table with the required fields
2. `budget_data` table with contact_id, field_id, and field_val
3. `budget_fields` table with field_type (I/E) definitions
4. Sample budget data for testing

## Error Handling

The system includes comprehensive error handling:

- **Database errors**: Graceful fallback with error messages
- **Missing data**: Clear indication of insufficient information
- **Invalid contact IDs**: Proper error messages
- **No budget data**: Clear indication when no budget information exists

## Monitoring and Logging

The system logs:
- Budget analysis requests and results
- Surplus calculations and validity decisions
- Processing times and performance metrics
- Error conditions and fallback scenarios

Check logs for entries like:
```
INFO: Budget analysis completed for contact 123: pass
INFO: Budget analysis failed for contact 456: Analysis failed
```

## Best Practices

1. **Always review edge cases**: Even with clear surplus calculations, review borderline cases
2. **Monitor data quality**: Ensure budget data is accurate and up-to-date
3. **Regular validation**: Run periodic checks to ensure system accuracy
4. **Document decisions**: Use the recommendations to guide agent workflows

## Troubleshooting

### Common Issues

1. **"Contact not found"**
   - Verify the contact ID exists in the database
   - Check if the contact meets the filtering criteria
   - Verify database connection and permissions

2. **"No budget data available"**
   - Ensure budget data is populated for the contact
   - Check if the contact meets the filtering criteria
   - Verify budget_data and budget_fields tables exist

3. **"Analysis failed"**
   - Check database configuration
   - Verify table structure and relationships
   - Review error logs for specific issues

4. **Incorrect surplus calculations**
   - Verify budget_data.field_val contains numeric values
   - Check budget_fields.field_type is correctly set (I/E)
   - Ensure proper aggregation in the query

### Debug Mode

Enable debug logging to see detailed analysis:

```python
import logging
logging.getLogger('uwbot.services.budget_validation_service').setLevel(logging.DEBUG)
```

## Support

For issues or questions:
1. Check the logs for error details
2. Run the test script to verify functionality
3. Review the API documentation
4. Contact the development team with specific error messages

## Integration with Existing Systems

The budget validation system integrates seamlessly with the existing hardship validation system:

- **Shared contact service**: Both systems use the same contact lookup logic
- **Unified API**: Both validation types are available through the same endpoints
- **Teams integration**: Automatic detection of validation type based on keywords
- **Consistent formatting**: Both systems provide similar response formats

## Future Enhancements

Potential improvements for the budget validation system:

1. **Advanced filtering**: Additional criteria for budget validation
2. **Historical analysis**: Track budget changes over time
3. **Risk scoring**: More sophisticated scoring algorithms
4. **Integration with other systems**: Connect with financial analysis tools
5. **Automated alerts**: Notifications for budget changes 