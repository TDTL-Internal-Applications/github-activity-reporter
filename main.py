import sys
import os
import json
import argparse
from app.config import Config
from app.github_client import GitHubClient
from app.analytics import AnalyticsEngine
from app.report_generator import ReportGenerator
from app.email_sender import EmailSender

def main():
    parser = argparse.ArgumentParser(description="Generate GitHub Engineering Activity Report")
    parser.add_argument('--type', choices=['daily', 'weekly'], default='daily', help='Type of report to generate (daily or weekly)')
    args = parser.parse_args()
    report_type = args.type

    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        sys.exit(1)
        
    print(f"Starting {report_type.capitalize()} GitHub Engineering Activity Report generation...")

    # Initialize GitHub Client
    client = GitHubClient(
        token=Config.GITHUB_TOKEN,
        org_name=Config.GITHUB_ORG_NAME
    )

    # Fetch and process data
    print("Fetching data from GitHub API...")
    
    # Load project config
    project_config = {}
    if os.path.exists("project_config.json"):
        with open("project_config.json", "r", encoding="utf-8") as f:
            project_config = json.load(f)
            print(f"Loaded project config for {len(project_config.get('projects', []))} projects.")
    
    engine = AnalyticsEngine(client, team_config=project_config)
    report_data = engine.run_analytics(report_type=report_type)
    
    # Generate HTML Report
    print("Generating HTML report...")
    generator = ReportGenerator()
    html_content = generator.generate_html(report_data, report_type=report_type)

    # For debugging, we can save a local copy
    with open("latest_report.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # Send Main Report Email
    print(f"Sending main {report_type} report email...")
    if report_type == 'weekly':
        receivers_str = Config.WEEKLY_RECEIVERS
    else:
        receivers_str = Config.DAILY_RECEIVERS
        
    receivers = [email.strip() for email in receivers_str.split(',') if email.strip()]
    if receivers:
        sender = EmailSender(
            host=Config.SMTP_HOST,
            port=Config.SMTP_PORT,
            email=Config.SMTP_EMAIL,
            password=Config.SMTP_PASSWORD
        )
        sender.send_email(receivers, html_content, subject_prefix=f"[{report_type.capitalize()}]")
    else:
        print(f"No receivers configured for {report_type} report. Skipping email.")

    # Send Warning Emails to Inactive Developers
    print("Checking for inactive developers...")
    inactive_devs = report_data.get('inactive_developers', [])
    for dev in inactive_devs:
        if dev.get('email'):
            warning_html = generator.generate_warning_html(dev['login'])
            sender.send_warning_email(dev['email'], warning_html)
        else:
            print(f"Skipping warning email for {dev['login']} (No public email found)")
            
    print("Report generation and distribution completed successfully.")

if __name__ == "__main__":
    main()
