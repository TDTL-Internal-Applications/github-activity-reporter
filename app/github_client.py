import requests
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

class GitHubClient:
    def __init__(self, token: str, org_name: str):
        self.token = token
        self.org_name = org_name
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def _get_paginated(self, url: str, params: Dict = None) -> List[Dict]:
        results = []
        if params is None:
            params = {}
        params['per_page'] = 100
        
        while url:
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                sleep_time = max(reset_time - time.time(), 0) + 1
                print(f"Rate limit exceeded. Sleeping for {sleep_time} seconds.")
                time.sleep(sleep_time)
                continue
                
            response.raise_for_status()
            results.extend(response.json())
            
            # check for next page
            url = None
            if 'next' in response.links:
                url = response.links['next']['url']
                params = None # params are already in the next URL
                
        return results

    def get_org_repos(self) -> List[Dict]:
        # Try organization endpoint first, fall back to user endpoint
        url = f"{self.base_url}/orgs/{self.org_name}/repos"
        response = requests.get(url, headers=self.headers, params={"type": "all", "per_page": 1})
        if response.status_code == 404:
            print(f"'{self.org_name}' is not an org, trying as a user account...")
            url = f"{self.base_url}/users/{self.org_name}/repos"
            return self._get_paginated(url, params={"type": "all"})
        return self._get_paginated(
            f"{self.base_url}/orgs/{self.org_name}/repos", params={"type": "all"}
        )

    def get_commits_for_repo(self, repo_name: str, since: str, until: str) -> List[Dict]:
        url = f"{self.base_url}/repos/{self.org_name}/{repo_name}/commits"
        params = {"since": since, "until": until}
        try:
            return self._get_paginated(url, params=params)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching commits for {repo_name}: {e}")
            return []

    def get_commit_details(self, repo_name: str, sha: str) -> Dict:
        url = f"{self.base_url}/repos/{self.org_name}/{repo_name}/commits/{sha}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return {}

    def get_pull_requests_for_repo(self, repo_name: str) -> List[Dict]:
        # We fetch recently updated PRs and filter them in the analytics layer
        url = f"{self.base_url}/repos/{self.org_name}/{repo_name}/pulls"
        params = {"state": "all", "sort": "updated", "direction": "desc"}
        try:
            return self._get_paginated(url, params=params)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching PRs for {repo_name}: {e}")
            return []

    def get_org_members(self) -> List[Dict]:
        # Try organization endpoint first; personal accounts don't have members
        url = f"{self.base_url}/orgs/{self.org_name}/members"
        response = requests.get(url, headers=self.headers, params={"per_page": 1})
        if response.status_code == 404:
            print(f"'{self.org_name}' is a personal account. Skipping org members lookup.")
            return []
        try:
            return self._get_paginated(
                f"{self.base_url}/orgs/{self.org_name}/members"
            )
        except requests.exceptions.RequestException as e:
            print(f"Error fetching org members: {e}")
            return []

    def get_user_email(self, username: str) -> str:
        url = f"{self.base_url}/users/{username}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            user_data = response.json()
            return user_data.get('email')
        return None

    def has_prior_commits(self, repo_name: str, author_login: str, until: str) -> bool:
        """Check if an author has any commits in a repo before a certain date."""
        url = f"{self.base_url}/repos/{self.org_name}/{repo_name}/commits"
        params = {"author": author_login, "until": until, "per_page": 1}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 200:
                commits = response.json()
                return len(commits) > 0
        except requests.exceptions.RequestException:
            pass
        return False

    def get_recent_commit_dates(self, repo_name: str, author_login: str, per_page: int = 100) -> set:
        """Fetch the dates of the most recent commits for a user to calculate streaks."""
        url = f"{self.base_url}/repos/{self.org_name}/{repo_name}/commits"
        params = {"author": author_login, "per_page": per_page}
        dates = set()
        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 200:
                for commit in response.json():
                    date_str = commit.get('commit', {}).get('author', {}).get('date')
                    if date_str:
                        dates.add(date_str)
        except requests.exceptions.RequestException:
            pass
        return dates

