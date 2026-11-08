"""Recurring jobs, run by ``uv run rq cron app/workers/cron.py`` next to the workers.

The hourly alerts job decides by itself when to send (morning digest, once a day) and
remembers what it sent, so several schedulers or a missed hour do no harm. The notice
import runs every 2 hours, at :20 so that the next alerts run (at :05) sees its matches;
a lock per source keeps two passes from overlapping (services/tender_import.py).
"""

from rq import cron

from app.workers.jobs import daily_alerts_job, import_tenders_job

cron.register(daily_alerts_job, queue_name="default", cron="5 * * * *", job_timeout=1800)
cron.register(import_tenders_job, queue_name="default", cron="20 */2 * * *", job_timeout=3600)
