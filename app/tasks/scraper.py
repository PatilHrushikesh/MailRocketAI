import sqlite3
import time
import traceback
from app.tasks.analyzer import analyze_job_match_task
from app.tasks.db_utils import insert_linkedin_post
from app.tasks.email_sender import send_email_task
from app.tasks.linkedin_post_scrapper.linkedin_post_scrapper import scrape_linkedin_feed
import os
from dotenv import load_dotenv

from app.tasks.resume_analyser.utils import append_dict_to_json_array

load_dotenv()

# @app.task(name="tasks.scrape_linkedin_feed")


def insert_linkedin_post_wrapper(post_data) -> int | None:
    try:
        # print(f"Inserting post2: {post_data}")
        uid = insert_linkedin_post(post_data)
        return uid
    except sqlite3.IntegrityError as e:
        print(
            f"Duplicate post link: {post_data['post_link']} Error: {str(e)}"
        )
        return None
    

def scrape_linkedin_feed_task():
    """Scrape LinkedIn feed for job postings matching search queries."""

    current_dir = os.path.dirname(__file__)
    queries_file_path = os.path.join(current_dir, os.getenv("QUERIES_FILE_PATH"))

    username = os.getenv("LINKEDIN_USERNAME")
    password = os.getenv("LINKEDIN_PASSWORD")

    for job_post in scrape_linkedin_feed(
		username=username, password=password, queries_file=queries_file_path
	):
        # if isinstance(job_post, dict):
        # 	for key in job_post:
        # 		if isinstance(job_post[key], str):
        # 			job_post[key] = job_post[key].encode('utf-8', errors='replace').decode('utf-8')
        # print(f"Job post: {job_post}")
        try:
            uid = insert_linkedin_post_wrapper(job_post)
            if uid is None:
                continue
            result = analyze_job_match_task(job_post, uid)
            # time.sleep(2)
            # post_result = {
            #     "job_post": job_post,
            #     "result": result
			# }
            # append_dict_to_json_array(post_result, os.path.join(current_dir, "final_output_to_be_sent.json"))

            # send_email_task(result, job_post)
        except Exception as e:
            print(f"Error processing job post: {job_post}")
            print(f"Error: {e}")
            print(f"Traceback:\n{traceback.format_exc()}")
        time.sleep(10)

    return "Scraping and processing completed."

if __name__ == "__main__":
	scrape_linkedin_feed_task()
