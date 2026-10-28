"""Player-facing draft controls for the verified scoped primal opportunity rule."""
import ui_theme
from localized_widgets import tk
from localized_widgets import ttk

from primal_drop_settings import SCOPE, primal_label, primal_preferences
from settings_service import installed_config


class PrimalDropPanel(ttk.Frame):
    def __init__(self, notebook, host):
        super().__init__(notebook, padding=18)
        self.host, self.updating = host, True
        self.enabled = tk.BooleanVar()
        self.multiplier = tk.StringVar(value='×2')
        ttk.Label(self, text='原始装备的额外奖励机会', font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w')
        self.installed = tk.StringVar()
        ttk.Label(self, textvariable=self.installed, foreground=ui_theme.TEXT, wraplength=850).pack(anchor='w', pady=(10, 14))
        self.enable_check = ttk.Checkbutton(self, text='启用原始额外掉落修改', variable=self.enabled, command=self.changed)
        self.enable_check.pack(anchor='w')
        row = ttk.Frame(self)
        row.pack(fill='x', pady=14)
        ttk.Label(row, text='原有机会倍率').pack(side='left')
        self.rate = ttk.Combobox(row, textvariable=self.multiplier, state='readonly', values=['×2', '×3', '×5'], width=10)
        self.rate.pack(side='left', padx=12)
        self.rate.bind('<<ComboboxSelected>>', self.changed)
        self.preview = tk.StringVar()
        ttk.Label(self, textvariable=self.preview, foreground=ui_theme.TEXT, wraplength=850).pack(anchor='w', pady=(0, 12))
        ttk.Separator(self).pack(fill='x', pady=8)
        ttk.Label(self, text='作用范围：试炼之塔的常规装备主题宝箱，包括本次已验证的超凡塔金色长剑箱。\n'
                  '原始物品专属房间未纳入；其他玩法不作为本版已验证范围。', wraplength=850).pack(anchor='w', pady=8)
        ttk.Label(self, text='保留随层数变化的规则，以及玩家、目标和联机掉落加成。\n'
                  '每次奖励机会最高100%；已100%的分支保持原样，不复制装备。\n'
                  '原始装备仍按原品质规则生成，不保证都是传奇品质。', foreground=ui_theme.MUTED,
                  wraplength=850).pack(anchor='w', pady=8)
        self.draft_text = tk.StringVar()
        ttk.Label(self, textvariable=self.draft_text, wraplength=850, foreground=ui_theme.TEXT).pack(anchor='w', pady=(12, 4))
        ttk.Label(self, text='这里仅编辑草稿。退出游戏后点击下方“保存并安装”，装备与掉率设置会一起保存。',
                  wraplength=850, foreground=ui_theme.MUTED).pack(anchor='w', pady=6)
        self.refresh()

    def value(self):
        return {'enabled': bool(self.enabled.get()), 'multiplier': int(self.multiplier.get().removeprefix('×')), 'scope': SCOPE}

    def refresh(self):
        self.updating = True
        profile = primal_preferences(self.host.draft)
        self.enabled.set(profile['enabled'])
        self.multiplier.set(f"×{profile['multiplier']}")
        self.updating = False
        self.refresh_status()

    def refresh_status(self):
        current, status = installed_config()
        profile = self.value()
        if current is None:
            self.installed.set('当前未启用本地补丁。' + status)
            same = False
        else:
            active = primal_preferences(current)
            self.installed.set('已安装：' + primal_label(active) + '。改动后需要下次启动游戏加载。')
            same = active == profile
        if not profile['enabled']:
            self.preview.set('草稿将关闭原始掉落修改，装备设置仍按各自开关处理。')
        else:
            rate = profile['multiplier']
            self.preview.set(f'已核对的金色长剑箱分支示例：20% → {min(100, 20*rate)}%。这是分支单次机会，不是整箱最终概率。')
        evidence = '×2已验证一次真实开箱。' if profile['multiplier'] == 2 else '×3、×5沿用相同规则，尚未进行游戏内实测。'
        self.draft_text.set(('与已安装掉率设置一致。' if same else '掉率草稿尚未安装。') + evidence)
        self.set_busy(self.host.busy)

    def changed(self, _event=None):
        if not self.updating and not self.host.busy:
            self.host.draft['primalDrop'] = self.value()
            self.refresh_status()
            self.host.changed()

    def set_busy(self, busy):
        self.enable_check.configure(state='disabled' if busy else 'normal')
        self.rate.configure(state='disabled' if busy or not self.enabled.get() else 'readonly')
