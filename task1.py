import AI_analyse_V1 as Analyser
import os
import pyperclip
import base64

class QualityCheckStep1():
    """审题逻辑"""

    def __init__(self, log_callback, result_callback, input_num_for_AI: str):    
        self.log = log_callback
        self.result = result_callback
        self.reviewer = Analyser.Reviewer()
        self._user_input = input_num_for_AI
        self.page_1 = None
        self.page_2 = None

    def locate_pages(self, pages):
        for page in pages:
            try:
                if page.locator("div.box-wrapper").is_visible(timeout=500):
                    self.page_1 = page
                    self.log(f"已锁定题目页面: {page.title()}")
                elif page.locator("input#SName").is_visible(timeout=500):
                    self.page_2 = page
                    self.log(f"已锁定搜索页面: {page.title()}")
            except:
                continue
        
        if not self.page_1:
            self.log("!!! 警告: 未找到题目页面 (div.box-wrapper)")

    def execute(self):

        # self.page_1.on("dialog", self.manual_check)

        self.log("\n>>> 开始执行任务...")
        problem_alltext = ""

        # 1. 截图
        self.log("1. 正在截图题目...")
        imgs = self.problem_screenshot(self.page_1)
        if imgs == None : 
            self.log(f"！！！截图失败！！！")
            return
        (choices_path, problem_path) = imgs

        self.log("2. 正在获取答案...")
        answer = self.jump_and_search_copy_and_return(self.page_1, self.page_2)

        # 2. OCR (Qwen)
        self.log("3. 调用多模态LLM进行 OCR...")
        
        # ... Base64编码 ...
        try:
            with open(problem_path, "rb") as f:
                problem_base64 = base64.b64encode(f.read()).decode("utf-8")
            choices_base64 = ""
            if choices_path:
                with open(choices_path, "rb") as f:
                    choices_base64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            self.log(f"文件读取错误: {e}")
        
        # 于此删除本地图片
        os.remove(problem_path)
        if choices_path:
            os.remove(choices_path)

        # 构造消息
        content_payload = []
        content_payload.append({"type": "text", "text": "用latex源码仅输出图片识别内容。"})
        content_payload.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{problem_base64}"}})
        if choices_path:
            content_payload.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{choices_base64}"}})

        problem_response = Analyser.qwen_client.chat.completions.create(
            model="qwen3-vl-flash",
            messages=[{"role": "user", "content": content_payload}],
            stream=True,
            stream_options={"include_usage": True},
        )

        for chunk in problem_response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    problem_alltext += delta.content
        print(problem_alltext)

        # 3. 审核 
        self.log("4. 提交与 AI 审核...")
        final_result = self.analyze_answer(problem_alltext, answer, self._user_input)
        ai_output = ""
        ai_output = final_result
        self.log(f">>> 审核结果已返回")
        
        # 发送结果到 GUI 进行渲染
        self.result(ai_output)
        
        self.log(f"本次任务已完成。")
        self.log('='*20)

    def problem_screenshot(self, operator_page):
        '''依靠特定页面元素定位，对题目进行截图'''

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
                choices_locator = operator_page.locator("table.ques")
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
                problem_locator = operator_page.locator("div#Mark_Content_" + problem_sn)
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

    def jump_and_search_copy_and_return(self, page1, page2):
        '''依照特定页面逻辑与元素，获取题目答案'''

        if not page2: return "无法获取第二页面"
        problem_sn = page1.locator("td > a").first.inner_text()
        
        try:
            page2.bring_to_front()
            search_input = page2.locator("input#SName")
            search_button = page2.locator("input#SSearch")
            search_input.fill(problem_sn)
            search_button.click()
            page2.locator("div#Method_" + problem_sn).click()
            page2.locator("input.code").click()
            
            iframe = page2.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.click()
            page2.keyboard.press("Control+A")
            page2.keyboard.press("Control+C")
            answer = pyperclip.paste()
            page2.locator("input.hclose:nth-child(2)").click()
            page1.bring_to_front()
            return answer
        except Exception as e:
            self.log(f"搜索复制失败: {e}")
            page1.bring_to_front()
            return ""

    def analyze_answer(self, problem_text: str, answer_text: str , client_num) -> str:
        """调用 AI 审核并返回结果"""
        combined_content = f"题目内容:\n{problem_text}\n\n参考答案:\n{answer_text}\n\n就解题准确性、思路笨重性进行审核，并对题目进行简评。"
        self.log("正在调用 AI API...")
        result = self.reviewer.review_analyser(combined_content, client_num) 
        return result
