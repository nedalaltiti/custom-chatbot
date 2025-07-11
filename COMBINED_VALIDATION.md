# Combined Hardship and Budget Validation System

This document explains how to use the UWBot's **combined validation system**, which analyzes both hardship AND budget data for contacts in a single comprehensive assessment.

## Overview

The combined validation system allows you to:
- **Retrieve both hardship and budget data** for a contact simultaneously
- **Analyze both datasets** using AI-powered hardship analysis and budget calculations
- **Get a unified assessment** with clear recommendations
- **Handle mixed results** intelligently with manual review recommendations
- **Integrate seamlessly** with both API endpoints and Microsoft Teams

## How It Works

The system performs **three types of validation**:

### 1. **Hardship Validation** 🔍
- Analyzes financial hardship claims using AI
- Checks hardship descriptions and financial hardship status
- Provides confidence scores and detailed reasoning
- Uses the Gemini AI model for intelligent analysis

### 2. **Budget Validation** 💰
- Calculates total net income and total expenses
- Determines if client has positive surplus (income > expenses)
- Uses your exact SQL query structure with specific criteria
- Provides clear PASS/NO PASS recommendations

### 3. **Combined Assessment** 📊
- Evaluates both validations together
- Provides unified recommendation
- Handles edge cases and mixed results
- Gives clear action guidance

## Result Classifications

The combined system provides **four possible outcomes**:

### ✅ **PASS** - APPROVE
- **Both validations pass** OR
- **One validation passes with high confidence** (≥80%)
- **Recommendation:** Can be shown to agents for further processing
- **Example:** Hardship passes + Budget shows positive surplus

### ❌ **NO PASS** - REJECT
- **Both validations fail** OR
- **Insufficient data** for meaningful analysis
- **Recommendation:** Should not be shown to agents
- **Example:** Hardship fails + Budget shows negative surplus

### ⚠️ **MIXED** - MANUAL REVIEW
- **One validation passes, one fails** with moderate confidence
- **Recommendation:** Requires supervisor review before proceeding
- **Example:** Hardship passes but budget fails, or vice versa

### ❓ **NO DATA** - INSUFFICIENT DATA
- **No validation data available** for either hardship or budget
- **Recommendation:** Contact may need additional data collection
- **Example:** Contact exists but has no hardship or budget records

## API Usage

### 1. Debug Endpoint (Testing)

**Endpoint:** `POST /api/debug/combined`

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
    "hardship_info": {
        "result": "pass",
        "confidence": 0.85,
        "reason": "Clear evidence of legitimate hardship with proper documentation"
    },
    "budget_info": {
        "result": "pass",
        "confidence": 1.0,
        "reason": "Positive surplus of $1,500.00 (Income: $5,000.00, Expenses: $3,500.00)",
        "total_net_income": 5000.0,
        "total_expenses": 3500.0,
        "surplus": 1500.0
    },
    "combined_result": "pass",
    "response": "# 📊 Combined Validation Analysis for Contact 123\n\n## ✅ OVERALL RESULT: PASS\n\n### 🔍 Hardship Validation\n**Status:** ✅ PASS\n**Confidence:** 85.0%\n**Reason:** Clear evidence of legitimate hardship...\n\n### 💰 Budget Validation\n**Status:** ✅ PASS\n**Confidence:** 100.0%\n**Reason:** Positive surplus of $1,500.00...\n\n### 📋 Summary & Recommendation\n✅ RECOMMENDATION: APPROVE\nThis client shows positive indicators in both hardship and budget validation.\n**Action:** Can be shown to agents for further processing.",
    "success": true,
    "processing_time": 2.45
}
```

### 2. Teams Integration

Send messages in Microsoft Teams with **combined validation keywords**:

#### **Combined Validation Keywords:**
- "Full validation for contact 123"
- "Check both hardship and budget for contact 456"
- "Complete analysis for contact 789"
- "Everything for contact 101"
- "Comprehensive validation for contact 202"

#### **Individual Validation Keywords:**
- **Hardship only:** "Contact 123", "Check hardship for contact 456"
- **Budget only:** "Budget check for contact 789", "Check surplus for contact 101"

## Database Queries

The system uses your exact query structures:

### Hardship Query
```sql
SELECT contacts.id,
       contacts.acctid,
       contacts.del,
       contacts.iscoapp,
       contacts.c_type,
       contacts.leadstatus,
       financial_hardship.f_string as financial_hardship,
       hardship_description.f_string as hardship_description
FROM contacts
LEFT JOIN contacts_userfields financial_hardship ON contacts.id = financial_hardship.contact_id AND financial_hardship.custom_id = 322256
LEFT JOIN contacts_userfields hardship_description ON contacts.id = hardship_description.contact_id AND hardship_description.custom_id = 322271
WHERE contacts.id = :contact_id
```

### Budget Query
```sql
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
    AND contacts.acctid = 2996
    AND contacts.c_type = 20588
    AND contacts.del = 'f'
    AND contacts.iscoapp = 0
    AND contacts.leadstatus = 134774
