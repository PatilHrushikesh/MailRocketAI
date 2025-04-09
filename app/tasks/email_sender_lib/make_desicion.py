import datetime
import json
import os
from dotenv import load_dotenv
import re

load_dotenv()


email_regex = r"""(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)])"""
def is_valid_email(email):
	return re.fullmatch(email_regex, email, re.IGNORECASE) is not None


def should_send_email(job_data):
    if not isinstance(job_data, dict):
        raise TypeError("job_data must be a dictionary")

    email_list = job_data.get("contact_email", [])
    if not email_list:
        return False, f"Mail is None"
    
    new_mail_list = []
    for email in email_list:
        email = str(email)
        if is_valid_email(email):
            new_mail_list.append(email)
    if not new_mail_list:
        return False, f"Emails from list {email_list} are not valid"

    # Check if user manually opted out
    # if not job_data.get('should_apply', False):
    #     return False, "Should apply is set to False."
    # print(f"JOb data:{json.dumps(job_data, indent=4)}")

    # Check match percentage
    try:
        match_percent = float(job_data.get('match_percentage', 0))
    except (ValueError, TypeError):
        raise TypeError("match_percentage must be convertible to a number")
    if match_percent <= 68:
        return False, f"Match percentage {match_percent}% is not greater than 68%."

    # Check experience gap
    try:
        exp_gap = float(job_data.get('experience_gap', 0))
    except (ValueError, TypeError):
        raise TypeError("experience_gap must be convertible to a number")
    if exp_gap >= 1:
        return False, f"Experience gap of {exp_gap} years is more than or equal to 1 year."

    # Check employment type
    additional_data = job_data.get('additional_data', {})
    if not isinstance(additional_data, dict):
        raise TypeError("additional_data must be a dictionary")

    employment_type = str(additional_data.get('employment_type', '')).lower()
    if employment_type == 'internship':
        return False, "Employment type is internship."

    # Check application deadline (if present)
    # deadline_str = additional_data.get('application_deadline')
    # if deadline_str:
    #     try:
    #         deadline_date = datetime.datetime.strptime(deadline_str, "%Y-%m-%d").date()
    #         today = datetime.date.today()
    #         if deadline_date < today:
    #             return False, f"Application deadline {deadline_str} has passed."
    #     except ValueError:
    #         return False, f"Invalid deadline format: {deadline_str}. Use YYYY-MM-DD."

    # All conditions met
    return True, "All conditions met."

def decide_and_send_email(job_data, send_email_function, job_post):
	send, reason = should_send_email(job_data)
	if not send:
		return None, reason
	


	# Extract email details
	subject = job_data["message_content"]["subject"]
	body = job_data["message_content"]["body"]
	contact_emails = job_data["contact_email"]
	from_mail = os.getenv("FROM_MAIL")

	responses = []
	# read post_url.txt as list
	already_applied = [line.strip() for line in open("post_url.txt")]
	if job_post["post_link"] in already_applied:
		return None, "Already applied to this job."

	print(f"===Sending mail to {','.join(contact_emails)}===")
	for email in contact_emails:
		response = send_email_function(subject, body, email, from_mail)
		responses.append(response)

	body += "\n\n"
	body += f"Mail Sent to {', '.join(contact_emails)}.\n\n"
	body += f"Job Post URL: {job_post['post_link']}\n"
	body += f"AI Model Used: {job_data['model_name']}\n"
	body += "GRANTED BY ME"

	# add append entry of post_url in separate file
	with open("post_url.txt", "a") as f:
		f.write(f"{job_post['post_link']}\n")

	print("===Sending mail to myself ===")
	my_email = "prohrushi@gmail.com"
	response = send_email_function(subject, body, my_email, from_mail)

	return responses, f"Email(s) sent to {len(contact_emails)} recipient(s)."
