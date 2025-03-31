from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import json
import os

from dotenv import load_dotenv
load_dotenv()


# Initialize Groq model
llm = ChatGroq(
	model="deepseek-r1-distill-llama-70b",
	temperature=0.4,
	max_tokens=None,
	timeout=None,
	max_retries=2
)

current_dir = os.path.dirname(__file__)

response_template_path = os.path.join(current_dir, os.getenv("ANALYZE_RESUME_PROMPT_PATH"))
data_path = os.path.join(current_dir, os.getenv("JSON_STRUCT_PATH"))
messege_content_path = os.path.join(current_dir, os.getenv("MESSAGE_CONTENT_PATH"))
resume_path = os.path.join(current_dir, os.getenv("RESUME_PATH"))

response_template = ""
with open(response_template_path, "r") as file:
	response_template = file.read()

with open(data_path, "r") as file:
	data = json.load(file)

response_template += json.dumps(data)

# parsing prompt
prompt = ChatPromptTemplate.from_template(
	"""RESUME ANALYSIS TASK
{response_template}

RESUME CONTENT:
{resume}

JOB POSTINGS:
{jobs}

MESSEGE_CONTENT:
{messege_content}

STRICT JSON OUTPUT:"""
)

parser = JsonOutputParser()
chain = prompt | llm | parser

with open(messege_content_path, "r") as file:
	messege_content = file.read()

with open(resume_path, "r") as f:
	resume_text = f.read()

def analyze_job_match(jobs_text, resume_text=resume_text, messege_content=messege_content):
	try:
		result = chain.invoke({
			"response_template": response_template,
			"resume": resume_text,
			"jobs": jobs_text,
			"messege_content": messege_content
		})
		
		# Validate and clean output
		if isinstance(result, dict):
			result = [result]
		return result
	
	except Exception as e:
		print(f"Analysis error: {e}")
		return []

if __name__ == "__main__":


	job_post_path = os.path.join(current_dir, os.getenv("JOB_POSTS_PATH"))
	with open(job_post_path, "r") as f:
		linkedin_job_post = f.read()

	with open(messege_content_path, "r") as file:
		messege_content = file.read()

	output = analyze_job_match(linkedin_job_post, resume_text, messege_content)
	print(json.dumps(output, indent=2))

	# 	sample_jobs = """Hiring Multiple Roles:
		
	# Role: Senior Cloud Engineer
	# Requirements:
	# - 5+ years cloud experience
	# - AWS/GCP certifications
	# - Terraform expertise
	# - Contact: careers@techcorp.com
	# Apply: techcorp.com/cloud-form

	# Position: Data Analyst
	# Needs:
	# - Advanced SQL skills
	# - 2+ years Python
	# - Tableau experience
	# - Submit: forms.analytics-hub.com/data-app"""