GROUP BY contacts.id, contacts.acctid, contacts.del, contacts.iscoapp, contacts.c_type, contacts.leadstatus
```

## Implementation Details

### Services

1. **ContactService** (`src/uwbot/services/contact_service.py`)
   - `get_contact_combined_validation()` - Main combined validation method
   - `_determine_combined_result()` - Logic for combining results
   - `_format_combined_response()` - Comprehensive response formatting

2. **HardshipValidationService** (`src/uwbot/services/hardship_validation_service.py`)
   - AI-powered hardship analysis
   - Confidence scoring
   - Detailed reasoning

3. **BudgetValidationService** (`src/uwbot/services/budget_validation_service.py`)
   - Surplus calculations
   - Budget data analysis
   - Financial recommendations

### API Endpoints

1. **Debug Endpoint:** `POST /api/debug/combined`
   - For testing and development
   - Returns detailed JSON response

2. **Teams Integration:** Automatic detection via keywords
   - Detects "both", "combined", "full", "complete", "all", "everything"
   - Provides comprehensive analysis in Teams chat

## Usage Examples

### Teams Messages

#### Combined Validation:
```
User: "Full validation for contact 123"
Bot: [Comprehensive analysis with both hardship and budget results]

User: "Check both hardship and budget for contact 456"
Bot: [Detailed breakdown of both validations]

User: "Complete analysis for contact 789"
Bot: [Unified assessment with recommendation]
```

#### Individual Validation:
```
User: "Contact 123"
Bot: [Hardship validation only]

User: "Budget check for contact 456"
Bot: [Budget validation only]
```

### API Testing

```bash
# Test combined validation
curl -X POST http://localhost:3978/api/debug/combined \
  -H "Content-Type: application/json" \
  -d '{"contact_id": 123, "user_id": "test-user"}'

# Test individual validations
curl -X POST http://localhost:3978/api/debug/contact \
  -H "Content-Type: application/json" \
  -d '{"contact_id": 123, "user_id": "test-user"}'

curl -X POST http://localhost:3978/api/debug/budget \
  -H "Content-Type: application/json" \
  -d '{"contact_id": 123, "user_id": "test-user"}'
```

## Test Script

Run the test script to see the combined validation in action:

```bash
python test_combined_validation.py
```

This will test multiple contact IDs and show detailed results for each validation type.

## Best Practices

### 1. **Use Combined Validation for Comprehensive Assessment**
- When you need a complete picture of a client's situation
- For final approval/rejection decisions
- When both hardship and budget data are available

### 2. **Use Individual Validation for Specific Focus**
- When you only need hardship analysis
- When you only need budget analysis
- For quick checks or specific concerns

### 3. **Handle Mixed Results Appropriately**
- Mixed results require manual review
- Don't automatically approve or reject
- Escalate to supervisor for decision

### 4. **Monitor Data Quality**
- Ensure both hardship and budget data are accurate
- Regular validation of data completeness
- Address missing or inconsistent data

## Troubleshooting

### Common Issues

1. **"No validation data available"**
   - Check if contact exists in database
   - Verify hardship and budget data are populated
   - Check database permissions and connections

2. **"Mixed results"**
   - This is expected behavior for edge cases
   - Review both hardship and budget data manually
   - Consider additional data collection

3. **"Analysis failed"**
   - Check database configuration
   - Verify AI service connectivity
   - Review error logs for specific issues

4. **"Incorrect results"**
   - Verify data accuracy in database
   - Check query criteria and filters
   - Review AI analysis prompts and logic

### Debug Mode

Enable detailed logging to troubleshoot issues:

```python
import logging
logging.getLogger('uwbot.services.contact_service').setLevel(logging.DEBUG)
logging.getLogger('uwbot.services.hardship_validation_service').setLevel(logging.DEBUG)
logging.getLogger('uwbot.services.budget_validation_service').setLevel(logging.DEBUG)
```

## Integration with Existing Systems

The combined validation system integrates seamlessly with your existing workflow:

- **Unified API**: Same endpoints, enhanced functionality
- **Teams Integration**: Automatic detection and response
- **Database Compatibility**: Uses your existing schema
- **Backward Compatibility**: Individual validations still work
- **Scalable**: Easy to extend with additional validation types

## Support

For issues or questions:
1. Check the logs for detailed error information
2. Run the test script to verify functionality
3. Review the API documentation
4. Contact the development team with specific error messages

## Future Enhancements

Potential improvements for the combined validation system:

1. **Additional Validation Types**: Credit score, employment verification, etc.
2. **Weighted Scoring**: Different weights for different validation types
3. **Historical Analysis**: Track validation results over time
4. **Automated Workflows**: Integration with approval/rejection processes
5. **Advanced Analytics**: Trend analysis and reporting features 