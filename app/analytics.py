from typing import List, Dict, Any
from datetime import datetime, timezone
import pytz
from app.github_client import GitHubClient
from app.alerts import detect_alerts

class AnalyticsEngine:
    def __init__(self, client: GitHubClient, team_config: dict = None):
        self.client = client
        self.ist_tz = pytz.timezone('Asia/Kolkata')
        self.team_config = team_config or {}

    def get_start_and_end_of_day_utc(self):
        # We want "today" in IST, converted to UTC bounds for GitHub API
        now_ist = datetime.now(self.ist_tz)
        start_of_day_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day_ist = now_ist.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        start_utc = start_of_day_ist.astimezone(pytz.utc)
        end_utc = end_of_day_ist.astimezone(pytz.utc)
        
        return start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_yesterday_bounds_utc(self):
        from datetime import timedelta
        now_ist = datetime.now(self.ist_tz)
        yesterday_ist = now_ist - timedelta(days=1)
        start_of_day_ist = yesterday_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day_ist = yesterday_ist.replace(hour=23, minute=59, second=59, microsecond=999999)
        start_utc = start_of_day_ist.astimezone(pytz.utc)
        end_utc = end_of_day_ist.astimezone(pytz.utc)
        return start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"), end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    def run_daily_analytics(self) -> Dict[str, Any]:
        since, until = self.get_start_and_end_of_day_utc()
        y_since, y_until = self.get_yesterday_bounds_utc()
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
        for dev in self.team_config.get('developers', []):
            username = dev['github_username']
            org_member_logins.add(username)
            dev_accountability[username] = {
                'name': dev['name'],
                'is_night_owl': False,
                'repos': {}
            }
            for repo in dev['assigned_repos']:
                dev_accountability[username]['repos'][repo] = {
                    'commits': 0,
                    'files_changed': 0,
                    'lines_added': 0,
                    'lines_deleted': 0,
                    'last_push': "",
                    'is_first_push': False
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
                        'repos': {}
                    }
                    
                if repo_name not in dev_accountability[dev_key]['repos']:
                    dev_accountability[dev_key]['repos'][repo_name] = {
                        'commits': 0,
                        'files_changed': 0,
                        'lines_added': 0,
                        'lines_deleted': 0,
                        'last_push': ""
                    }
                    
                repo_stats_dev = dev_accountability[dev_key]['repos'][repo_name]
                repo_stats_dev['commits'] += 1
                repo_stats_dev['files_changed'] += files_changed
                repo_stats_dev['lines_added'] += additions
                repo_stats_dev['lines_deleted'] += deletions
                
                commit_time = commit_detail.get('commit', {}).get('author', {}).get('date', '')
                if commit_time:
                    try:
                        utc_time = datetime.strptime(commit_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                        ist_time = utc_time.astimezone(self.ist_tz)
                        if ist_time.hour >= 22 or ist_time.hour < 4:
                            dev_accountability[dev_key]['is_night_owl'] = True
                    except ValueError:
                        pass
                        
                if commit_time > repo_stats_dev['last_push']:
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
        
        pr_opened = sum(1 for pr in all_prs if pr['created_at'] >= since)
        pr_merged = sum(1 for pr in all_prs if pr.get('merged_at') and pr['merged_at'] >= since)
        
        # Convert set to length for repo stats
        for r_name in repo_stats:
            repo_stats[r_name]['contributors'] = len(repo_stats[r_name]['contributors'])
            
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
            for r_name, r_stats in dev_info['repos'].items():
                if r_stats['commits'] > 0:
                    dev_pushed_today = True
                    has_prior = self.client.has_prior_commits(r_name, dev_key, since)
                    if not has_prior:
                        r_stats['is_first_push'] = True

            streak = 0
            if dev_pushed_today:
                all_commit_dates = set()
                for r_name in dev_info['repos']:
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

        # Transform nested dict into sorted list for template
        dev_activity_nested = []
        spring_cleaner = None
        min_net_lines = 0

        for dev_key, dev_info in dev_accountability.items():
            repos_list = []
            dev_lines_added = 0
            dev_lines_deleted = 0
            for r_name, r_stats in dev_info['repos'].items():
                repos_list.append({
                    'repo_name': r_name,
                    'commits': r_stats['commits'],
                    'files_changed': r_stats['files_changed'],
                    'lines_added': r_stats['lines_added'],
                    'lines_deleted': r_stats['lines_deleted'],
                    'last_push': r_stats['last_push'],
                    'is_first_push': r_stats.get('is_first_push', False)
                })
                dev_lines_added += r_stats['lines_added']
                dev_lines_deleted += r_stats['lines_deleted']
            
            repos_list.sort(key=lambda x: x['repo_name'])
            dev_net_lines = dev_lines_added - dev_lines_deleted

            if dev_net_lines < min_net_lines:
                min_net_lines = dev_net_lines
                spring_cleaner = dev_key

            dev_activity_nested.append({
                'developer_name': dev_info['name'],
                'github_username': dev_key,
                'repos': repos_list,
                'total_commits': sum(r['commits'] for r in repos_list),
                'is_night_owl': dev_info.get('is_night_owl', False),
                'streak': dev_info.get('streak', 0)
            })
            
        for dev in dev_activity_nested:
            dev['is_spring_cleaner'] = (dev['github_username'] == spring_cleaner and spring_cleaner is not None)

        dev_activity_nested.sort(key=lambda x: (-x['total_commits'], x['developer_name']))
        dev_activity = dev_activity_nested
        
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
        
        return {
            'executive_summary': executive_summary,
            'developer_activity': dev_activity,
            'commits': all_commits,
            'prs': all_prs,
            'alerts': alerts_list,
            'repo_summary': repo_stats,
            'inactive_developers': inactive_developers,
            'quote': quote_of_the_day
        }
