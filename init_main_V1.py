import os
import sys
import time
import base64
import keyboard
import pyperclip
import markdown

# PyQt6 导入
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,  QPushButton,
                              QTextEdit, QSplitter, QLabel, QInputDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QEventLoop
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtGui import QColor

# 导入 Playwright
from playwright.sync_api import sync_playwright

try:
    # import ocr_processing_tencent_tailscale as Ocr_Processor
    import AI_analyse_V1 as Analyser
except ImportError as e:
    print(f"Error importing modules: {e}")

# ---------------- 
os.environ["QT_OPENGL"] = "software"  
os.environ["QT_XCB_FORCE_SOFTWARE_OPENGL"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
# ---------------- 

# ==========================================
# 1. 原始逻辑封装 (Worker Thread)
# ==========================================

class AutomationWorker(QThread):
    log_signal = pyqtSignal(str)      # 用于发送日志
    result_signal = pyqtSignal(str)   # 用于发送 AI 最终结果 (Markdown)
    input_signal = pyqtSignal(str)    # 用于接收用户输入
    _user_input = ""
    _loop = None


    def __init__(self):
        super().__init__()
        self.running = True
        self.reviewer = Analyser.Reviewer()
        self._user_input = None
        self._loop = None
        self.playwright = None
        self.browser = None


    def run(self):
        self.re_init_locator()

    def manual_check(self, dialog):
            print(f"弹窗出现了")
            time.sleep(2) 
            try:
                dialog.accept() 
            except:
                pass

    def initialize(self):
        self.log_signal.emit(">>> 初始化 Playwright 连接...")
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            return 
        except Exception as e:
            self.log_signal.emit(f"连接失败: {str(e)}")
            self.close_all_browser() 
            return None

    def close_all_browser(self):
        """记得在程序退出或不需要时手动关闭"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


    def re_init_locator(self):
        self.initialize()
        default_context = self.browser.contexts[0]
        pages = default_context.pages
                
        target_page_1 = None
        target_page_2 = None

        for page in pages:
            try:
                if page.locator("div.box-wrapper").is_visible(timeout=500):
                    target_page_1 = page
                    self.log_signal.emit(f"已锁定题目页面: {page.title()}")
                elif page.locator("input#SName").is_visible(timeout=500):
                    target_page_2 = page
                    self.log_signal.emit(f"已锁定搜索页面: {page.title()}")
            except:
                continue
        
        if not target_page_1:
            self.log_signal.emit("!!! 警告: 未找到题目页面 (div.box-wrapper)")
        
        self.hotkey_listener(target_page_1, target_page_2)



    def problem_screenshot(self, operator_page):
        if not operator_page:
            self.log_signal.emit("目标页面未找到")
            return None

        problem_sn = ""
        save_path_choices = ""
        save_path_problem = ""
        script_path = os.path.dirname(os.path.abspath(__file__))

        try:
            problem_sn = operator_page.locator("td > a").first.inner_text()
            self.log_signal.emit(f"当前题目SN: {problem_sn}")
        except Exception as e:
            self.log_signal.emit(f"***※未能找到题目SN※***: {e}")

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
                    self.log_signal.emit("※非选择题※")
            except Exception as e:
                self.log_signal.emit(f"***※选项截图失败※***: {e}")
            
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
                    self.log_signal.emit("***※未能找到题目元素※***")
            except Exception as e:
                self.log_signal.emit(f"题目截图错误: {e}")
 
        return (save_path_choices, save_path_problem) if problem_sn else None   

    '''拒绝此读图方案'''
    # def answer_screenshot(self, Operator_page):
    #     if not Operator_page: return None
    #     problem_sn = ""
    #     save_path = ""
    #     try:
    #         problem_sn = Operator_page.locator("td > a").first.inner_text()
    #         if problem_sn:
    #             answer_locator = Operator_page.locator("div#Mark_Method_" + problem_sn)
    #             if answer_locator.is_visible():
    #                 save_path = f"E:/131_pyCoding/截图/{problem_sn}_answer.png"
    #                 clone_handle = answer_locator.evaluate_handle("""original => {
    #                     const clone = original.cloneNode(true);
    #                     Object.assign(clone.style, {
    #                         position: 'absolute', top: '0', left: '0', width: 'auto',
    #                         height: 'auto', maxHeight: 'none', overflow: 'visible',
    #                         zIndex: '2147483647', backgroundColor: '#ffffff', padding: '20px'
    #                     });
    #                     document.body.appendChild(clone);
    #                     return clone;
    #                 }""")
    #                 clone_handle.screenshot(path=save_path)
    #                 clone_handle.evaluate("el => el.remove()")
    #     except Exception as e:
    #         self.log_signal.emit(f"***※答案截图失败※***: {e}")
    #     return save_path if problem_sn else None

    def jump_and_search_copy_and_return(self, page1, page2):
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
            self.log_signal.emit(f"搜索复制失败: {e}")
            page1.bring_to_front()
            return ""

    def client_select_request(self):
        """选择 AI 审核客户端"""
        ls = []
        self.log_signal.emit(f"*" * 20)
        self.log_signal.emit("请预先确认 VPN 已正确配置")
        self.log_signal.emit(f"*" * 20)
        self.log_signal.emit("请选择 AI 审核客户端:")
        for num, name in self.reviewer.client_map.items():
            self.log_signal.emit(f"{num} . {name[0]}")
            ls.append(num)

        self._loop = QEventLoop()
        self.input_signal.emit("选择数字:")
        self._loop.exec()

    def client_receive_input(self, data):
        if data:
            self._user_input = data
        else: 
            self._user_input = "3"
        if self._loop:
            self._loop.quit()
        
    def analyze_answer(self, problem_text: str, answer_text: str , client_num) -> str:
        """调用 AI 审核并返回结果"""
        combined_content = f"题目内容:\n{problem_text}\n\n参考答案:\n{answer_text}\n\n就解题准确性、思路笨重性进行审核，并对题目进行简评。"
        self.log_signal.emit("正在调用 AI API...")
        result = self.reviewer.review_analyser(combined_content, client_num) 
        return result
    

    def hotkey_listener(self, page_obj_1, page_obj_2):
        HOTKEY = 'ctrl+alt+z'
        self.client_select_request()
        num = self._user_input
        self.log_signal.emit(f"{'='*30}")
        self.log_signal.emit(f" 监听启动: 按下 [{HOTKEY}] 开始")
        self.log_signal.emit(f"{'='*30}")

        while self.running:
            
            page_obj_1.on("dialog", self.manual_check)
            try:
                keyboard.wait(HOTKEY)
                self.log_signal.emit("\n>>> 开始执行任务...")
                
                problem_alltext = ""

                # 1. 截图
                self.log_signal.emit("1. 正在截图题目...")
                imgs = self.problem_screenshot(page_obj_1)
                if not imgs: continue
                (choices_path, problem_path) = imgs

                self.log_signal.emit("2. 正在获取答案...")
                # answer_path = self.answer_screenshot(page_obj_1)
                answer = self.jump_and_search_copy_and_return(page_obj_1, page_obj_2)

                # 2. OCR (Qwen)
                self.log_signal.emit("3. 调用 多模态LLM 进行 OCR...")
                
                # ... Base64编码 ...
                try:
                    with open(problem_path, "rb") as f:
                        problem_base64 = base64.b64encode(f.read()).decode("utf-8")
                    choices_base64 = ""
                    if choices_path:
                        with open(choices_path, "rb") as f:
                            choices_base64 = base64.b64encode(f.read()).decode("utf-8")
                except Exception as e:
                    self.log_signal.emit(f"文件读取错误: {e}")
                    continue
                
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
                
                # self.log_signal.emit("OCR 完成。")

                # 3. 审核 
                self.log_signal.emit("4. 提交与 AI 审核...")
                final_result = self.analyze_answer(problem_alltext, answer, num)
                ai_output = ""
                ai_output = final_result
                self.log_signal.emit(f">>> 审核结果已返回")
                
                # 发送结果到 GUI 进行渲染
                self.result_signal.emit(ai_output)
                
                time.sleep(0.5)
                self.log_signal.emit(f"等待下一次快捷键[{HOTKEY}]...")
                self.log_signal.emit('='*20)


            except Exception as e:
                self.log_signal.emit(f"Critical Error: {e}")
                time.sleep(1)


# ==========================================
# 2. GUI 主窗口
# ==========================================

class LogRedirector(QObject):
    """捕获 stdout 并发送信号"""
    text_written = pyqtSignal(str)
    def write(self, text):
        self.text_written.emit(str(text))
    def flush(self):
        pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()        

        # 窗口设置
        self.setWindowTitle("Auto-Check HUD")
        self.resize(600, 800)
        
        # *** 关键：始终置顶 ***
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        # 样式表 (Dark Mode)
        self.setStyleSheet("""
            QInputDialog { background-color: #2b2b2b; }
            QMainWindow { background-color: #2b2b2b; }
            QTextEdit { 
                background-color: #1e1e1e; 
                color: #00ff00; 
                font-family: Consolas; 
                font-size: 10pt;
                border: 1px solid #444;
            }
            QLabel { color: white; font-weight: bold; padding: 5px;}
        """)

        # 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 分割器 (上下拖动)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 上半部分：日志控制台
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.addWidget(QLabel("运行日志 (Console)"))
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        log_layout.addWidget(self.console_output)
        
        # 下半部分：Markdown 结果渲染器
        result_container = QWidget()
        result_layout = QVBoxLayout(result_container)
        result_layout.addWidget(QLabel("AI 审核结果 (Markdown/LaTeX)"))
        
        self.browser = QWebEngineView()
        page0 = self.browser.page()
        if page0:
            page0.setBackgroundColor(QColor("#2b2b2b"))
        result_layout.addWidget(self.browser)

        result_layout.setStretch(0, 0) # 标签不拉伸，保持最小高度
        result_layout.setStretch(1, 1) # 浏览器拉伸，占用剩余空间

        splitter.addWidget(log_container)
        splitter.addWidget(result_container)
        splitter.setSizes([200,600]) # 默认高度比例

        layout.addWidget(splitter)

        # --- 新增部分：底部按钮区域 ---
        button_layout = QHBoxLayout()
        # 如果你希望按钮靠右对齐，可以先加一个弹簧 (Spacer)
        button_layout.addStretch() 

        self.btn1 = QPushButton("输出 1")
        self.btn2 = QPushButton("输出 2")

        # 连接信号（这里演示输出到控制台和日志框）
        self.btn1.clicked.connect(lambda: self.handle_button_click("1"))
        self.btn2.clicked.connect(lambda: self.handle_button_click("2"))

        button_layout.addWidget(self.btn1)
        button_layout.addWidget(self.btn2)

        # 将按钮布局添加到主垂直布局的最下方
        layout.addLayout(button_layout)

        # 启动后台线程
        self.worker = AutomationWorker()
        self.worker.log_signal.connect(self.update_log)
        self.worker.result_signal.connect(self.render_markdown)
        self.worker.input_signal.connect(self.receive_input)
        self.worker.start()

    # 简单的处理函数
    def handle_button_click(self, value):
        print(value)  # 在终端打印
        self.console_output.append(f"按钮按下: {value}") # 在 UI 日志框显示

    def receive_input(self, prompt):
        """接收输入请求并显示对话框"""
        while True:
            text, ok = QInputDialog.getText(self, "用户输入", prompt)
            if ok and text in self.worker.reviewer.client_map:
                self.worker.client_receive_input(text)
                break

    def update_log(self, text):
        self.console_output.append(text.strip())

    def render_markdown(self, markdown_text):
        def texreplace(text):
            # 先把双反斜杠转义，防止被 Markdown 吃掉
            # 这一步非常激进，建议仅针对公式块处理，但在简单场景下可用
            text = text.replace('\\', '\\\\') 
            return text
        
        markdown_text = texreplace(markdown_text) 
        
        md_extensions = [
            'fenced_code', 
            'tables', 
        ]
        
        rendered_md = markdown.markdown(
            markdown_text,
            extensions=md_extensions,
        )
        
        html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                
                <!-- 1. 定义配置 (必须在加载库之前) -->
                <script>
                window.MathJax = {{
                    tex: {{
                        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                        displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
                        processEscapes: true
                    }},
                    startup: {{
                        // 2. 关键修复：使用 pageReady 回调
                        // 这个函数会在 MathJax 库加载完成且 DOM 准备好后自动调用
                        pageReady: () => {{
                            console.log('MathJax 开始渲染...');
                            return MathJax.startup.defaultPageReady().then(() => {{
                                console.log('MathJax 渲染完成');
                            }});
                        }}
                    }}
                }};
                </script>
                
                <!-- 3. 加载库 (移除 polyfill，只留 MathJax) -->
                <script id="MathJax-script" src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
                
                <style>
                    body {{
                        background-color: #2b2b2b;
                        color: #e0e0e0;
                        font-family: "Segoe UI", sans-serif;
                        padding: 15px;
                        line-height: 1.6;
                    }}
                    code {{
                        background-color: #444;
                        padding: 2px 5px;
                        border-radius: 3px;
                    }}
                    pre {{
                        background-color: #111;
                        padding: 10px;
                        border-radius: 5px;
                        overflow-x: auto;
                    }}
                    /* 强制公式颜色适配深色模式 */
                    mjx-container {{ color: #e0e0e0 !important; }}
                </style>
            </head>
            <body>
                {rendered_md}
                
                <!-- 4. 底部不再需要手动触发脚本，配置里的 pageReady 会自动处理 -->
            </body>
            </html>
        """
        self.browser.setHtml(html_content)

    def closeEvent(self, event):
        self.worker.running = False
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())