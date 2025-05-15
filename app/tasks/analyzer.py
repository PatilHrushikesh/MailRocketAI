import os
from app.celery_app import app
from app.tasks.db_utils import insert_post_analysis, read_linkedin_posts
from app.tasks.email_sender import send_email_task
from app.tasks.resume_analyser.resume_job_match_analysis import analyze_job_match


linkedin_db_path = os.path.join(
	os.path.dirname(os.path.abspath(__file__)),
	"linkedin_posts.db"
)
print(linkedin_db_path)

@app.task(name="tasks.analyze_job_match", max_retries=3)
def  analyze_job_match_task(job_post, uid):
	# Implement actual analysis logic here
	
	analysis_result, current_model = analyze_job_match(job_post)
	insert_post_analysis(uid, analysis_result, current_model["name"])
	return analysis_result
	# send_email_task.delay(analysis_result)

if __name__ == "__main__":

	not_analyzed_posts = read_linkedin_posts(linkedin_db_path, {"analysed": 0})
	for post in not_analyzed_posts:
		output = analyze_job_match_task(post, post["uid"])
		print(output)