import datetime

import os
from dotenv import load_dotenv

load_dotenv()

def should_send_email(job_data):
    # Check if user manually opted out
    # if not job_data.get('should_apply', False):
    #     return False, "Should apply is set to False."
    
    # Check match percentage
    match_percent = job_data.get('match_percentage', 0)
    if match_percent <= 68:
        return False, f"Match percentage {match_percent}% is not greater than 68%."
    
    # Check experience gap
    exp_gap = job_data.get('experience_gap', 0)
    if exp_gap >= 1:
        return False, f"Experience gap of {exp_gap} years is more than or equal to 1 year."
    
    # Check employment type
    additional_data = job_data.get('additional_data', {})
    employment_type = additional_data.get('employment_type', '').lower()
    if employment_type == 'internship':
        return False, "Employment type is internship."
    
    # Check contact email exists
    contact_emails = job_data.get('contact_email', [])
    if not contact_emails:
        return False, "No contact email provided."
    
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

def decide_and_send_email(job_data, send_email_function):
    send, reason = should_send_email(job_data)
    if not send:
        return None, reason
    
    # Extract email details
    subject = job_data['message_content']['subject']
    body = job_data['message_content']['body']
    contact_emails = job_data['contact_email']
    from_mail = os.getenv("FROM_MAIL")
    
    responses = []
    print("Replacing Contact emails:", contact_emails)
    contact_emails = ["prohrushi@gmail.com"]
    for email in contact_emails:
        response = send_email_function(subject, body, email, from_mail)
        responses.append(response)
    
    return responses, f"Email(s) sent to {len(contact_emails)} recipient(s)."