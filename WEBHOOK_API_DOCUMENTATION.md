# Daily Attendance Webhook API Documentation

## Overview
This webhook receives daily attendance data in CSV format from external systems and stores it in MongoDB.

**Webhook Access Key:** `vdm_attendance_webhook_2025`

---

## Endpoints

### 1. POST `/attendance/webhook/daily-attendance/`
Receives and processes attendance CSV data.

### 2. GET `/attendance/webhook/status/`
Get webhook statistics and status.

---

## Authentication

Include the access key in **one** of the following ways:

### Option 1: Header (Recommended)
```
X-Webhook-Key: vdm_attendance_webhook_2025
```

### Option 2: Query Parameter
```
?key=vdm_attendance_webhook_2025
```

---

## CSV Format

### Required Columns
The CSV must have these columns (column names are flexible):

| Column | Accepted Names | Format | Example |
|--------|---------------|---------|---------|
| Enrollment Number | `enrollment_number`, `enrol_no`, `roll_number`, `rollnumber`, `student_id` | Integer | `2110000` |
| Status | `status`, `type`, `action` | String: `in` or `out` | `in` |
| Timestamp | `timestamp`, `time`, `datetime`, `date_time` | Various formats supported | `2025-01-15 09:00:00` |

### Sample CSV File

**daily_attendance.csv:**
```csv
enrollment_number,status,timestamp
2110001,in,2025-01-15 09:00:00
2110001,out,2025-01-15 17:30:00
2110002,in,2025-01-15 09:15:00
2110003,in,2025-01-15 09:05:00
2110002,out,2025-01-15 17:45:00
```

### Alternative Formats (All Supported)

