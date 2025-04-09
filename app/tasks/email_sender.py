import json
import time
from app.celery_app import app
from app.tasks.email_sender_lib.gmail_sender import send_email_via_gmail_api
from app.tasks.email_sender_lib.make_desicion import decide_and_send_email
import os

# @app.task(name="tasks.send_email", autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def send_email_task(job_data_json_list: list, job_post=None):
    for job_data_json in job_data_json_list:
        _, reason = decide_and_send_email(job_data_json, send_email_via_gmail_api, job_post)
        print(reason)

if __name__ == "__main__":
    count = 0
    item_no = 0
    filepath = os.path.join(os.path.dirname(__file__), "final_output_to_be_sent.json")
    with open(filepath, "r") as f:
        data = json.load(f)
        for item in data[item_no:]:
            print(f"Item no:{item_no}")
            item_no += 1
            for model_result in item["result"]:
                print(f"Post link:{item['job_post']['post_link']}")
                ok, reason = decide_and_send_email(model_result, send_email_via_gmail_api, item["job_post"])
                time.sleep(2)
                print(reason)
                if ok:
                    count += 1
                    print(f"Send mail to {count}")
            print("====\n")


# email ["none"], ["null"]
