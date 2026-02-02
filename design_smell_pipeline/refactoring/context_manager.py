"""
Context Manager - Handle large files with intelligent chunking

This module handles:
1. AST-based chunking of large Java files
2. Context window management
3. Chunk merging after refactoring
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    import javalang
except ImportError:
    javalang = None

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """Represents a chunk of code for LLM processing"""
    chunk_id: int
    content: str
    start_line: int
    end_line: int
    chunk_type: str  # 'class', 'method', 'full_file'
    class_name: Optional[str] = None
    method_name: Optional[str] = None
    context_header: str = ""  # Imports, package declaration
    original_content: str = ""
    refactored_content: Optional[str] = None


@dataclass
class FileContext:
    """Complete context for a Java file"""
    file_path: str
    package: str
    imports: List[str]
    chunks: List[CodeChunk] = field(default_factory=list)
    original_content: str = ""
    
    def get_context_header(self) -> str:
        """Get the header that should be prepended to each chunk"""
        lines = []
        if self.package:
            lines.append(f"package {self.package};")
            lines.append("")
        for imp in self.imports:
            lines.append(imp)
        if self.imports:
            lines.append("")
        return "\n".join(lines)


class ContextManager:
    """
    Manages context window for LLM processing of large Java files.
    
    Strategies:
    1. Small files (< 50KB): Send entire file
    2. Medium files (50KB - 200KB): Split by classes
    3. Large files (> 200KB): Split by methods with class context
    """
    
    # Size thresholds in bytes
    SMALL_FILE_THRESHOLD = 50000    # 50 KB
    MEDIUM_FILE_THRESHOLD = 200000  # 200 KB
    
    # Token limits (conservative)
    MAX_TOKENS_PER_CHUNK = 50000
    
    def __init__(self, config: Dict):
        """
        Initialize the ContextManager.
        
        Args:
            config: Pipeline configuration
        """
        chunking_config = config.get('chunking', {})
        self.max_chunk_size = chunking_config.get('max_file_size', self.SMALL_FILE_THRESHOLD)
        self.max_chunk_tokens = chunking_config.get('max_chunk_tokens', self.MAX_TOKENS_PER_CHUNK)
        self.overlap_lines = chunking_config.get('overlap_lines', 20)
        self.strategy = chunking_config.get('strategy', 'ast_based')
        
    def should_chunk(self, file_path: Path) -> bool:
        """
        Determine if a file needs to be chunked.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file should be chunked
        """
        if not file_path.exists():
            return False
            
        size = file_path.stat().st_size
        return size > self.max_chunk_size
        
    def process_file(self, file_path: Path) -> FileContext:
        """
        Process a Java file and create chunks if needed.
        
        Args:
            file_path: Path to the Java file
            
        Returns:
            FileContext with chunks
        """
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        context = FileContext(
            file_path=str(file_path),
            package="",
            imports=[],
            original_content=content
        )
        
        # Parse package and imports
        self._parse_header(content, context)
        
        # Decide on chunking strategy
        if not self.should_chunk(file_path):
            # Small file - single chunk
            chunk = CodeChunk(
                chunk_id=0,
                content=content,
                start_line=1,
                end_line=len(content.split('\n')),
                chunk_type='full_file',
                original_content=content
            )
            context.chunks.append(chunk)
        else:
            # Large file - use AST-based or line-based chunking
            if self.strategy == 'ast_based' and javalang:
                self._chunk_by_ast(content, context)
            else:
                self._chunk_by_lines(content, context)
                
        logger.info(f"Created {len(context.chunks)} chunks for {file_path}")
        return context
        
    def _parse_header(self, content: str, context: FileContext):
        """
        Parse package and imports from Java file.
        
        Args:
            content: File content
            context: FileContext to populate
        """
        lines = content.split('\n')
        
        for line in lines:
            stripped = line.strip()
            
            # Package declaration
            if stripped.startswith('package '):
                match = re.match(r'package\s+([\w.]+);', stripped)
                if match:
                    context.package = match.group(1)
                    
            # Import statements
            elif stripped.startswith('import '):
                context.imports.append(stripped)
                
            # Stop at class declaration
            elif 'class ' in stripped or 'interface ' in stripped or 'enum ' in stripped:
                break
                
    def _chunk_by_ast(self, content: str, context: FileContext):
        """
        Chunk file using AST parsing.
        
        Args:
            content: File content
            context: FileContext to populate with chunks
        """
        try:
            tree = javalang.parse.parse(content)
            lines = content.split('\n')
            
            chunk_id = 0
            
            # Find all class declarations
            for path, node in tree.filter(javalang.tree.ClassDeclaration):
                class_start = node.position.line - 1 if node.position else 0
                
                # Find class end (simplified - find matching brace)
                class_end = self._find_block_end(lines, class_start)
                
                class_content = '\n'.join(lines[class_start:class_end + 1])
                
                # Check if class itself is too large
                if len(class_content) > self.max_chunk_size:
                    # Split by methods
                    self._chunk_class_by_methods(
                        content, context, node, class_start, class_end, chunk_id
                    )
                    chunk_id += len([m for m in node.body 
                                    if isinstance(m, javalang.tree.MethodDeclaration)])
                else:
                    # Class as single chunk
                    chunk = CodeChunk(
                        chunk_id=chunk_id,
                        content=class_content,
                        start_line=class_start + 1,
                        end_line=class_end + 1,
                        chunk_type='class',
                        class_name=node.name,
                        context_header=context.get_context_header(),
                        original_content=class_content
                    )
                    context.chunks.append(chunk)
                    chunk_id += 1
                    
        except Exception as e:
            logger.warning(f"AST parsing failed, falling back to line-based: {e}")
            self._chunk_by_lines(content, context)
            
    def _chunk_class_by_methods(
        self, 
        content: str, 
        context: FileContext, 
        class_node, 
        class_start: int, 
        class_end: int,
        start_chunk_id: int
    ):
        """
        Chunk a large class by its methods.
        
        Args:
            content: Full file content
            context: FileContext to populate
            class_node: javalang ClassDeclaration node
            class_start: Start line of class
            class_end: End line of class
            start_chunk_id: Starting chunk ID
        """
        lines = content.split('\n')
        chunk_id = start_chunk_id
        
        # Get class header (signature, fields, etc.)
        class_header_end = class_start
        for member in class_node.body:
            if isinstance(member, javalang.tree.MethodDeclaration):
                if member.position:
                    class_header_end = member.position.line - 2
                break
                
        class_header = '\n'.join(lines[class_start:class_header_end + 1])
        
        # Create chunks for each method
        for member in class_node.body:
            if isinstance(member, javalang.tree.MethodDeclaration):
                if not member.position:
                    continue
                    
                method_start = member.position.line - 1
                method_end = self._find_block_end(lines, method_start)
                
                method_content = '\n'.join(lines[method_start:method_end + 1])
                
                # Include class header as context
                full_context = f"{context.get_context_header()}\n{class_header}\n\n    // ... other methods ...\n\n{method_content}\n}}"
                
                chunk = CodeChunk(
                    chunk_id=chunk_id,
                    content=method_content,
                    start_line=method_start + 1,
                    end_line=method_end + 1,
                    chunk_type='method',
                    class_name=class_node.name,
                    method_name=member.name,
                    context_header=f"{context.get_context_header()}\n{class_header}",
                    original_content=method_content
                )
                context.chunks.append(chunk)
                chunk_id += 1
                
    def _chunk_by_lines(self, content: str, context: FileContext):
        """
        Simple line-based chunking for fallback.
        
        Args:
            content: File content
            context: FileContext to populate
        """
        lines = content.split('\n')
        
        # Calculate lines per chunk (rough estimate: 4 chars per token)
        chars_per_chunk = self.max_chunk_tokens * 4
        avg_line_length = len(content) / len(lines) if lines else 80
        lines_per_chunk = int(chars_per_chunk / avg_line_length)
        
        chunk_id = 0
        start = 0
        
        while start < len(lines):
            end = min(start + lines_per_chunk, len(lines))
            
            # Try to end at a method boundary (line ending with '{' or '}')
            for i in range(end - 1, max(start + lines_per_chunk // 2, start), -1):
                if lines[i].strip().endswith('}'):
                    end = i + 1
                    break
                    
            chunk_content = '\n'.join(lines[start:end])
            
            chunk = CodeChunk(
                chunk_id=chunk_id,
                content=chunk_content,
                start_line=start + 1,
                end_line=end,
                chunk_type='lines',
                context_header=context.get_context_header(),
                original_content=chunk_content
            )
            context.chunks.append(chunk)
            
            # Move to next chunk with overlap
            start = end - self.overlap_lines
            chunk_id += 1
            
    def _find_block_end(self, lines: List[str], start: int) -> int:
        """
        Find the end of a code block by matching braces.
        
        Args:
            lines: List of code lines
            start: Starting line index
            
        Returns:
            End line index
        """
        brace_count = 0
        in_block = False
        
        for i in range(start, len(lines)):
            line = lines[i]
            
            # Skip strings and comments (simplified)
            clean_line = re.sub(r'"[^"]*"', '', line)
            clean_line = re.sub(r'//.*$', '', clean_line)
            
            for char in clean_line:
                if char == '{':
                    brace_count += 1
                    in_block = True
                elif char == '}':
                    brace_count -= 1
                    
            if in_block and brace_count == 0:
                return i
                
        return len(lines) - 1
        
    def merge_refactored_chunks(self, context: FileContext) -> str:
        """
        Merge refactored chunks back into a complete file.
        
        Args:
            context: FileContext with refactored chunks
            
        Returns:
            Complete refactored file content
        """
        if len(context.chunks) == 1 and context.chunks[0].chunk_type == 'full_file':
            # Single chunk - return as is
            refactored = context.chunks[0].refactored_content
            return refactored if refactored else context.chunks[0].content
            
        # Multiple chunks - need to merge
        lines = context.original_content.split('\n')
        
        # Sort chunks by start line
        sorted_chunks = sorted(context.chunks, key=lambda c: c.start_line)
        
        # Replace each chunk's lines with refactored content
        offset = 0
        for chunk in sorted_chunks:
            if chunk.refactored_content:
                refactored_lines = chunk.refactored_content.split('\n')
                original_lines = chunk.content.split('\n')
                
                # Calculate actual positions with offset
                start = chunk.start_line - 1 + offset
                end = chunk.end_line - 1 + offset
                
                # Replace lines
                lines[start:end + 1] = refactored_lines
                
                # Update offset for next chunk
                offset += len(refactored_lines) - len(original_lines)
                
        return '\n'.join(lines)
        
    def prepare_prompt_context(self, chunk: CodeChunk, smell_info: str) -> str:
        """
        Prepare the full context for an LLM prompt.
        
        Args:
            chunk: CodeChunk to process
            smell_info: Information about detected smells
            
        Returns:
            Complete context string
        """
        context_parts = []
        
        # Add context header if available
        if chunk.context_header:
            context_parts.append("// File context (imports and declarations):")
            context_parts.append(chunk.context_header)
            context_parts.append("")
            
        # Add smell information
        context_parts.append("// Detected design smells in this code:")
        context_parts.append(smell_info)
        context_parts.append("")
        
        # Add the actual code
        context_parts.append("// Code to refactor:")
        context_parts.append(chunk.content)
        
        return '\n'.join(context_parts)


if __name__ == "__main__":
    # Test the context manager
    import yaml
    
    with open("config/config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    manager = ContextManager(config)
    
    # Test with a sample file
    test_file = Path("./app/src/main/java/org/apache/roller/weblogger/business/WebloggerImpl.java")
    if test_file.exists():
        context = manager.process_file(test_file)
        print(f"Chunks created: {len(context.chunks)}")
        for chunk in context.chunks:
            print(f"  Chunk {chunk.chunk_id}: {chunk.chunk_type}, lines {chunk.start_line}-{chunk.end_line}")
