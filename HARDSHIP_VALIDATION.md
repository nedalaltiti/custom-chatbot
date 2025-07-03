# Financial Hardship Validation System

This document explains how to use the UWBot's financial hardship validation system, which uses the Gemini AI model to analyze and validate hardship claims.

## Overview

The hardship validation system allows you to:
- Retrieve hardship data from the database using your exact query structure
- Analyze hardship validity using AI-powered analysis
- Get structured results with confidence scores and recommendations
- Integrate with both API endpoints and Microsoft Teams

## Database Schema

The system works with your existing database structure:

```sql
-- Your exact query structure
SELECT contacts.id,
       contacts.acctid,
       contacts.del,
       contacts.iscoapp,
       contacts.c_type,
       contacts.leadstatus,
       financial_hardship.f_string as financial_hardship,
       hardship_description.f_string as hardship_description,
       financial_hardship_details.f_string as financial_hardship_details
FROM contacts
LEFT JOIN contacts_userfields financial_hardship ON contacts.id = financial_hardship.contact_id AND financial_hardship.custom_id = 322256
LEFT JOIN contacts_userfields hardship_description ON contacts.id = hardship_description.contact_id AND hardship_description.custom_id = 322271
LEFT JOIN contacts_userfields financial_hardship_details ON contacts.id = financial_hardship_details.contact_id AND financial_hardship_details.custom_id = 322256
WHERE contacts.id = :contact_id
```

### Required Custom Field IDs
- `322256`: Financial hardship status/details
- `322271`: Hardship description

## API Usage

### 1. Debug Endpoint (Testing)

**Endpoint:** `POST /debug/contact`

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
    "hardship_data": {
        "contact_id": 123,
        "financial_hardship": "Yes",
        "hardship_description": "Lost job due to downsizing...",
        "financial_hardship_details": "Monthly income reduced..."
    },
    "analysis": {
        "result": "pass",
        "confidence": 0.85,
        "reason": "Clear evidence of legitimate hardship with proper documentation and reasonable circumstances"
    },
    "formatted_response": "**Financial Hardship Analysis for Contact 123**\n\n**Result:** PASS\n**Confidence:** 85.0%\n\n**Reason:** Clear evidence of legitimate hardship with proper documentation and reasonable circumstances",
    "success": true,
    "processing_time": 2.34,
    "error": null
}
```

### 2. Teams Integration

Send messages in Microsoft Teams with contact IDs:

- "Contact 123"
- "Get hardship analysis for contact 456"
- "Check contact 789"

The bot will automatically detect contact IDs and perform hardship analysis.

## Result Classifications

The system provides a simple pass/no-pass assessment:

### 1. **PASS** ✅
- Clear evidence of legitimate hardship
- Proper documentation provided
- Reasonable and verifiable circumstances
- **Example:** Medical emergency with bills, job loss with unemployment records

### 2. **NO_PASS** ❌
- Insufficient documentation
- Fraudulent or non-compliant claim
- Clearly unreasonable hardship
- **Example:** Vacation requests, luxury purchases, missing documentation

## Confidence Scoring

The system provides confidence scores from 0.0 to 1.0:

- **0.9-1.0**: Very high confidence
- **0.7-0.89**: High confidence with minor uncertainties
- **0.5-0.69**: Moderate confidence, some uncertainty
- **0.3-0.49**: Low confidence, significant uncertainty
- **0.0-0.29**: Very low confidence, highly uncertain



## Implementation Details

### Services

1. **HardshipValidationService** (`src/uwbot/services/hardship_validation_service.py`)
   - Core AI analysis logic
   - Prompt engineering for Gemini
   - Response parsing and validation

2. **ContactService** (`src/uwbot/services/contact_service.py`)
   - Database queries for hardship data
   - Integration with hardship validation
   - Response formatting

### Database Models

Updated models in `src/uwbot/db/models.py`:
- `Contact`: Extended with hardship-related fields
- `ContactUserField`: New model for custom fields

### API Endpoints

- **Debug Router**: `/debug/contact` for testing
- **Teams Router**: Automatic detection and processing

## Testing

### 1. Run the Test Script

```bash
python test_hardship_validation.py
```

This will test various hardship scenarios and show you how the system works.

### 2. Test with Real Data

```bash
# Using curl
curl -X POST "http://localhost:3978/debug/contact" \
  -H "Content-Type: application/json" \
  -d '{"contact_id": 123, "user_id": "test-user"}'
```

### 3. Test in Teams

Send a message like: "Contact 123"

## Configuration

### Environment Variables

Ensure these are set in your environment:

```bash
# Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Optional: AWS Secrets Manager
USE_AWS_SECRETS=true
GEMINI_SECRET_NAME=your_secret_name
```

### Database Setup

Make sure your database has:
1. `contacts` table with hardship-related fields
2. `contacts_userfields` table with the correct custom field IDs
3. Sample hardship data for testing

## Error Handling

The system includes comprehensive error handling:

- **Database errors**: Graceful fallback with error messages
- **AI service errors**: Fallback analysis with reduced confidence
- **Parsing errors**: Default analysis with manual review flag
- **Missing data**: Clear indication of insufficient information

## Monitoring and Logging

The system logs:
- Hardship analysis requests and results
- Confidence scores and validity decisions
- Processing times and performance metrics
- Error conditions and fallback scenarios

Check logs for entries like:
```
INFO: Hardship analysis completed for contact 123: valid
INFO: Hardship analysis failed for contact 456: Analysis failed
```

## Best Practices

1. **Always review high-risk cases**: Even with high confidence, review cases marked as high risk
2. **Document decisions**: Use the recommendations to guide manual review processes
3. **Monitor confidence scores**: Low confidence cases may need additional documentation
4. **Regular model updates**: The AI analysis can be improved with feedback and retraining

## Troubleshooting

### Common Issues

1. **"Contact not found"**
   - Verify the contact ID exists in the database
   - Check database connection and permissions

2. **"No hardship data available"**
   - Ensure hardship fields are populated for the contact
   - Verify custom field IDs match the expected values

3. **"Analysis failed"**
   - Check Gemini API configuration
   - Verify API key and service availability
   - Review error logs for specific issues

4. **Low confidence scores**
   - This is normal for complex or unusual cases
   - Use manual review for low-confidence results
   - Consider requesting additional documentation

### Debug Mode

Enable debug logging to see detailed analysis:

```python
import logging
logging.getLogger('uwbot.services.hardship_validation_service').setLevel(logging.DEBUG)
```

## Support

For issues or questions:
1. Check the logs for error details
2. Run the test script to verify functionality
3. Review the API documentation
4. Contact the development team with specific error messages 