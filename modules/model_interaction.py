import subprocess

def get_response_from_model(command_text):
    try:
        result = subprocess.run(
            ["ollama", "run", "taozhiyuai/llama-3-8b-lexi-uncensored:f16", "--text", command_text],
            capture_output=True,
            text=True
        )
        response = result.stdout.strip()
        return response
    except Exception as e:
        print(f"An error occurred while getting response from the model: {e}")
        return ""
