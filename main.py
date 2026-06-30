import sys
import os
import json
from app.config import Config
from app.github_client import GitHubClient
from app.analytics import AnalyticsEngine
from app.report_generator import ReportGenerator
from app.email_sender import EmailSender

def main():
    try:
        Config.validate()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        sys.exit(1)
        
    print("Starting Daily GitHub Engineering Activity Report generation...")

    # Initialize GitHub Client
    client = GitHubClient(
        token=Config.GITHUB_TOKEN,
        org_name=Config.GITHUB_ORG_NAME
    )

    # Fetch and process data
    print("Fetching data from GitHub API...")
    
    # Load team config
    team_config = {}
    if os.path.exists("team_config.json"):
        with open("team_config.json", "r", encoding="utf-8") as f:
            team_config = json.load(f)
            print(f"Loaded team config for {len(team_config.get('developers', []))} developers.")
    
    engine = AnalyticsEngine(client, team_config=team_config)
    report_data = engine.run_daily_analytics()
    
    # Generate HTML Report
    print("Generating HTML report...")
    generator = ReportGenerator()
    html_content = generator.generate_html(report_data)

    # For debugging, we can save a local copy
    with open("latest_report.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    # Send Main Report Email
    print("Sending main report email...")
    receivers = [email.strip() for email in Config.RECEIVER_EMAIL.split(',')]
    sender = EmailSender(
        host=Config.SMTP_HOST,
        port=Config.SMTP_PORT,
        email=Config.SMTP_EMAIL,
        password=Config.SMTP_PASSWORD
    )
    sender.send_email(receivers, html_content)

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
