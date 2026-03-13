import AI_analyse_V1 as analyser
import os
import pyperclip
import base64
import re

class QualityCheckStep2():
    """收尾逻辑"""

    # 根据题目与解答：
    # 1. 审查解答【手动修改】
    # 2. 审查考点【手动修改】
    # 3. 以源码格式输出分析与点评【自动输入】

    def __init__(self, log_callback, result_callback, input_num_for_AI: str):    
        self.log = log_callback
        self.result = result_callback
        self.analyser = analyser.Analyser()
        self._user_input = input_num_for_AI

        self.page_1 = None

        # 待作为外置配置文件
        self.instruction = ""

    def sys_instruct_AI(self):
        with open("task1_sys_instruct.txt", 'r', encoding='utf-8') as f:
            return f.read().strip()

    def locate_pages(self, pages):
        for page in pages:
            try:
                if page.locator("input#SStatus_3").is_visible(timeout=500):
                    self.page_1 = page
                    self.log(f"已锁定题目全修改页面: {page.title()}")
            except:
                continue
        
        if not self.page_1:
            self.log("!!! 警告: 未找到题目页面 (div.box-wrapper)")

    def encodebase64(self, imgs: list):
        # ... Base64编码 ...
        (choices_path, problem_path) = imgs
        try:
            with open(problem_path, "rb") as f:
                problem_base64 = base64.b64encode(f.read()).decode("utf-8")
            choices_base64 = ""
            if choices_path:
                with open(choices_path, "rb") as f:
                    choices_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            # 于此删除本地图片
            os.remove(problem_path)
            if choices_path:
                os.remove(choices_path)
            return (problem_base64, choices_base64)
        
        except Exception as e:
            self.log(f"文件读取错误: {e}")    

    def execute(self):

        self.log("\n>>> 开始执行任务...")
        problem_alltext = ""

        # 1. 截图
        self.log("1. 正在截图题目...")
        imgs = self.problem_screenshot(self.page_1)
        if imgs == None : 
            self.log(f"！！！截图失败！！！")
            return

        self.log("2. 正在获取答案与考点...")
        answer = self.copy_answer(self.page_1)
        keypoint = self.copy_keypoint(self.page_1)

        # 2. OCR (Qwen)
        self.log("3. 调用多模态LLM进行题目OCR...")

        # 构造消息
        problem_pic64, choices_pic64 = self.encodebase64(self.problem_screenshot(self.page_1))
        content_payload = []
        content_payload.append({"type": "text", "text": "用latex源码仅输出图片识别内容。"})
        content_payload.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{problem_pic64}"}})
        if choices_pic64:
            content_payload.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{choices_pic64}"}})

        problem_alltext = self.analyser.call_analyser(content_payload, '4') 
        print(problem_alltext)

        # 3. 审核 
        self.log("4. 提交与 AI 审核...")
        final_result = self.analyze_answer(problem_alltext, answer, keypoint, self._user_input)
        ai_output = ""
        ai_output = final_result
        self.log(f">>> 审核结果已返回")
        
        # 发送结果到 GUI 进行渲染
        self.result(ai_output)
        
        self.log(f"本次任务已完成。")
        self.log('='*20)

    def problem_screenshot(self, operator_page):
        '''截图题目，返回截图地址'''

        if not operator_page:
            self.log("目标页面未找到")
            return None

        problem_sn = ""
        save_path_choices = ""
        save_path_problem = ""
        script_path = os.path.dirname(os.path.abspath(__file__))

        try:
            problem_sn = operator_page.locator("td > a").first.inner_text()
            self.log(f"当前题目SN: {problem_sn}")
        except Exception as e:
            self.log(f"***※未能找到题目SN※***: {e}")

        if problem_sn:
            try:
                choices_locator = operator_page.locator("table.qanswer")
                if choices_locator.is_visible():
                    save_path_choices = script_path + f"{problem_sn}_problem_choices.png"
                    clone_handle = choices_locator.evaluate_handle("""original => {
                        const clone = original.cloneNode(true);
                        Object.assign(clone.style, {
                            position: 'absolute', top: '0', left: '0', width: 'auto',
                            height: 'auto', maxHeight: 'none', overflow: 'visible',
                            zIndex: '2147483647', backgroundColor: '#ffffff', padding: '20px'
                        });
                        document.body.appendChild(clone);
                        return clone;
                    }""")
                    clone_handle.screenshot(path=save_path_choices)
                    clone_handle.evaluate("el => el.remove()")
                else:
                    self.log("※非选择题※")
            except Exception as e:
                self.log(f"***※选项截图失败※***: {e}")
            
            try:
                problem_locator = operator_page.locator("div#Content_" + problem_sn)
                if problem_locator.is_visible():
                    save_path_problem = script_path + f"{problem_sn}_problem.png"
                    clone_handle = problem_locator.evaluate_handle("""original => {
                        const clone = original.cloneNode(true);
                        Object.assign(clone.style, {
                            position: 'absolute', top: '0', left: '0', width: 'auto',
                            height: 'auto', maxHeight: 'none', overflow: 'visible',
                            zIndex: '2147483647', backgroundColor: '#ffffff', padding: '20px'
                        });
                        document.body.appendChild(clone);
                        return clone;
                    }""")
                    clone_handle.screenshot(path=save_path_problem)
                    clone_handle.evaluate("el => el.remove()")
                else:
                    self.log("***※未能找到题目元素※***")
            except Exception as e:
                self.log(f"题目截图错误: {e}")
 
        return (save_path_choices, save_path_problem) if problem_sn else None

    def copy_answer(self, page1):
        problem_sn = page1.locator("td > a").first.inner_text()
        
        try:
            # 按页面元素交互逻辑复制解答
            page1.locator("div#Method_" + problem_sn).click()
            page1.locator("input.code").click()
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.click()
            page1.keyboard.press("Control+A")
            page1.keyboard.press("Control+C")
            return pyperclip.paste()
            page1.locator("input.hclose:nth-child(2)").click()
        
        except Exception as e:
            self.log(f"搜索复制失败: {e}")
            return ""
        
    def copy_keypoint(self, page1):
        unformatted = page1.locator("tbody:nth-child(2) > tr:nth-child(3) > td:nth-child(2)").first.inner_text()
        formatted = re.sub(r'\d+:','',unformatted).strip()
        formatted = re.sub(r'\n+',',',formatted)
        return formatted

    def analyze_answer(self, problem_text: str, answer_text: str, keypoint_text: str, client_num) -> str:
        """调用 AI 审核并返回结果"""
        self.instruction = self.sys_instruct_AI()
        combined_content = f"{self.instruction}\n题目（可能有误）:\n{problem_text}\n考点：{keypoint_text}\n解答:\n{answer_text}\n"
        self.log("正在调用 AI API...")
        result = self.analyser.call_analyser(combined_content, client_num) 
        return result
