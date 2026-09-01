# Blue Tigers Equipment Store

## Deploy to Render Free Tier

1. Create a GitHub repository and upload this project folder.
2. Go to Render and create a new Web Service from that repository.
3. Use these settings:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `python app.py`
4. Add these environment variables:
   - `ADMIN_PASSWORD` = your admin password
   - `GOOGLE_SHEETS_WEB_APP_URL` = your Google Apps Script `/exec` URL
   - `GOOGLE_SHEETS_API_TOKEN` = the private token used in your Apps Script
5. Deploy.

The app reads Render's `PORT` automatically.

After these Google Sheets variables are configured, equipment records are stored in your Google Sheet instead of Render's temporary local file. To copy the sample local records to a new empty Sheet one time, temporarily add `MIGRATE_JSON_RECORDS_TO_SHEETS=true`, open the site once, then remove that variable.
