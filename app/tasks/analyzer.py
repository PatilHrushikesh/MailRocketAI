from app.celery_app import app
from app.tasks.email_sender import send_email_task
from app.tasks.resume_analyser.resume_job_match_analysis import analyze_job_match

@app.task(name="tasks.analyze_job_match", max_retries=3)
def analyze_job_match_task(job_post):
	# Implement actual analysis logic here
	analysis_result = analyze_job_match(job_post)
	return analysis_result
	# send_email_task.delay(analysis_result)