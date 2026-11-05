"""Recurring jobs, run by ``uv run rq cron app/workers/cron.py`` next to the workers.

The hourly alerts job decides by itself when to send (morning digest, once a day) and
remembers what it sent, so several schedulers or a missed hour do no harm.
"""

from rq import cron

from app.workers.jobs import daily_alerts_job

cron.register(daily_alerts_job, queue_name="default", cron="5 * * * *", job_timeout=1800)
