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

    def run_daily_analytics(self) -> Dict[str, Any]:
        since, until = self.get_start_and_end_of_day_utc()
        repos = self.client.get_org_repos()
        
        all_commits = []
        all_prs = []
        
        repo_stats = {}
        alerts_list = []
        
        active_developers = set()
        active_developer_logins = set()
        
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
                'repos': {}
            }
            for repo in dev['assigned_repos']:
                dev_accountability[username]['repos'][repo] = {
                    'commits': 0,
                    'files_changed': 0,
                    'lines_added': 0,
                    'lines_deleted': 0,
                    'last_push': ""
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
            
            for basic_commit in commits:
                # Need details for lines added/deleted
                commit_detail = self.client.get_commit_details(repo_name, basic_commit['sha'])
                if not commit_detail:
                    continue
                    
                all_commits.append(commit_detail)
                
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
        for login in inactive_logins:
            email = self.client.get_user_email(login)
            inactive_developers.append({
                'login': login,
                'email': email
            })
        
        executive_summary = {
            'total_active_developers': len(active_developers),
            'total_commits_today': len(all_commits),
            'total_repos_changed': len([r for r, s in repo_stats.items() if s['total_commits'] > 0]),
            'total_lines_added': total_lines_added,
            'total_lines_deleted': total_lines_deleted,
            'total_prs_opened': pr_opened,
            'total_prs_merged': pr_merged
        }

        # Transform nested dict into sorted list for template
        dev_activity_nested = []
        for dev_key, dev_info in dev_accountability.items():
            repos_list = []
            for r_name, r_stats in dev_info['repos'].items():
                repos_list.append({
                    'repo_name': r_name,
                    'commits': r_stats['commits'],
                    'files_changed': r_stats['files_changed'],
                    'lines_added': r_stats['lines_added'],
                    'lines_deleted': r_stats['lines_deleted'],
                    'last_push': r_stats['last_push']
                })
            
            repos_list.sort(key=lambda x: x['repo_name'])
            dev_activity_nested.append({
                'developer_name': dev_info['name'],
                'github_username': dev_key,
                'repos': repos_list,
                'total_commits': sum(r['commits'] for r in repos_list)
            })
            
        dev_activity_nested.sort(key=lambda x: (-x['total_commits'], x['developer_name']))
        dev_activity = dev_activity_nested
        
        return {
            'executive_summary': executive_summary,
            'developer_activity': dev_activity,
            'commits': all_commits,
            'prs': all_prs,
            'alerts': alerts_list,
            'repo_summary': repo_stats,
            'inactive_developers': inactive_developers
        }
