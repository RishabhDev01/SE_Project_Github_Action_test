"""
Refactoring Prompts - Templates for LLM-based code refactoring

This module provides specialized prompts for each type of design smell,
ensuring consistent and effective refactoring suggestions.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class RefactoringPrompt:
    """A refactoring prompt with system and user components"""
    system_prompt: str
    user_prompt_template: str
    expected_output_format: str


class RefactoringPrompts:
    """
    Collection of prompts for different design smell refactoring scenarios.
    
    Each prompt is designed to:
    1. Explain the smell and why it's problematic
    2. Provide clear refactoring instructions
    3. Preserve functionality while improving design
    """
    
    # System prompt for all refactoring tasks
    BASE_SYSTEM_PROMPT = """You are an expert Java developer specializing in code refactoring and clean code practices. 
Your task is to refactor code to eliminate design smells while:
1. Preserving all existing functionality
2. Maintaining API compatibility where possible
3. Following SOLID principles and clean code practices
4. Adding appropriate comments to explain complex changes

CRITICAL RULES - FAILURE TO FOLLOW THESE WILL CAUSE COMPILATION ERRORS:
- Return ONLY the refactored Java code, no explanations
- NEVER remove or change 'throws' declarations on methods - preserve ALL checked exceptions
- NEVER remove exception handling (try-catch blocks) unless refactoring specifically targets it
- Keep ALL existing imports - only add new ones if needed
- Keep method signatures EXACTLY the same (name, parameters, return type, throws clause)
- Do NOT introduce new method calls to methods that don't exist
- Do NOT use variables that haven't been declared
- Preserve ALL public and protected method signatures exactly
- Add TODO comments for any breaking changes that require updates elsewhere
- Use meaningful names that reflect the purpose of classes and methods

CRITICAL EXCEPTION HANDLING RULES (MOST COMMON ERROR):
1. If the original method has: "public void foo() throws IOException" 
   Your refactored version MUST ALSO have: "public void foo() throws IOException"
   
2. If the original has: "throws WebloggerException, IOException"
   You MUST preserve: "throws WebloggerException, IOException"
   
3. Examples of WRONG refactoring:
   ORIGINAL: public void parse() throws IOException, SAXException { ... }
   WRONG:    public void parse() { ... }  // COMPILATION ERROR!
   CORRECT:  public void parse() throws IOException, SAXException { ... }

4. If you extract code to a new helper method that calls something throwing an exception,
   the new method must ALSO declare "throws" for those exceptions.
"""

    # Prompts for specific smell types
    SMELL_PROMPTS: Dict[str, RefactoringPrompt] = {
        
        "God Class": RefactoringPrompt(
            system_prompt=BASE_SYSTEM_PROMPT + """
SMELL: God Class
A God Class is a class that knows too much or does too much. It has too many responsibilities.

REFACTORING STRATEGY:
1. Identify distinct responsibilities within the class
2. Extract each responsibility into a separate, focused class
3. Use composition or dependency injection to coordinate between classes
4. Keep the original class as a facade if needed for backward compatibility
""",
            user_prompt_template="""
Refactor the following God Class to eliminate the design smell.

DETECTED ISSUE: {cause}

METRICS:
- Lines of Code: {loc}
- Number of Methods: {methods_count}
- Cyclomatic Complexity: {cyclomatic_complexity}

CODE TO REFACTOR:
```java
{code}
```

Return the refactored code. If you split into multiple classes, include all classes in your response with clear class separators.
Use this format for multiple classes:
// === ClassName.java ===
<class code>
// === AnotherClass.java ===
<class code>
""",
            expected_output_format="java_code"
        ),
        
        "Long Method": RefactoringPrompt(
            system_prompt=BASE_SYSTEM_PROMPT + """
SMELL: Long Method
A Long Method is a method that has grown too large and does too many things.

REFACTORING STRATEGY:
1. Identify logical sections within the method
2. Extract each section into a private method with a descriptive name
3. The extracted methods should do one thing and do it well
4. Use comments to document the overall algorithm flow
""",
            user_prompt_template="""
Refactor the following Long Method to improve readability and maintainability.

DETECTED ISSUE: {cause}
METHOD NAME: {method_name}

