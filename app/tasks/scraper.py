from app.celery_app import app
from app.tasks.analyzer import analyze_job_match_task
from app.tasks.linkedin_post_scrapper.linkedin_post_scrapper import scrape_linkedin_feed

import os
from dotenv import load_dotenv

load_dotenv()

@app.task(name="tasks.scrape_linkedin_feed")
def scrape_linkedin_feed_task():
	"""Scrape LinkedIn feed for job postings matching search queries."""

	current_dir = os.path.dirname(__file__)
	queries_file_path = os.path.join(current_dir, os.getenv("QUERIES_FILE_PATH"))

	username = os.getenv("LINKEDIN_USERNAME")
	password = os.getenv("LINKEDIN_PASSWORD")

	for job_post in scrape_linkedin_feed(
		username=username, password=password, queries_file=queries_file_path
	):
		analyze_job_match_task.delay(job_post)
