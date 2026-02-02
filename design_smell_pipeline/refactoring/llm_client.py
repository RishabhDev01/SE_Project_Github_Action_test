"""
LLM Client - Unified interface for OpenAI and Gemini APIs

This module handles:
1. API initialization and configuration
2. Request handling with retries
3. Response parsing
"""

import os
import logging
import time
from typing import Dict, List, Optional, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response from the LLM"""
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        pass


class OpenAIClient(BaseLLMClient):
    """OpenAI GPT client implementation"""
    
    def __init__(self, config: Dict):
        """
        Initialize OpenAI client.
        
        Args:
            config: LLM configuration dictionary
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
            
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
            
        self.client = OpenAI(api_key=api_key)
        self.model = config.get('openai', {}).get('model', 'gpt-4-turbo')
        self.max_tokens = config.get('openai', {}).get('max_tokens', 4096)
        self.temperature = config.get('openai', {}).get('temperature', 0.2)
        
        logger.info(f"Initialized OpenAI client with model: {self.model}")
        
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate a response from OpenAI.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            Generated response text
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
            
    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        # Rough estimation: ~4 characters per token for English
        return len(text) // 4


class GroqClient(BaseLLMClient):
    """Groq client implementation (uses OpenAI-compatible API with ultra-fast inference)"""
    
    def __init__(self, config: Dict):
        """
        Initialize Groq client.
        
        Groq API uses OpenAI-compatible format with custom base URL.
        Get your free API key from: https://console.groq.com/
        
        Args:
            config: LLM configuration dictionary
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
            
        api_key = os.environ.get('GROQ_API_KEY')
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")
            
        # Groq uses OpenAI-compatible API with custom base URL
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        
        # Groq supports: llama-3.3-70b-versatile, mixtral-8x7b-32768, llama3-8b-8192
        self.model = config.get('groq', {}).get('model', 'llama-3.3-70b-versatile')
        self.max_tokens = config.get('groq', {}).get('max_tokens', 8192)
        self.temperature = config.get('groq', {}).get('temperature', 0.2)
        
        logger.info(f"Initialized Groq client with model: {self.model}")
        
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate a response from Groq.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            Generated response text
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise
            
    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        # Similar to OpenAI tokenization
        return len(text) // 4


class GeminiClient(BaseLLMClient):
    """Google Gemini client implementation"""
    
    def __init__(self, config: Dict):
        """
        Initialize Gemini client.
        
        Args:
            config: LLM configuration dictionary
        """
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("Google AI package not installed. Run: pip install google-generativeai")
            
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
            
        genai.configure(api_key=api_key)
        
        self.model_name = config.get('gemini', {}).get('model', 'gemini-1.5-pro')
        self.max_tokens = config.get('gemini', {}).get('max_tokens', 8192)
        self.temperature = config.get('gemini', {}).get('temperature', 0.2)
        
        # Configure generation settings
        generation_config = genai.GenerationConfig(
            max_output_tokens=self.max_tokens,
            temperature=self.temperature
        )
        
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=generation_config
        )
        
        logger.info(f"Initialized Gemini client with model: {self.model_name}")
        
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate a response from Gemini.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            Generated response text
        """
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
            
        try:
            response = self.model.generate_content(full_prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
            
    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        # Gemini uses similar tokenization to OpenAI
        return len(text) // 4


class LLMClient:
    """
    Unified LLM client that supports Groq, OpenAI, and Gemini.
    Handles retries and rate limiting.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize the LLM client based on configuration.
        
        Args:
            config: Full pipeline configuration
        """
        llm_config = config.get('llm', {})
        provider = llm_config.get('provider', 'groq').lower()
        
        self.max_retries = config.get('refactoring', {}).get('max_retries', 3)
        self.retry_delay = 5  # seconds
        
        if provider == 'groq':
            self._client = GroqClient(llm_config)
        elif provider == 'openai':
            self._client = OpenAIClient(llm_config)
        elif provider == 'gemini':
            self._client = GeminiClient(llm_config)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
            
        self.provider = provider
        logger.info(f"Using LLM provider: {provider}")
        
    def generate_with_retry(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        validation_fn: Optional[callable] = None
    ) -> Optional[str]:
        """
        Generate response with automatic retries.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            validation_fn: Optional function to validate response
            
        Returns:
            Generated response or None if all retries failed
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self._client.generate(prompt, system_prompt)
                
                # Validate if function provided
                if validation_fn:
                    if validation_fn(response):
                        return response
                    else:
                        logger.warning(f"Validation failed on attempt {attempt + 1}")
                        continue
                        
                return response
                
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                    
        logger.error(f"All {self.max_retries} attempts failed. Last error: {last_error}")
        return None
        
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            Generated response text
        """
        return self._client.generate(prompt, system_prompt)
        
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.
        
        Args:
            text: Text to count
            
        Returns:
            Token count
        """
        return self._client.count_tokens(text)
        
    def can_fit_in_context(self, text: str, max_tokens: int = 100000) -> bool:
        """
        Check if text fits within context window.
        
        Args:
            text: Text to check
            max_tokens: Maximum token limit
            
        Returns:
            True if text fits in context
        """
        return self.count_tokens(text) < max_tokens


if __name__ == "__main__":
    # Test the client
    import yaml
    
    with open("config/config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    try:
        client = LLMClient(config)
        response = client.generate("Say hello in one sentence.")
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")
