"""Recurring jobs, run by ``uv run rq cron app/workers/cron.py`` next to the workers.

The hourly alerts job decides by itself when to send (morning digest, once a day) and
remembers what it sent, so several schedulers or a missed hour do no harm. The notice
import runs every 2 hours, at :20 so that the next alerts run (at :05) sees its matches;
a lock per source keeps two passes from overlapping (services/tender_import.py). Every 15
minutes, the works left for dead are closed and their credits given back
(services/stale_works.py); closing twice does nothing. Every morning, the DCE retrieved by the
robot are checked for changes (services/dce_retrieval.py, spec « Récupération des DCE »).
Every 2 minutes, the DCE mailbox is read (services/inbound_mail.py, ADR-055): an advisory lock
keeps two passes apart; every night, « À classer » left too long is removed.
"""

from rq import cron

from app.workers.jobs import (
    daily_alerts_job,
    import_tenders_job,
    poll_dce_mail_job,
    purge_dce_mail_job,
    sweep_stale_works_job,
    watch_dces_job,
)

cron.register(daily_alerts_job, queue_name="default", cron="5 * * * *", job_timeout=1800)
cron.register(import_tenders_job, queue_name="default", cron="20 */2 * * *", job_timeout=3600)
cron.register(sweep_stale_works_job, queue_name="default", cron="*/15 * * * *", job_timeout=600)
# 06:40 in Paris in winter (cron runs in UTC): the DCE retrieved by the robot, before the day
cron.register(watch_dces_job, queue_name="default", cron="40 5 * * *", job_timeout=3600)
# The DCE mailbox (ADR-055): nothing is done while it is switched off in the administration
cron.register(poll_dce_mail_job, queue_name="default", cron="*/2 * * * *", job_timeout=900)
cron.register(purge_dce_mail_job, queue_name="default", cron="17 2 * * *", job_timeout=900)
