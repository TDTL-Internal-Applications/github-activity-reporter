from typing import Dict, List
from datetime import datetime
import pytz

def detect_alerts(commit: Dict, prs: List[Dict]) -> List[str]:
    alerts = []
    
    stats = commit.get('stats', {})
    additions = stats.get('additions', 0)
    deletions = stats.get('deletions', 0)
    total_changes = stats.get('total', 0)
    
    # Large deletions (>1000 lines)
    if deletions > 1000:
        alerts.append(f"Large deletion ({deletions} lines)")
        
    # Massive commits (>5000 lines)
    if total_changes > 5000:
        alerts.append(f"Massive commit ({total_changes} lines changed)")
        

    # Suspicious late-night pushes (10 PM to 6 AM IST)
    # Commit time is usually in UTC. Convert to IST.
    commit_date_str = commit.get('commit', {}).get('committer', {}).get('date')
    if commit_date_str:
        dt_utc = datetime.strptime(commit_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
        ist_tz = pytz.timezone('Asia/Kolkata')
        dt_ist = dt_utc.astimezone(ist_tz)
        
        if dt_ist.hour >= 22 or dt_ist.hour < 6:
            alerts.append(f"Late-night push ({dt_ist.strftime('%I:%M %p')} IST)")
            
    return alerts
