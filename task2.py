import AI_analyse_V1 as analyser
import os
import pyperclip
import base64
import re
from playwright.sync_api import Page
import json
import time
import threading


class QualityCheckStep2():
    """修题逻辑"""

    # 根据题目与解答：
    # 1. 审查解答【手动修改】
    # 2. 审查考点【手动修改】
    # 3. 以源码格式输出分析与点评【自动输入】

    def __init__(self, log_callback, result_callback, alert_callback, input_num_for_AI: str, stop_signal: threading.Event):    
        self.log = log_callback
        self.result_log = result_callback
        self.alert = alert_callback
        self.stop = stop_signal
        self.analyser = analyser.Analyser()
        self._user_input = input_num_for_AI

        self.page_1: Page = None

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
            self.log("!!! 警告: 未找到题目全修改页面 (div.box-wrapper)")

    def encodebase64(self, img):
        # ... Base64编码 ...
        choices_path = img
        try:
            choices_base64 = ""
            if choices_path:
                with open(choices_path, "rb") as f:
                    choices_base64 = base64.b64encode(f.read()).decode("utf-8")
            else: return ''
            
            # 于此删除本地图片
            if os.path.exists(choices_path):
                os.remove(choices_path)
            return choices_base64
        
        except Exception as e:
            self.log(f"文件读取或删除错误: {e}")    
            return ""

    def execute(self):
        
        # 先保存当前页修改
        self.save()
        while not self.stop.is_set():  
                
            self.log("\n>>> 开始执行任务...")
            start_time = time.perf_counter()

            # 1. 截图
            imgs = self.choices_screenshot(self.page_1)
            if imgs == None : 
                self.log(f"***※截图失败※***")
                return

            self.log("2. 正在获取题目、答案、考点...")
            answer = self.copy_answer(self.page_1)
            keypoint = self.copy_keypoint(self.page_1)
            problem = self.copy_problem(self.page_1)
            
            # 跳过已经写入分析/点评的题目
            # analysis = self.copy_analysis(self.page_1)
            discuss = self.copy_discuss(self.page_1)
            if "略" not in discuss:
                self.next()
                self.log(f">>>此题跳过")
                continue


            # 构造识题消息
            choices_pic64 = self.encodebase64(imgs)
            choices_alltext = ''
            if choices_pic64 != '':
                self.log("3. 调用多模态LLM进行题目OCR...")
                content_payload = []
                content_payload.append({"type": "text", "text": "用latex源码仅输出图片识别内容。"})
                content_payload.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{choices_pic64}"}})
                choices_alltext = self.analyser.call_analyser(content_payload, '4') 
                print(choices_alltext)

            # 3. 审核 
            self.log("4. 提交与 AI 审核...")
            ai_output = self.analyze_answer(problem, choices_alltext, answer, keypoint, self._user_input)
            self.log(f">>> 审核结果已返回")
            
            # 发送结果到 GUI 进行渲染
            self.result_log(ai_output)
            print(ai_output)

            # 根据特定格式返回文本，尝试填写表单
            self.log(f"5. 正在改写表单...")
            if ai_output != "":
                try:
                    ai_output_formatted = self.formatize_ai_output2json(ai_output)
                    parsed_json = json.loads(ai_output_formatted)
                    self.fill_forms(self.page_1, parsed_json)
                    if parsed_json["problem"]["s"] == '0':
                        self.log(f"**题目**有误, 请参照msg修改或检查ocr。")            

                    if parsed_json["keypoint"]["s"] == '0':
                        self.log(f"**考点**有误, 请参照msg修改。")            

                    if parsed_json["answer"]["s"] == '0':
                        self.log(f"**解答**有误, 请参照msg修改。")            
                        
                    if parsed_json["problem"]["s"] == '0' or parsed_json["keypoint"]["s"] == '0' or parsed_json["answer"]["s"] == '0' :
                        self.alert("需参考console_log修改")
                        end_time = time.perf_counter()
                        self.log(f"本次任务已完成。")
                        self.log(f"本次任务耗时：{end_time-start_time:.2f}秒")
                        self.log(f"=" * 30)
                        break
                    self.save()
                    self.next()
                except Exception as e:
                    self.log(f"解析 JSON 或改写表单或alert失败: {e}")
                    print(f"异常，原始输出: {ai_output}")

            
            self.log(f"本次任务已完成。")
            end_time = time.perf_counter()
            self.log(f"本次任务耗时：{end_time-start_time:.2f}秒")
            self.log(f"=" * 30)

            self.stop.wait(3)
            if self.stop.is_set():
                break
        

    def choices_screenshot(self, operator_page: Page):
        '''截图题目，返回截图地址'''

        if not operator_page:
            self.log("目标页面未找到")
            return None

        problem_sn = ""
        save_path_choices = ""
        script_path = os.path.dirname(os.path.abspath(__file__))

        try:
            problem_sn = operator_page.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()
            self.log(f"当前题目SN: {problem_sn}")
        except Exception as e:
            self.log(f"***※未能找到题目SN※***: {e}")

        if problem_sn:
            try:
                choices_locator = operator_page.locator("table.qanwser")
                if choices_locator.is_visible():
                    self.log("1. 正在截图题目...")
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
 
        return save_path_choices if problem_sn else None
    
    
    def formatize_ai_output2json(self, ai_output: str):
        text = ai_output
        text = text.replace("```", "")
        text = text.replace("json\n", "")
        text = text.replace("\\\\", "\\")
        text = text.replace("\\", "\\\\")
        text = text.replace(" ", "")
        return text

    def copy_problem(self, page1: Page):
        problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()
        
        try:
            # 按页面元素交互逻辑复制解答
            page1.locator("div#Content_" + problem_sn).click()
            page1.locator("input.code").click()
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.click()
            page1.keyboard.press("Control+A")
            page1.keyboard.press("Control+C")
            content = pyperclip.paste()
            page1.locator("input.hclose:nth-child(2)").click()
            return content
        
        except Exception as e:
            self.log(f"搜索复制失败: {e}")
            return ""

    def copy_answer(self, page1: Page):
        problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()
        
        try:
            # 按页面元素交互逻辑复制解答
            page1.locator("div#Method_" + problem_sn).click()
            page1.locator("input.code").click()
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.click()
            page1.keyboard.press("Control+A")
            page1.keyboard.press("Control+C")
            content = pyperclip.paste()
            page1.locator("input.hclose:nth-child(2)").click()
            return content
        
        except Exception as e:
            self.log(f"搜索复制失败: {e}")
            return ""
        
    # 大部分分析与点评处于“略”的状态，无需审阅。
    # def copy_analysis(self, page1: Page):
    #     problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()
        
    #     try:
    #         # 按页面元素交互逻辑复制解答
    #         page1.locator("div#Analyse_" + problem_sn).click()
    #         page1.locator("input.code").click()
    #         iframe = page1.frame_locator("#htmlSourceFrame")
    #         textarea = iframe.locator("textarea#htmlSource")
    #         textarea.click()
    #         page1.keyboard.press("Control+A")
    #         page1.keyboard.press("Control+C")
    #         content = pyperclip.paste()
    #         page1.locator("input.hclose:nth-child(2)").click()
    #         return content
        
    #     except Exception as e:
    #         self.log(f"搜索复制失败: {e}")
    #         return ""
        
    def copy_discuss(self, page1: Page):
        problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()
        
        try:
            # 按页面元素交互逻辑复制
            page1.locator("div#Discuss_" + problem_sn).click()
            page1.locator("input.code").click()
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.click()
            page1.keyboard.press("Control+A")
            page1.keyboard.press("Control+C")
            content = pyperclip.paste()
            page1.locator("input.hclose:nth-child(2)").click()
            return content
        
        except Exception as e:
            self.log(f"搜索复制失败: {e}")
            return ""
        
    def copy_keypoint(self, page1: Page):
        unformatted = page1.locator("tbody:nth-child(2) > tr:nth-child(3) > td:nth-child(2)").first.inner_text()
        formatted = re.sub(r'\d+：','',unformatted).strip()
        formatted = re.sub(r'\n+',',',formatted)
        return formatted

    def analyze_answer(self, problem_text: str, choices_text: str, answer_text: str, keypoint_text: str, client_num) -> str:
        """调用 AI 审核并返回结果"""
        self.instruction = self.sys_instruct_AI()
        combined_content = f"{self.instruction}\n\nInputData：problem:{problem_text}\n{choices_text}\nkeypoint：{keypoint_text}\nanswer:{answer_text}\n"
        self.log("正在调用 AI API...")
        result = self.analyser.call_analyser(combined_content, client_num) 
        return result
    
    def fill_forms(self, page1: Page, data: dict):
        problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()

        try:
            # 填写分析
            page1.locator("div#Analyse_" + problem_sn).click()
            page1.locator("input.code").click()
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.fill(data["analysis"]["msg"].replace("。", "。\n"))
            iframe.locator("div:nth-child(3) > input:nth-child(3)").click()

            # 填写点评
            page1.locator("div#Discuss_" + problem_sn).click()
            page1.locator("input.code").click()
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.fill(data["discuss"]["msg"])
            iframe.locator("div:nth-child(3) > input:nth-child(3)").click()

            # 判断解答，并填写解答
            # 暂不直接于此解答
            # if data["answer"]["s"] !='1':
            #     page1.locator("div#Method_" + problem_sn).click()
            #     page1.locator("input.code").click()
            #     iframe = page1.frame_locator("#htmlSourceFrame")
            #     textarea = iframe.locator("textarea#htmlSource")
            #     textarea.fill(data["answer"]["msg"].replace("。", "。\n"))
            #     iframe.locator("div:nth-child(3) > input:nth-child(3)").click()

            # 填写难度
            page1.locator("input#Degree_" + problem_sn + "_" + str(data["difficulty"])).click() 
            self.log(f"填写完成。")           
         
        except Exception as e:
            self.log(f"fill_form func error")
            print(e)
            return
            
    def save(self):
        try:
            self.page_1.locator("button:nth-child(1)").click()   
        except Exception as e:
            print(e)
            
    def next(self):
        try:
            self.page_1.locator(".tablebar:nth-child(6) .tedit:nth-child(4)").click()
        except Exception as e:
            print(e)
