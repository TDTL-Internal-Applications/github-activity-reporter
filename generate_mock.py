from app.report_generator import ReportGenerator

def generate_mock_report():
    mock_data = {
        'executive_summary': {
            'total_active_developers': 4,
            'total_commits_today': 12,
            'total_repos_changed': 3,
            'total_lines_added': 4530,
            'total_lines_deleted': 1205,
            'total_prs_opened': 2,
            'total_prs_merged': 1
        },
        'alerts': [
            {
                'alert': 'Commit without PR / Direct Push',
                'repo': 'core-backend',
                'developer': 'Alice Smith',
                'sha': 'a1b2c3d',
                'url': '#'
            },
            {
                'alert': 'Large deletion (1050 lines)',
                'repo': 'frontend-app',
                'developer': 'Bob Johnson',
                'sha': 'f4e5d6c',
                'url': '#'
            }
        ],
        'developer_activity': [
            {
                'dev_name': 'Alice Smith',
                'repo_name': 'core-backend',
                'commits': 5,
                'files_changed': 12,
                'lines_added': 2500,
                'lines_deleted': 400,
                'last_push': '2026-05-14T15:30:00Z'
            },
            {
                'dev_name': 'Bob Johnson',
                'repo_name': 'frontend-app',
                'commits': 3,
                'files_changed': 4,
                'lines_added': 150,
                'lines_deleted': 1050,
                'last_push': '2026-05-14T12:15:00Z'
            }
        ],
        'commits': [
            {
                'commit': {
                    'author': {'name': 'Alice Smith', 'date': '2026-05-14T15:30:00Z'},
                    'message': 'Fix database connection pool issue'
                },
                'html_url': 'https://github.com/org/core-backend/commit/a1b2c3d',
                'sha': 'a1b2c3d'
            },
            {
                'commit': {
                    'author': {'name': 'Bob Johnson', 'date': '2026-05-14T12:15:00Z'},
                    'message': 'Remove deprecated legacy components'
                },
                'html_url': 'https://github.com/org/frontend-app/commit/f4e5d6c',
                'sha': 'f4e5d6c'
            }
        ],
        'prs': [
            {
                'title': 'Feature: User Authentication Module',
                'html_url': '#',
                'base': {'repo': {'name': 'core-backend'}},
                'user': {'login': 'Alice Smith'},
                'state': 'closed',
                'created_at': '2026-05-13T10:00:00Z',
                'merged_at': '2026-05-14T14:20:00Z'
            },
            {
                'title': 'Bugfix: Mobile responsive header',
                'html_url': '#',
                'base': {'repo': {'name': 'frontend-app'}},
                'user': {'login': 'Charlie Brown'},
                'state': 'open',
                'created_at': '2026-05-14T09:00:00Z',
                'merged_at': None
            }
        ],
        'repo_summary': {
            'core-backend': {
                'total_commits': 5,
                'contributors': 1,
                'lines_added': 2500,
                'lines_deleted': 400
            },
            'frontend-app': {
                'total_commits': 7,
                'contributors': 3,
                'lines_added': 2030,
                'lines_deleted': 805
            }
        }
    }
    
    generator = ReportGenerator()
    html = generator.generate_html(mock_data)
    with open("sample_report.html", "w") as f:
        f.write(html)
        
    print("sample_report.html created.")

if __name__ == "__main__":
    generate_mock_report()
