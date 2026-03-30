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

# ====================== 3. 通用调用核心类 ======================
class Analyser:
    def __init__(self):
        # 客户端映射：key=选择编号，value=(名称, 通用调用函数)
        self.client_map = {
            "1": ("DeepSeek", self._call_deepseek),
            "2": ("doubao", self._call_doubao),
            "3": ("Google Gemini", self._call_google),
            "4": ("Qwen", self._call_qwen),
            "99": ("QwenVL", self._call_qwenvl)
        }

    def select_analyser_client(self, num: str):
        # 循环校验输入
        while True:
            choice = num
            if choice in self.client_map:
                name, call_func = self.client_map[choice]
                return call_func
            else:
                return self._call_google

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
            model="doubao-seed-2-0-lite-260215",
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
    
    def _call_qwen(self, content: str):
        """封装Qwen调用 + 结果解析"""
        response = qwen_client.chat.completions.create(
            model="qwen3.5-flash",
            messages=[{"role": "user", "content": content}],
            stream=False,
        )
        # 解析Qwen返回文本
        return(response.choices[0].message.content)
    
    def _call_qwenvl(self, content: str):
        """Qwen快速识别"""
        response = qwen_client.chat.completions.create(
            model="qwen3-vl-flash",
            messages=[{"role": "user", "content": content}],
            stream=False,
        )
        # 解析Qwen返回文本
        return(response.choices[0].message.content)

    def call_analyser(self, content: str, num: str) -> str:
        """通用审核入口：一键调用，自动适配所有客户端"""
        call_func = self.select_analyser_client(num)
        try:
            result = call_func(content)
            return result
        except Exception as e:
            print(f"API调用失败: {e}")
            return f"Error: API调用失败 - {e}"
