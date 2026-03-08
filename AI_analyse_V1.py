import os
from dotenv import load_dotenv
from openai import OpenAI
from google import genai

# ====================== 1. 加载配置 ======================
load_dotenv()  # 从 .env 文件加载环境变量

# ====================== 2. 初始化各客户端 ======================
# QWEN 客户端（OCR用，保留参考）
qwen_client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# DeepSeek 客户端
deepseek_client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# DUOBAO 客户端
doubao_client = OpenAI(
    api_key=os.getenv("DOUBAO_API_KEY"),
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)

# Google GenAI 客户端
google_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# ====================== 3. 通用审核调用核心类 ======================
class Reviewer:
    def __init__(self):
        # 客户端映射：key=选择编号，value=(名称, 通用调用函数)
        self.client_map = {
            "0": ("EXIT","NULL"),
            "1": ("DeepSeek", self._call_deepseek),
            "2": ("doubao", self._call_doubao),
            "3": ("Google Gemini", self._call_google),
        }

    def select_reviewer_client(self, num: str):
        # 循环校验输入
        while True:
            choice = num
            if choice in self.client_map:
                name, call_func = self.client_map[choice]
                print(f"已选择 {name} 作为审核客户端。")
                return call_func
            if choice == "0":
                print(f"退出审核系统。")
                exit(0)
            else:
                print(f"输入错误")

    def _call_deepseek(self, content: str) :
        """封装DeepSeek调用 + 结果解析"""
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": content}],
            stream=False
        )
        # 解析DeepSeek返回文本
        return response.choices[0].message.content

    def _call_doubao(self, content: str) :
        """封装DUOBAO调用 + 结果解析"""
        response = doubao_client.responses.create(
            model="doubao-seed-2.0-lite",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text", 
                            "text": content
                         }
                    ],
                }
            ]
        )
        # 解析DUOBAO返回文本
        return response.output_text

    def _call_google(self, content: str) :
        """封装Google Gemini调用 + 结果解析"""
        response = google_client.models.generate_content(
            model="gemini-flash-latest",
            contents=content
        )
        # 解析Gemini返回文本
        return response.text

    def review_analyser(self, content: str, num: str) -> str:
        """通用审核入口：一键调用，自动适配所有客户端"""
        call_func = self.select_reviewer_client(num)
        try:
            result = call_func(content)
            return result
        except Exception as e:
            return ""

# ====================== 4. 测试 ======================
if __name__ == "__main__":
    reviewer = Reviewer()
    # 测试审核（替换为你的实际内容）
    
    # for t1,t2 in reviewer.client_map.items():
    #     print(f"{t1}{t2[0]}")