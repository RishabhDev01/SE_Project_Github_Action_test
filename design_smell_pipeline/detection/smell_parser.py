"""
Smell Parser - Aggregate and prioritize detected design smells

This module handles:
1. Parsing and aggregating smells from multiple sources
2. Calculating priority scores
3. Ranking files for refactoring
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from .designite_runner import DesigniteRunner, DesignSmell, ImplementationSmell
from .typemetrics_runner import TypeMetricsRunner, ClassMetrics

logger = logging.getLogger(__name__)


@dataclass
class SmellReport:
    """Aggregated smell report for a single file"""
    file_path: str
    package: str
    class_name: str
    design_smells: List[DesignSmell] = field(default_factory=list)
    implementation_smells: List[ImplementationSmell] = field(default_factory=list)
    metrics: Optional[ClassMetrics] = None
    priority_score: float = 0.0
    
    @property
    def total_smells(self) -> int:
        return len(self.design_smells) + len(self.implementation_smells)
    
    @property
    def high_severity_count(self) -> int:
        count = sum(1 for s in self.design_smells if s.severity == 'high')
        count += sum(1 for s in self.implementation_smells if s.severity == 'high')
        return count
    
    def get_smell_summary(self) -> str:
        """Get a summary of all smells for this file"""
        lines = []
        
        if self.design_smells:
            lines.append("Design Smells:")
            for smell in self.design_smells:
                lines.append(f"  - {smell.smell_type}: {smell.cause}")
                
        if self.implementation_smells:
            lines.append("Implementation Smells:")
            for smell in self.implementation_smells:
                lines.append(f"  - {smell.smell_type} in {smell.method_name}: {smell.cause}")
                
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        """Convert report to dictionary for serialization"""
        return {
            'file_path': self.file_path,
            'package': self.package,
            'class_name': self.class_name,
            'total_smells': self.total_smells,
            'high_severity_count': self.high_severity_count,
            'priority_score': self.priority_score,
            'design_smells': [
                {'type': s.smell_type, 'cause': s.cause, 'severity': s.severity}
                for s in self.design_smells
            ],
            'implementation_smells': [
                {'type': s.smell_type, 'method': s.method_name, 'cause': s.cause, 'severity': s.severity}
                for s in self.implementation_smells
            ],
            'metrics': {
                'loc': self.metrics.loc if self.metrics else 0,
                'cyclomatic_complexity': self.metrics.cyclomatic_complexity if self.metrics else 0,
                'methods_count': self.metrics.methods_count if self.metrics else 0,
                'coupling': self.metrics.coupling if self.metrics else 0,
            }
        }


class SmellParser:
    """
    Parser that aggregates smells from DesigniteJava and TypeMetrics,
    calculates priority scores, and ranks files for refactoring.
    """
    
    # Weight factors for priority calculation
    PRIORITY_WEIGHTS = {
        'high_severity_smell': 0.4,
        'medium_severity_smell': 0.2,
        'low_severity_smell': 0.1,
        'complexity_factor': 0.2,
        'loc_factor': 0.1,
    }
    
    # Smell type priorities (higher = more important)
    SMELL_PRIORITIES = {
        "God Class": 10,
        "Blob Class": 10,
        "Long Method": 9,
        "Complex Method": 9,
        "Feature Envy": 8,
        "Data Class": 7,
        "Long Parameter List": 6,
        "Duplicate Abstraction": 5,
        "Magic Number": 3,
        "Empty Catch Clause": 2,
    }
    
    def __init__(self, config: Dict):
        """
        Initialize the SmellParser.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.designite_runner = DesigniteRunner(config)
        self.typemetrics_runner = TypeMetricsRunner(config)
        self.reports: Dict[str, SmellReport] = {}
        
        # Get priority smell types from config
        self.priority_smells = config.get('refactoring', {}).get('priority_smells', [])
        self.min_severity = config.get('refactoring', {}).get('min_severity', 'low')
        self.max_files = config.get('refactoring', {}).get('max_files_per_run', 5)
        
    def run_detection(self) -> bool:
        """
        Run the full detection pipeline.
        
        Returns:
            True if detection completed successfully
        """
        logger.info("Starting design smell detection...")
        
        # Run DesigniteJava
        if not self.designite_runner.run_analysis():
            logger.warning("DesigniteJava analysis failed, continuing with metrics only")
            
        # Run TypeMetrics
        self.typemetrics_runner.analyze_directory()
        
        logger.info("Detection completed")
        return True
    
    def aggregate_smells(self) -> Dict[str, SmellReport]:
        """
        Aggregate all detected smells into SmellReports.
        
        Returns:
            Dictionary mapping file paths to SmellReports
        """
        logger.info("Aggregating smells...")
        
        # Get smells by file from DesigniteJava
        smells_by_file = self.designite_runner.get_smells_by_file()
        
        # Create reports
        reports = {}
        
        for file_path, smells in smells_by_file.items():
            # Separate design and implementation smells
            design_smells = [s for s in smells if isinstance(s, DesignSmell)]
            impl_smells = [s for s in smells if isinstance(s, ImplementationSmell)]
            
            # Get metrics for this file
            metrics = self.typemetrics_runner.get_metrics_for_file(file_path)
            
            # Create report
            report = SmellReport(
                file_path=file_path,
                package=design_smells[0].package if design_smells else 
                        (impl_smells[0].package if impl_smells else ""),
                class_name=design_smells[0].type_name if design_smells else 
                          (impl_smells[0].type_name if impl_smells else ""),
                design_smells=design_smells,
                implementation_smells=impl_smells,
                metrics=metrics
            )
            
            # Calculate priority
            report.priority_score = self._calculate_priority(report)
            reports[file_path] = report
            
        self.reports = reports
        logger.info(f"Aggregated {len(reports)} smell reports")
        
        return reports
    
    def _calculate_priority(self, report: SmellReport) -> float:
        """
        Calculate priority score for a smell report.
        
        Factors:
        - Number and severity of smells
        - Type of smells (God Class > Magic Number)
        - Code metrics (complexity, LOC)
        - Configuration priorities
        
        Args:
            report: SmellReport to score
            
        Returns:
            Priority score (0.0 to 1.0)
        """
        score = 0.0
        max_score = 0.0
        
        # Smell severity scores
        for smell in report.design_smells:
            smell_priority = self.SMELL_PRIORITIES.get(smell.smell_type, 5) / 10.0
            
            if smell.severity == 'high':
                score += smell_priority * self.PRIORITY_WEIGHTS['high_severity_smell']
                max_score += self.PRIORITY_WEIGHTS['high_severity_smell']
            elif smell.severity == 'medium':
                score += smell_priority * self.PRIORITY_WEIGHTS['medium_severity_smell']
                max_score += self.PRIORITY_WEIGHTS['medium_severity_smell']
            else:
                score += smell_priority * self.PRIORITY_WEIGHTS['low_severity_smell']
                max_score += self.PRIORITY_WEIGHTS['low_severity_smell']
                
            # Bonus for priority smells from config
            if smell.smell_type in self.priority_smells:
                score += 0.2
                
        for smell in report.implementation_smells:
            smell_priority = self.SMELL_PRIORITIES.get(smell.smell_type, 5) / 10.0
            
            if smell.severity == 'high':
                score += smell_priority * self.PRIORITY_WEIGHTS['high_severity_smell']
                max_score += self.PRIORITY_WEIGHTS['high_severity_smell']
            elif smell.severity == 'medium':
                score += smell_priority * self.PRIORITY_WEIGHTS['medium_severity_smell']
                max_score += self.PRIORITY_WEIGHTS['medium_severity_smell']
            else:
                score += smell_priority * self.PRIORITY_WEIGHTS['low_severity_smell']
                max_score += self.PRIORITY_WEIGHTS['low_severity_smell']
        
        # Metrics factor
        if report.metrics:
            metrics_score = self.typemetrics_runner.get_priority_score(report.file_path)
            score += metrics_score * self.PRIORITY_WEIGHTS['complexity_factor']
            max_score += self.PRIORITY_WEIGHTS['complexity_factor']
            
        # Normalize to 0-1 range
        if max_score > 0:
            normalized = min(score / max_score, 1.0)
        else:
            normalized = 0.0
            
        return round(normalized, 3)
    
    def get_prioritized_reports(self) -> List[SmellReport]:
        """
        Get smell reports sorted by priority (highest first).
        
        Returns:
            List of SmellReports sorted by priority
        """
        if not self.reports:
            self.aggregate_smells()
            
        # Filter by minimum severity
        severity_levels = {'low': 0, 'medium': 1, 'high': 2}
        min_sev = severity_levels.get(self.min_severity, 0)
        
        filtered = []
        for report in self.reports.values():
            # Include if any smell meets minimum severity
            has_qualifying_smell = any(
                severity_levels.get(s.severity, 0) >= min_sev 
                for s in report.design_smells
            ) or any(
                severity_levels.get(s.severity, 0) >= min_sev 
                for s in report.implementation_smells
            )
            
            if has_qualifying_smell:
                filtered.append(report)
        
        # Sort by priority (descending)
        return sorted(filtered, key=lambda r: r.priority_score, reverse=True)
    
    def get_top_files_for_refactoring(self) -> List[SmellReport]:
        """
        Get the top N files that should be refactored.
        
        Returns:
            List of top priority SmellReports
        """
        prioritized = self.get_prioritized_reports()
        return prioritized[:self.max_files]
    
    def generate_summary_report(self) -> str:
        """
        Generate a human-readable summary of all detected smells.
        
        Returns:
            Markdown-formatted summary
        """
        if not self.reports:
            self.aggregate_smells()
            
        lines = [
            "# Design Smell Detection Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            f"- Total files analyzed: {len(self.reports)}",
            f"- Files with smells: {sum(1 for r in self.reports.values() if r.total_smells > 0)}",
            f"- Total design smells: {sum(len(r.design_smells) for r in self.reports.values())}",
            f"- Total implementation smells: {sum(len(r.implementation_smells) for r in self.reports.values())}",
            "",
            "## Top Priority Files",
        ]
        
        for i, report in enumerate(self.get_top_files_for_refactoring(), 1):
            lines.append(f"\n### {i}. {report.class_name}")
            lines.append(f"- **File**: `{report.file_path}`")
            lines.append(f"- **Priority Score**: {report.priority_score}")
            lines.append(f"- **Total Smells**: {report.total_smells}")
            
            if report.metrics:
                lines.append(f"- **Metrics**: LOC={report.metrics.loc}, CC={report.metrics.cyclomatic_complexity}")
                
            lines.append(f"\n{report.get_smell_summary()}")
            
        return "\n".join(lines)


if __name__ == "__main__":
    # Test the parser
    import yaml
    
    with open("config/config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    parser = SmellParser(config)
    parser.run_detection()
    
    print(parser.generate_summary_report())
