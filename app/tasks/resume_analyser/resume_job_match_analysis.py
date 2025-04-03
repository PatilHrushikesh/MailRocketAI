import itertools
import time
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import json
import os
from dotenv import load_dotenv
from models import models_list, get_llm

load_dotenv()

current_dir = os.path.dirname(__file__)

# Path configurations
response_template_path = os.path.join(
    current_dir, os.getenv("ANALYZE_RESUME_PROMPT_PATH"))
output_json_struct = os.path.join(current_dir, os.getenv("JSON_STRUCT_PATH"))
messege_content_path = os.path.join(
    current_dir, os.getenv("MESSAGE_CONTENT_PATH"))
resume_path = os.path.join(current_dir, os.getenv("RESUME_PATH"))

# Load templates and content
response_template = ""

# analyse_resume_post_prompt.txt
with open(response_template_path, "r") as file:
    response_template = file.read()

with open(output_json_struct, "r") as file:
    data = json.load(file)

response_template += json.dumps(data)

# Create prompt template
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

# Load content files
with open(messege_content_path, "r") as file:
    messege_content = file.read()

with open(resume_path, "r") as f:
    resume_text = f.read()

model_cycle = itertools.cycle(models_list)
parser = JsonOutputParser()

def analyze_job_match(jobs_text, resume_text=resume_text, messege_content=messege_content):
    try:
        current_model = next(model_cycle)
        print(f"Using {current_model['provider']} model: {current_model['name']}")

        llm = get_llm(current_model)
        chain = prompt | llm | parser

        result = chain.invoke({
            "response_template": response_template,
            "resume": resume_text,
            "jobs": jobs_text,
            "messege_content": messege_content
        })
        
        if isinstance(result, list):
            for item in result:
                item["model_name"] = current_model["name"]
        else:
            result["model_name"] = current_model["name"]

        return [result] if isinstance(result, dict) else result

    except Exception as e:
        print(f"Analysis error using {current_model['provider']} model {current_model['name']}: {e}")
        return []

if __name__ == "__main__":
    job_post_path = os.path.join(current_dir, os.getenv("JOB_POSTS_PATH"))
    with open(job_post_path, "r") as f:
        linkedin_job_post = f.read()

    op_text = {}
    for _ in range(len(models_list)):
        output = analyze_job_match(linkedin_job_post)
        current_model = models_list[_ % len(models_list)]
        key = f"{current_model['provider']}_{current_model['name']}"
        op_text[key] = output

    with open("output_final.json", "w") as f:
        json.dump(op_text, f, indent=2)
    print(json.dumps(op_text, indent=2))