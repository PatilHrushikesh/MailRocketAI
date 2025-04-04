import itertools
import json
import logging
import os
import time
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.tasks.resume_analyser.models import models_list, get_llm

from app.tasks.resume_analyser.utils import load_file_content, load_json_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("resume_analysis.log")],
)

logger = logging.getLogger("resume_analyzer")

# Load environment variables
load_dotenv()
current_dir = os.path.dirname(__file__)

# Global paths
RESPONSE_TEMPLATE_PATH = os.path.join(
    current_dir, os.getenv("ANALYZE_RESUME_PROMPT_PATH")
)
JSON_STRUCT_PATH = os.path.join(current_dir, os.getenv("JSON_STRUCT_PATH"))
MESSAGE_CONTENT_PATH = os.path.join(current_dir, os.getenv("MESSAGE_CONTENT_PATH"))
RESUME_PATH = os.path.join(current_dir, os.getenv("RESUME_PATH"))
TAILORING_INSTRUCTIONS_PATH = os.path.join(
    current_dir, os.getenv("EMAIL_TAILORING_PROMPT_PATH")
)

# Load necessary data
RESUME_TEXT = load_file_content(RESUME_PATH)
MESSAGE_CONTENT = load_file_content(MESSAGE_CONTENT_PATH)
TAILORING_INSTRUCTIONS = load_file_content(TAILORING_INSTRUCTIONS_PATH)

# Get prompt template

# Set up model cycle
model_cycle = itertools.cycle(models_list)


def initialize_prompt():
    """Initialize and return the prompt template and necessary data."""
    logger.info("Initializing prompt template")

    # Load all necessary files
    response_template = load_file_content(RESPONSE_TEMPLATE_PATH)
    json_structure = load_json_file(JSON_STRUCT_PATH)
    full_template = response_template + json.dumps(json_structure)

    # Create the prompt template
    prompt = ChatPromptTemplate.from_template(
        """RESUME ANALYSIS TASK
{response_template}

RESUME CONTENT:
{resume}

JOB POSTINGS:
{jobs}

MESSEGE_CONTENT_TAILORING_INSTRUCTIONS:
{messege_content_tailoring_instructions}

MESSEGE_CONTENT:
{messege_content}

RESUME_URL:
{resume_url}

LINKEDIN_PROFILE_URL:
{linkedin_profile_url}

STRICT JSON OUTPUT:"""
    )

    return prompt, full_template

PROMPT, FULL_TEMPLATE = initialize_prompt()

def invoke_model(prompt, parameter_dict):
    """Invoke the LLM with the given prompt and parameters."""
    global model_cycle

    logger.info("Invoking model")

    # Validate prompt parameters
    missing_keys = [key for key in prompt.input_variables if key not in parameter_dict]
    if missing_keys:
        error_msg = f"Missing required keys in parameter_dict: {missing_keys}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        # Get the next model in the cycle
        current_model = next(model_cycle)
        logger.info(f"Using {current_model['provider']} model: {current_model['name']}")

        # Set up the processing chain
        llm = get_llm(current_model)
        parser = JsonOutputParser()
        chain = prompt | llm | parser

        # Invoke the model
        result = chain.invoke(parameter_dict)
        logger.debug("Model response received")

        # Add model name to the result
        if isinstance(result, list):
            for item in result:
                item["model_name"] = current_model["name"]
        else:
            result["model_name"] = current_model["name"]

        return [result] if isinstance(result, dict) else result, current_model

    except Exception as e:
        error_msg = f"Error invoking model: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def analyze_job_match(jobs_text):
    """Analyze how well a resume matches job postings."""
    logger.info("Starting job match analysis with provided job posting")

    # Prepare input dictionary
    input_dict = {
        "response_template": FULL_TEMPLATE,
        "resume": RESUME_TEXT,
        "jobs": jobs_text,
        "messege_content": MESSAGE_CONTENT,
        "messege_content_tailoring_instructions": TAILORING_INSTRUCTIONS,
        "resume_url": os.getenv("RESUME_URL", ""),
        "linkedin_profile_url": os.getenv("LINKEDIN_PROFILE_URL", ""),
    }

    try:
        # Invoke the model
        result, current_model = invoke_model(PROMPT, input_dict)

        logger.info(
            f"Analysis complete using {current_model['provider']} model {current_model['name']}"
        )
        logger.info(f"Result: {json.dumps(result, indent=2)}")
        return result

    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        return []


def save_output_to_file(output_data, filename="output_final.json"):
    """Save the output data to a JSON file."""
    logger.info(f"Saving output to {filename}")
    try:
        with open(filename, "w") as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Output successfully saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving output to {filename}: {str(e)}")
        raise


def main():
    """Main function to orchestrate the resume analysis process."""
    logger.info("Starting resume analysis process")

    # Load job posts
    job_posts_path = os.path.join(current_dir, os.getenv("JOB_POSTS_PATH"))
    job_posts = load_file_content(job_posts_path)

    # Run analysis with each model
    output_results = {}
    for i in range(len(models_list[:])):
        current_model = models_list[i % len(models_list)]
        logger.info(f"Running analysis with model {i+1} of {len(models_list[:2])}")

        # Call analyze_job_match with just the job_posts
        output = analyze_job_match(job_posts)

        key = f"{current_model['provider']}_{current_model['name']}"
        output_results[key] = output

    # Save results to file
    save_output_to_file(output_results)

    # Print results
    print(json.dumps(output_results, indent=2))
    logger.info("Resume analysis process completed successfully")


if __name__ == "__main__":
    main()
