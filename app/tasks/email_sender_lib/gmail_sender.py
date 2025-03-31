import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from email.mime.text import MIMEText
import base64

# Define OAuth2 scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Get the directory of the current script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Construct file paths relative to the script location
CLIENT_SECRET_FILE = os.path.join(BASE_DIR, 'client_secret.json')  
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')

def get_gmail_credentials():
	"""Retrieve or generate OAuth2 credentials."""
	creds = None
	if os.path.exists(TOKEN_FILE):
		creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
	if not creds or not creds.valid:
		if creds and creds.expired and creds.refresh_token:
			creds.refresh(Request())
		else:
			flow = InstalledAppFlow.from_client_secrets_file(
				CLIENT_SECRET_FILE, SCOPES)
			creds = flow.run_local_server(port=0)
		with open(TOKEN_FILE, 'w') as token:
			token.write(creds.to_json())
	return creds

def send_email_via_gmail_api(
		subject: str,
		body: str,
		to_email: str,
		from_email: str
	) -> dict:
	"""
	Send email using Gmail API.
	
	Args:
		subject: Email subject
		body: Email body (plain text)
		to_email: Recipient email address
		from_email: Sender email (default: authenticated user)
	
	Returns:
		dict: Sent message details
	"""
	try:
		creds = get_gmail_credentials()
		service = build('gmail', 'v1', credentials=creds)

		message = MIMEText(body)
		message['to'] = to_email
		message['subject'] = subject
		if from_email:
			message['from'] = from_email
		
		raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
		
		result = service.users().messages().send(
			userId='me',
			body={'raw': raw_message}
		).execute()
		
		return result
	except Exception as e:
		raise RuntimeError(f"Failed to send email: {str(e)}")

# Example usage
if __name__ == '__main__':
	try:
		response = send_email_via_gmail_api(
			subject="Important Notification",
			body="This is a production email sent via Gmail API",
			to_email="prohrushi@gmail.com",
			from_email="prohrushi@gmail.com"
		)
		print(f"Email sent successfully! Message ID: {response}")
	except Exception as e:
		print(f"Error sending email: {e}")
