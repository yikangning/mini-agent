import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key=os.getenv("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1"
)

stream = client.chat.completions.create(
    model="moonshot-v1-8k",
    messages=[{"role": "user", "content": "你好，请回复一个字"}],
    stream=True,
)

for chunk in stream:
    print(f"CHUNK: {chunk}")
