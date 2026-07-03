from typing import List, Dict, Any
from datetime import datetime, timezone
import pytz
import google.generativeai as genai
from app.github_client import GitHubClient
from app.alerts import detect_alerts
from app.config import Config

class AnalyticsEngine:
    def __init__(self, client: GitHubClient, team_config: dict = None):
        self.client = client
        self.ist_tz = pytz.timezone('Asia/Kolkata')
        self.team_config = team_config or {}

    def _generate_ai_summary(self, commits: List[dict], report_type: str) -> str:
        if not Config.GEMINI_API_KEY:
            # Fallback heuristic summary
            return f"The engineering team logged {len(commits)} commits { 'this week' if report_type == 'weekly' else 'today' }. Focus was distributed across feature development and bug fixes. Review the project dashboard below for individual impact."
        
        try:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-pro')
            
            # Extract just the messages to save tokens
            messages = [c.get('commit', {}).get('message', '').split('\n')[0] for c in commits[:100]]
            if not messages:
                return "No code changes were logged in this period."
                
            prompt = f"You are a CTO summarizing a GitHub activity report. Write a strict 2-3 sentence executive summary of the following commit messages from the engineering team. Focus on high-level business impact (e.g. 'The team heavily focused on UI overhauls...'). Do not list individual commits. Commits: {'; '.join(messages)}"
            
            response = model.generate_content(prompt)
            return response.text.replace('\n', ' ').strip()
        except Exception as e:
            print(f"AI Summary generation failed: {e}")
            return f"The engineering team logged {len(commits)} commits { 'this week' if report_type == 'weekly' else 'today' }."

    def get_time_bounds(self, report_type: str = 'daily'):
        from datetime import timedelta
        now_ist = datetime.now(self.ist_tz)
        
        if report_type == 'weekly':
            start_ist = (now_ist - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
            
        end_ist = now_ist.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        start_utc = start_ist.astimezone(pytz.utc)
        end_utc = end_ist.astimezone(pytz.utc)
        return start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_prev_time_bounds(self, report_type: str = 'daily'):
        from datetime import timedelta
        now_ist = datetime.now(self.ist_tz)
        
        if report_type == 'weekly':
            end_ist = (now_ist - timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)
            start_ist = (now_ist - timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            yesterday_ist = now_ist - timedelta(days=1)
            start_ist = yesterday_ist.replace(hour=0, minute=0, second=0, microsecond=0)
            end_ist = yesterday_ist.replace(hour=23, minute=59, second=59, microsecond=999999)
            
        start_utc = start_ist.astimezone(pytz.utc)
        end_utc = end_ist.astimezone(pytz.utc)
        return start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def run_analytics(self, report_type: str = 'daily') -> Dict[str, Any]:
        since, until = self.get_time_bounds(report_type)
        y_since, y_until = self.get_prev_time_bounds(report_type)
        repos = self.client.get_org_repos()
        
        all_commits = []
        all_prs = []
        
        repo_stats = {}
        alerts_list = []
        
        active_developers = set()
        active_developer_logins = set()
        yesterday_total_commits = 0
        
        # Build full team list from org members
        all_members = self.client.get_org_members()
        org_member_logins = {member['login'] for member in all_members}
        
        # Initialize developer stats from config
        dev_accountability = {}
        for proj in self.team_config.get('projects', []):
            proj_name = proj['project_name']
            for dev in proj.get('developers', []):
                username = dev['github_username']
                org_member_logins.add(username)
                if username not in dev_accountability:
                    dev_accountability[username] = {
                        'name': dev['name'],
                        'is_night_owl': False,
                        'projects': {}
                    }
                
                assigned_repos = []
                if dev['role'].lower() == 'frontend' and 'frontend' in proj.get('repositories', {}):
                    assigned_repos.append(proj['repositories']['frontend'])
                elif dev['role'].lower() == 'backend' and 'backend' in proj.get('repositories', {}):
                    assigned_repos.append(proj['repositories']['backend'])
                else:
                    assigned_repos = list(proj.get('repositories', {}).values())
                    
                dev_accountability[username]['projects'][proj_name] = {
                    'role': dev['role'],
                    'repos': {r: {
                        'commits': 0, 'files_changed': 0, 'lines_added': 0, 'lines_deleted': 0, 'last_push': "", 'is_first_push': False, 'bugs_fixed': 0
                    } for r in assigned_repos}
                }
        
        for repo in repos:
            repo_name = repo['name']
            repo_stats[repo_name] = {
                'total_commits': 0,
                'contributors': set(),
                'lines_added': 0,
                'lines_deleted': 0
            }
            
            # Fetch commits
            commits = self.client.get_commits_for_repo(repo_name, since, until)
            
            # Fetch yesterday commits for velocity trend
            y_commits = self.client.get_commits_for_repo(repo_name, y_since, y_until)
            yesterday_total_commits += len(y_commits)
            
            # Fetch PRs
            prs = self.client.get_pull_requests_for_repo(repo_name)
            
            # Filter PRs for today
            today_prs = []
            for pr in prs:
                created_at = datetime.strptime(pr['created_at'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                if created_at.strftime("%Y-%m-%dT%H:%M:%SZ") >= since:
                    today_prs.append(pr)
                elif pr.get('merged_at'):
                    merged_at = datetime.strptime(pr['merged_at'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                    if merged_at.strftime("%Y-%m-%dT%H:%M:%SZ") >= since:
                        today_prs.append(pr)
            
            all_prs.extend(today_prs)
            
            if 'commit_focus' not in locals():
                commit_focus = {'features': 0, 'bugs': 0, 'refactor': 0, 'docs': 0, 'other': 0}
            
            for basic_commit in commits:
                # Need details for lines added/deleted
                commit_detail = self.client.get_commit_details(repo_name, basic_commit['sha'])
                if not commit_detail:
                    continue
                    
                all_commits.append(commit_detail)
                
                msg = commit_detail.get('commit', {}).get('message', '').lower()
                if any(k in msg for k in ['feat', 'add', 'new', 'create', '✨']):
                    commit_focus['features'] += 1
                elif any(k in msg for k in ['fix', 'bug', 'resolve', 'patch', '🐛']):
                    commit_focus['bugs'] += 1
                elif any(k in msg for k in ['refactor', 'clean', 'remove', 'update', '♻️']):
                    commit_focus['refactor'] += 1
                elif any(k in msg for k in ['doc', 'readme', '📝']):
                    commit_focus['docs'] += 1
                else:
                    commit_focus['other'] += 1
                
                author_name = commit_detail.get('commit', {}).get('author', {}).get('name', 'Unknown')
                author_login = None
                if commit_detail.get('author'):
                    author_login = commit_detail.get('author').get('login')
                
                active_developers.add(author_name)
                if author_login:
                    active_developer_logins.add(author_login)
                
                stats = commit_detail.get('stats', {})
                additions = stats.get('additions', 0)
                deletions = stats.get('deletions', 0)
                files_changed = len(commit_detail.get('files', []))
                
                # Repo stats update
                repo_stats[repo_name]['total_commits'] += 1
                repo_stats[repo_name]['contributors'].add(author_name)
                repo_stats[repo_name]['lines_added'] += additions
                repo_stats[repo_name]['lines_deleted'] += deletions
                
                # Developer stats update
                dev_key = author_login if author_login else author_name
                if dev_key not in dev_accountability:
                    dev_accountability[dev_key] = {
                        'name': author_name,
                        'is_night_owl': False,
                        'is_early_bird': False,
                        'bugs_squashed': 0,
                        'total_commits': 0,
                        'total_lines_added': 0,
                        'total_prs_merged': 0,
                        'projects': {'Unknown Project': {'role': 'Unknown', 'repos': {}}}
                    }
                
                # Check if this repo is in any of their projects
                found_proj = False
                for proj_name, proj_data in dev_accountability[dev_key]['projects'].items():
                    if repo_name in proj_data['repos']:
                        found_proj = True
                        break
                        
                if not found_proj:
                    # If repo not mapped for this user, add it to their first project or Unknown
                    first_proj = next(iter(dev_accountability[dev_key]['projects']))
                    dev_accountability[dev_key]['projects'][first_proj]['repos'][repo_name] = {
                        'commits': 0, 'files_changed': 0, 'lines_added': 0, 'lines_deleted': 0, 'last_push': "", 'is_first_push': False, 'bugs_fixed': 0
                    }
                    
                # Track developer global metrics
                dev_accountability[dev_key]['total_commits'] += 1
                dev_accountability[dev_key]['total_lines_added'] += additions
                if any(k in msg for k in ['fix', 'bug', 'resolve', 'patch', '🐛']):
                    dev_accountability[dev_key]['bugs_squashed'] += 1

                for proj_name, proj_data in dev_accountability[dev_key]['projects'].items():
                    if repo_name in proj_data['repos']:
                        repo_stats_dev = proj_data['repos'][repo_name]
                        repo_stats_dev['commits'] += 1
                        repo_stats_dev['files_changed'] += files_changed
                        repo_stats_dev['lines_added'] += additions
                        repo_stats_dev['lines_deleted'] += deletions
                        if any(k in msg for k in ['fix', 'bug', 'resolve', 'patch', '🐛']):
                            repo_stats_dev['bugs_fixed'] += 1
                        
                        commit_time = commit_detail.get('commit', {}).get('author', {}).get('date', '')
                        if commit_time:
                            try:
                                utc_time = datetime.strptime(commit_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                                ist_time = utc_time.astimezone(self.ist_tz)
                                if ist_time.hour >= 22 or ist_time.hour < 4:
                                    dev_accountability[dev_key]['is_night_owl'] = True
                                elif ist_time.hour < 8:
                                    dev_accountability[dev_key]['is_early_bird'] = True
                            except ValueError:
                                pass
                                
                        if not repo_stats_dev['last_push'] or commit_time > repo_stats_dev['last_push']:
                            repo_stats_dev['last_push'] = commit_time
                
                # Alerts
                commit_alerts = detect_alerts(commit_detail, today_prs)
                for alert in commit_alerts:
                    alerts_list.append({
                        'alert': alert,
                        'repo': repo_name,
                        'developer': author_name,
                        'sha': commit_detail['sha'][:7],
                        'url': commit_detail.get('html_url')
                    })
                    
        # Post-process for report
        total_lines_added = sum(r['lines_added'] for r in repo_stats.values())
        total_lines_deleted = sum(r['lines_deleted'] for r in repo_stats.values())
        
        pr_opened = 0
        pr_merged = 0
        for pr in all_prs:
            if pr['created_at'] >= since:
                pr_opened += 1
            if pr.get('merged_at') and pr['merged_at'] >= since:
                pr_merged += 1
                pr_user = pr.get('user', {}).get('login')
                if pr_user and pr_user in dev_accountability:
                    dev_accountability[pr_user]['total_prs_merged'] += 1
        
        # Calculate MVP and Top Bug Squasher
        mvp_dev = None
        highest_score = -1
        top_bug_squasher = None
        most_bugs = 0
        
        for dev_key, data in dev_accountability.items():
            # MVP Score = (Commits * 2) + (PRs Merged * 10) + (Lines Added * 0.01)
            score = (data['total_commits'] * 2) + (data['total_prs_merged'] * 10) + (data['total_lines_added'] * 0.01)
            if score > highest_score and data['total_commits'] > 0:
                highest_score = score
                mvp_dev = data
                
            if data['bugs_squashed'] > most_bugs:
                most_bugs = data['bugs_squashed']
                top_bug_squasher = data
        
        # Convert set to length for repo stats and calculate Health Grades
        for r_name in repo_stats:
            repo_stats[r_name]['contributors'] = len(repo_stats[r_name]['contributors'])
            r_commits = repo_stats[r_name]['total_commits']
            r_added = repo_stats[r_name]['lines_added']
            r_deleted = repo_stats[r_name]['lines_deleted']
            
            # Simple heuristic for grading
            if r_commits == 0:
                grade = 'N/A'
            elif r_added > r_deleted * 2 and r_commits >= 5:
                grade = 'A+'
            elif r_added > r_deleted and r_commits >= 2:
                grade = 'A'
            elif r_deleted > r_added * 2:
                grade = 'C (High Churn)'
            else:
                grade = 'B'
            
            repo_stats[r_name]['health_grade'] = grade
            
        # Identify inactive developers
        inactive_logins = org_member_logins - active_developer_logins
        inactive_developers = []
        
        import json
        from app.config import Config
        try:
            secure_emails = json.loads(Config.DEV_EMAILS)
        except:
            secure_emails = {}
            
        for login in inactive_logins:
            email = secure_emails.get(login) or self.client.get_user_email(login)
            inactive_developers.append({
                'login': login,
                'email': email
            })

        if yesterday_total_commits == 0:
            commit_trend = 0.0
        else:
            commit_trend = ((len(all_commits) - yesterday_total_commits) / yesterday_total_commits) * 100

        # Process commit focus percentages
        total_focus = sum(commit_focus.values()) if 'commit_focus' in locals() else 0
        focus_percentages = {}
        if total_focus > 0:
            for k, v in commit_focus.items():
                focus_percentages[k] = round((v / total_focus) * 100)
        else:
            focus_percentages = {'features': 0, 'bugs': 0, 'refactor': 0, 'docs': 0, 'other': 0}

        executive_summary = {
            'total_active_developers': len(active_developers),
            'total_commits_today': len(all_commits),
            'yesterday_total_commits': yesterday_total_commits,
            'commit_trend_percentage': round(commit_trend, 1),
            'total_repos_changed': len([r for r, s in repo_stats.items() if s['total_commits'] > 0]),
            'total_lines_added': total_lines_added,
            'total_lines_deleted': total_lines_deleted,
            'total_prs_opened': pr_opened,
            'total_prs_merged': pr_merged,
            'focus_percentages': focus_percentages
        }

        # Identify first pushes and calculate streaks
        from datetime import timedelta
        for dev_key, dev_info in dev_accountability.items():
            dev_pushed_today = False
            for proj_name, proj_data in dev_info['projects'].items():
                for r_name, r_stats in proj_data['repos'].items():
                    if r_stats['commits'] > 0:
                        dev_pushed_today = True
                        has_prior = self.client.has_prior_commits(r_name, dev_key, since)
                        if not has_prior:
                            r_stats['is_first_push'] = True

            streak = 0
            if dev_pushed_today:
                all_commit_dates = set()
                for proj_name, proj_data in dev_info['projects'].items():
                    for r_name in proj_data['repos']:
                        repo_dates = self.client.get_recent_commit_dates(r_name, dev_key, per_page=100)
                        for d_str in repo_dates:
                            try:
                                utc_time = datetime.strptime(d_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                                ist_time = utc_time.astimezone(self.ist_tz)
                                all_commit_dates.add(ist_time.strftime("%Y-%m-%d"))
                            except ValueError:
                                pass
                
                now_ist = datetime.now(self.ist_tz)
                check_date = now_ist
                
                while check_date.strftime("%Y-%m-%d") in all_commit_dates:
                    streak += 1
                    check_date -= timedelta(days=1)
            
            dev_info['streak'] = streak

        # Transform nested dict into project-centric list for template
        projects_data = {}
        for proj in self.team_config.get('projects', []):
            projects_data[proj['project_name']] = {'project_name': proj['project_name'], 'developers': []}
            
        spring_cleaner = None
        min_net_lines = 0

        # We first calculate dev global stats for spring cleaner
        for dev_key, dev_info in dev_accountability.items():
            dev_lines_added = 0
            dev_lines_deleted = 0
            for proj_name, proj_data in dev_info['projects'].items():
                for r_name, r_stats in proj_data['repos'].items():
                    dev_lines_added += r_stats['lines_added']
                    dev_lines_deleted += r_stats['lines_deleted']
            
            dev_net_lines = dev_lines_added - dev_lines_deleted
            if dev_net_lines < min_net_lines:
                min_net_lines = dev_net_lines
                spring_cleaner = dev_key

        developer_dashboards = []
        for dev_key, dev_info in dev_accountability.items():
            is_spring = (dev_key == spring_cleaner and spring_cleaner is not None)
            
            if dev_info['total_commits'] == 0:
                continue
                
            dev_projects = []
            for proj_name, proj_data in dev_info['projects'].items():
                repos_list = []
                for r_name, r_stats in proj_data['repos'].items():
                    if r_stats['commits'] > 0:
                        commits = r_stats['commits']
                        fixes = r_stats.get('bugs_fixed', 0)
                        features = commits - fixes
                        fixes_pct = int((fixes / commits) * 100)
                        features_pct = 100 - fixes_pct
                        
                        repos_list.append({
                            'repo_name': r_name,
                            'commits': commits,
                            'files_changed': r_stats['files_changed'],
                            'lines_added': r_stats['lines_added'],
                            'lines_deleted': r_stats['lines_deleted'],
                            'fixes_pct': fixes_pct,
                            'features_pct': features_pct,
                            'last_push': r_stats['last_push'],
                            'is_first_push': r_stats.get('is_first_push', False)
                        })
                
                if repos_list:
                    repos_list.sort(key=lambda x: x['repo_name'])
                    dev_projects.append({
                        'project_name': proj_name,
                        'repos': repos_list,
                        'role': proj_data.get('role', 'Unknown')
                    })
                    
            dev_projects.sort(key=lambda x: x['project_name'])
            
            if dev_projects:
                developer_dashboards.append({
                    'developer_name': dev_info['name'],
                    'github_username': dev_key,
                    'total_commits': dev_info['total_commits'],
                    'is_night_owl': dev_info.get('is_night_owl', False),
                    'is_early_bird': dev_info.get('is_early_bird', False),
                    'streak': dev_info.get('streak', 0),
                    'is_spring_cleaner': is_spring,
                    'projects': dev_projects
                })

        # Sort developers by total commits descending
        developer_dashboards.sort(key=lambda x: x['total_commits'], reverse=True)
        
        import random
        quotes = [
            "“Talk is cheap. Show me the code.” – Linus Torvalds",
            "“Programs must be written for people to read, and only incidentally for machines to execute.” – Harold Abelson",
            "“Always code as if the guy who ends up maintaining your code will be a violent psychopath who knows where you live.” – John Woods",
            "“Any fool can write code that a computer can understand. Good programmers write code that humans can understand.” – Martin Fowler",
            "“First, solve the problem. Then, write the code.” – John Johnson",
            "“Experience is the name everyone gives to their mistakes.” – Oscar Wilde",
            "“Java is to JavaScript what car is to Carpet.” – Chris Heilmann",
            "“Sometimes it pays to stay in bed on Monday, rather than spending the rest of the week debugging Monday's code.” – Dan Salomon",
            "“Perfection is achieved not when there is nothing more to add, but rather when there is nothing more to take away.” – Antoine de Saint-Exupery",
            "“Code is like humor. When you have to explain it, it’s bad.” – Cory House",
            "“Fix the cause, not the symptom.” – Steve Maguire",
            "“Make it work, make it right, make it fast.” – Kent Beck"
        ]
        quote_of_the_day = random.choice(quotes)
        
        # Generate AI Summary
        ai_summary = self._generate_ai_summary(all_commits, report_type)

        return {
            'executive_summary': executive_summary,
            'developers': developer_dashboards,
            'commits': all_commits,
            'prs': all_prs,
            'alerts': alerts_list,
            'repo_summary': repo_stats,
            'inactive_developers': inactive_developers,
            'quote': quote_of_the_day,
            'ai_summary': ai_summary,
            'mvp': mvp_dev,
            'bug_squasher': top_bug_squasher
        }
