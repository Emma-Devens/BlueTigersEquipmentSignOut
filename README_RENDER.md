# Blue Tigers Equipment Store

## Deploy to Render Free Tier

1. Create a GitHub repository and upload this project folder.
2. Go to Render and create a new Web Service from that repository.
3. Use these settings:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `python app.py`
4. Add an environment variable:
   - `ADMIN_PASSWORD` = your admin password
5. Deploy.

The app reads Render's `PORT` automatically.

Note: Render free services can sleep when unused. Also, the free tier does not give this app a durable database, so `data/equipment_log.json` is fine for a prototype but not ideal for long-term official records.
