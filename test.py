import requests

TOKEN = "8031049269:AAFlN4EyETxaku0BM0ovyi77uTbI6VeYlmM"

url = f"https://api.telegram.org/bot{TOKEN}/getMe"
response = requests.get(url)
print(response.json())