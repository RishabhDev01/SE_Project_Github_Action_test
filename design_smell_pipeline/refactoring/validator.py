"""
Code Validator - Validate refactored code before applying changes

This module handles:
1. Syntax validation using Java parsers
2. Compilation checking with Maven
3. Test execution for affected code
4. Rollback on validation failure
"""

import subprocess
import logging
import os
import tempfile
import shutil
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

try:
    import javalang
except ImportError:
    javalang = None

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of code validation"""
    is_valid: bool
    syntax_valid: bool = True
    compiles: bool = True
    tests_pass: bool = True
    error_message: str = ""
    details: Dict = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


class CodeValidator:
    """
    Validates refactored Java code before applying changes.
    
    Validation steps:
    1. Syntax validation (fast, catch obvious errors)
    2. Compilation check (catch type errors)
    3. Test execution (catch behavioral changes)
    """
    
    def __init__(self, config: Dict):
        """
        Initialize the validator.
        
        Args:
            config: Pipeline configuration
        """
        validation_config = config.get('validation', {})
        self.run_compile = validation_config.get('run_compile', True)
        self.run_tests = validation_config.get('run_tests', True)
        self.compile_command = validation_config.get('compile_command', 'mvn compile -q')
        self.test_command = validation_config.get('test_command', 'mvn test -q')
        
        # Determine project root - check for CI environment first
        github_workspace = os.environ.get('GITHUB_WORKSPACE')
        if github_workspace:
            self.project_root = Path(github_workspace)
        else:
            # Try to find project root by looking for .git directory or pom.xml
            source_path = Path(config.get('detection', {}).get('source_path', '.')).resolve()
            project_root = source_path
            for _ in range(10):  # Limit traversal depth
                if (project_root / '.git').exists() or (project_root / 'pom.xml').exists():
                    break
                if project_root.parent == project_root:  # Reached filesystem root
                    break
                project_root = project_root.parent
            self.project_root = project_root
        
    def validate_syntax(self, code: str) -> ValidationResult:
        """
        Validate Java syntax using javalang parser.
        
        Args:
            code: Java code to validate
            
        Returns:
            ValidationResult
        """
        if not javalang:
            logger.warning("javalang not available, skipping syntax validation")
            return ValidationResult(is_valid=True, syntax_valid=True)
            
        try:
            javalang.parse.parse(code)
            return ValidationResult(is_valid=True, syntax_valid=True)
            
        except javalang.parser.JavaSyntaxError as e:
            return ValidationResult(
                is_valid=False,
                syntax_valid=False,
                error_message=f"Syntax error: {str(e)}",
                details={'line': getattr(e, 'at', None)}
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                syntax_valid=False,
                error_message=f"Parse error: {str(e)}"
            )
            
    def validate_compilation(self, file_path: Path, new_code: str) -> ValidationResult:
        """
        Validate code compiles with Maven.
        
        Creates a temporary copy with the new code and runs compilation.
        
        Args:
            file_path: Path to the original file
            new_code: New code to validate
            
        Returns:
            ValidationResult
        """
        if not self.run_compile:
            return ValidationResult(is_valid=True, compiles=True)
        
        # Ensure file_path is absolute
        if not file_path.is_absolute():
            file_path = self.project_root / file_path
        file_path = file_path.resolve()
        
        # Store original content
        original_content = None
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
                
        try:
            # Write new code temporarily
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_code)
                
            # Run compilation
            result = subprocess.run(
                self.compile_command.split(),
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return ValidationResult(is_valid=True, compiles=True)
            else:
                # Extract error details
                error_details = self._parse_compile_errors(result.stderr + result.stdout)
                return ValidationResult(
                    is_valid=False,
                    compiles=False,
                    error_message=f"Compilation failed: {error_details.get('summary', 'Unknown error')}",
                    details=error_details
                )
                
        except subprocess.TimeoutExpired:
            return ValidationResult(
                is_valid=False,
                compiles=False,
                error_message="Compilation timed out after 5 minutes"
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                compiles=False,
                error_message=f"Compilation error: {str(e)}"
            )
        finally:
            # Restore original content
            if original_content is not None:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                    
    def validate_tests(self, file_path: Path, new_code: str) -> ValidationResult:
        """
        Run tests to ensure functionality is preserved.
        
        Args:
            file_path: Path to the modified file
            new_code: New code to validate
            
        Returns:
            ValidationResult
        """
        if not self.run_tests:
            return ValidationResult(is_valid=True, tests_pass=True)
        
        # Ensure file_path is absolute
        if not file_path.is_absolute():
            file_path = self.project_root / file_path
        file_path = file_path.resolve()
        
        # Store original content
        original_content = None
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
                
        try:
            # Write new code temporarily
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_code)
                
            # Find related test classes
            test_classes = self._find_related_tests(file_path)
            
            if test_classes:
                # Run specific tests
                test_pattern = ",".join(test_classes)
                cmd = f"{self.test_command} -Dtest={test_pattern}"
            else:
                # Run all tests (slower but safer)
                cmd = self.test_command
                
            result = subprocess.run(
                cmd.split(),
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                return ValidationResult(is_valid=True, tests_pass=True)
            else:
                error_details = self._parse_test_failures(result.stdout + result.stderr)
                return ValidationResult(
                    is_valid=False,
                    tests_pass=False,
                    error_message=f"Tests failed: {error_details.get('summary', 'Unknown failure')}",
                    details=error_details
                )
                
        except subprocess.TimeoutExpired:
            return ValidationResult(
                is_valid=False,
                tests_pass=False,
                error_message="Tests timed out after 10 minutes"
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                tests_pass=False,
                error_message=f"Test error: {str(e)}"
            )
        finally:
            # Restore original content
            if original_content is not None:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                    
    def _find_related_tests(self, file_path: Path) -> List[str]:
        """
        Find test classes related to a source file.
        
        Args:
            file_path: Path to the source file
            
        Returns:
            List of test class names
        """
        # Extract class name from file
        class_name = file_path.stem
        
        # Look for test files
        test_dir = self.project_root / "app" / "src" / "test" / "java"
        if not test_dir.exists():
            return []
            
        # Common test naming conventions
        test_patterns = [
            f"{class_name}Test.java",
            f"{class_name}Tests.java",
            f"Test{class_name}.java",
        ]
        
        test_classes = []
        for pattern in test_patterns:
            matches = list(test_dir.rglob(pattern))
            for match in matches:
                test_classes.append(match.stem)
                
        return test_classes
        
    def _parse_compile_errors(self, output: str) -> Dict:
        """
        Parse Maven compilation errors.
        
        Args:
            output: Compiler output
            
        Returns:
            Dictionary with error details
        """
        details = {'errors': [], 'summary': ''}
        
        # Look for error patterns
        error_pattern = r'\[ERROR\].*?:\[(\d+),(\d+)\] (.+)'
        matches = re.findall(error_pattern, output)
        
        for match in matches:
            line, col, message = match
            details['errors'].append({
                'line': int(line),
                'column': int(col),
                'message': message
            })
            
        if details['errors']:
            details['summary'] = details['errors'][0]['message']
        else:
            # Try to extract any error message
            error_lines = [l for l in output.split('\n') if 'error' in l.lower()]
            if error_lines:
                details['summary'] = error_lines[0][:200]
                
        return details
        
    def _parse_test_failures(self, output: str) -> Dict:
        """
        Parse Maven test failures.
        
        Args:
            output: Test output
            
        Returns:
            Dictionary with failure details
        """
        details = {'failures': [], 'summary': ''}
        
        # Look for failure patterns
        failure_pattern = r'(\w+)\((\w+)\).*?(?:FAILURE|ERROR)'
        matches = re.findall(failure_pattern, output)
        
        for match in matches:
            method, test_class = match
            details['failures'].append({
                'test_class': test_class,
                'method': method
            })
            
        if details['failures']:
            f = details['failures'][0]
            details['summary'] = f"{f['test_class']}.{f['method']} failed"
        else:
            # Try to extract summary
            summary_pattern = r'Tests run: (\d+), Failures: (\d+), Errors: (\d+)'
            match = re.search(summary_pattern, output)
            if match:
                total, failures, errors = match.groups()
                details['summary'] = f"{failures} failures, {errors} errors out of {total} tests"
                
        return details
        
    def full_validation(
        self, 
        file_path: Path, 
        new_code: str,
        quick_only: bool = False
    ) -> ValidationResult:
        """
        Run full validation pipeline.
        
        Args:
            file_path: Path to the file being modified
            new_code: New code to validate
            quick_only: If True, only do syntax validation
            
        Returns:
            ValidationResult
        """
        # Step 1: Syntax validation (always run)
        logger.info(f"Validating syntax for {file_path.name}")
        syntax_result = self.validate_syntax(new_code)
        if not syntax_result.is_valid:
            logger.warning(f"Syntax validation failed: {syntax_result.error_message}")
            return syntax_result
            
        if quick_only:
            return syntax_result
            
        # Step 2: Compilation check
        if self.run_compile:
            logger.info(f"Validating compilation for {file_path.name}")
            compile_result = self.validate_compilation(file_path, new_code)
            if not compile_result.is_valid:
                logger.warning(f"Compilation failed: {compile_result.error_message}")
                return compile_result
                
        # Step 3: Test execution
        if self.run_tests:
            logger.info(f"Running tests for {file_path.name}")
            test_result = self.validate_tests(file_path, new_code)
            if not test_result.is_valid:
                logger.warning(f"Tests failed: {test_result.error_message}")
                return test_result
                
        logger.info(f"All validation passed for {file_path.name}")
        return ValidationResult(
            is_valid=True,
            syntax_valid=True,
            compiles=True,
            tests_pass=True
        )
        
    def validate_multiple_files(
        self, 
        files: Dict[Path, str]
    ) -> Tuple[bool, Dict[Path, ValidationResult]]:
        """
        Validate multiple files together.
        
        Args:
            files: Dictionary mapping file paths to new code
            
        Returns:
            Tuple of (all_valid, results_by_file)
        """
        results = {}
        all_valid = True
        
        # First, validate all syntax (fast)
        for file_path, new_code in files.items():
            result = self.validate_syntax(new_code)
            if not result.is_valid:
                results[file_path] = result
                all_valid = False
            else:
                results[file_path] = result
                
        if not all_valid:
            return (False, results)
            
        # Then, do full validation
        for file_path, new_code in files.items():
            result = self.full_validation(file_path, new_code)
            results[file_path] = result
            if not result.is_valid:
                all_valid = False
                
        return (all_valid, results)


if __name__ == "__main__":
    # Test the validator
    import yaml
    
    with open("config/config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    validator = CodeValidator(config)
    
    # Test syntax validation
    valid_code = """
    package com.example;
    
    public class Test {
        public void hello() {
            System.out.println("Hello");
        }
    }
    """
    
    result = validator.validate_syntax(valid_code)
    print(f"Valid code result: {result.is_valid}")
    
    invalid_code = """
    package com.example;
    
    public class Test {
        public void hello() {
            System.out.println("Hello"  // Missing closing bracket
        }
    }
    """
    
    result = validator.validate_syntax(invalid_code)
    print(f"Invalid code result: {result.is_valid}")
    print(f"Error: {result.error_message}")
