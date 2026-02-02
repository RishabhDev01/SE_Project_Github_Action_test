"""
Git Operations - Handle Git branch creation, commits, and pushes

This module handles:
1. Creating feature branches for refactoring
2. Staging and committing changes
3. Pushing to remote repository
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from git import Repo, GitCommandError
except ImportError:
    Repo = None
    GitCommandError = Exception

logger = logging.getLogger(__name__)


class GitOperations:
    """
    Git operations for the refactoring pipeline.
    
    Handles:
    - Branch creation
    - File staging and commits
    - Push to remote
    """
    
    def __init__(self, config: Dict, repo_path: Optional[Path] = None):
        """
        Initialize Git operations.
        
        Args:
            config: Pipeline configuration
            repo_path: Path to the repository (optional)
        """
        if Repo is None:
            raise ImportError("GitPython not installed. Run: pip install GitPython")
            
        git_config = config.get('git', {})
        self.branch_prefix = git_config.get('branch_prefix', 'refactoring/design-smells')
        self.commit_template = git_config.get(
            'commit_message_template', 
            'refactor: Automated design smell fixes - {timestamp}'
        )
        
        # Find repository root
        if repo_path:
            self.repo_path = Path(repo_path)
        else:
            # Try to find repo from source path
            source_path = Path(config.get('detection', {}).get('source_path', '.'))
            self.repo_path = self._find_repo_root(source_path)
            
        self.repo = None
        self.original_branch = None
        self.current_branch = None
        
    def _find_repo_root(self, start_path: Path) -> Path:
        """
        Find the Git repository root from a starting path.
        
        Args:
            start_path: Path to start searching from
            
        Returns:
            Path to repository root
        """
        current = start_path.resolve()
        
        while current != current.parent:
            if (current / '.git').exists():
                return current
            current = current.parent
            
        # Default to current directory
        return Path.cwd()
        
    def initialize(self) -> bool:
        """
        Initialize the Git repository connection.
        
        Returns:
            True if successful
        """
        try:
            self.repo = Repo(self.repo_path)
            self.original_branch = self.repo.active_branch.name
            logger.info(f"Initialized Git repo at {self.repo_path}, branch: {self.original_branch}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Git repo: {e}")
            return False
            
    def create_refactoring_branch(self) -> Optional[str]:
        """
        Create a new branch for refactoring changes.
        
        Returns:
            Branch name or None if failed
        """
        if not self.repo:
            logger.error("Repository not initialized")
            return None
            
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        branch_name = f"{self.branch_prefix}-{timestamp}"
        
        try:
            # Make sure we're on a clean state
            if self.repo.is_dirty():
                logger.warning("Repository has uncommitted changes")
                
            # Create and checkout new branch
            new_branch = self.repo.create_head(branch_name)
            new_branch.checkout()
            
            self.current_branch = branch_name
            logger.info(f"Created and checked out branch: {branch_name}")
            return branch_name
            
        except GitCommandError as e:
            logger.error(f"Failed to create branch: {e}")
            return None
            
    def stage_files(self, file_paths: List[Path]) -> bool:
        """
        Stage files for commit.
        
        Args:
            file_paths: List of file paths to stage
            
        Returns:
            True if successful
        """
        if not self.repo:
            logger.error("Repository not initialized")
            return False
            
        try:
            for file_path in file_paths:
                # Convert to relative path
                rel_path = file_path.relative_to(self.repo_path) if file_path.is_absolute() else file_path
                self.repo.index.add([str(rel_path)])
                logger.info(f"Staged: {rel_path}")
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to stage files: {e}")
            return False
            
    def commit_changes(self, message: Optional[str] = None) -> Optional[str]:
        """
        Commit staged changes.
        
        Args:
            message: Custom commit message (optional)
            
        Returns:
            Commit SHA or None if failed
        """
        if not self.repo:
            logger.error("Repository not initialized")
            return None
            
        if message is None:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            message = self.commit_template.format(timestamp=timestamp)
            
        try:
            commit = self.repo.index.commit(message)
            logger.info(f"Created commit: {commit.hexsha[:8]} - {message}")
            return commit.hexsha
            
        except Exception as e:
            logger.error(f"Failed to commit: {e}")
            return None
            
    def push_branch(self, remote_name: str = 'origin') -> bool:
        """
        Push the current branch to remote.
        
        Args:
            remote_name: Name of the remote (default: origin)
            
        Returns:
            True if successful
        """
        if not self.repo or not self.current_branch:
            logger.error("Repository or branch not initialized")
            return False
            
        try:
            remote = self.repo.remote(remote_name)
            remote.push(self.current_branch, set_upstream=True)
            logger.info(f"Pushed {self.current_branch} to {remote_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to push: {e}")
            return False
            
    def get_changed_files(self) -> List[str]:
        """
        Get list of changed files in current branch vs original.
        
        Returns:
            List of changed file paths
        """
        if not self.repo or not self.original_branch:
            return []
            
        try:
            diff = self.repo.head.commit.diff(self.original_branch)
            return [d.a_path for d in diff]
            
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            return []
            
    def get_file_diff(self, file_path: Path) -> str:
        """
        Get the diff for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Diff string
        """
        if not self.repo:
            return ""
            
        try:
            rel_path = file_path.relative_to(self.repo_path) if file_path.is_absolute() else file_path
            
            # Get diff against original branch
            diff = self.repo.git.diff(self.original_branch, str(rel_path))
            return diff
            
        except Exception as e:
            logger.error(f"Failed to get file diff: {e}")
            return ""
            
    def rollback(self) -> bool:
        """
        Rollback to original branch and delete the refactoring branch.
        
        Returns:
            True if successful
        """
        if not self.repo or not self.original_branch:
            return False
            
        try:
            # Checkout original branch
            self.repo.heads[self.original_branch].checkout()
            
            # Delete refactoring branch if it exists
            if self.current_branch and self.current_branch in [h.name for h in self.repo.heads]:
                self.repo.delete_head(self.current_branch, force=True)
                logger.info(f"Deleted branch: {self.current_branch}")
                
            self.current_branch = None
            logger.info(f"Rolled back to: {self.original_branch}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback: {e}")
            return False
            
    def get_remote_url(self, remote_name: str = 'origin') -> Optional[str]:
        """
        Get the remote URL for the repository.
        
        Args:
            remote_name: Name of the remote
            
        Returns:
            Remote URL or None
        """
        if not self.repo:
            return None
            
        try:
            remote = self.repo.remote(remote_name)
            urls = list(remote.urls)
            return urls[0] if urls else None
            
        except Exception as e:
            logger.error(f"Failed to get remote URL: {e}")
            return None
            
    def extract_repo_info(self) -> Dict[str, str]:
        """
        Extract repository owner and name from remote URL.
        
        Returns:
            Dictionary with 'owner' and 'repo' keys
        """
        url = self.get_remote_url()
        
        if not url:
            return {'owner': '', 'repo': ''}
            
        # Handle different URL formats
        # SSH: git@github.com:owner/repo.git
        # HTTPS: https://github.com/owner/repo.git
        
        if url.startswith('git@'):
            # SSH format
            parts = url.split(':')[-1].replace('.git', '').split('/')
        else:
            # HTTPS format
            parts = url.replace('.git', '').split('/')[-2:]
            
        if len(parts) >= 2:
            return {'owner': parts[-2], 'repo': parts[-1]}
            
        return {'owner': '', 'repo': ''}


if __name__ == "__main__":
    # Test Git operations
    import yaml
    
    with open("config/config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    git_ops = GitOperations(config)
    
    if git_ops.initialize():
        print(f"Current branch: {git_ops.original_branch}")
        print(f"Remote URL: {git_ops.get_remote_url()}")
        print(f"Repo info: {git_ops.extract_repo_info()}")
