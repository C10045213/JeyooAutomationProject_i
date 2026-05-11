import sys
import threading
import argparse
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from cli_worker import CLIWorker


class CLIMain:
    def __init__(self, args):
        self.args = args
        self.running = True
        self._print_lock = threading.Lock()

        self.worker = CLIWorker(
            log_callback=self.on_log,
            result_callback=self.on_result,
            alert_callback=self.on_alert,
        )

        commands = ["connect", "api", "task1", "task2", "run",
                    "stop", "restart", "status", "help", "quit"]
        self._cmd_completer = WordCompleter(commands, ignore_case=True)
        self._cmd_session = PromptSession(history=FileHistory(".jeyoo_history"))
        self._model_completer = WordCompleter(["1", "2", "3", "4", "5"])

    def on_log(self, text):
        with self._print_lock:
            print(text)

    def on_result(self, text):
        with self._print_lock:
            text = text.replace("\\[","")
            text = text.replace("\\]","")
            text = text.replace("\\(","")
            text = text.replace("\\)","")
            print()
            print("=" * 60)
            print(text)
            print("=" * 60)

    def on_alert(self, text):
        with self._print_lock:
            print(f"\n!!! {text} !!!\n")

    def print_help(self):
        print("""
命令列表:
  connect    重置浏览器连接并定位页面
  api        重新选择 AI 审核模型
  task1      切换到 Task #1 (审题)
  task2      切换到 Task #2 (修题)
  run        执行当前任务
  stop       终止当前任务
  restart    关闭并重启浏览器
  status     查看当前状态
  help       显示此帮助
  quit       退出程序
        """)

    def print_status(self):
        api_name = "未选择"
        if self.worker._user_input:
            num = self.worker._user_input
            if num in self.worker.analyser.client_map:
                api_name = self.worker.analyser.client_map[num][0]
            else:
                api_name = f"#{num}"

        if self.worker._task1_flag:
            task_name = "TASK#1 (审题)"
        elif self.worker._task2_flag:
            task_name = "TASK#2 (修题)"
        else:
            task_name = "未选择"

        conn_status = "已连接" if self.worker._connected else "未连接"

        print(f"  API: {api_name}")
        print(f"  任务: {task_name}")
        print(f"  连接: {conn_status}")

    def process_command(self, cmd):
        cmd = cmd.strip().lower()
        if not cmd:
            return

        if cmd == "help":
            self.print_help()
        elif cmd == "connect":
            self.worker.request_reinit()
        elif cmd == "api":
            self.worker.request_rechooseAPI()
            # 等待工作线程完成请求处理后，在下一轮循环中显示"请选择"提示
            self.worker._awaiting_input.wait(timeout=5)
        elif cmd == "task1":
            self.worker.request_change_strategy_to_task1()
        elif cmd == "task2":
            self.worker.request_change_strategy_to_task2()
        elif cmd == "run":
            self.worker.request_task()
        elif cmd == "stop":
            self.worker.request_stop()
        elif cmd == "restart":
            self.worker.request_restart()
        elif cmd == "status":
            self.print_status()
        elif cmd in ("quit", "exit", "q"):
            self.running = False
            self.worker.running = False
            self.worker.stop_signal.set()
            print("正在退出...")
        else:
            print(f"未知命令: {cmd}，输入 help 查看命令列表")

    def run(self):
        self.worker.start()

        # 等待工作线程请求 API 选择，如果指定了 --api 则自动填入
        if self.worker._awaiting_input.wait(timeout=10):
            if self.args.api:
                self.worker.provide_input(self.args.api)
        else:
            print("警告: 工作线程未在超时时间内请求输入")

        # 预设任务模式
        if self.args.task1:
            self.worker.request_change_strategy_to_task1()
        elif self.args.task2:
            self.worker.request_change_strategy_to_task2()
        print("输入 help 查看命令列表")

        while self.running:
            try:
                choice = None
                cmd = None
                with patch_stdout():
                    if self.worker.awaiting_input:
                        # 工作线程需要模型选择输入
                        choice = self._cmd_session.prompt(
                            "请选择模型编号 (1-5): ",
                            completer=self._model_completer,
                        ).strip()
                    else:
                        cmd = self._cmd_session.prompt(
                            "JeyooAutoCheck > ",
                            completer=self._cmd_completer,
                        )

                if self.worker.awaiting_input:
                    if choice in self.worker.analyser.client_map and choice != "99":
                        self.worker.provide_input(choice)
                    else:
                        print("无效选择，已取消。")
                        self.worker.provide_input(None)
                else:
                    self.process_command(cmd)
            except KeyboardInterrupt:
                print("\n正在退出...")
                self.running = False
                self.worker.running = False
                self.worker.stop_signal.set()
            except EOFError:
                self.running = False
                self.worker.running = False
                self.worker.stop_signal.set()

        print("已退出。")


def main():
    parser = argparse.ArgumentParser(description="JeyooAutoCheck CLI")
    parser.add_argument(
        "--api", type=str, choices=["1", "2", "3", "4", "5"],
        help="预选 AI 模型 (1-5)"
    )
    parser.add_argument(
        "--task1", action="store_true",
        help="启动后切换到 Task 1 (审题)"
    )
    parser.add_argument(
        "--task2", action="store_true",
        help="启动后切换到 Task 2 (修题)"
    )
    args = parser.parse_args()

    cli = CLIMain(args)
    cli.run()


if __name__ == "__main__":
    main()
