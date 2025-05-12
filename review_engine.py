from transformers import pipeline
import os
from openai import OpenAI

class CodeReviewer:
    def __init__(self, llm_choice="openai"):
        self.llm_choice = llm_choice
        self.client=OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.system_prompt = """You are an expert code reviewer. Follow these rules:
1. Only answer questions about code reviews and software development
2. Base answers strictly on the provided code diff and established best practices
3. Never invent information outside the code context
4. For suggestions, always provide concrete code examples
5. Reject non-technical questions politely
6. Use Markdown formatting for code blocks
7. A corrected or improved version of the code (in a Markdown code block)
8. Always wrap code suggestions in triple backticks.
9. Explanations for your changes
If the code is already optimal, explain why."""

        # elif llm_choice == "codellama":
        #     self.pipeline = pipeline(
        #         "text-generation",
        #         model="codellama/CodeLlama-7b-hf",
        #         device_map="auto"
        #     )
        # elif llm_choice == "starcoder":
        #     self.pipeline = pipeline(
        #         "text-generation",
        #         model="bigcode/starcoder",
        #         device_map="auto"
        #     )

    def generate_review(self, code_diff):
        prompt = f"""Analyze this code diff and provide feedback:
        {code_diff}
        Focus on:
        - Code quality issues
        - Security vulnerabilities
        - Performance improvements
        - Style inconsistencies"""
        
        if self.llm_choice == "openai":
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                # messages=[{"role": "user", "content": prompt}]
                messages=[
                {"role": "system", "content": self.system_prompt},  # <-- Add this line
                {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        else:
            return self.pipeline(prompt, max_new_tokens=500)[0]['generated_text']
        
    def validate_question(self, question):
        """Check if question is code-related using LLM"""
        validation_prompt = f"""Classify if this question is about code review/development or code suggestion (respond 'yes' or 'no'):
Question: {question}"""

        response = self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": validation_prompt}],
            temperature=0.0
        )
        return "yes" in response.choices[0].message.content.lower()

    def get_response(self, question, code_diff, conversation_history):
        # Handle missing or empty code_diff
        if not code_diff.strip():
            code_diff = "No code diff provided. Please provide code or specify the context."

        # Validate the question
        if not self.validate_question(question):
            return "I specialize in code review questions. Please ask about software development best practices or specific code issues."

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Code diff:\n{code_diff}"},
            *conversation_history[-6:],  # Keep last 3 exchanges
            {"role": "user", "content": question}
        ]

        response = self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.3,
            max_tokens=500
        )

        return self.postprocess_response(response.choices[0].message.content)

    def postprocess_response(self, response):
        """Ensure response follows guidelines"""
        forbidden_phrases = ["I don't know", "I'm not sure", "as an AI"]
        for phrase in forbidden_phrases:
            if phrase in response.lower():
                return "I can only provide definitive answers based on the code. Please ask specific code-related questions."
        return response
