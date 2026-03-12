import keyboard
import time
from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop
from AI_analyse_V1 import Reviewer
from broswer_manager import BrowserManager

import task1

class AutomationWorker(QThread):
    
    log_signal = pyqtSignal(str)      
    result_signal = pyqtSignal(str)   
    input_signal = pyqtSignal(str)    

    def __init__(self):
        super().__init__()
        self.running = True
        self.hotkey = 'ctrl+alt+z' # 于此确认设置HOTKEY
        self.reviewer = Reviewer()
        
        # 标志位
        self._task_requested = False   
        self._reinit_requested = False 
        self._rechooseAPI_requested = False
        self._requested_change_to_task1 = False
        
        # Playwright
        self.browser_manager = BrowserManager(self.log_signal.emit)
        
        # 当前执行的策略
        self.current_strategy = 0

    def request_change_strategy_to_task1(self):
        self._requested_change_to_task1 = True

    def request_reinit(self):
        self._reinit_requested = True
        self.log_signal.emit(">>> 已收到重置指令，等待线程调度...")

    def _hotkey_callback(self):
        self._task_requested = True

    def request_rechooseAPI(self):
        self._rechooseAPI_requested = True  

    def run(self):
        self.log_signal.emit(f'=' * 20)
        self.log_signal.emit(f"启动快捷键预设为：{self.hotkey} ")
        self.log_signal.emit(f'=' * 20)

        keyboard.add_hotkey(self.hotkey, self._hotkey_callback)
        self._rechooseAPI_requested = True  

        while self.running:
            # 1. 根据当前目标，执行重连和重新定位
            if self._reinit_requested:
                self._reinit_requested = False
                self._do_reinit()

            # 2. 处理热键任务
            if self._task_requested:
                self._task_requested = False
                if self.current_strategy:
                    self.current_strategy.execute() # Task的execute函数名需统一
                else:
                    self.log_signal.emit("未设置任务策略！")

            # 3. 处理重选API
            if self._rechooseAPI_requested:
                self._rechooseAPI_requested = False
                self.client_select_request()

            if self._requested_change_to_task1:
                self._requested_change_to_task1 = False
                self.change_strategy_to_task1()

            time.sleep(0.1)
            
        # 退出时清理
        self.browser_manager.close()

# ========== 线程基础逻辑 ==========
    def _do_reinit(self):
        """线程内部执行的重置逻辑"""
        connected = self.browser_manager.connect()
        if connected and self.current_strategy:
            pages = self.browser_manager.get_all_pages()
            self.current_strategy.locate_pages(pages) # Task的locate_pages函数名需统一
        elif self.current_strategy == None:
            print(f"错误：尚未连接或未选择任务")
            self.log_signal.emit(f"错误：尚未连接或未选择任务")

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
        self.input_signal.emit("请选择")
        self._loop.exec()

    def client_receive_input(self, data):
        if data != None:
            self._user_input = data
            self.log_signal.emit(f"#{data} Choosen")
        else: 
            self.log_signal.emit(f"默认选择3号位。")
            self._user_input = "3"
        if self._loop:
            self._loop.quit()

    def change_strategy_to_task1(self):
        self.current_strategy = task1.QualityCheckStep1(self.log_signal.emit,self.result_signal.emit,self._user_input)
        self.log_signal.emit(f"已切换工作模式: {task1.QualityCheckStep1.__annotations__}")
        self._reinit_requested = True