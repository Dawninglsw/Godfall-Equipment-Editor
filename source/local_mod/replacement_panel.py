"""Review and install the separately prepared, once-only replacement workflow."""
import json
from pathlib import Path
from localized_widgets import tk
from localized_widgets import ttk

import replacement_service as service
from settings_service import installation_state, installed_config
from trait_types import trim_item
import ui_theme


class ReplacementPanel(ttk.Frame):
    def __init__(self, notebook, host):
        super().__init__(notebook, padding=12)
        self.host, self.plan, self.editor, self.batch_editor = host, None, None, None
        header = ttk.Frame(self); header.pack(fill='x')
        ttk.Label(header, text='保留原件，制作修改后的同款新物品', font=('Microsoft YaHei UI', 14, 'bold')).pack(side='left')
        host.button(header, '整件副词条编辑', self.open_editor).pack(side='right')
        host.button(header, '多件批量方案', self.open_batch).pack(side='right',padx=6)
        ttk.Label(self, text='支持普通、原始装备及强化0的已解咒戒指，可一次设置多条副词条；保留强化与精通词条。\n'
                  '默认保留原词条档次，也可以在正常范围内选值。新物品正常拾取保存后不依赖生成补丁。',
                  wraplength=900).pack(anchor='w', pady=(8, 14))
        ttk.Label(self, text='1. 到“旧词条工具”选择物品、副词条和目标类型，点击“制作同款替代品”。\n'
                  '2. 在本页检查方案，正常退出游戏后点击“安装同款生成”。\n'
                  '3. 启动游戏，在单人关卡正常打怪或开箱，正常或自动拾取新物品。\n'
                  '4. 读取兵器库核对新物品；之后可退出游戏并停用全部补丁。',
                  wraplength=900, foreground=ui_theme.MUTED).pack(anchor='w', pady=(0, 14))
        self.details = tk.StringVar()
        detail_frame = ttk.Frame(self); detail_frame.pack(fill='x', pady=8)
        self.detail_box = tk.Text(detail_frame, height=7, width=1, wrap='word', relief='flat',
                                  font=('Microsoft YaHei UI', 9), background=self.winfo_toplevel().cget('background'))
        ui_theme.detail_text(self.detail_box)
        detail_scroll = ttk.Scrollbar(detail_frame, orient='vertical', command=self.detail_box.yview)
        self.detail_box.configure(yscrollcommand=detail_scroll.set, state='disabled')
        self.detail_box.pack(side='left', fill='x', expand=True); detail_scroll.pack(side='right', fill='y')
        self.details.trace_add('write', self.display_details)
        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, wraplength=900, foreground=ui_theme.TEXT).pack(anchor='w', pady=12)
        row = ttk.Frame(self); row.pack(fill='x', pady=8)
        host.button(row, '选择物品与词条', self.choose).pack(side='left')
        host.button(row, '安装同款生成', self.install).pack(side='left', padx=8)
        host.button(row, '刷新方案状态', self.refresh).pack(side='left')
        host.button(row, '读取兵器库核对', host.read_game).pack(side='left', padx=8)
        host.button(row, '检查生成状态', self.read_status).pack(side='left')
        ttk.Label(self, text='每个方案只生成一件。原件若被强化、分解或词条发生变化，将停止生成。\n'
                  '安装时会备份当前补丁，并关闭本地装备覆盖和掉率加成。制作方案不影响这些设置。',
                  wraplength=900, foreground=ui_theme.MUTED).pack(anchor='w', pady=12)
        self.refresh()

    def display_details(self, *_):
        self.detail_box.configure(state='normal')
        self.detail_box.delete('1.0', 'end'); self.detail_box.insert('1.0', self.details.get())
        self.detail_box.configure(state='disabled')

    def choose(self):
        self.host.notebook.select(self.host.type_tab)
        if self.host.type_tab.snapshot:
            self.host.type_tab.scope.set('兵器库全部')
            self.host.type_tab.apply_scope()
        self.host.type_tab.open_browser()

    def open_editor(self):
        if self.host.busy:
            return
        if self.editor and self.editor.winfo_exists():
            self.editor.lift(); return
        source = self.host.type_tab.source
        if not source:
            self.host.message.set('请先选中一件装备，再打开整件副词条编辑。')
            self.choose(); return
        reason = service.availability(source)
        if reason:
            self.host.message.set(reason); return
        if not any(t.get('slotType') == 'Secondary Trait' for t in source.get('traits', [])):
            self.host.message.set('这件物品没有可修改的副词条。'); return
        from replacement_multi_panel import MultiReplacementEditor
        self.editor = MultiReplacementEditor(self, source)

    def open_batch(self):
        if self.host.busy:return
        if self.batch_editor and self.batch_editor.winfo_exists():self.batch_editor.lift();return
        from replacement_batch_panel import BatchReplacementPanel
        self.batch_editor=BatchReplacementPanel(self)

    def refresh(self, plan=None):
        self.plan = plan or service.load_plan()
        if not self.plan:
            self.details.set('尚未制作同款方案。')
            self.status.set('请先选择物品与副词条；已强化物品及部分装备类型的同款生成仍待游戏内验证。')
            return
        p = self.plan
        warning = '\n这类同款生成已通过离线检查，尚待游戏内验证。' if p.get('family') in {'Weapon', 'Banner', 'Consumable', 'Amulet', 'Charm'} else ''
        if p.get('primal'):
            warning = '\n原始戒指已验证生成、拾取与穿戴效果；本件停补丁后的重启保留尚待核对。'
        if p.get('upgrade_rank', 0):
            warning = '\n已有已强化原始长柄武器实测；本件请核对实际结果及重启保留。'
        if p.get('awakened'):
            warning = '\n已解咒戒指已有生成、拾取与穿戴效果实测；保留觉醒主词条加成，本方案仍需核对新件。'
        if p.get('primary_trial'):
            warning = '\n随机主词条同款试验；强化等级、原始标记和精通词条保留，本件仍需核对新生成结果。'
        meta = p.get('preserved_metadata', {})
        attributes = meta.get('lootAttributes') or {}
        extra = ''
        if 'attackPower' in attributes:
            damage = {'Damage.Primary.Physical': '物理', 'Damage.Primary.Elemental.Air': '气系',
                      'Damage.Primary.Elemental.Cold': '冰系', 'Damage.Primary.Elemental.Fire': '火系',
                      'Damage.Primary.Elemental.Shadow': '虚空', 'Damage.Primary.Elemental.Earth': '土系'}
            element = '、'.join(damage.get(k, '原伤害类型') for k in (meta.get('damageTypes') or {}))
            extra = f' · 攻击力 {attributes["attackPower"]:g} · {element}'
        if 'BannerOvershield' in attributes:
            extra = f' · 护盾量 {attributes["BannerOvershield"]:g}'
        if 'ConsumableHealingPower' in attributes:
            extra = f' · 回复量 {attributes["ConsumableHealingPower"]:g} · 充能 {meta.get("amount", 1)} 次'
        label = ('已解咒 · ' if p.get('awakened') else '原始 · ' if p.get('primal') else '') + p['label']
        upgrade = p.get('preserved_upgrade', {})
        upgrade_text = ('\n精通词条保留：' + '、'.join(upgrade['masterwork_traits'])) if upgrade.get('masterwork_traits') else ''
        changes = p.get('changes', [])
        change_text = ('\n'.join(f'副词条{c["index"]+1}：{c["source_trait"]} {c["source_value"]} → {c["target_trait"]} {c["target_value"]}' for c in changes)
                       if len(changes) > 1 else f'原词条：{p["source_trait"]} {p["source_value"]}\n新词条：{p["target_trait"]} {p["target_value"]}')
        self.details.set(f'{label} · 等级 {p["tier"]} · 强化 {p.get("upgrade_rank", 0)}{extra}\n' + change_text + '\n'
                         f'原件编号：{p["source_id"]}\n方案编号：{p["trial_id"]}' + upgrade_text + warning)
        current, _ = installed_config()
        trial = installation_state().get('replacement_copy_trial', {})
        if current is not None and trial.get('trial_id') == p['trial_id']:
            self.status.set('同款生成已安装；启动后单人正常打怪或开箱并拾取。每个方案只生成一次。')
        elif current is not None:
            self.status.set('当前安装的是其他方案；本页同款方案尚未启用。')
        else:
            self.status.set('当前没有启用本地补丁。此方案已制作，尚未启用。')

    def install(self):
        if self.host.busy:
            return
        if not self.plan:
            self.host.message.set('请先在“旧词条工具”制作同款替代品方案。')
            return
        plan = self.plan
        self.host.start_job('正在备份并安装同款生成；游戏须保持关闭。',
                            lambda: service.install(plan), self.finish_install)

    def finish_install(self, result):
        self.host.finish_install(result)
        self.refresh()

    def read_status(self):
        if self.host.busy or not self.plan:
            return
        plan = self.plan
        self.host.start_job('正在只读检查生成状态，约半分钟；不修改游戏。',
                            lambda: service.generation_status(plan), self.finish_status)

    def finish_status(self, message):
        self.status.set(message)
        self.host.message.set('生成状态检查完成。拾取保存情况请用兵器库清单核对。')

    def inspect_snapshot(self, snapshot):
        """Report matching owned items only for the active generation plan and process."""
        self.refresh()
        if not self.plan or not snapshot or not snapshot.get('live_process'):
            return
        state = installation_state()
        if state.get('replacement_copy_trial', {}).get('trial_id') != self.plan['trial_id']:
            return
        try:
            preview = json.loads(Path(self.plan['preview_path']).read_bytes())
        except (OSError, ValueError):
            return
        expected = preview['expected_materialized']
        keys = ['gameplayTag', 'tierIdentifier', 'rarityIdentifier', 'masterworkUpgradeRank',
                'mutationNames', 'selectedTraitTags', 'traits', 'damageTypes']
        matches = [i for i in snapshot['items'] if i['id'] != self.plan['source_id']
                   and all(trim_item(i).get(k) == trim_item(expected).get(k) for k in keys)]
        if matches:
            self.status.set('本次兵器库已找到符合方案的新物品：' + '、'.join(i['id'][-12:] for i in matches)
                            + '。可以在游戏中查看或装备；同款生成可在退出游戏后停用。')

    def set_busy(self, busy):
        # Buttons are managed centrally by the main window.
        pass
