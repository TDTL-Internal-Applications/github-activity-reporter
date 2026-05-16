# Automated Daily GitHub Engineering Activity Reporting System

A Python-based automated system that connects to the GitHub REST API, fetches daily commits and pull requests across all organization repositories, generates comprehensive analytics, and sends a professional HTML email report.

## Features
- **Executive Summary:** Total active developers, commits, lines added/deleted, and PR metrics.
- **Developer-wise Activity:** Commits, files changed, and net changes per developer.
- **Commit Details:** Detailed view of recent commits with links.
- **Pull Request Details:** Status of opened and merged PRs for the day.
- **Alerts Section:** Detects direct pushes to main, large deletions (>1000 lines), massive commits (>5000 lines), and late-night pushes.
- **Repository Summary:** Overview of activity across all active repositories.

## Setup Instructions

1. **Install Dependencies**
   Ensure you have Python 3.8+ installed.
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   Rename `.env.example` to `.env` and fill in your credentials:
   ```env
   GITHUB_TOKEN=your_github_personal_access_token
   GITHUB_ORG_NAME=your_github_organization_name
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_EMAIL=your_email@gmail.com
   SMTP_PASSWORD=your_app_password
   RECEIVER_EMAIL=receiver1@example.com,receiver2@example.com
   ```
   *Note: If using Gmail, you need to generate an "App Password" from your Google Account settings.*

3. **Run Manually**
   ```bash
   python main.py
   ```

## Cron Job Scheduling

To automate the daily report at 7:00 PM IST (which is 1:30 PM UTC), add a cron job on your server.

1. Open your cron editor:
   ```bash
   crontab -e
   ```

2. Add the following entry (adjust the path to your script and python executable):
   ```cron
   # Run daily at 7:00 PM IST (13:30 UTC)
   30 13 * * * cd /path/to/github-activity-report && /path/to/python main.py >> /path/to/github-activity-report/logs/cron.log 2>&1
   ```

*Make sure to create a `logs` directory inside the project folder if you use the logging path above.*
