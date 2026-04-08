import json
from urllib import error, request

OLLAMA_API_URL = "http://localhost:11434/api/generate"

def call_ollama(prompt: str, model: str = "llama3") -> str:
    """Calls a local Ollama instance for truly local generation."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            OLLAMA_API_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60.0) as response:
            if response.status == 200:
                body = json.loads(response.read().decode("utf-8"))
                return body["response"].strip()
            return (
                f"Error: Ollama returned {response.status}. "
                f"Make sure model '{model}' is installed (run 'ollama pull {model}')."
            )
    except error.HTTPError as e:
        return (
            f"Error: Ollama returned {e.code}. "
            f"Make sure model '{model}' is installed (run 'ollama pull {model}')."
        )
    except Exception as e:
        return f"Error connecting to Ollama: {str(e)}\nEnsure Ollama is running (https://ollama.com)."
