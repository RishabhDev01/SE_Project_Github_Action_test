"""
DesigniteJava Runner - Integration with DesigniteJava for design smell detection

This module handles:
1. Running DesigniteJava on the source code
2. Parsing the output CSV files
3. Extracting design and implementation smells
"""

import subprocess
import os
import csv
import logging
import requests
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DesignSmell:
    """Represents a detected design smell"""
    project: str
    package: str
    type_name: str
    smell_type: str
    cause: str
    file_path: Optional[str] = None
    severity: str = "medium"
    

@dataclass
class ImplementationSmell:
    """Represents a detected implementation smell"""
    project: str
    package: str
    type_name: str
    method_name: str
    smell_type: str
    cause: str
    file_path: Optional[str] = None
    severity: str = "medium"


class DesigniteRunner:
    """
    Runner for DesigniteJava - a design quality assessment tool for Java projects.
    
    DesigniteJava detects:
    - Design Smells: God Class, Feature Envy, Data Class, etc.
    - Implementation Smells: Long Method, Complex Conditional, etc.
    - Architecture Smells: Cyclic Dependencies, etc.
    """
    
    # Mapping of smell types to severity levels
    SMELL_SEVERITY = {
        # High severity - significant design issues
        "God Class": "high",
        "Blob Class": "high",
        "Complex Method": "high",
        "Long Method": "high",
        
        # Medium severity - notable issues
        "Feature Envy": "medium",
        "Data Class": "medium",
        "Long Parameter List": "medium",
        "Duplicate Abstraction": "medium",
        
        # Lower severity - minor issues
        "Magic Number": "low",
        "Empty Catch Clause": "low",
        "Missing Default": "low",
    }
    
    def __init__(self, config: Dict):
        """
        Initialize the DesigniteJava runner.
        
        Args:
            config: Configuration dictionary containing paths and settings
        """
        # Determine project root
        github_workspace = os.environ.get('GITHUB_WORKSPACE')
        if github_workspace:
            project_root = Path(github_workspace)
        else:
            # Find project root by traversing up from this file
            project_root = Path(__file__).parent.parent.parent
            
        # Resolve all paths to absolute
        jar_path = config.get('detection', {}).get('designite', {}).get('jar_path', './tools/DesigniteJava.jar')
        source_path = config.get('detection', {}).get('source_path', './app/src/main/java')
        output_path = config.get('detection', {}).get('output_path', './output/smells')
        
        self.jar_path = (project_root / jar_path).resolve()
        self.source_path = (project_root / source_path).resolve()
        self.output_path = (project_root / output_path).resolve()
        self.excluded_patterns = config.get('detection', {}).get('excluded_patterns', [])
        
    def ensure_designite_available(self) -> bool:
        """
        Ensure DesigniteJava JAR is available, download if necessary.
        
        Returns:
            True if JAR is available, False otherwise
        """
        if self.jar_path.exists():
            logger.info(f"DesigniteJava found at {self.jar_path}")
            return True
            
        logger.warning(f"DesigniteJava not found at {self.jar_path}")
        
        # Create tools directory
        self.jar_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Note: DesigniteJava requires a license for full features
        # For CI/CD, you may need to purchase or use the trial version
        logger.info("Please download DesigniteJava manually from https://www.designite-tools.com/designitejava/")
        logger.info(f"Place the JAR file at: {self.jar_path}")
        
        return False
    
    def run_analysis(self, output_suffix: str = "") -> bool:
        """
        Run DesigniteJava analysis on the source code.
        
        Args:
            output_suffix: Optional suffix for output directory (e.g., '_after' for post-refactoring)
        
        Returns:
            True if analysis completed successfully, False otherwise
        """
        if not self.ensure_designite_available():
            logger.error("DesigniteJava is not available")
            return False
        
        # Use custom output path if suffix provided
        output_path = self.output_path
        if output_suffix:
            output_path = Path(str(self.output_path) + output_suffix)
            
        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Build the command
        cmd = [
            "java", "-jar", str(self.jar_path),
            "-i", str(self.source_path),
            "-o", str(output_path)
        ]
        
        logger.info(f"Running DesigniteJava: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "No error output"
                logger.error(f"DesigniteJava failed (exit code {result.returncode}): {error_msg}")
                return False
                
            logger.info(f"DesigniteJava analysis completed successfully (output: {output_path})")
            
            # Update output path for parsing if suffix was used
            if output_suffix:
                self._current_output_path = output_path
            else:
                self._current_output_path = self.output_path
                
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("DesigniteJava timed out after 10 minutes")
            return False
        except FileNotFoundError:
            logger.error("Java not found. Please ensure Java is installed and in PATH")
            return False
        except Exception as e:
            logger.error(f"Error running DesigniteJava: {e}")
            return False
    
    def parse_design_smells(self) -> List[DesignSmell]:
        """
        Parse the designCodeSmells.csv output file.
        
        Returns:
            List of DesignSmell objects
        """
        # DesigniteJava uses 'designCodeSmells.csv' not 'DesignSmells.csv'
        current_path = getattr(self, '_current_output_path', self.output_path)
        csv_path = current_path / "designCodeSmells.csv"
        smells = []
        
        if not csv_path.exists():
            logger.warning(f"Design smells file not found: {csv_path}")
            return smells
            
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # DesigniteJava column names may vary
                    smell = DesignSmell(
                        project=row.get('Project Name', row.get('project_name', '')),
                        package=row.get('Package Name', row.get('package_name', '')),
                        type_name=row.get('Type Name', row.get('type_name', '')),
                        smell_type=row.get('Code Smell', row.get('Design Smell', '')),
                        cause=row.get('Cause', row.get('Cause of the Smell', '')),
                        severity=self.SMELL_SEVERITY.get(row.get('Code Smell', row.get('Design Smell', '')), 'medium')
                    )
                    
                    # Construct file path from package and type
                    smell.file_path = self._construct_file_path(smell.package, smell.type_name)
                    smells.append(smell)
                    
            logger.info(f"Parsed {len(smells)} design smells")
            
        except Exception as e:
            logger.error(f"Error parsing design smells: {e}")
            
        return smells
    
    def parse_implementation_smells(self) -> List[ImplementationSmell]:
        """
        Parse the implementationCodeSmells.csv output file.
        
        Returns:
            List of ImplementationSmell objects
        """
        # DesigniteJava uses 'implementationCodeSmells.csv' not 'ImplementationSmells.csv'
        current_path = getattr(self, '_current_output_path', self.output_path)
        csv_path = current_path / "implementationCodeSmells.csv"
        smells = []
        
        if not csv_path.exists():
            logger.warning(f"Implementation smells file not found: {csv_path}")
            return smells
            
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # DesigniteJava column names may vary
                    smell = ImplementationSmell(
                        project=row.get('Project Name', row.get('project_name', '')),
                        package=row.get('Package Name', row.get('package_name', '')),
                        type_name=row.get('Type Name', row.get('type_name', '')),
                        method_name=row.get('Method Name', row.get('method_name', '')),
                        smell_type=row.get('Code Smell', row.get('Implementation Smell', '')),
                        cause=row.get('Cause', row.get('Cause of the Smell', '')),
                        severity=self.SMELL_SEVERITY.get(row.get('Code Smell', row.get('Implementation Smell', '')), 'medium')
                    )
                    
                    smell.file_path = self._construct_file_path(smell.package, smell.type_name)
                    smells.append(smell)
                    
            logger.info(f"Parsed {len(smells)} implementation smells")
            
        except Exception as e:
            logger.error(f"Error parsing implementation smells: {e}")
            
        return smells
    
    def _construct_file_path(self, package: str, type_name: str) -> str:
        """
        Construct the file path from package and type name.
        
        Args:
            package: Java package name (e.g., 'org.apache.roller.weblogger')
            type_name: Class name (e.g., 'UserManager')
            
        Returns:
            Relative file path (e.g., 'org/apache/roller/weblogger/UserManager.java')
        """
        package_path = package.replace('.', '/')
        return f"{package_path}/{type_name}.java"
    
    def parse_type_metrics(self) -> Dict[str, Dict]:
        """
        Parse the TypeMetrics.csv output file from DesigniteJava.
        
        Returns:
            Dictionary mapping class names to their metrics
        """
        current_path = getattr(self, '_current_output_path', self.output_path)
        csv_path = current_path / "TypeMetrics.csv"
        metrics = {}
        
        if not csv_path.exists():
            logger.warning(f"Type metrics file not found: {csv_path}")
            return metrics
            
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    class_name = row.get('Type Name', row.get('type_name', ''))
                    if class_name:
                        metrics[class_name] = {
                            'loc': int(row.get('LOC', row.get('loc', 0)) or 0),
                            'cyclomatic_complexity': int(row.get('WMC', row.get('wmc', 0)) or 0),  # Weighted Methods per Class
                            'methods_count': int(row.get('NOM', row.get('nom', 0)) or 0),  # Number of Methods
                            'fields_count': int(row.get('NOF', row.get('nof', 0)) or 0),  # Number of Fields
                            'coupling': int(row.get('CBO', row.get('cbo', 0)) or 0),  # Coupling Between Objects
                            'depth_inheritance': int(row.get('DIT', row.get('dit', 0)) or 0),  # Depth of Inheritance Tree
                            'package': row.get('Package Name', row.get('package_name', ''))
                        }
                        
            logger.info(f"Parsed metrics for {len(metrics)} classes")
            
        except Exception as e:
            logger.error(f"Error parsing type metrics: {e}")
            
        return metrics
    
    def get_metrics_for_class(self, class_name: str) -> Optional[Dict]:
        """
        Get DesigniteJava metrics for a specific class.
        
        Args:
            class_name: Name of the class
            
        Returns:
            Dictionary of metrics or None
        """
        all_metrics = self.parse_type_metrics()
        
        # Try exact match first
        if class_name in all_metrics:
            return all_metrics[class_name]
            
        # Try case-insensitive match
        for name, metrics in all_metrics.items():
            if name.lower() == class_name.lower():
                return metrics
                
        return None
    
    def get_all_smells(self) -> Dict:
        """
        Get all detected smells (design + implementation).
        
        Returns:
            Dictionary containing both design and implementation smells
        """
        return {
            'design_smells': self.parse_design_smells(),
            'implementation_smells': self.parse_implementation_smells()
        }
    
    def get_smells_by_file(self) -> Dict[str, List]:
        """
        Group all smells by file path for easier processing.
        
        Returns:
            Dictionary mapping file paths to lists of smells
        """
        all_smells = self.get_all_smells()
        smells_by_file = {}
        
        for smell in all_smells['design_smells']:
            if smell.file_path:
                if smell.file_path not in smells_by_file:
                    smells_by_file[smell.file_path] = []
                smells_by_file[smell.file_path].append(smell)
                
        for smell in all_smells['implementation_smells']:
            if smell.file_path:
                if smell.file_path not in smells_by_file:
                    smells_by_file[smell.file_path] = []
                smells_by_file[smell.file_path].append(smell)
                
        return smells_by_file
    
    def get_smell_count_for_class(self, class_name: str) -> int:
        """
        Get the total smell count for a specific class.
        
        Args:
            class_name: Name of the class to check
            
        Returns:
            Number of smells detected for this class
        """
        all_smells = self.get_all_smells()
        count = 0
        
        for smell in all_smells['design_smells']:
            if smell.type_name.lower() == class_name.lower():
                count += 1
                
        for smell in all_smells['implementation_smells']:
            if smell.type_name.lower() == class_name.lower():
                count += 1
                
        return count
    
    def run_and_get_smell_count(self, class_name: str) -> Optional[int]:
        """
        Run DesigniteJava analysis and return smell count for a specific class.
        This is used for post-refactoring validation.
        
        Args:
            class_name: Name of the class to check
            
        Returns:
            Number of smells detected, or None if analysis failed
        """
        if not self.run_analysis():
            logger.warning("DesigniteJava analysis failed, skipping smell count validation")
            return None
            
        return self.get_smell_count_for_class(class_name)


if __name__ == "__main__":
    # Test the runner
    import yaml
    
    with open("config/config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    runner = DesigniteRunner(config)
    
    if runner.run_analysis():
        smells = runner.get_smells_by_file()
        for file_path, file_smells in smells.items():
            print(f"\n{file_path}:")
            for smell in file_smells:
                print(f"  - {smell.smell_type}: {smell.cause}")
