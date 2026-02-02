"""
GitHub API - Create Pull Requests via GitHub API

This module handles:
1. Authentication with GitHub
2. Creating Pull Requests
3. Adding labels and reviewers
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

try:
    from github import Github, GithubException
except ImportError:
    Github = None
    GithubException = Exception

logger = logging.getLogger(__name__)


class GitHubAPI:
    """
    GitHub API client for creating Pull Requests.
    
    Handles:
    - PR creation with detailed descriptions
    - Label management
    - Reviewer assignment
    """
    
    def __init__(self, config: Dict):
        """
        Initialize GitHub API client.
        
        Args:
            config: Pipeline configuration
        """
        if Github is None:
            raise ImportError("PyGithub not installed. Run: pip install PyGithub")
            
        self.token = os.environ.get('GITHUB_TOKEN')
        if not self.token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
            
        self.client = Github(self.token)
        
        pr_config = config.get('pr', {})
        self.base_branch = pr_config.get('base_branch', 'master')
        self.labels = pr_config.get('labels', ['refactoring', 'automated'])
        self.assign_reviewers = pr_config.get('assign_reviewers', False)
        self.reviewers = pr_config.get('reviewers', [])
        self.title_template = pr_config.get(
            'title_template', 
            '🔧 Automated Design Smell Refactoring - {date}'
        )
        
        self.repo = None
        
    def connect_to_repo(self, owner: str, repo_name: str) -> bool:
        """
        Connect to a GitHub repository.
        
        Args:
            owner: Repository owner
            repo_name: Repository name
            
        Returns:
            True if successful
        """
        try:
            self.repo = self.client.get_repo(f"{owner}/{repo_name}")
            logger.info(f"Connected to repository: {owner}/{repo_name}")
            return True
            
        except GithubException as e:
            logger.error(f"Failed to connect to repository: {e}")
            return False
            
    def create_pull_request(
        self,
        head_branch: str,
        title: Optional[str] = None,
        body: str = "",
    ) -> Optional[Dict]:
        """
        Create a Pull Request.
        
        Args:
            head_branch: Branch with changes
            title: PR title (optional, uses template if not provided)
            body: PR description body
            
        Returns:
            PR information dictionary or None if failed
        """
        if not self.repo:
            logger.error("Repository not connected")
            return None
            
        if title is None:
            date = datetime.now().strftime('%Y-%m-%d')
            title = self.title_template.format(date=date)
            
        try:
            # Create the PR
            pr = self.repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=self.base_branch
            )
            
            logger.info(f"Created PR #{pr.number}: {title}")
            
            # Add labels
            self._add_labels(pr)
            
            # Add reviewers
            if self.assign_reviewers and self.reviewers:
                self._add_reviewers(pr)
                
            return {
                'number': pr.number,
                'html_url': pr.html_url,
                'title': pr.title,
                'state': pr.state
            }
            
        except GithubException as e:
            logger.error(f"Failed to create PR: {e}")
            return None
            
    def _add_labels(self, pr) -> bool:
        """
        Add labels to a PR.
        
        Args:
            pr: GitHub PR object
            
        Returns:
            True if successful
        """
        try:
            # Ensure labels exist
            existing_labels = [l.name for l in self.repo.get_labels()]
            
            for label in self.labels:
                if label not in existing_labels:
                    # Create label with a default color
                    self.repo.create_label(label, "0e8a16")  # Green color
                    
            pr.add_to_labels(*self.labels)
            logger.info(f"Added labels: {self.labels}")
            return True
            
        except GithubException as e:
            logger.warning(f"Failed to add labels: {e}")
            return False
            
    def _add_reviewers(self, pr) -> bool:
        """
        Add reviewers to a PR.
        
        Args:
            pr: GitHub PR object
            
        Returns:
            True if successful
        """
        try:
            pr.create_review_request(reviewers=self.reviewers)
            logger.info(f"Added reviewers: {self.reviewers}")
            return True
            
        except GithubException as e:
            logger.warning(f"Failed to add reviewers: {e}")
            return False
            
    def get_open_refactoring_prs(self) -> List[Dict]:
        """
        Get existing open refactoring PRs.
        
        Returns:
            List of PR information dictionaries
        """
        if not self.repo:
            return []
            
        try:
            prs = self.repo.get_pulls(state='open', base=self.base_branch)
            
            refactoring_prs = []
            for pr in prs:
                # Check if it's a refactoring PR by labels or title
                if 'refactoring' in [l.name for l in pr.labels]:
                    refactoring_prs.append({
                        'number': pr.number,
                        'html_url': pr.html_url,
                        'title': pr.title,
                        'created_at': pr.created_at.isoformat()
                    })
                    
            return refactoring_prs
            
        except GithubException as e:
            logger.error(f"Failed to get PRs: {e}")
            return []
            
    def add_comment(self, pr_number: int, comment: str) -> bool:
        """
        Add a comment to a PR.
        
        Args:
            pr_number: PR number
            comment: Comment text
            
        Returns:
            True if successful
        """
        if not self.repo:
            return False
            
        try:
            pr = self.repo.get_pull(pr_number)
            pr.create_issue_comment(comment)
            logger.info(f"Added comment to PR #{pr_number}")
            return True
            
        except GithubException as e:
            logger.error(f"Failed to add comment: {e}")
            return False
            
    def close_pr(self, pr_number: int, comment: Optional[str] = None) -> bool:
        """
        Close a PR without merging.
        
        Args:
            pr_number: PR number
            comment: Optional closing comment
            
        Returns:
            True if successful
        """
        if not self.repo:
            return False
            
        try:
            pr = self.repo.get_pull(pr_number)
            
            if comment:
                pr.create_issue_comment(comment)
                
            pr.edit(state='closed')
            logger.info(f"Closed PR #{pr_number}")
            return True
            
        except GithubException as e:
            logger.error(f"Failed to close PR: {e}")
            return False


if __name__ == "__main__":
    # Test GitHub API
    import yaml
    
    with open("config/config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    try:
        github_api = GitHubAPI(config)
        print("GitHub API initialized successfully")
        
        # You would need to set GITHUB_TOKEN and connect to a repo to test further
        
    except Exception as e:
        print(f"Error: {e}")
