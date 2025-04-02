from app.celery_app import app
from app.tasks.email_sender_lib.gmail_sender import send_email_via_gmail_api
from app.tasks.email_sender_lib.make_desicion import decide_and_send_email


# @app.task(name="tasks.send_email", autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def send_email_task(job_data_json_list: list, job_post=None):
    for job_data_json in job_data_json_list:
        _, reason = decide_and_send_email(job_data_json, send_email_via_gmail_api, job_post)
        print(reason)