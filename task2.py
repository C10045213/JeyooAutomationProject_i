import AI_analyse_V1 as analyser
import os
import pyperclip
import base64
import re
from playwright.sync_api import Page
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError


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
        with open("task2_sys_instruct.txt", 'r', encoding='utf-8') as f:
            return f.read().strip()

    def locate_pages(self, pages):
        for page in pages:
            try:
                if page.locator("input#SStatus_3").is_visible(timeout=500):
                    self.page_1 = page
                    self.log(f"已锁定题目全修改页面: {page.title()}")
            except:
                self.log(f"页面定位异常。")
        
        if not self.page_1:
            self.log("!!! 警告: 未找到题目全修改页面")

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
        
        if self.page_1 == None:
            self.log(f"页面未定位，非法操作。")
            return
        
        if self.page_1.locator("input#SStatus_3").is_visible(timeout=500) == 0:
            self.log(f"非目标页面，请重连。")
            return

        if self.page_1.is_closed():
            self.log(f"***※目标页面已关闭※***")
            return 
        
        # 先保存当前页修改
        self.save()
        if self.stop.is_set():
            self.log(f"***※已终止※***")

        while not self.stop.is_set():  
                
            self.log("\n>>> 开始执行任务...")
            start_time = time.perf_counter()
            self.page_1.locator(".tablebar:nth-child(2) > h2 > input").is_visible(timeout=500)
            num = self.page_1.locator(".tablebar:nth-child(2) > h2 > input").get_attribute("value")

            # 1. 截图
            imgs = self.choices_screenshot(self.page_1)
            if imgs == None : 
                self.log(f"***※截图失败※***")
                self.stop.set()
                return
            
            # analysis = self.copy_analysis(self.page_1)
            discuss = self.copy_discuss(self.page_1)
            if "略" not in discuss:
                self.next()
                self.log(f"当前页码：{num}，>>>此题跳过")
                if self.stop.is_set():
                    self.log(f"***※已终止※***")
                    return
                continue
            else:
                self.log("2. 正在获取题目、答案、考点...")
                problem = self.copy_problem(self.page_1)
                answer = self.copy_answer(self.page_1)
                keypoint = self.copy_keypoint(self.page_1)


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
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.analyze_answer, problem, choices_alltext, answer, keypoint, self._user_input)
                try:
                    result = future.result(timeout=60)
                    ai_output = result
                    self.log(f">>> 审核结果已返回")
                except TimeoutError:
                    ai_output = ""
                    self.log(f"等待response返回超时。")
                    return
            
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
                        self.log(f"**解答**有误, 请参照msg自行或复制与AI修改。")
                        self.log("*" * 20)
                        self.log(problem)
                        self.log(choices_alltext)
                        self.log(answer)  
                        self.log("*" * 20)          
                        
                    if parsed_json["problem"]["s"] == '0' or parsed_json["keypoint"]["s"] == '0' or parsed_json["answer"]["s"] == '0' :
                        self.alert("需参考console_log修改")
                        end_time = time.perf_counter()
                        self.log(f"本次任务已结束。")
                        self.log(f"本次任务耗时：{end_time-start_time:.2f}秒")
                        self.log(f"=" * 30)
                        return

                    if len(re.sub(r'[^\u4e00-\u9fff]', "", parsed_json["analysis"]["msg"])) > 50 or "解答" in parsed_json["analysis"]["msg"] or "涉及" in parsed_json["analysis"]["msg"]:
                        self.alert("请检查AI输出")
                        end_time = time.perf_counter()
                        self.log(f"本次任务已结束。")
                        self.log(f"本次任务耗时：{end_time-start_time:.2f}秒")
                        self.log(f"=" * 30)
                        return
                    
                    # 注意检查输出
                    self.page_1.wait_for_timeout(2000)
                    self.save()
                    self.page_1.wait_for_timeout(200)
                    self.next()
                except Exception as e:
                    self.log(f"解析 JSON 或改写表单或alert失败: {e}")
                    print(f"异常，原始输出: {ai_output}")
                    return

            
            self.log(f"当前页码：{num}，本次任务已完成。")
            end_time = time.perf_counter()
            self.log(f"本次任务耗时：{end_time-start_time:.2f}秒")
            self.log(f"=" * 30)

            if self.stop.is_set():
                self.log(f"***※已终止※***")
                return

            self.stop.wait(3)
        

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
            self.stop.set()

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
                self.stop.set()
 
        return save_path_choices if problem_sn else None
    
    
    def formatize_ai_output2json(self, ai_output: str):
        text = ai_output
        text = text.replace("```", "")
        text = text.replace("json\n", "")
        text = text.replace("\\\\", "\\")
        text = text.replace("\\", "\\\\")
        text = text.replace(" ", "")
        text = text.replace("【", "")
        text = text.replace("】", "")
        text = text.replace(">", "＞")
        text = text.replace("<", "＜")
        return text

    def copy_problem(self, page1: Page):
        problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()
        
        try:
            # 按页面元素交互逻辑复制解答
            page1.locator("div#Content_" + problem_sn).click()
            page1.wait_for_timeout(200)
            page1.locator("input.code").click()
            page1.wait_for_timeout(200)
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.click()
            page1.keyboard.press("Control+A")
            page1.keyboard.press("Control+C")
            content = pyperclip.paste()
            page1.locator("input.hclose:nth-child(2)").click()
            page1.wait_for_timeout(200)
            return content
        
        except Exception as e:
            self.log(f"搜索复制失败: {e}")
            self.stop.set()
            return ""

    def copy_answer(self, page1: Page):
        problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()
        
        try:
            # 按页面元素交互逻辑复制解答
            page1.locator("div#Method_" + problem_sn).click()
            page1.wait_for_timeout(200)
            page1.locator("input.code").click()
            page1.wait_for_timeout(200)
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.click()
            page1.keyboard.press("Control+A")
            page1.keyboard.press("Control+C")
            content = pyperclip.paste()
            page1.locator("input.hclose:nth-child(2)").click()
            page1.wait_for_timeout(200)
            return content
        
        except Exception as e:
            self.log(f"搜索复制失败: {e}")
            self.stop.set()
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
    #         self.stop.set()
    #         return ""
        
    def copy_discuss(self, page1: Page):
        problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()
        
        try:
            # 按页面元素交互逻辑复制
            page1.locator("div#Discuss_" + problem_sn).click()
            page1.wait_for_timeout(200)
            page1.locator("input.code").click()
            page1.wait_for_timeout(200)
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.click()
            page1.keyboard.press("Control+A")
            page1.keyboard.press("Control+C")
            content = pyperclip.paste()
            page1.locator("input.hclose:nth-child(2)").click()
            page1.wait_for_timeout(200)
            return content
        
        except Exception as e:
            self.log(f"搜索复制失败: {e}")
            self.stop.set()
            return ""
        
    def copy_keypoint(self, page1: Page):
        unformatted = page1.locator("tbody:nth-child(2) > tr:nth-child(3) > td:nth-child(2)").first.inner_text()
        formatted = re.sub(r'\d+：','',unformatted).strip()
        formatted = re.sub(r'\n+',',',formatted)
        return formatted

    def analyze_answer(self, problem_text: str, choices_text: str, answer_text: str, keypoint_text: str, client_num) -> str:
        """调用 AI 审核并返回结果"""
        self.log(f"正在调用 AI API...")
        self.instruction = self.sys_instruct_AI()
        combined_content = f"{self.instruction}\n\nInputData：problem:{problem_text}\n{choices_text}\nkeypoint：{keypoint_text}\nanswer:{answer_text}\n"
        result = self.analyser.call_analyser(combined_content, client_num) 
        return result

    
    def fill_forms(self, page1: Page, data: dict):
        problem_sn = page1.locator("td:nth-child(2) > a:nth-child(2)").first.inner_text()

        try:
            # 填写分析
            page1.locator("div#Analyse_" + problem_sn).click()
            page1.wait_for_timeout(200)
            page1.locator("input.code").click()
            page1.wait_for_timeout(200)
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.fill(data["analysis"]["msg"].replace("。", "。\n"))
            iframe.locator("div:nth-child(3) > input:nth-child(3)").click()
            page1.wait_for_timeout(200)

            # 填写点评
            page1.locator("div#Discuss_" + problem_sn).click()
            page1.wait_for_timeout(200)
            page1.locator("input.code").click()
            page1.wait_for_timeout(200)
            iframe = page1.frame_locator("#htmlSourceFrame")
            textarea = iframe.locator("textarea#htmlSource")
            textarea.fill(data["discuss"]["msg"])
            iframe.locator("div:nth-child(3) > input:nth-child(3)").click()
            page1.wait_for_timeout(200)

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
            self.log(f"***※填表异常※***")
            print(e)
            self.stop.set()
            return
            
    def save(self):
        try:
            self.page_1.get_by_role('button',name='保存').click()
        except Exception as e:
            self.log(f"***※保存异常※***")
            print(e)
            self.stop.set()
            
    def next(self):
        try:
            self.page_1.locator(".tablebar:nth-child(2) .tedit:nth-child(4)").click()
        except Exception as e:
            self.log(f"***※翻页异常※***")
            print(e)
            self.stop.set()
