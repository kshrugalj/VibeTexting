"""
VibeTexting Backend - FastAPI server for AI-powered text response generation.

This server receives voice-to-text input and tone preferences from the iOS app,
constructs prompts for the AI, and returns human-like response suggestions.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="VibeTexting API",
    description="AI-powered text response generation for iOS messaging app",
    version="1.0.0"
)

# Configure CORS for iOS app communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Groq API configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Request/Response models
class MessageRequest(BaseModel):
    """Request model for generating AI responses."""
    original_message: str  # The message the user received
    user_reply: Optional[str] = None  # Optional: voice-to-text reply from user
    tone: str = "casual"  # Tone: casual, professional, funny, friendly, concise
    context: Optional[str] = None  # Optional: additional context about the conversation


class MessageResponse(BaseModel):
    """Response model with AI-generated suggestions."""
    generated_reply: str
    tone: str
    alternatives: Optional[List[str]] = None  # Alternative phrasings


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str


# Prompt builder function
def build_prompt(request: MessageRequest) -> str:
    """
    Constructs a prompt for the AI based on user input and tone preference.
    
    This function formats the request into a clear instruction for the AI,
    ensuring consistent, tone-appropriate responses.
    """
    tone_instructions = {
        "casual": "Keep it relaxed, friendly, and conversational. Use everyday language.",
        "professional": "Keep it polite, clear, and business-appropriate. Avoid slang.",
        "funny": "Add humor, wit, or a playful twist. Keep it light-hearted.",
        "friendly": "Warm, supportive, and kind. Show genuine interest.",
        "concise": "Brief and to the point. Minimal words, maximum clarity."
    }
    
    instruction = tone_instructions.get(request.tone, tone_instructions["casual"])
    
    if request.user_reply:
        prompt = f"""You are helping someone respond to a text message.

Original message: "{request.original_message}"
User's draft reply: "{request.user_reply}"
Tone: {request.tone} - {instruction}

Refine the user's draft reply to match the requested tone while keeping their intended meaning. 
Make it sound natural and human-like. Keep it concise for a text message.

Response:"""
    else:
        prompt = f"""You are helping someone respond to a text message.

Original message: "{request.original_message}"
Tone: {request.tone} - {instruction}

Generate a natural, human-like text response that matches the tone. 
Keep it concise and appropriate for a text message.

Response:"""
    
    return prompt


# Placeholder API call function (will be replaced with actual Groq integration)
async def call_groq_api(prompt: str) -> str:
    """
    Makes an API call to Groq to generate AI responses.
    
    Args:
        prompt: The formatted prompt to send to the AI
        
    Returns:
        Generated text response from the AI
    """
    if not GROQ_API_KEY:
        # Return placeholder for development without API key
        return "[AI Response would appear here - configure GROQ_API_KEY to enable]"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.3-70b-versatile",  # Current high-quality versatile model
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 100,
        "temperature": 0.7,
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GROQ_API_URL,
            headers=headers,
            json=payload,
            timeout=10.0
        )
        
        if response.status_code != 200:
            print(f"DEBUG: Groq API Error: {response.status_code} - {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to get AI response: {response.text}"
            )
        
        data = response.json()
        result = data["choices"][0]["message"]["content"].strip()
        return result


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for the iOS app to verify connectivity."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/generate-reply", response_model=MessageResponse)
async def generate_reply(request: MessageRequest):
    """
    Main endpoint for generating AI-powered text responses.
    
    Receives the original message, optional user voice reply, and tone preference.
    Returns a refined, tone-appropriate response.
    """
    print(f"DEBUG: Generating reply for tone: {request.tone}")
    
    # Build the prompt for the AI
    prompt = build_prompt(request)
    
    # Call Groq API to generate response
    try:
        generated_reply = await call_groq_api(prompt)
        print(f"DEBUG: Generated reply: {generated_reply[:50]}...")
    except HTTPException:
        # Fallback for development/testing
        generated_reply = f"[Generated {request.tone} reply for: {request.original_message[:50]}...]"
        print(f"DEBUG: Fallback reply triggered")
    
    # Generate alternatives (optional feature)
    alternatives = []
    
    return MessageResponse(
        generated_reply=generated_reply,
        tone=request.tone,
        alternatives=alternatives
    )


@app.post("/generate-alternatives", response_model=List[str])
async def generate_alternatives(request: MessageRequest):
    """
    Generate multiple alternative responses for the user to choose from.
    
    Returns 3 different phrasings of the same message.
    """
    prompt = build_prompt(request)
    
    # Request multiple variations
    alternatives_prompt = f"""{prompt}

Now provide 3 different ways to say this, all matching the same tone.
Format each on a separate line with "1.", "2.", "3." prefixes."""

    try:
        response = await call_groq_api(alternatives_prompt)
        # Parse the numbered list
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        alternatives = []
        for line in lines:
            # Remove numbering
            if line.startswith(('1.', '2.', '3.', '1)', '2)', '3)')):
                alternatives.append(line[2:].strip())
        return alternatives[:3]  # Return max 3 alternatives
    except Exception:
        return ["Alternative 1", "Alternative 2", "Alternative 3"]


# Run with: uvicorn main:app --reload --host 0.0.0.0 --port 8000