METRICS:
- Method Lines of Code: {method_loc}
- Cyclomatic Complexity: {cyclomatic_complexity}

CODE TO REFACTOR:
```java
{code}
```

Return the refactored method and any new helper methods. Keep the original method signature.
""",
            expected_output_format="java_code"
        ),
        
        "Feature Envy": RefactoringPrompt(
            system_prompt=BASE_SYSTEM_PROMPT + """
SMELL: Feature Envy
Feature Envy occurs when a method uses more features from another class than from its own class.

REFACTORING STRATEGY:
1. Identify which class the method is most interested in
2. Consider moving the method to that class
3. If moving isn't possible, extract the envious behavior into a new method in the appropriate class
4. Update the original method to delegate to the new location
""",
            user_prompt_template="""
Refactor the following code to eliminate Feature Envy.

DETECTED ISSUE: {cause}

The method appears to be more interested in another class's data/behavior.

CODE TO REFACTOR:
```java
{code}
```

Suggest how to refactor this. If the method should move to another class, show both:
1. The updated original class
2. The method as it should appear in the target class

Mark moved/new code clearly with comments.
""",
            expected_output_format="java_code"
        ),
        
        "Data Class": RefactoringPrompt(
            system_prompt=BASE_SYSTEM_PROMPT + """
SMELL: Data Class
A Data Class is a class that contains only fields, getters, and setters without meaningful behavior.

REFACTORING STRATEGY:
1. Identify behavior that belongs with this data (look at classes that frequently use this class)
2. Move related behavior into the data class
3. Add meaningful methods that operate on the data
4. Consider encapsulating fields that shouldn't be directly exposed
""",
            user_prompt_template="""
Refactor the following Data Class to add meaningful behavior.

DETECTED ISSUE: {cause}

This class only contains data without behavior. Look for opportunities to add methods that operate on this data.

CODE TO REFACTOR:
```java
{code}
```

Add meaningful methods that:
- Validate data
- Perform calculations related to the data
- Enforce business rules
- Provide formatted or computed values
""",
            expected_output_format="java_code"
        ),
        
        "Complex Method": RefactoringPrompt(
            system_prompt=BASE_SYSTEM_PROMPT + """
SMELL: Complex Method
A Complex Method has high cyclomatic complexity, making it hard to understand and test.

REFACTORING STRATEGY:
1. Simplify complex conditionals using guard clauses
2. Replace nested conditionals with polymorphism or strategy pattern
3. Extract complex boolean expressions into well-named methods
4. Use early returns to reduce nesting
""",
            user_prompt_template="""
Refactor the following Complex Method to reduce its cyclomatic complexity.

DETECTED ISSUE: {cause}
CYCLOMATIC COMPLEXITY: {cyclomatic_complexity}

CODE TO REFACTOR:
```java
{code}
```

Simplify the logic while maintaining the same behavior. Consider:
- Using guard clauses for early returns
- Extracting conditional logic into helper methods
- Using the strategy pattern for complex branching
""",
            expected_output_format="java_code"
        ),
        
        "Long Parameter List": RefactoringPrompt(
            system_prompt=BASE_SYSTEM_PROMPT + """
SMELL: Long Parameter List
A method with many parameters is hard to understand and use correctly.

REFACTORING STRATEGY:
1. Group related parameters into a parameter object
2. Use builder pattern for optional parameters
3. Consider if some parameters can be instance fields instead
4. Check if the method is doing too much (might need splitting)
""",
            user_prompt_template="""
Refactor the following method with a Long Parameter List.

DETECTED ISSUE: {cause}
NUMBER OF PARAMETERS: {param_count}

CODE TO REFACTOR:
```java
{code}
```

Create a parameter object class if needed and update the method signature.
Show both the new parameter class and the updated method.
""",
            expected_output_format="java_code"
        ),
        
        "Duplicate Abstraction": RefactoringPrompt(
            system_prompt=BASE_SYSTEM_PROMPT + """
SMELL: Duplicate Abstraction
Multiple classes or methods have very similar implementations.

REFACTORING STRATEGY:
1. Identify common behavior between duplicates
2. Extract common behavior into a shared base class or utility method
3. Use composition or templates to handle variations
4. Ensure the abstraction makes semantic sense
""",
            user_prompt_template="""
