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
    messages=[{"role": "user", "content": "1"}],
    stream=True,
)

for chunk in stream:
    print(f"\n---")
    print(f"chunk.usage: {getattr(chunk, 'usage', None)}")
    if len(chunk.choices) > 0:
        c0 = chunk.choices[0]
        print(f"c0.usage (getattr): {getattr(c0, 'usage', None)}")
        print(f"c0.__dict__: {c0.__dict__}")
        print(f"c0 model_dump: {c0.model_dump()}")
