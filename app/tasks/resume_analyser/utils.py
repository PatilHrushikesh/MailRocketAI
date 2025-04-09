import json
import logging
import os
from datetime import datetime

# Configure the logging settings
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # Logs will be sent to the standard output
)

# Create a logger instance for this module
logger = logging.getLogger(__name__)


# Get the base directory (project root)
BASE_DIR = "D:\\Projects\\linkedin_mail_sender"

def convert_datetime(obj):
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")  # Or use obj.isoformat()
    return obj


def append_dict_to_json_array(data: dict, filename: str) -> None:
    """
    Appends a dictionary to a JSON file as part of a JSON array.
    If the file doesn't exist or is empty, creates a new JSON array with the data.
    Operates efficiently by avoiding reading the entire file.

    Parameters:
    - data (dict): The dictionary data to append
    - filename (str): Full path to the JSON file
    """
    data_json = json.dumps(data, indent=2, default=convert_datetime)

    try:
        if not os.path.exists(filename):
            logger.info(f"File {filename} does not exist. Creating a new JSON array.")
            with open(filename, "w") as f:
                f.write("[\n")
                f.write(data_json)
                f.write("\n]")
        else:
            logger.info(f"Appending data to existing file {filename}.")
            with open(filename, "rb+") as f:
                f.seek(0, os.SEEK_END)
                if f.tell() == 0:
                    logger.warning(f"File {filename} is empty. Writing new JSON array.")
                    f.write(b"[\n")
                    f.write(data_json.encode("utf-8"))
                    f.write(b"\n]")
                else:
                    f.seek(-1, os.SEEK_END)
                    last_char = f.read(1)
                    f.seek(-1, os.SEEK_END)
                    f.truncate()  # Remove the last character ']'
                    f.write(b",\n")
                    f.write(data_json.encode("utf-8"))
                    f.write(b"\n]")
    except Exception as e:
        logger.error(f"Failed to append data to {filename}: {e}")
        raise


def save_model_result_to_json(
    result: dict, model_name: str, filename: str = None
) -> None:
    """
    Saves a model result dictionary to a model-specific JSON file.
    Handles the file path generation and delegates the actual file operations.

    Parameters:
    - result (dict): The model result to save
    - model_name (str): Name of the model (used for default filename)
    - filename (str, optional): Custom filename override
    """
    if not filename:
        filename = os.path.join(BASE_DIR, "final_output_by_model", f"{model_name}.json")


def should_send_email(job_data):
    if not isinstance(job_data, dict):
        logger.error("job_data must be a dictionary")
        raise TypeError("job_data must be a dictionary")

    # Debug log job_data for inspection
    logger.debug("Job data: %s", json.dumps(job_data, indent=4))

    # Check match percentage
    try:
        match_percent = float(job_data.get("match_percentage", 0))
    except (ValueError, TypeError) as e:
        logger.error("Invalid match_percentage: %s", e)
        raise TypeError("match_percentage must be convertible to a number")
    if match_percent <= 68:
        logger.info("Match percentage too low: %s%%, not sending email", match_percent)
        return False, f"Match percentage {match_percent}% is not greater than 68%."

    # Check experience gap
    try:
        exp_gap = float(job_data.get("experience_gap", 0))
    except (ValueError, TypeError) as e:
        logger.error("Invalid experience_gap: %s", e)
        raise TypeError("experience_gap must be convertible to a number")
    if exp_gap >= 1:
        logger.info("Experience gap too large: %s years, not sending email", exp_gap)
        return (
            False,
            f"Experience gap of {exp_gap} years is more than or equal to 1 year.",
        )

    # Check employment type
    additional_data = job_data.get("additional_data", {})
    if not isinstance(additional_data, dict):
        logger.error("additional_data must be a dictionary")
        raise TypeError("additional_data must be a dictionary")

    employment_type = str(additional_data.get("employment_type", "")).lower()
    if employment_type == "internship":
        logger.info("Employment type is internship, not sending email")
        return False, "Employment type is internship."

    # Check contact email exists
    contact_emails = job_data.get("contact_email", [])
    if not contact_emails:
        logger.warning("No contact email provided, not sending email")
        return False, "No contact email provided."

    # All conditions met
    logger.info("All conditions met, email should be sent")
    return True, "All conditions met."


def load_file_content(file_path):
    """Load content from a file."""
    logger.debug("Loading content from %s", file_path)
    try:
        with open(file_path, "r") as file:
            content = file.read()
        return content
    except FileNotFoundError:
        logger.error("File not found: %s", file_path)
        raise
    except Exception as e:
        logger.error("Error loading file %s: %s", file_path, str(e))
        raise


def load_json_file(file_path):
    """Load JSON content from a file."""
    logger.debug("Loading JSON from %s", file_path)
    try:
        with open(file_path, "r") as file:
            content = json.load(file)
        return content
    except json.JSONDecodeError:
        logger.error("Invalid JSON in file: %s", file_path)
        raise
    except Exception as e:
        logger.error("Error loading JSON file %s: %s", file_path, str(e))
        raise
