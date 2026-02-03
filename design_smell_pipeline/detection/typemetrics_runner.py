"""
TypeMetrics Runner - Extract code metrics for prioritization

This module handles:
1. Running code metrics analysis
2. Extracting LOC, Cyclomatic Complexity, Coupling, etc.
3. Providing metrics for smell prioritization
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import javalang

logger = logging.getLogger(__name__)


@dataclass
class ClassMetrics:
    """Metrics for a single class"""
    file_path: str
    package: str
    class_name: str
    loc: int = 0                  # Lines of Code
    methods_count: int = 0         # Number of methods
    fields_count: int = 0          # Number of fields
    cyclomatic_complexity: int = 0 # Total cyclomatic complexity
    avg_method_length: float = 0.0 # Average method length
    max_method_length: int = 0     # Maximum method length
    coupling: int = 0              # Coupling Between Objects (imports)
    depth_of_inheritance: int = 0  # Depth of Inheritance Tree
    public_methods: int = 0        # Number of public methods
    private_methods: int = 0       # Number of private methods


@dataclass
class MethodMetrics:
    """Metrics for a single method"""
    class_name: str
    method_name: str
    loc: int = 0
    parameters_count: int = 0
    cyclomatic_complexity: int = 0
    nested_depth: int = 0


class TypeMetricsRunner:
    """
    Extracts code metrics from Java source files for prioritization.
    
    Metrics collected:
    - Lines of Code (LOC)
    - Cyclomatic Complexity
    - Number of Methods/Fields
    - Coupling (import count)
    - Inheritance Depth
    """
    
    def __init__(self, config: Dict):
        """
        Initialize the TypeMetrics runner.
        
        Args:
            config: Configuration dictionary
        """
        self.source_path = Path(config.get('detection', {}).get('source_path', './app/src/main/java'))
        self.excluded_patterns = config.get('detection', {}).get('excluded_patterns', [])
        self.metrics_cache: Dict[str, ClassMetrics] = {}
        
    def analyze_file(self, file_path: Path) -> Optional[ClassMetrics]:
        """
        Analyze a single Java file and extract metrics.
        
        Args:
            file_path: Path to the Java file
            
        Returns:
            ClassMetrics object or None if parsing fails
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            # Parse the Java file
            tree = javalang.parse.parse(content)
            
            # Extract package name
            package = tree.package.name if tree.package else ""
            
            # Count lines
            lines = content.split('\n')
            loc = len([l for l in lines if l.strip() and not l.strip().startswith('//')])
            
            # Count imports (coupling indicator)
            coupling = len(tree.imports)
            
            # Analyze classes
            for path, node in tree.filter(javalang.tree.ClassDeclaration):
                metrics = ClassMetrics(
                    file_path=str(file_path),
                    package=package,
                    class_name=node.name,
                    loc=loc,
                    coupling=coupling
                )
                
                # Count methods
                methods = [m for m in node.body if isinstance(m, javalang.tree.MethodDeclaration)]
                metrics.methods_count = len(methods)
                
                # Count fields
                fields = [f for f in node.body if isinstance(f, javalang.tree.FieldDeclaration)]
                metrics.fields_count = len(fields)
                
                # Analyze methods
                method_lengths = []
                total_cc = 0
                
                for method in methods:
                    method_loc = self._estimate_method_loc(method)
                    method_lengths.append(method_loc)
                    total_cc += self._calculate_cyclomatic_complexity(method)
                    
                    # Count public/private
                    if 'public' in (method.modifiers or []):
                        metrics.public_methods += 1
                    elif 'private' in (method.modifiers or []):
                        metrics.private_methods += 1
                
                if method_lengths:
                    metrics.max_method_length = max(method_lengths)
                    metrics.avg_method_length = sum(method_lengths) / len(method_lengths)
                    
                metrics.cyclomatic_complexity = total_cc
                
                # Check inheritance
                if node.extends:
                    metrics.depth_of_inheritance = 1  # Simplified, actual depth requires full analysis
                    
                return metrics
                
        except javalang.parser.JavaSyntaxError as e:
            logger.warning(f"Syntax error parsing {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Error analyzing {file_path}: {e}")
            
        return None
    
    def _estimate_method_loc(self, method) -> int:
        """
        Estimate the lines of code in a method.
        
        Args:
            method: javalang MethodDeclaration node
            
        Returns:
            Estimated LOC
        """
        # Simple estimation based on node structure
        # In a real implementation, you'd use actual line numbers
        loc = 1  # Method signature
        
        if method.body:
            for statement in method.body:
                loc += self._count_statements(statement)
                
        return loc
    
    def _count_statements(self, node, depth=0) -> int:
        """
        Recursively count statements in a node.
        
        Args:
            node: javalang AST node
            depth: Current recursion depth
            
        Returns:
            Statement count
        """
        if depth > 10:  # Prevent infinite recursion
            return 1
            
        count = 1
        
        if hasattr(node, 'body') and node.body:
            if isinstance(node.body, list):
                for stmt in node.body:
                    count += self._count_statements(stmt, depth + 1)
            else:
                count += self._count_statements(node.body, depth + 1)
                
        if hasattr(node, 'then_statement') and node.then_statement:
            count += self._count_statements(node.then_statement, depth + 1)
            
        if hasattr(node, 'else_statement') and node.else_statement:
            count += self._count_statements(node.else_statement, depth + 1)
            
        return count
    
    def _calculate_cyclomatic_complexity(self, method) -> int:
        """
        Calculate cyclomatic complexity for a method.
        
        Counts: if, for, while, case, catch, &&, ||
        
        Args:
            method: javalang MethodDeclaration node
            
        Returns:
            Cyclomatic complexity value
        """
        cc = 1  # Base complexity
        
        if not method.body:
            return cc
            
        for path, node in method:
            if isinstance(node, (
                javalang.tree.IfStatement,
                javalang.tree.ForStatement,
                javalang.tree.WhileStatement,
                javalang.tree.DoStatement,
                javalang.tree.SwitchStatementCase,
                javalang.tree.CatchClause,
                javalang.tree.TernaryExpression
            )):
                cc += 1
            elif isinstance(node, javalang.tree.BinaryOperation):
                if node.operator in ('&&', '||'):
                    cc += 1
                    
        return cc
    
    def analyze_directory(self) -> Dict[str, ClassMetrics]:
        """
        Analyze all Java files in the source directory.
        
        Returns:
            Dictionary mapping file paths to ClassMetrics
        """
        logger.info(f"Analyzing Java files in {self.source_path}")
        results = {}
        
        for java_file in self.source_path.rglob("*.java"):
            # Check exclusion patterns
            if self._should_exclude(java_file):
                continue
                
            metrics = self.analyze_file(java_file)
            if metrics:
                results[str(java_file)] = metrics
                
        logger.info(f"Analyzed {len(results)} Java files")
        self.metrics_cache = results
        return results
    
    def _should_exclude(self, file_path: Path) -> bool:
        """
        Check if a file should be excluded based on patterns.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file should be excluded
        """
        path_str = str(file_path)
        
        for pattern in self.excluded_patterns:
            if pattern.strip('*').strip('/') in path_str:
                return True
                
        return False
    
    def get_metrics_for_file(self, file_path: str) -> Optional[ClassMetrics]:
        """
        Get metrics for a specific file.
        
        Args:
            file_path: Path to the file (can be partial path or class name)
            
        Returns:
            ClassMetrics or None
        """
        if not self.metrics_cache:
            self.analyze_directory()
            
        # Try exact match first
        if file_path in self.metrics_cache:
            return self.metrics_cache[file_path]
        
        # Normalize the file path for comparison
        normalized_path = file_path.replace('\\', '/').lower()
        
        # Try partial match
        for cached_path, metrics in self.metrics_cache.items():
            cached_normalized = cached_path.replace('\\', '/').lower()
            
            # Path contains match
            if normalized_path in cached_normalized or cached_normalized.endswith(normalized_path):
                return metrics
            
            # Match by class name
            class_name = metrics.class_name.lower()
            if class_name in normalized_path or normalized_path.endswith(class_name) or \
               normalized_path.endswith(class_name + '.java'):
                return metrics
                
            # Match by just the filename
            if normalized_path.endswith(f"/{class_name}.java") or \
               normalized_path == f"{class_name}.java" or \
               file_path.lower() == class_name:
                return metrics
                
        return None
    
    def get_priority_score(self, file_path: str) -> float:
        """
        Calculate a priority score for a file based on metrics.
        Higher score = higher priority for refactoring.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Priority score (0.0 to 1.0)
        """
        metrics = self.get_metrics_for_file(file_path)
        
        if not metrics:
            return 0.5  # Default medium priority
            
        score = 0.0
        
        # LOC factor (higher LOC = higher priority)
        if metrics.loc > 500:
            score += 0.3
        elif metrics.loc > 200:
            score += 0.15
            
        # Complexity factor
        if metrics.cyclomatic_complexity > 50:
            score += 0.3
        elif metrics.cyclomatic_complexity > 20:
            score += 0.15
            
        # Method length factor
        if metrics.max_method_length > 100:
            score += 0.2
        elif metrics.max_method_length > 50:
            score += 0.1
            
        # Coupling factor
        if metrics.coupling > 20:
            score += 0.2
        elif metrics.coupling > 10:
            score += 0.1
            
        return min(score, 1.0)


if __name__ == "__main__":
    # Test the runner
    import yaml
    
    with open("config/config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    runner = TypeMetricsRunner(config)
    metrics = runner.analyze_directory()
    
    # Print top 10 most complex files
    sorted_metrics = sorted(
        metrics.items(),
        key=lambda x: x[1].cyclomatic_complexity,
        reverse=True
    )[:10]
    
    print("\nTop 10 Most Complex Files:")
    for path, m in sorted_metrics:
        print(f"  {m.class_name}: CC={m.cyclomatic_complexity}, LOC={m.loc}")
