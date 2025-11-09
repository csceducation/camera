# Daily Attendance Webhook Documentation

## Overview
This webhook allows external servers to send student attendance data in CSV format, which will be automatically stored in the MongoDB database.

---

## Webhook Details

### Endpoint
```
POST /attendance/api/attendance/webhook/
```

### Authentication
Include the secret key in the request header:
```
X-Webhook-Secret: vdm_attendance_webhook_2024
```

**⚠️ Keep this secret key secure!** Change it in `apps/attendancev2/webhook.py` if needed.

---

## CSV Format

### Required Columns
- `rollnumber` (or `roll_number`, `enrol_no`) - Student enrollment number
- `in/out` (or `action`, `type`) - Entry or exit action
- `time` (or `timestamp`) - Time in HH:MM format

### Example CSV
```csv
rollnumber,in/out,time
2110000,in,09:30
2110000,out,17:45
2110001,in,09:35
2110001,out,17:30
2110002,in,09:40
```

---

## How to Use

### Method 1: Using curl (Command Line)

```bash
# Send attendance for today
curl -X POST \
  -H "X-Webhook-Secret: vdm_attendance_webhook_2024" \
  -F "file=@attendance.csv" \
  http://vdm.csceducation.net/attendance/api/attendance/webhook/

# Send attendance for a specific date
curl -X POST \
  -H "X-Webhook-Secret: vdm_attendance_webhook_2024" \
  -F "file=@attendance.csv" \
  -F "date=2024-11-08" \
  http://vdm.csceducation.net/attendance/api/attendance/webhook/
```

### Method 2: Using Python

```python
import requests

url = 'http://vdm.csceducation.net/attendance/api/attendance/webhook/'
headers = {
    'X-Webhook-Secret': 'vdm_attendance_webhook_2024'
}

# Upload CSV file
with open('attendance.csv', 'rb') as f:
    files = {'file': f}
    data = {'date': '2024-11-08'}  # Optional, defaults to today
    
    response = requests.post(url, headers=headers, files=files, data=data)
    print(response.json())
```

### Method 3: Using Postman

1. **Method**: POST
2. **URL**: `http://vdm.csceducation.net/attendance/api/attendance/webhook/`
3. **Headers**:
   - Key: `X-Webhook-Secret`
   - Value: `vdm_attendance_webhook_2024`
4. **Body** (form-data):
   - Key: `file` (Type: File) - Select your CSV file
   - Key: `date` (Type: Text) - `2024-11-08` (Optional)

---

## Response Format

### Success Response
```json
{
  "success": true,
  "date": "2024-11-08",
  "processed_rows": 10,
  "saved_students": 5,
  "unique_students": 5,
  "message": "Successfully processed 5 student attendance records"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Invalid webhook secret key"
}
```

### Response with Warnings
```json
{
  "success": true,
  "date": "2024-11-08",
  "processed_rows": 8,
  "saved_students": 4,
  "unique_students": 4,
  "message": "Successfully processed 4 student attendance records",
  "warnings": [
    "Row 3: Missing required fields",
    "Row 7: Invalid action 'enter'. Must be 'in' or 'out'"
  ],
  "total_errors": 2
}
```

---

## Data Storage

The attendance data is stored in MongoDB:
- **Collection**: `student_collection`
- **Structure**:
```javascript
{
  "date": "2024-11-08",
  "attendance": {
    "2110000": {
      "entry_time": "09:30",
      "exit_time": "17:45",
      "status": "present"
    },
    "2110001": {
      "entry_time": "09:35",
      "exit_time": "17:30",
      "status": "present"
    }
  }
}
```

---

## Status Rules

- **present**: Student has an entry time (in)
- **absent**: Student has no entry time

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| 401 - Invalid webhook secret key | Wrong or missing secret in header | Check `X-Webhook-Secret` header |
| 400 - No CSV file provided | Missing file upload | Include `file` parameter |
| 400 - File must be a CSV file | Wrong file type | Upload only .csv files |
| 400 - Invalid date format | Wrong date format | Use YYYY-MM-DD format |
| Row X: Missing required fields | CSV row incomplete | Ensure all columns present |
| Row X: Invalid action | Wrong in/out value | Use only 'in' or 'out' |

---

## Testing

### Test Endpoint (GET request)
```
GET /attendance/api/attendance/webhook/info/
```

This returns information about the webhook without authentication.

### Sample Test File
Use the provided `sample_attendance.csv` file for testing:
```csv
rollnumber,in/out,time
2110000,in,09:30
2110000,out,17:45
2110001,in,09:35
2110001,out,17:30
```

---

## Security

### Change the Secret Key

Edit `apps/attendancev2/webhook.py`:
```python
# Line 11
WEBHOOK_SECRET_KEY = "your_new_secret_key_here"
```

### Best Practices
1. ✅ Use HTTPS in production
2. ✅ Rotate secret keys periodically
3. ✅ Monitor webhook logs
4. ✅ Validate sender IP (optional)
5. ✅ Keep secret key confidential

---

## Integration Examples

### Automated Daily Upload
```python
# daily_attendance_upload.py
import requests
from datetime import datetime
import os

def upload_attendance(csv_file_path):
    url = 'http://vdm.csceducation.net/attendance/api/attendance/webhook/'
    headers = {'X-Webhook-Secret': 'vdm_attendance_webhook_2024'}
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    with open(csv_file_path, 'rb') as f:
        files = {'file': f}
        data = {'date': today}
        
        response = requests.post(url, headers=headers, files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success: {result['message']}")
            print(f"   Processed: {result['processed_rows']} rows")
            print(f"   Saved: {result['saved_students']} students")
        else:
            print(f"❌ Error: {response.json()['error']}")

# Run daily
if __name__ == '__main__':
    upload_attendance('attendance.csv')
```

### Schedule with cron (Linux)
```bash
# Run every day at 8 PM
0 20 * * * /usr/bin/python3 /path/to/daily_attendance_upload.py
```

---

## Support

For issues or questions:
- Check webhook info: `GET /attendance/api/attendance/webhook/info/`
- Review CSV format carefully
- Verify secret key in header
- Check date format (YYYY-MM-DD)

---

## Changelog

**v1.0 - November 2024**
- Initial webhook implementation
- CSV file upload support
- MongoDB integration
- Entry/Exit time tracking
- Automatic status detection
