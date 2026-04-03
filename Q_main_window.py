import os
import sys
import markdown
import re

# PyQt6 导入
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,  QPushButton,
                              QTextEdit, QSplitter, QLabel, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtGui import QColor

from automation_worker import AutomationWorker

# ==========================================
# GUI 主窗口
# ==========================================

os.environ["QT_OPENGL"] = "software"  
os.environ["QT_XCB_FORCE_SOFTWARE_OPENGL"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"


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
        self.resize(450, 800)
        
        # *** 关键：始终置顶 ***
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        # 样式表 (Dark Mode)
        self.setStyleSheet("""
            /* 1. 统一窗口背景 */
            QMainWindow, QDialog, QMessageBox { 
                background-color: #2b2b2b; 
                color: white; 
            }

            /* 2. 修复文本显示（核心修复） */
            QLabel { 
                color: #ffffff; 
                font-weight: bold; 
                /* 不要在这里写全局 padding，否则会干扰所有小控件 */
            }

            /* 3. 专门针对控制台/文本框的样式 */
            QTextEdit { 
                background-color: #1e1e1e; 
                color: #00ff00; 
                font-family: 'Consolas', 'Courier New', monospace; 
                font-size: 10pt;
                border: 1px solid #444;
                padding: 5px;
            }

            /* 4. 让对话框里的按钮也变酷一点 */
            QPushButton {
                background-color: #444;
                color: white;
                border: 1px solid #666;
                padding: 5px 15px;
                border-radius: 3px;
                min-width: 45px;
            }
            QPushButton:hover {
                background-color: #555;
                border: 1px solid #00ff00; /* 悬停时显示科技绿边框 */
            }
            QPushButton:pressed {
                background-color: #222;
            }

            /* 5. 针对 QInputDialog 的特殊处理 */
            QInputDialog {
                background-color: #2b2b2b;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: white;
                border: 1px solid #444;
                padding: 3px;
            }
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

        # 启动后台线程
        self.worker = AutomationWorker()
        self.worker.log_signal.connect(self.update_log)
        self.worker.result_signal.connect(self.render_markdown)
        self.worker.input_signal.connect(self.receive_input)
        self.worker.critical_signal.connect(self.msg_critical)
        self.worker.start()

        # --- 新增部分：底部按钮区域 ---
        button_layout = QHBoxLayout()
        # 如果你希望按钮靠右对齐，可以先加一个弹簧 (Spacer)
        button_layout.addStretch() 

        self.btn1 = QPushButton("重置连接")
        self.btn2 = QPushButton("重选API")
        self.btn3 = QPushButton("TASK#1")
        self.btn4 = QPushButton("TASK#2")
        self.btn5 = QPushButton("重启动")

        button_layout.addWidget(self.btn1)
        button_layout.addWidget(self.btn2)
        button_layout.addWidget(self.btn3)
        button_layout.addWidget(self.btn4)
        button_layout.addWidget(self.btn5)

        # 将按钮布局添加到主垂直布局的最下方
        layout.addLayout(button_layout)

        self.btn1.clicked.connect(self.worker.request_reinit)
        self.btn2.clicked.connect(self.worker.request_rechooseAPI)
        self.btn3.clicked.connect(self.worker.request_change_strategy_to_task1)
        self.btn4.clicked.connect(self.worker.request_change_strategy_to_task2)
        self.btn5.clicked.connect(self.worker.request_restart)

    def receive_input(self, prompt):
        """接收输入请求并显示对话框"""
        while True:
            text, ok = QInputDialog.getText(self, "用户输入", prompt)
            if ok and text in self.worker.analyser.client_map:
                self.worker.client_receive_input(text)
                break
            else: 
                self.worker.client_receive_input(None)
                break

    def update_log(self, text):
        self.console_output.append(text.strip())

    def msg_critical(self, text):
        QMessageBox.critical(self, "终止", text)

    def render_markdown(self, markdown_text):
        def texreplace(text):
            # 双反斜杠与单星转义、单下划线紧随大括号转义
            text = text.replace('\\', '\\\\')
            text = re.sub(r'(?<!\*)\^\*(?!\*)', r'^\\*', text)
            text = text.replace('_{', '\\_{')
            print(repr(text))
            return text
        
        markdown_text = texreplace(markdown_text) 
        
        md_extensions = [
            'fenced_code', 
            'tables', 
        ]
        
        try:
            rendered_md = markdown.markdown(
                markdown_text,
                extensions=md_extensions,
            )
        except Exception as e:
            rendered_md = f"<p>Markdown 解析失败: {e}</p><pre>{markdown_text}</pre>"
        
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