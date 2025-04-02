import time
import traceback
from app.tasks.analyzer import analyze_job_match_task
from app.tasks.email_sender import send_email_task
from app.tasks.linkedin_post_scrapper.linkedin_post_scrapper import scrape_linkedin_feed
import os
from dotenv import load_dotenv

load_dotenv()

# @app.task(name="tasks.scrape_linkedin_feed")
def scrape_linkedin_feed_task():
	"""Scrape LinkedIn feed for job postings matching search queries."""

	current_dir = os.path.dirname(__file__)
	queries_file_path = os.path.join(current_dir, os.getenv("QUERIES_FILE_PATH"))

	username = os.getenv("LINKEDIN_USERNAME")
	password = os.getenv("LINKEDIN_PASSWORD")

	for job_post in scrape_linkedin_feed(
		username=username, password=password, queries_file=queries_file_path
	):
		if isinstance(job_post, dict):
			for key in job_post:
				if isinstance(job_post[key], str):
					job_post[key] = job_post[key].encode('utf-8', errors='replace').decode('utf-8')
		# print(f"Job post: {job_post}")
		try:
			result = analyze_job_match_task(job_post)
			send_email_task(result, job_post)
		except Exception as e:
			print(f"Error processing job post: {job_post}")
			print(f"Error: {e}")
			print(f"Traceback:\n{traceback.format_exc()}")
		time.sleep(10)


	return "Scraping and processing completed."

if __name__ == "__main__":
	scrape_linkedin_feed_task()