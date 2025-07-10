import datetime
import json
import os
from dotenv import load_dotenv
import re

load_dotenv(override=True)

email_regex = r"""(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)])"""


def is_valid_email(email):
    return re.fullmatch(email_regex, email, re.IGNORECASE) is not None


def should_send_email(job_data):
    print(f"\n{'='*30} Starting Email Decision {'='*30}")
    if not isinstance(job_data, dict):
        raise TypeError("job_data must be a dictionary")

    email_list = job_data.get("contact_email", [])
    print(f"Found {len(email_list)} contact emails in job data")

    if not email_list:
        print("❌ No contact emails found in job data")
        return False, "Mail is None"

    new_mail_list = []
    invalid_emails = []
    for email in email_list:
        email = str(email)
        if is_valid_email(email):
            new_mail_list.append(email)
        else:
            invalid_emails.append(email)

    if invalid_emails:
        print(
            f"🛑 Found {len(invalid_emails)} invalid emails: {invalid_emails}")

    if not new_mail_list:
        print(f"❌ All emails invalid in list: {email_list}")
        return False, f"Emails from list {email_list} are not valid"

    try:
        match_percent = float(job_data.get('match_percentage', 0))
        print(f"🔍 Match Percentage: {match_percent}%")
        if match_percent <= 68:
            print(f"❌ Below threshold: {match_percent}% <= 68%")
            return False, f"Match percentage {match_percent}% is not greater than 68%."
    except (ValueError, TypeError):
        raise TypeError("match_percentage must be convertible to a number")

    try:
        exp_gap = float(job_data.get('experience_gap', 0))
        print(f"📅 Experience Gap: {exp_gap} years")
        if exp_gap >= 1:
            print(f"❌ Experience gap too large: {exp_gap} years >= 1 year")
            return False, f"Experience gap of {exp_gap} years is more than or equal to 1 year."
    except (ValueError, TypeError):
        
        raise TypeError("experience_gap must be convertible to a number")

    additional_data = job_data.get('additional_data', {})
    employment_type = str(additional_data.get('employment_type', '')).lower()
    print(f"🏢 Employment Type: {employment_type or 'Not specified'}")

    if employment_type == 'internship':
        print("❌ Internship position filtered out")
        return False, "Employment type is internship."

    print("✅ All conditions met for sending email")
    return True, "All conditions met."


def decide_and_send_email(job_data, send_email_function, job_post):
    print(f"\n{'='*30} Processing Job Post {'='*30}")
    print(f"📌 Post Title: {job_post.get('post_title', 'Unknown')}")
    print(f"🔗 Post URL: {job_post.get('post_link', 'Unknown')}")

    send, reason = should_send_email(job_data)
    if not send:
        print(f"⏩ Decision: Will not send email. Reason: {reason}")
        return None, reason, False

    subject = job_data["message_content"]["subject"]
    body = job_data["message_content"]["body"]
    contact_emails = job_data["contact_email"]
    from_mail = os.getenv("FROM_MAIL")

    print(f"\n📨 Email Details:")
    print(f"Subject: {subject}")
    print(f"Recipients: {', '.join(contact_emails)}")
    print(f"From: {from_mail}")

    responses = []
    already_applied = []
    try:
        with open("post_url.txt", "r") as f:
            already_applied = [line.strip() for line in f.readlines()]
            print(
                f"📋 Found {len(already_applied)} entries in application history")
    except FileNotFoundError:
        print("⚠️ post_url.txt not found, creating new file")

    if job_post["post_link"] in already_applied:
        print(f"⏭️ Already applied to: {job_post['post_link']}")
        return None, "Already applied to this job.", True

    print("\n🚀 Attempting to send emails...")
    for email in contact_emails:
        print(f"✉️ Sending email to: {email}")
        response = send_email_function(
            subject, body, email, from_mail, pdf_file_path=os.getenv("resume_pdf_path"))
        responses.append(response)
        print(
            f"✅ Successfully sent to {email}" if response else f"❌ Failed to send to {email}")

    body += "\n\nMail Sent to " + ", ".join(contact_emails) + ".\n\n"
    body += f"Job Post URL: {job_post['post_link']}\n"
    body += f"AI Model Used: {job_data['model_name']}\nGRANTED BY ME"

    try:
        with open("post_url.txt", "a") as f:
            f.write(f"{job_post['post_link']}\n")
            print(f"📝 Added to application history: {job_post['post_link']}")
    except Exception as e:
        print(f"❌ Failed to update application history: {str(e)}")

    print("\n📩 Sending confirmation email to myself")
    my_email = "prohrushi@gmail.com"
    response = send_email_function(subject, body, my_email, from_mail, pdf_file_path=os.getenv("resume_pdf_path"))
    print("✅ Confirmation email sent" if response else "❌ Failed to send confirmation email")

    print(f"\n{'='*30} Process Complete {'='*30}")
    return responses, f"Email(s) sent to {len(contact_emails)} recipient(s).", True