**With time only (uses today's date):**
```csv
enrollment_number,status,time
2110001,in,09:00:00
2110001,out,17:30:00
```

**Different date formats:**
```csv
enrol_no,action,datetime
2110001,in,15-01-2025 09:00:00
2110001,out,15/01/2025 17:30
```

---

## Supported Timestamp Formats

### Full DateTime Formats
- `2025-01-15 09:00:00` (YYYY-MM-DD HH:MM:SS)
- `2025-01-15 09:00` (YYYY-MM-DD HH:MM)
- `15-01-2025 09:00:00` (DD-MM-YYYY HH:MM:SS)
- `15-01-2025 09:00` (DD-MM-YYYY HH:MM)
- `15/01/2025 09:00:00` (DD/MM/YYYY HH:MM:SS)
- `15/01/2025 09:00` (DD/MM/YYYY HH:MM)
- `2025/01/15 09:00:00` (YYYY/MM/DD HH:MM:SS)
- `2025/01/15 09:00` (YYYY/MM/DD HH:MM)

### Time Only Formats (uses current date)
- `09:00:00` (HH:MM:SS)
- `09:00` (HH:MM)

---

## Edge Cases Handled

### ✅ Duplicate Detection
1. **Within Same CSV**: Prevents duplicate entries in the same upload
2. **In Database**: Checks existing records before inserting
3. **Same Day, Same Status**: Won't allow duplicate in/out for same student on same day

### ✅ Validation
- **Student Exists**: Verifies enrollment number in database
- **Valid Status**: Only accepts `in` or `out`
- **Valid Timestamp**: Validates all supported date/time formats
- **Required Fields**: Ensures all mandatory fields are present
- **Data Types**: Validates enrollment number is numeric

### ✅ Error Handling
- **Invalid Enrollment**: Reports student not found
- **Duplicate Entries**: Reports existing records
- **Invalid Format**: Detailed error messages
- **Missing Fields**: Specific field validation
- **Batch Processing**: Continues processing even if some rows fail

### ✅ Smart Updates
- If student has `in` time but no `out` time → updates with `out` time
- If student has both → rejects as duplicate
- Maintains separate records for different dates

---

## API Request Examples

### Using cURL (with file upload)

```bash
curl -X POST http://vdm.csceducation.net/attendance/webhook/daily-attendance/ \
  -H "X-Webhook-Key: vdm_attendance_webhook_2025" \
  -F "file=@daily_attendance.csv"
```

### Using cURL (with CSV in body)

```bash
curl -X POST http://vdm.csceducation.net/attendance/webhook/daily-attendance/?key=vdm_attendance_webhook_2025 \
  -H "Content-Type: text/csv" \
  --data-binary @daily_attendance.csv
```

### Using Python Requests

```python
import requests

url = "http://vdm.csceducation.net/attendance/webhook/daily-attendance/"
headers = {
    "X-Webhook-Key": "vdm_attendance_webhook_2025"
}

# Option 1: Upload file
with open('daily_attendance.csv', 'rb') as f:
    files = {'file': f}
    response = requests.post(url, headers=headers, files=files)

# Option 2: Send CSV data directly
csv_data = """enrollment_number,status,timestamp
2110001,in,2025-01-15 09:00:00
2110001,out,2025-01-15 17:30:00"""

response = requests.post(url, headers=headers, data=csv_data)

print(response.json())
```

### Using JavaScript/Node.js

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

const form = new FormData();
form.append('file', fs.createReadStream('daily_attendance.csv'));

axios.post('http://vdm.csceducation.net/attendance/webhook/daily-attendance/', form, {
    headers: {
        'X-Webhook-Key': 'vdm_attendance_webhook_2025',
        ...form.getHeaders()
    }
})
.then(response => console.log(response.data))
.catch(error => console.error(error.response.data));
```

---

## Response Format

### Success Response

```json
{
    "success": true,
    "summary": {
        "total_rows": 5,
        "successful": 4,
        "failed": 0,
        "duplicates": 1
    },
    "processed_records": [
        {
            "row": 2,
            "enrollment": 2110001,
            "name": "John Doe",
            "status": "in",
            "time": "09:00:00",
            "date": "2025-01-15",
            "action": "created"
        },
        {
            "row": 3,
            "enrollment": 2110001,
            "name": "John Doe",
            "status": "out",
            "time": "17:30:00",
            "date": "2025-01-15",
            "action": "updated"
        }
    ],
    "total_processed": 4
}
```

### Response with Errors

```json
{
    "success": true,
    "summary": {
        "total_rows": 5,
        "successful": 3,
        "failed": 1,
        "duplicates": 1
    },
    "processed_records": [...],
    "total_processed": 3,
    "errors": [
        {
            "row": 4,
            "error": "Student not found: 9999999",
            "data": {
                "enrollment_number": "9999999",
                "status": "in",
                "timestamp": "2025-01-15 09:00:00"
            }
        },
        {
            "row": 5,
            "error": "Entry already exists in database",
            "data": {
                "enrollment_number": "2110001",
                "status": "in",
                "timestamp": "2025-01-15 09:00:00"
            },
            "existing_record_id": "507f1f77bcf86cd799439011"
        }
    ],
    "total_errors": 2
}
```

### Error Response (Unauthorized)

```json
{
    "success": false,
    "error": "Unauthorized - Invalid webhook key",
    "message": "Provide valid webhook key in X-Webhook-Key header or ?key parameter"
}
```

---

## Check Webhook Status

### Request
```bash
curl -X GET "http://vdm.csceducation.net/attendance/webhook/status/?key=vdm_attendance_webhook_2025"
```

### Response
```json
{
    "success": true,
    "webhook_active": true,
    "statistics": {
        "today": {
            "total_records": 45,
            "in_records": 42,
            "out_records": 38,
            "date": "2025-01-15"
        },
        "all_time": {
            "total_records": 12450
        }
    },
    "webhook_url": "http://vdm.csceducation.net/attendance/webhook/daily-attendance/",
    "documentation": {
        "method": "POST",
        "authentication": "X-Webhook-Key header or ?key parameter",
        "csv_format": "enrollment_number,status,timestamp",
        "example": "2110000,in,2025-01-15 09:00:00"
    }
}
```

---

## MongoDB Collection Structure

Data is stored in `student_collection` with the following structure:

```javascript
{
    "_id": ObjectId("..."),
    "enrol_no": 2110001,
    "student_name": "John Doe",
    "date": "2025-01-15",
    "in_time": "09:00:00",
    "out_time": "17:30:00",
    "status": "out",  // Last status
    "timestamp": "2025-01-15T17:30:00",  // Last update timestamp
    "created_at": "2025-01-15T09:00:00",
    "updated_at": "2025-01-15T17:30:00",  // If updated
    "source": "webhook",
    "processed_by": "system"
}
```

---

## Error Types

| Error | Meaning | Solution |
|-------|---------|----------|
| `Missing enrollment number` | Column not found or empty | Check CSV column names |
| `Missing status (in/out)` | Status column missing | Add status column |
| `Missing timestamp` | Time column missing | Add timestamp column |
| `Invalid enrollment number` | Not a number | Ensure enrollment is numeric |
| `Invalid status` | Not 'in' or 'out' | Use only 'in' or 'out' |
| `Invalid timestamp format` | Unrecognized format | Use supported formats |
| `Student not found` | Enrollment not in database | Verify student exists |
| `Duplicate entry in CSV` | Same record twice in file | Remove duplicates |
| `Entry already exists` | Already in database | Check existing records |
| `In-time already recorded` | Student already has in-time | Can't record twice |
| `Out-time already recorded` | Student already has out-time | Can't record twice |

---

## Best Practices

1. **Always include headers** in your CSV file
2. **Use consistent date format** throughout the file
3. **Test with small batch** before sending large files
4. **Check response** for errors before considering it successful
5. **Store webhook key securely** - don't commit to version control
6. **Monitor duplicate count** - high duplicates may indicate issues
7. **Send in batches** if you have large datasets (e.g., 500-1000 rows per request)

---

## Troubleshooting

### Issue: All rows failing
- **Check**: Webhook key is correct
- **Check**: CSV columns match required names
- **Check**: Students exist in database

### Issue: High duplicate count
- **Reason**: Data already uploaded
- **Solution**: Check database before uploading, or upload only new records

### Issue: Invalid timestamp errors
- **Reason**: Unsupported date format
- **Solution**: Use one of the supported formats listed above

### Issue: 401 Unauthorized
- **Reason**: Missing or invalid webhook key
- **Solution**: Include `X-Webhook-Key` header or `?key=` parameter

---

## Security Notes

1. **Webhook Key**: Change `WEBHOOK_ACCESS_KEY` in `webhook_views.py` for production
2. **HTTPS**: Always use HTTPS in production
3. **IP Whitelist**: Consider adding IP restriction for production
4. **Rate Limiting**: Implement rate limiting for production use
5. **Logging**: All webhook calls are logged for audit

---

## Change Webhook Key

Edit `apps/attendancev2/webhook_views.py`:

```python
# Line 11
WEBHOOK_ACCESS_KEY = "your_new_secret_key_here"
```

---

## Production Deployment

1. Change webhook access key
2. Enable HTTPS
3. Set up IP whitelisting (optional)
4. Enable rate limiting
5. Set up monitoring/alerts
6. Regular backup of MongoDB collection

---

**Support**: For issues or questions, check the logs at `/var/log/django/` or contact the system administrator.
