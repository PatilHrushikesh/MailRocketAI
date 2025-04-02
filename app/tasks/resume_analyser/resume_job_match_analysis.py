import itertools
import time
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import json
import os

from dotenv import load_dotenv
load_dotenv()

current_dir = os.path.dirname(__file__)

# Path configurations (keep the same)
response_template_path = os.path.join(
    current_dir, os.getenv("ANALYZE_RESUME_PROMPT_PATH"))
data_path = os.path.join(current_dir, os.getenv("JSON_STRUCT_PATH"))
messege_content_path = os.path.join(
    current_dir, os.getenv("MESSAGE_CONTENT_PATH"))
resume_path = os.path.join(current_dir, os.getenv("RESUME_PATH"))

# Load templates and content (keep the same)
response_template = ""
with open(response_template_path, "r") as file:
    response_template = file.read()

with open(data_path, "r") as file:
    data = json.load(file)

response_template += json.dumps(data)

# Create prompt template (keep the same)
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

# Load content files (keep the same)
with open(messege_content_path, "r") as file:
    messege_content = file.read()

with open(resume_path, "r") as f:
    resume_text = f.read()
grok_based_models = ["deepseek-r1-distill-llama-70b", "deepseek-r1-distill-qwen-32b", "gemma2-9b-it", "llama-3.1-8b-instant",
               "llama-3.3-70b-specdec", "llama-3.3-70b-versatile", "llama3-8b-8192", "llama3-70b-8192", "mistral-saba-24b", "qwen-2.5-32b", "qwen-2.5-coder-32b", "qwen-qwq-32b"]
# Define models with their providers
models_list = [
    {"provider": "google", "name": "gemini-2.0-flash"},
    {"provider": "google", "name": "gemini-2.5-pro-exp-03-25"},
    {"provider": "groq", "name": "llama3-70b-8192"},
    {"provider": "groq", "name": "mistral-saba-24b"},
	{"provider": "groq", "name": "llama3-8b-8192"},
    {"provider": "groq", "name": "deepseek-r1-distill-llama-70b"},
    # {"provider": "groq", "name": "deepseek-r1-distill-qwen-32b"},
    {"provider": "groq", "name": "gemma2-9b-it"},
    {"provider": "groq", "name": "llama-3.1-8b-instant"},
    {"provider": "groq", "name": "llama-3.3-70b-specdec"},
    {"provider": "groq", "name": "llama-3.3-70b-versatile"},
    # {"provider": "groq", "name": "qwen-2.5-32b"},
    # {"provider": "groq", "name": "qwen-2.5-coder-32b"},
    # {"provider": "groq", "name": "qwen-qwq-32b"},
	
]

model_cycle = itertools.cycle(models_list)
parser = JsonOutputParser()


def create_chain(model_info):
    """Create processing chain based on model provider"""
    if model_info["provider"] == "groq":
        llm = ChatGroq(
            model=model_info["name"],
            temperature=0.4,
            max_tokens=None,
            timeout=None,
            max_retries=2
        )
    elif model_info["provider"] == "google":
        llm = ChatGoogleGenerativeAI(
            model=model_info["name"],
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.7
        )
    else:
        raise ValueError(f"Unsupported provider: {model_info['provider']}")

    return prompt | llm | parser


def analyze_job_match(jobs_text, resume_text=resume_text, messege_content=messege_content):
    try:
        # Get next model in rotation
        current_model = next(model_cycle)
        print(
            f"Using {current_model['provider']} model: {current_model['name']}")

        # Create processing chain
        chain = create_chain(current_model)

        # Invoke the chain
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

        # Validate and return output
        return [result] if isinstance(result, dict) else result

    except Exception as e:
        print(
            f"Analysis error using {current_model['provider']} model {current_model['name']}: {e}")
        return []


if __name__ == "__main__":
    job_post_path = os.path.join(current_dir, os.getenv("JOB_POSTS_PATH"))
    with open(job_post_path, "r") as f:
        linkedin_job_post = f.read()

    op_text = {}
    for _ in range(len(models_list)):  # Test all models once
        output = analyze_job_match(linkedin_job_post)
        current_model = models_list[_ % len(models_list)]
        key = f"{current_model['provider']}_{current_model['name']}"
        op_text[key] = output

    with open("output_final.json", "w") as f:
        json.dump(op_text, f, indent=2)
    print(json.dumps(op_text, indent=2))
