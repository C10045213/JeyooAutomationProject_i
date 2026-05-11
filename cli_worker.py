import time
import threading
import os
import subprocess
from AI_analyse_V1 import Analyser
from broswer_manager import BrowserManager
from dotenv import load_dotenv

import task1, task2

load_dotenv()

class CLIWorker(threading.Thread):

    def __init__(self, log_callback, result_callback, alert_callback):
        super().__init__(daemon=True)
        self.running = True

        # 回调函数（替代 pyqtSignal）
        self.log = log_callback
        self.result = result_callback
        self.alert = alert_callback

        self.analyser = Analyser()

        # 标志位
        self._request_restart = False
        self._task_requested = False
        self._reinit_requested = False
        self._rechooseAPI_requested = False
        self._requested_change_to_task1 = False
        self._requested_change_to_task2 = False
        self._task1_flag = False
        self._task2_flag = False
        self._connected = False

        # Playwright
        self.browser_manager = BrowserManager(self.log)
        self.pages = None
        self.browser_path = None
        self.browser_process = None

        # 当前执行的策略与线程控制
        self.current_strategy = None
        self.method_thread = None
        self.stop_signal = threading.Event()

        # 用户选择的模型编号
        self._user_input = ""

        # 输入同步（替代 QEventLoop）
        self._awaiting_input = threading.Event()
        self._input_ready = threading.Event()
        self._pending_input = None

    # ========== 公共 API（CLI 主线程调用）==========

    def request_reinit(self):
        self._reinit_requested = True
        self.log(">>> 已收到重置指令，等待线程调度...")

    def request_rechooseAPI(self):
        self._rechooseAPI_requested = True
        self.log("请等待...")

    def request_change_strategy_to_task1(self):
        self._requested_change_to_task1 = True
        self.log("请等待...")

    def request_change_strategy_to_task2(self):
        self._requested_change_to_task2 = True
        self.log("请等待...")

    def request_task(self):
        self._task_requested = True
        self.log("请等待...")

    def request_stop(self):
        self.log("已发出终止指令。")
        self.stop_signal.set()

    def request_restart(self):
        self._request_restart = True
        self.log("请等待...")

    @property
    def awaiting_input(self):
        return self._awaiting_input.is_set()

    def provide_input(self, data):
        self._pending_input = data
        self._awaiting_input.clear()
        self._input_ready.set()

    # ========== 线程主循环 ==========

    def run(self):
        self.log('=' * 60)
        self.log("命令: connect / api / task1 / task2 / run / stop / restart / status / help / quit")
        self.log(f"TASK#1: {task1.QualityCheckStep1.__doc__}")
        self.log(f"TASK#2: {task2.QualityCheckStep2.__doc__}")
        self.log('=' * 60)

        self._rechooseAPI_requested = True

        while self.running:
            # 1. 重连和重新定位
            if self._reinit_requested:
                self._reinit_requested = False
                self._do_reinit()

            # 2. 处理任务执行
            if self._task_requested:
                self._task_requested = False
                if self.current_strategy:
                    try:
                        self.stop_signal.clear()
                        self.current_strategy.execute()
                    except Exception as e:
                        error_msg = str(e)
                        if "closed" in error_msg.lower():
                            self.log("检测到浏览器页面已关闭，需要重连...")
                        else:
                            self.log(f"任务执行其他异常: {e}")
                else:
                    self.log("未设置任务策略！")

            # 3. 处理重选API
            if self._rechooseAPI_requested:
                self._rechooseAPI_requested = False
                self.client_select_request()

            # 4. 处理切换任务
            if self._requested_change_to_task1:
                self._requested_change_to_task1 = False
                self.change_strategy_to_task1()
                self._task2_flag = False
                self._task1_flag = True

            if self._requested_change_to_task2:
                self._requested_change_to_task2 = False
                self.change_strategy_to_task2()
                self._task1_flag = False
                self._task2_flag = True

            # 5. 刷新与处理弹窗
            self.refresh_n_check_pages_ondialog()

            # 6. 处理重启动
            if self._request_restart:
                self._request_restart = False
                self._do_restart()

            time.sleep(0.2)

    # ========== 内部方法 ==========

    def _do_reinit(self):
        self._connected = self.browser_manager.connect()
        if self._connected and self.current_strategy:
            self.pages = self.browser_manager.get_all_pages()
            self.current_strategy.locate_pages(self.pages)
        elif self.current_strategy is None:
            self.log("错误：尚未连接或未选择任务")

    def _do_restart(self):
        try:
            self.browser_process = os.getenv("BROWSER_PROCESS")
            self.browser_path = os.getenv("BROWSER_PATH")

            cmdline1 = f"taskkill /F /IM {self.browser_process}"
            result = subprocess.run(cmdline1, shell=True,
                                   capture_output=True, text=True, encoding='gbk')
            if result.returncode != 0 and result.stderr:
                self.log(f"taskkill: {result.stderr.strip()}")
            subprocess.Popen([
                self.browser_path,
                "--remote-debugging-port=9222"
            ], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.log(str(e))

        try:
            process_filtered = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq msedge.exe'],
                capture_output=True,
                text=True,
                encoding='gbk'
            )
            if 'msedge.exe' not in process_filtered.stdout:
                self.log("command重启msedge.exe:9222失败，请检查路径")
        except Exception as e:
            self.log(f"检查进程失败: {e}")

    def client_select_request(self):
        """重选 AI 审核客户端（使用 threading.Event 替代 QEventLoop）"""
        self.current_strategy = None
        self.log("*" * 40)
        self.log("请选择 AI 审核客户端:")
        for num, name in self.analyser.client_map.items():
            if num != '99':
                self.log(f"{num} . {name[0]}")
        self.log("*" * 40)

        # 通知主线程需要输入，阻塞等待
        self._awaiting_input.set()
        self._input_ready.wait()
        self._input_ready.clear()

        data = self._pending_input
        if data is not None:
            self._user_input = data
            self.log(f"#{data} Choosen")
        else:
            self.log("操作已取消。")
            self._user_input = ""

    def refresh_n_check_pages_ondialog(self):
        if self.pages is None:
            return

        if self._connected:
            try:
                self.pages = self.browser_manager.get_all_pages()
            except:
                self.log("刷新页面出现异常。")

        for p in self.pages:
            try:
                if p.is_closed():
                    continue
                p.on("dialog", self.manual_check)
                p.wait_for_timeout(100)
            except Exception as e:
                error_msg = str(e).lower()
                if "closed" in error_msg or "detached" in error_msg:
                    if p in self.pages:
                        self.pages.remove(p)
                    continue
                else:
                    self.log(f"检查页面时出错: {e}")

    def manual_check(self, dialog):
        try:
            dialog.accept()
        except:
            return

    def change_strategy_to_task1(self):
        if self._user_input == '':
            self.log("未选择API！")
            return
        self.current_strategy = task1.QualityCheckStep1(
            self.log, self.result, self._user_input, self.stop_signal
        )
        self.log(f"正在切换工作模式: {task1.QualityCheckStep1.__doc__}")
        self._reinit_requested = True

    def change_strategy_to_task2(self):
        if self._user_input == '':
            self.log("未选择API！")
            return
        self.current_strategy = task2.QualityCheckStep2(
            self.log, self.result, self.alert, self._user_input, self.stop_signal
        )
        self.log(f"正在换工作模式: {task2.QualityCheckStep2.__doc__}")
        self._reinit_requested = True
