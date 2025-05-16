import json
import sqlite3
import time
from app.celery_app import app
from app.tasks.email_sender_lib.gmail_sender import send_email_via_gmail_api
from app.tasks.email_sender_lib.make_desicion import decide_and_send_email
import os

# @app.task(name="tasks.send_email", autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})

linkedin_db_path = os.path.join(
	os.path.dirname(os.path.abspath(__file__)),
	"linkedin_posts.db"
)
print(linkedin_db_path)

def send_email_task(job_data_json_list: list, job_post=None):
    for job_data_json in job_data_json_list:
        _, reason, final_decision = decide_and_send_email(
            job_data_json, send_email_via_gmail_api, job_post)
        print(reason)


def send_email_task_from_db(db_path=linkedin_db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            pa.*, 
            lp.post_link 
        FROM post_analysis pa
        JOIN linkedin_posts lp ON pa.post_uid = lp.uid
        WHERE pa.mail_sent = -1
    """)

    rows = cursor.fetchall()
    if not rows:
        print("No pending emails to send.")
        return

    for row in rows[:]:
        try:
            # Load full analysis JSON
            job_data_json = json.loads(row["full_analysis_json"])

            # Override fields from SQL where applicable
            job_data_json["model_name"] = row["model_used"] if row["model_used"] is not None else "N/A"
            job_data_json["contact_email"] = row["contact_email"] if row["contact_email"] else []
            job_data_json["contact_email"] = json.loads(job_data_json["contact_email"])


            job_data_json["message_content"] = {
                "subject": row["subject"] if row["subject"] else "No Subject",
                "body": row["body"] if row["body"] else "No Body"
            }

            job_post = {"post_link": row["post_link"]}

            _, reason, final_decision = decide_and_send_email(
                job_data_json, send_email_via_gmail_api, job_post
            )
            print(f"[{row['analysis_id']}] {reason}")


            # convert final_decision to int
            final_decision = 1 if final_decision else 0
            # set mail_sent value to final_decision
            cursor.execute("""
                UPDATE post_analysis
                SET mail_sent = ?
                WHERE analysis_id = ?
            """, (final_decision, row["analysis_id"]))

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error processing row {row['analysis_id']}: {e}")

    conn.commit()  # Enable if you're marking emails as sent
    conn.close()


if __name__ == "__main__":
    # count = 0
    # item_no = 0
    # filepath = os.path.join(os.path.dirname(__file__),
    #                         "final_output_to_be_sent2_not_sent.json")
    # with open(filepath, "r") as f:
    #     data = json.load(f)
    #     for item in data[item_no:]:
    #         print(f"Item no:{item_no}")
    #         item_no += 1
    #         for model_result in item["result"]:
    #             print(f"Post link:{item['job_post']['post_link']}")
    #             ok, reason = decide_and_send_email(
    #                 model_result, send_email_via_gmail_api, item["job_post"])
    #             time.sleep(2)
    #             print(reason)
    #             if ok:
    #                 count += 1
    #                 print(f"Send mail to {count}")
    #         print("====\n")

    send_email_task_from_db(linkedin_db_path)
# email ["none"], ["null"]
