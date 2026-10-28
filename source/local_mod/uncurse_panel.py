"""One selected existing item's original curse objective workflow."""
import ui_theme
from copy import deepcopy
from localized_widgets import tk
from localized_widgets import ttk

import uncurse_service as service
from settings_service import installation_state


class UncursePanel(ttk.Frame):
    def __init__(self, notebook, host):
        super().__init__(notebook, padding=14)
        self.host, self.plan = host, None
        ttk.Label(self, text='一键解除所选装备的诅咒（试验）', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(self, text='支持未装备、未保存到配装、强化0且剩余1至3层诅咒的物品。\n'
                  '保留原编号和词条类型，自动串联目标达标、铁匠觉醒与保存核对。', wraplength=880).pack(anchor='w', pady=12)
        ttk.Label(self, text='1. 在“旧词条工具”筛选诅咒物品，再回到本页点击“为选中装备制作计划”。\n'
                  '2. 查看计划，退出游戏后点击“安装解咒计划”。\n'
                  '3. 下次启动会自动尝试完成目标并觉醒；目标已达标时直接继续觉醒。', wraplength=880).pack(anchor='w', pady=8)
        self.details = tk.StringVar()
        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.details, wraplength=880).pack(anchor='w', pady=12)
        ttk.Label(self, textvariable=self.status, wraplength=880, foreground=ui_theme.TEXT).pack(anchor='w', pady=12)
        row = ttk.Frame(self); row.pack(fill='x', pady=10)
        host.button(row, '选择诅咒装备', self.choose).pack(side='left')
        host.button(row, '为选中装备制作计划', self.prepare).pack(side='left', padx=6)
        host.button(row, '安装解咒计划', self.install).pack(side='left')
        host.button(row, '读取处理结果', self.read_status).pack(side='left', padx=6)
        host.button(row, '读取兵器库', host.read_game).pack(side='left')
        ttk.Label(self, text='每层保存并核对后才继续下一层；失败或超时停止，不自动重试。计数到目标不等于已解除成功。\n'
                  '安装时备份补丁和设置；装备的解咒结果由游戏保存。本页不制作替代品，也不替换词条类型。',
                  wraplength=880, foreground=ui_theme.MUTED).pack(anchor='w', pady=12)
        self.refresh()

    def choose(self):
        self.host.notebook.select(self.host.type_tab)
        self.host.type_tab.scope.set('兵器库全部')
        self.host.type_tab.apply_scope()
        self.host.type_tab.open_browser()

    def prepare(self):
        item = self.host.type_tab.source
        if self.host.busy:
            return
        if not item:
            self.host.message.set('请先在词条类型页选中一件诅咒装备。')
            return
        source = deepcopy(item)
        self.host.start_job('正在核对原件与进度并制作解咒计划；尚不提交任务。',
                            lambda: service.prepare(source), self.finish_prepare)

    def finish_prepare(self, plan):
        self.refresh(plan)
        self.host.message.set('解咒计划已制作，尚未安装或提交。')

    def refresh(self, plan=None):
        self.plan = plan or service.load_plan()
        if not self.plan:
            self.details.set('尚无解咒计划。')
            self.status.set('选择物品后先制作计划，安装后才会在下一次启动执行。')
            return
        p = self.plan
        self.details.set(f'{p["label"]} · 等级 {p["tier"]} · 剩余 {p.get("total_layers", 1)} 层诅咒\n'
                         f'当前进度：{p["before_progress"]:g}/{p["target_progress"]:g}\n'
                         f'处理目标：任务达标后执行觉醒；保留原编号和词条类型\n'
                         f'装备编号：{p["source_id"]}\n计划编号：{p["plan_id"]}')
        installed = installation_state().get('uncurse_trial', {})
        self.status.set('计划已安装；下次启动会自动尝试解咒，随后读取结果。' if installed.get('plan_id') == p['plan_id']
                        else '计划尚未安装，游戏内物品与任务进度未改变。')

    def install(self):
        if self.host.busy or not self.plan:
            return
        plan = self.plan
        self.host.start_job('正在备份并安装单件解咒计划；游戏须关闭。', lambda: service.install(plan), self.finish_install)

    def finish_install(self, result):
        self.host.finish_install(result)
        self.refresh()

    def read_status(self):
        if self.host.busy or not self.plan:
            return
        plan = self.plan
        self.host.start_job('正在只读核对解咒处理记录。', lambda: service.read_status(plan), self.finish_status)

    def finish_status(self, message):
        self.status.set(message)
        self.host.message.set(message)
