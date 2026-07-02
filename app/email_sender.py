import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import pytz

class EmailSender:
    def __init__(self, host: str, port: int, email: str, password: str):
        self.host = host
        self.port = port
        self.email = email
        self.password = password

    def send_email(self, receivers: list, html_content: str, subject_prefix: str = "[Daily]"):
        ist_tz = pytz.timezone('Asia/Kolkata')
        current_date = datetime.now(ist_tz).strftime("%d/%m/%Y")
        subject = f"{subject_prefix} GitHub Engineering Report - {current_date}"

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.email
        msg['To'] = ", ".join(receivers)

        part = MIMEText(html_content, 'html')
        msg.attach(part)

        try:
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)
                print(f"Successfully sent email to {', '.join(receivers)}")
        except Exception as e:
            print(f"Failed to send email: {e}")
    def send_warning_email(self, receiver: str, html_content: str):
        subject = "[Action Required] No GitHub Activity Detected Today"

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.email
        msg['To'] = receiver

        part = MIMEText(html_content, 'html')
        msg.attach(part)

        try:
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)
                print(f"Successfully sent warning email to {receiver}")
        except Exception as e:
            print(f"Failed to send warning email to {receiver}: {e}")
