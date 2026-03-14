import keyboard
import time
import threading
from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop
from AI_analyse_V1 import Analyser
from broswer_manager import BrowserManager

import task1, task2

class AutomationWorker(QThread):
    
    log_signal = pyqtSignal(str)      
    result_signal = pyqtSignal(str)   
    input_signal = pyqtSignal(str)    

    def __init__(self):
        super().__init__()
        self.running = True
        self.hotkey = 'ctrl+alt+z' # 于此确认设置HOTKEY
        self.save_hotkey = 'ctrl+alt+x' # 于此设置任务2存储专用HOTKEY
        self.save_event = threading.Event()
        self.analyser = Analyser()
        
        # 标志位
        self._task_requested = False   
        self._reinit_requested = False 
        self._rechooseAPI_requested = False
        self._requested_change_to_task1 = False
        self._requested_change_to_task2 = False
        self._task1_flag = False
        self._task2_flag = False
        self._save_task_requested = False
        
        # Playwright
        self.browser_manager = BrowserManager(self.log_signal.emit)
        self.pages = None
        
        # 当前执行的策略
        self.current_strategy = 0

    def request_change_strategy_to_task1(self):
        self._requested_change_to_task1 = True

    def request_change_strategy_to_task2(self):
        self._requested_change_to_task2 = True

    def request_reinit(self):
        self._reinit_requested = True
        self.log_signal.emit(">>> 已收到重置指令，等待线程调度...")

    def _hotkey_callback(self):
        self._task_requested = True

    def _save_hotkey_callback(self):
        self._save_task_requested = True
        self.save_event.set()

    def request_rechooseAPI(self):
        self._rechooseAPI_requested = True  

    def run(self):
        self.log_signal.emit(f'=' * 20)
        self.log_signal.emit(f"启动快捷键预设为：{self.hotkey} ")
        self.log_signal.emit(f"***※务必等待 当前自动化过程执行完成 之后再按下其他按钮※***")
        self.log_signal.emit(f"***※务必等待 当前自动化过程执行完成 之后再按下其他按钮※***")
        self.log_signal.emit(f"***※务必等待 当前自动化过程执行完成 之后再按下其他按钮※***")
        self.log_signal.emit(f'=' * 20)
        self.log_signal.emit(f"TASK#1: 审题逻辑")
        self.log_signal.emit(f"TASK#2: 收尾逻辑")

        keyboard.add_hotkey(self.hotkey, self._hotkey_callback)
        keyboard.add_hotkey(self.save_hotkey, self._save_hotkey_callback)
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
                    self.save_event.clear()

                    # TASK#2专用
                    if self._task2_flag:
                        self.log_signal.emit(f"按下: {self.save_hotkey} 以执行保存与翻页")
                        self.save_event.clear()
                        self._save_task_requested = False
                        self.save_event.wait(timeout=30)
                        if self._save_task_requested:
                            self._save_task_requested = False
                            self.current_strategy.saven_next()
                            self.log_signal.emit(f"本次任务已完成。")
                            self.log_signal.emit('='*30)
                            self.save_event.clear()
                        else:
                            self.log_signal.emit(f"等待超时，本次任务已终止。")
                            self.log_signal.emit('='*30)
                            self.save_event.clear()

                else:
                    self.log_signal.emit(f"未设置任务策略！")

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

            # 5. 处理弹窗
            self.check_pages_ondialog()

            time.sleep(0.1)
            
        # 退出时清理
        self.browser_manager.close()

# ========== 线程基础逻辑 ==========
    def _do_reinit(self):
        """线程内部执行的重置逻辑"""
        connected = self.browser_manager.connect()
        if connected and self.current_strategy:
            self.pages = self.browser_manager.get_all_pages()
            self.current_strategy.locate_pages(self.pages) # 各Task的locate_pages函数名需统一
        elif self.current_strategy == None:
            print(f"错误：尚未连接或未选择任务")
            self.log_signal.emit(f"错误：尚未连接或未选择任务")

    # rechoose AI API
    def client_select_request(self):
        """选择 AI 审核客户端"""
        ls = []
        self.log_signal.emit(f"*" * 20)
        self.log_signal.emit("请预先确认 VPN 已正确配置")
        self.log_signal.emit(f"*" * 20)
        self.log_signal.emit("请选择 AI 审核客户端:")
        for num, name in self.analyser.client_map.items():
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

     # 应对各页面中需要手动处置的弹窗
    def manual_check(self, dialog):
        print(f"弹窗出现了")
        dialog.accept() 
    
    def check_pages_ondialog(self):
        if self.pages != None:
            for page in self.pages:
                page.on("dialog", self.manual_check)
                page.wait_for_timeout(200)
        else: pass

    # 切换任务
    def change_strategy_to_task1(self):
        self.current_strategy = task1.QualityCheckStep1(self.log_signal.emit,self.result_signal.emit,self._user_input)
        self.log_signal.emit(f"已切换工作模式: {task1.QualityCheckStep1.__doc__}")
        self._reinit_requested = True

    def change_strategy_to_task2(self):
        self.current_strategy = task2.QualityCheckStep2(self.log_signal.emit,self.result_signal.emit,self._user_input)
        self.log_signal.emit(f"已切换工作模式: {task2.QualityCheckStep2.__doc__}")
        self._reinit_requested = True



