"""
Design Smell Detection & Refactoring Pipeline - Main Orchestrator

This is the main entry point for the pipeline that:
1. Detects design smells using DesigniteJava and TypeMetrics
2. Refactors code using LLM (OpenAI/Gemini)
3. Creates Pull Requests with detailed descriptions

Usage:
    python main.py --config config/config.yaml
    python main.py --config config/config.yaml --dry-run
"""

import argparse
import logging
import sys
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('pipeline.log')
    ]
)
logger = logging.getLogger(__name__)

# Import pipeline modules
from detection import SmellParser, SmellReport
from refactoring import LLMClient, ContextManager, RefactoringPrompts, CodeValidator
from pr_generator import GitOperations, GitHubAPI, PRDescriptionGenerator, RefactoringResult


class RefactoringPipeline:
    """
    Main orchestrator for the design smell detection and refactoring pipeline.
    
    Pipeline Flow:
    1. Detection Phase - Run DesigniteJava and TypeMetrics
    2. Analysis Phase - Aggregate and prioritize smells
    3. Refactoring Phase - Apply LLM-based refactoring
    4. Validation Phase - Verify refactored code
    5. PR Phase - Create Pull Request with changes
    """
    
    def __init__(self, config_path: str, dry_run: bool = False):
        """
        Initialize the pipeline.
        
        Args:
            config_path: Path to configuration file
            dry_run: If True, don't create actual PR
        """
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        self.dry_run = dry_run
        self.start_time = None
        self.results: List[RefactoringResult] = []
        
        # Initialize components
        self.smell_parser = SmellParser(self.config)
        self.llm_client = None  # Lazy initialization
        self.context_manager = ContextManager(self.config)
        self.validator = CodeValidator(self.config)
        self.git_ops = None  # Lazy initialization
        self.github_api = None  # Lazy initialization
        self.pr_generator = PRDescriptionGenerator(self.config)
        
        # Source path
        self.source_path = Path(self.config.get('detection', {}).get('source_path', './app/src/main/java'))
        
    def run(self) -> bool:
        """
        Run the complete pipeline.
        
        Returns:
            True if successful
        """
        self.start_time = time.time()
        logger.info("=" * 60)
        logger.info("Starting Design Smell Detection & Refactoring Pipeline")
        logger.info("=" * 60)
        
        try:
            # Phase 1: Detection
            logger.info("\n📍 Phase 1: Detection")
            if not self._run_detection():
                logger.error("Detection phase failed")
                return False
                
            # Phase 2: Analysis
            logger.info("\n📍 Phase 2: Analysis")
            files_to_refactor = self._analyze_smells()
            if not files_to_refactor:
                logger.info("No files need refactoring")
                return True
                
            # Phase 3: Refactoring
            logger.info("\n📍 Phase 3: Refactoring")
            if not self._run_refactoring(files_to_refactor):
                logger.warning("Some refactoring operations failed")
                
            if not self.results:
                logger.info("No successful refactoring results")
                return True
                
            # Phase 4: Create PR
            logger.info("\n📍 Phase 4: Creating Pull Request")
            if not self.dry_run:
                pr_url = self._create_pull_request()
                if pr_url:
                    logger.info(f"✅ Pipeline completed! PR created: {pr_url}")
                else:
                    logger.error("Failed to create PR")
                    return False
            else:
                logger.info("Dry run - skipping PR creation")
                self._log_summary()
                
            return True
            
        except Exception as e:
            logger.exception(f"Pipeline failed with error: {e}")
            return False
            
        finally:
            execution_time = time.time() - self.start_time
            logger.info(f"\nTotal execution time: {execution_time:.2f} seconds")
            
    def _run_detection(self) -> bool:
        """Run the detection phase."""
        return self.smell_parser.run_detection()
        
    def _analyze_smells(self) -> List[SmellReport]:
        """Analyze and prioritize detected smells."""
        self.smell_parser.aggregate_smells()
        
        top_files = self.smell_parser.get_top_files_for_refactoring()
        
        logger.info(f"Found {len(top_files)} files to refactor:")
        for i, report in enumerate(top_files, 1):
            logger.info(
                f"  {i}. {report.class_name} (priority: {report.priority_score:.2f}, "
                f"smells: {report.total_smells})"
            )
            
        return top_files
        
    def _run_refactoring(self, files: List[SmellReport]) -> bool:
        """
        Run refactoring on the prioritized files.
        
        Args:
            files: List of SmellReports to refactor
            
        Returns:
            True if at least one file was successfully refactored
        """
        # Initialize LLM client
        if not self.llm_client:
            try:
                self.llm_client = LLMClient(self.config)
            except Exception as e:
                logger.error(f"Failed to initialize LLM client: {e}")
                return False
                
        success_count = 0
        
        for report in files:
            logger.info(f"\n  Refactoring: {report.class_name}")
            
            try:
                result = self._refactor_file(report)
                if result:
                    self.results.append(result)
                    success_count += 1
                    logger.info(f"  ✅ Successfully refactored {report.class_name}")
                else:
                    logger.warning(f"  ❌ Failed to refactor {report.class_name}")
                    
            except Exception as e:
                logger.error(f"  Error refactoring {report.class_name}: {e}")
                
        return success_count > 0
        
    def _refactor_file(self, report: SmellReport) -> Optional[RefactoringResult]:
        """
        Refactor a single file.
        
        Args:
            report: SmellReport for the file
            
        Returns:
            RefactoringResult or None if failed
        """
        # Find the actual file path
        file_path = self._find_file(report.file_path)
        if not file_path:
            logger.error(f"File not found: {report.file_path}")
            return None
            
        # Process file (chunk if needed)
        context = self.context_manager.process_file(file_path)
        
        # Prepare smell information
        smells = []
        for smell in report.design_smells:
            smells.append({'type': smell.smell_type, 'cause': smell.cause})
        for smell in report.implementation_smells:
            smells.append({'type': smell.smell_type, 'cause': smell.cause})
            
        # Refactor each chunk
        for chunk in context.chunks:
            smell_info = "\n".join([f"- {s['type']}: {s['cause']}" for s in smells])
            
            # Get refactoring prompt
            if len(smells) == 1:
                system_prompt, user_prompt = RefactoringPrompts.format_prompt(
                    smell_type=smells[0]['type'],
                    code=chunk.content,
                    cause=smells[0]['cause'],
                    loc=report.metrics.loc if report.metrics else 0,
                    cyclomatic_complexity=report.metrics.cyclomatic_complexity if report.metrics else 0,
                    methods_count=report.metrics.methods_count if report.metrics else 0
                )
            else:
                system_prompt, user_prompt = RefactoringPrompts.get_multi_smell_prompt(
                    smells, chunk.content
                )
                
            # Add context for large files
            if chunk.context_header:
                user_prompt = f"Context (imports and package):\n{chunk.context_header}\n\n{user_prompt}"
                
            # Call LLM
            refactored_code = self.llm_client.generate_with_retry(
                user_prompt,
                system_prompt
            )
            
            if not refactored_code:
                logger.warning(f"LLM returned no response for chunk {chunk.chunk_id}")
                return None
                
            # Extract Java code from response
            refactored_code = self._extract_java_code(refactored_code)
            
            # Validate syntax
            validation = self.validator.validate_syntax(refactored_code)
            if not validation.is_valid:
                logger.warning(f"Syntax validation failed: {validation.error_message}")
                # Try to fix with another LLM call
                refactored_code = self._retry_with_error(
                    chunk.content, refactored_code, validation.error_message, smell_info
                )
                if not refactored_code:
                    return None
                    
            chunk.refactored_content = refactored_code
            
        # Merge chunks
        final_code = self.context_manager.merge_refactored_chunks(context)
        
        # Full validation (compile + test)
        if not self.dry_run:
            validation = self.validator.full_validation(file_path, final_code)
            if not validation.is_valid:
                logger.warning(f"Full validation failed: {validation.error_message}")
                return None
                
        # Write changes
        if not self.dry_run:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(final_code)
                
        # Calculate new metrics
        from detection.typemetrics_runner import TypeMetricsRunner
        metrics_runner = TypeMetricsRunner(self.config)
        new_metrics = metrics_runner.analyze_file(file_path)
        
        return RefactoringResult(
            file_path=str(file_path),
            class_name=report.class_name,
            smells_fixed=[{'type': s['type'], 'cause': s['cause'], 'severity': 'medium'} for s in smells],
            original_metrics={
                'loc': report.metrics.loc if report.metrics else 0,
                'cyclomatic_complexity': report.metrics.cyclomatic_complexity if report.metrics else 0,
                'methods_count': report.metrics.methods_count if report.metrics else 0
            },
            new_metrics={
                'loc': new_metrics.loc if new_metrics else 0,
                'cyclomatic_complexity': new_metrics.cyclomatic_complexity if new_metrics else 0,
                'methods_count': new_metrics.methods_count if new_metrics else 0
            }
        )
        
    def _find_file(self, relative_path: str) -> Optional[Path]:
        """Find the actual file path from a relative path."""
        # Get repo root (parent of design_smell_pipeline)
        repo_root = Path(__file__).parent.parent
        
        # Possible source directories to search
        source_dirs = [
            repo_root / "app" / "src" / "main" / "java",
            repo_root / "src" / "main" / "java",
            repo_root / "src",
            repo_root,
            self.source_path,
        ]
        
        # Try each source directory
        for source_dir in source_dirs:
            if not source_dir.exists():
                continue
                
            # Try direct match with relative path
            full_path = source_dir / relative_path
            if full_path.exists():
                return full_path
                
        # If still not found, try to find by class name
        class_name = Path(relative_path).stem  # e.g., "ThemeMetadataParser"
        target_file = f"{class_name}.java"
        
        for source_dir in source_dirs:
            if not source_dir.exists():
                continue
            for java_file in source_dir.rglob(target_file):
                # Verify it matches the expected path pattern
                if relative_path.replace("/", str(java_file).replace("\\", "/")) or \
                   str(java_file).replace("\\", "/").endswith(relative_path):
                    return java_file
                # If class name matches, return it
                if java_file.name == target_file:
                    return java_file
                    
        logger.debug(f"File search failed for: {relative_path}")
        return None
        
    def _extract_java_code(self, response: str) -> str:
        """Extract Java code from LLM response."""
        # Look for code blocks
        import re
        
        # Try to find ```java ... ``` blocks
        pattern = r'```(?:java)?\n(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            # Return the largest code block
            return max(matches, key=len).strip()
            
        # If no code blocks, return the response as-is
        return response.strip()
        
    def _retry_with_error(
        self, 
        original_code: str, 
        failed_code: str, 
        error: str,
        smell_info: str
    ) -> Optional[str]:
        """Retry refactoring with error feedback."""
        prompt = f"""The previous refactoring attempt resulted in a syntax error.

ERROR: {error}

ORIGINAL CODE:
```java
{original_code}
```

FAILED REFACTORING:
```java
{failed_code}
```

Please fix the refactoring while still addressing these smells:
{smell_info}

Return only valid Java code.
"""
        
        response = self.llm_client.generate_with_retry(prompt)
        if response:
            code = self._extract_java_code(response)
            validation = self.validator.validate_syntax(code)
            if validation.is_valid:
                return code
                
        return None
        
    def _create_pull_request(self) -> Optional[str]:
        """Create a Pull Request with the changes."""
        # Initialize Git operations
        self.git_ops = GitOperations(self.config)
        if not self.git_ops.initialize():
            return None
            
        # Create branch
        branch_name = self.git_ops.create_refactoring_branch()
        if not branch_name:
            return None
            
        # Stage files
        file_paths = [Path(r.file_path) for r in self.results]
        if not self.git_ops.stage_files(file_paths):
            self.git_ops.rollback()
            return None
            
        # Commit
        commit_sha = self.git_ops.commit_changes()
        if not commit_sha:
            self.git_ops.rollback()
            return None
            
        # Push
        if not self.git_ops.push_branch():
            self.git_ops.rollback()
            return None
            
        # Create PR
        try:
            self.github_api = GitHubAPI(self.config)
            repo_info = self.git_ops.extract_repo_info()
            
            if not self.github_api.connect_to_repo(repo_info['owner'], repo_info['repo']):
                return None
                
            # Generate PR description
            execution_time = time.time() - self.start_time
            description = self.pr_generator.generate_full_description(
                self.results,
                validation_passed=True,
                execution_time=execution_time
            )
            
            # Create PR
            pr_info = self.github_api.create_pull_request(
                head_branch=branch_name,
                body=description
            )
            
            if pr_info:
                return pr_info['html_url']
                
        except Exception as e:
            logger.error(f"Failed to create PR: {e}")
            
        return None
        
    def _log_summary(self):
        """Log a summary in dry-run mode."""
        logger.info("\n" + "=" * 60)
        logger.info("DRY RUN SUMMARY")
        logger.info("=" * 60)
        
        for result in self.results:
            logger.info(f"\n📄 {result.class_name}")
            logger.info(f"   Smells fixed: {len(result.smells_fixed)}")
            for smell in result.smells_fixed:
                logger.info(f"     - {smell['type']}")
            logger.info(f"   Metrics change:")
            logger.info(f"     LOC: {result.original_metrics['loc']} → {result.new_metrics['loc']}")
            logger.info(f"     CC: {result.original_metrics['cyclomatic_complexity']} → {result.new_metrics['cyclomatic_complexity']}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Design Smell Detection & Refactoring Pipeline'
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config/config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Run without creating actual PR'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    pipeline = RefactoringPipeline(args.config, dry_run=args.dry_run)
    success = pipeline.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
