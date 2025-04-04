import json
import logging

# Configure the logging settings
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # Logs will be sent to the standard output
)

# Create a logger instance for this module
logger = logging.getLogger(__name__)


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
