# VibeTexting Backend

FastAPI backend for AI-powered text response generation.

## Features

- 🚀 **FastAPI** - High-performance async API
- 🤖 **Groq API Integration** - Fast AI responses using Llama 3.1
- 🎯 **Tone-Based Generation** - Casual, Professional, Funny, Friendly, Concise
- 🔧 **Prompt Builder** - Intelligent prompt construction for better results

## Requirements

- Python 3.9+
- Groq API Key (get one at https://console.groq.com)

## Setup

### 1. Create Virtual Environment

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API Key

Create a `.env` file:

```bash
echo "GROQ_API_KEY=your_api_key_here" > .env
```

### 4. Run the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Health Check
```
GET /health
```
Returns server status.

### Generate Reply
```
POST /generate-reply
Content-Type: application/json

{
    "original_message": "Hey, are we still on for tonight?",
    "user_reply": "yeah definitely",
    "tone": "casual"
}
```

Response:
```json
{
    "generated_reply": "Yeah, definitely! See you then 😊",
    "tone": "casual",
    "alternatives": null
}
```

### Generate Alternatives
```
POST /generate-alternatives
```
Returns 3 alternative phrasings of the same message.

## Tone Options

| Tone | Description |
|------|-------------|
| `casual` | Relaxed, friendly, conversational |
| `professional` | Polite, clear, business-appropriate |
| `funny` | Humorous, playful, light-hearted |
| `friendly` | Warm, supportive, kind |
| `concise` | Brief, direct, minimal words |

## Development

### Test the API

```bash
# Health check
curl http://localhost:8000/health

# Generate reply
curl -X POST http://localhost:8000/generate-reply \
  -H "Content-Type: application/json" \
  -d '{"original_message": "Hello!", "tone": "friendly"}'
```

### Interactive Docs

FastAPI provides automatic API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── main.py              # FastAPI application
├── requirements.txt     # Python dependencies
└── .env                 # Environment variables (create this)
```

## Production Deployment

For production:

1. Set `GROQ_API_KEY` environment variable
2. Use a production ASGI server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
   ```
3. Consider deploying to:
   - Railway
   - Render
   - AWS Lambda
   - Google Cloud Run

## Security Notes

- Configure CORS properly in `main.py` for production
- Use HTTPS in production
- Consider adding API key authentication for the iOS app