The following code contains duplicate abstractions that should be consolidated.

DETECTED ISSUE: {cause}

CODE TO REFACTOR:
```java
{code}
```

Extract common behavior into a shared abstraction while preserving the unique aspects of each implementation.
""",
            expected_output_format="java_code"
        ),
    }
    
    # Default prompt for unrecognized smells
    DEFAULT_PROMPT = RefactoringPrompt(
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""
Refactor the following code to improve its design and maintainability.

DETECTED ISSUE: {cause}
SMELL TYPE: {smell_type}

CODE TO REFACTOR:
```java
{code}
```

Apply appropriate refactoring techniques while preserving functionality.
""",
        expected_output_format="java_code"
    )
    
    @classmethod
    def get_prompt(cls, smell_type: str) -> RefactoringPrompt:
        """
        Get the appropriate prompt for a smell type.
        
        Args:
            smell_type: Type of design smell
            
        Returns:
            RefactoringPrompt for the smell
        """
        return cls.SMELL_PROMPTS.get(smell_type, cls.DEFAULT_PROMPT)
    
    @classmethod
    def format_prompt(
        cls,
        smell_type: str,
        code: str,
        cause: str,
        **kwargs
    ) -> tuple:
        """
        Format a complete prompt for LLM.
        
        Args:
            smell_type: Type of design smell
            code: Code to refactor
            cause: Description of the smell cause
            **kwargs: Additional template variables
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        prompt = cls.get_prompt(smell_type)
        
        # Build template variables
        template_vars = {
            'code': code,
            'cause': cause,
            'smell_type': smell_type,
            **kwargs
        }
        
        # Fill in defaults for missing variables
        defaults = {
            'loc': 'N/A',
            'methods_count': 'N/A',
            'cyclomatic_complexity': 'N/A',
            'method_name': 'N/A',
            'method_loc': 'N/A',
            'param_count': 'N/A',
        }
        
        for key, default in defaults.items():
            if key not in template_vars:
                template_vars[key] = default
                
        user_prompt = prompt.user_prompt_template.format(**template_vars)
        
        return (prompt.system_prompt, user_prompt)
    
    @classmethod
    def get_multi_smell_prompt(cls, smells: List[Dict], code: str) -> tuple:
        """
        Create a prompt for code with multiple smells.
        
        Args:
            smells: List of smell dictionaries with 'type' and 'cause'
            code: Code to refactor
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt = cls.BASE_SYSTEM_PROMPT + """
MULTIPLE SMELLS DETECTED
Address all the listed design smells in a single refactoring pass.
Prioritize changes that address multiple smells at once.
"""
        
        smell_descriptions = []
        for smell in smells:
            smell_descriptions.append(f"- {smell['type']}: {smell['cause']}")
            
        user_prompt = f"""
Refactor the following code to address multiple design smells.

DETECTED ISSUES:
{chr(10).join(smell_descriptions)}

CODE TO REFACTOR:
```java
{code}
```

Address all smells while maintaining functionality. Return the complete refactored code.
"""
        
        return (system_prompt, user_prompt)
    
    @classmethod
    def get_validation_prompt(cls, original_code: str, refactored_code: str) -> tuple:
        """
        Create a prompt to validate refactored code.
        
        Args:
            original_code: Original code before refactoring
            refactored_code: Code after refactoring
            
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt = """You are a code review expert. Analyze the refactored code and verify:
1. All original functionality is preserved
2. No syntax errors exist
3. The refactoring addresses the intended issues
4. No new bugs or issues were introduced

Respond with ONLY:
- "VALID" if the refactoring is correct
- "INVALID: <reason>" if there are issues
"""
        
        user_prompt = f"""
ORIGINAL CODE:
```java
{original_code}
```

REFACTORED CODE:
```java
{refactored_code}
```

Is this refactoring valid?
"""
        
        return (system_prompt, user_prompt)


if __name__ == "__main__":
    # Test prompt generation
    system, user = RefactoringPrompts.format_prompt(
        smell_type="God Class",
        code="public class UserManager { /* ... */ }",
        cause="Class has too many responsibilities",
        loc=500,
        methods_count=25
    )
    
    print("System Prompt:")
    print(system[:500], "...")
    print("\nUser Prompt:")
    print(user)
