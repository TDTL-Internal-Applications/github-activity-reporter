import os
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import pytz

class ReportGenerator:
    def __init__(self, templates_dir: str = "templates"):
        self.env = Environment(loader=FileSystemLoader(templates_dir))
        self.template = self.env.get_template("email_template.html")

    def generate_html(self, data: dict, report_type: str = 'daily') -> str:
        ist_tz = pytz.timezone('Asia/Kolkata')
        current_date = datetime.now(ist_tz).strftime("%d/%m/%Y")
        
        return self.template.render(
            report_type=report_type.capitalize(),
            date=current_date,
            exec=data.get('executive_summary', {}),
            alerts=data.get('alerts', []),
            developers=data.get('developers', []),
            commits=data.get('commits', []),
            prs=data.get('prs', []),
            repo_summary=data.get('repo_summary', {}),
            inactive_developers=data.get('inactive_developers', []),
            quote=data.get('quote', ''),
            ai_summary=data.get('ai_summary', ''),
            mvp=data.get('mvp'),
            bug_squasher=data.get('bug_squasher')
        )

    def generate_warning_html(self, username: str) -> str:
        warning_template = self.env.get_template("warning_email_template.html")
        ist_tz = pytz.timezone('Asia/Kolkata')
        current_date = datetime.now(ist_tz).strftime("%d/%m/%Y")
        
        return warning_template.render(
            username=username,
            date=current_date
        )
