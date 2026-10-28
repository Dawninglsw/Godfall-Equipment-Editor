"""Normal-pool trait replacement panel; no game writes before installation."""
import ui_theme
from copy import deepcopy
from localized_widgets import tk
from localized_widgets import ttk

from trait_types import (number_for_quality, prepare_slot, request, source_items,
                         stage_replacement, trait_label, trait_value_text)
from inventory_snapshot import SCOPES, filter_rows, load_rows, load_snapshot


class TraitTypePanel(ttk.Frame):
    def __init__(self, notebook, host):
        super().__init__(notebook, padding=12)
        self.host = host
        self.updating = False
        self.source = self.working = self.info = self.preview = None
        self.index = None
        self.candidates = []
        self.browser = None
        self.snapshot = load_snapshot()
        self.scope = tk.StringVar(value='当前配装' if self.snapshot and self.snapshot.get('live_process') else '历史记录（未确认）')
        row = ttk.Frame(self)
        row.pack(fill='x')
        ttk.Label(row, text='装备').pack(side='left')
        self.equipment = ttk.Combobox(row, state='readonly', width=53)
        self.equipment.pack(side='left', padx=8, fill='x', expand=True)
        self.equipment.bind('<<ComboboxSelected>>', self.select_item)
        host.button(row, '从游戏读取', host.read_game).pack(side='right')
        row = ttk.Frame(self); row.pack(fill='x', pady=(5, 3))
        ttk.Label(row, text='范围').pack(side='left')
        self.scope_box = ttk.Combobox(row, textvariable=self.scope, values=SCOPES, width=23, state='readonly')
        self.scope_box.pack(side='left', padx=8)
        self.scope_box.bind('<<ComboboxSelected>>', lambda _: self.apply_scope())
        host.button(row, '筛选与排序', self.open_browser).pack(side='left')
        self.source_text = tk.StringVar()
        ttk.Label(self, textvariable=self.source_text, foreground=ui_theme.MUTED, wraplength=900).pack(anchor='w', pady=(0, 3))
        self.slots = host.tree(self, ('slot', 'trait', 'value'), ('位置', '当前词条', '原始数值'), (140, 480, 150), height=3)
        self.slots.bind('<<TreeviewSelect>>', self.select_slot)
        self.slots.bind('<Button-1>', lambda _: 'break' if self.host.busy else None)
        self.slots.bind('<KeyPress>', lambda _: 'break' if self.host.busy else None)
        row = ttk.Frame(self)
        row.pack(fill='x', pady=(10, 4))
        ttk.Label(row, text='替换为').pack(side='left')
        self.target = ttk.Combobox(row, state='readonly', width=51)
        self.target.pack(side='left', padx=8, fill='x', expand=True)
        self.target.bind('<<ComboboxSelected>>', self.select_target)
        self.range_text = tk.StringVar(value='先选装备，再选一条待更换的词条。')
        ttk.Label(self, textvariable=self.range_text, foreground=ui_theme.TEXT, wraplength=900).pack(anchor='w', pady=4)
        row = ttk.Frame(self)
        row.pack(fill='x')
        ttk.Label(row, text='正常范围内选值').pack(side='left')
        self.slider = ttk.Scale(row, from_=0, to=.999, command=self.slide)
        self.slider.pack(side='left', padx=8, fill='x', expand=True)
        self.value = tk.StringVar()
        host.entry(row, textvariable=self.value, width=10).pack(side='left')
        self.unit = tk.StringVar()
        ttk.Label(row, textvariable=self.unit, width=4).pack(side='left', padx=4)
        host.button(row, '保留原档次', self.use_original_quality).pack(side='left')
        row = ttk.Frame(self)
        row.pack(fill='x', pady=(6, 8))
        host.button(row, '加入类型修改草稿', self.add).pack(side='left')
        host.button(row, '移除选中草稿', self.remove).pack(side='left', padx=8)
        host.button(row, '制作同款替代品', self.prepare_copy).pack(side='left')
        host.button(row, '整件副词条编辑', lambda: self.host.replacement_tab.open_editor()).pack(side='left', padx=8)
        self.pending = host.tree(self, ('item', 'from', 'to', 'value'),
                                 ('装备 / 编号末尾', '原词条', '新词条', '新数值'), (240, 245, 245, 100), height=2)
        self.refresh()

    def refresh(self):
        selected = self.source['id'] if self.source else None
        self.snapshot = load_snapshot()
        self.browser_rows = load_rows(self.snapshot)
        self.pending.delete(*self.pending.get_children())
        for i, edit in enumerate(self.host.draft.get('traitReplacements', [])):
            source = edit['sourceItem']
            self.pending.insert('', 'end', iid=str(i), values=(edit.get('label', source['gameplayTag']) + ' / ' + source['id'][-8:],
                                trait_label(source['traits'][edit['sourceIndex']]),
                                edit.get('targetLabel', edit['targetTraitName']), edit.get('targetValueText', '')))
        self.apply_scope(selected)

    def apply_scope(self, selected_id=None):
        self.apply_rows(filter_rows(self.browser_rows, scope=self.scope.get()), selected_id)

    def apply_rows(self, rows, selected_id=None):
        selected_id = selected_id or (self.source['id'] if self.source else None)
        self.items = rows
        self.equipment.configure(values=[r['label'] + ' / ' + r['item']['id'][-12:] for r in rows])
        if self.scope.get() == '历史记录（未确认）':
            message = f'历史记录 {len(rows)} 件，未确认当前归属；不会混入兵器库快照。'
        elif self.snapshot:
            manifest = self.snapshot['manifest']
            from datetime import datetime
            stamp = datetime.fromtimestamp(manifest['capturedAt']/1000).strftime('%m-%d %H:%M:%S')
            warning = ' · 清单未完整读取' if manifest['omitted'] or not all(manifest['collections'].values()) else ''
            process = '本次启动' if self.snapshot.get('live_process') else '上次游戏，仅回看'
            message = f'{self.scope.get()} {len(rows)} 件 · {process}快照 {stamp}；装备变化后重新读取{warning}'
        else:
            message = '尚无兵器库快照。需加载新版读取组件；历史记录可另选，不能代表当前配装。'
        self.source_text.set(message)
        if not rows:
            self.equipment.set(''); self.source = None; self.index = None
            self.slots.delete(*self.slots.get_children())
            self.reset_target('此范围没有可显示的装备。可以调整范围或筛选条件。')
            return
        found = next((i for i, r in enumerate(rows) if r['item']['id'] == selected_id), 0)
        self.equipment.current(found)
        self.select_item()

    def open_browser(self):
        if self.host.busy: return
        if self.browser and self.browser.winfo_exists():
            self.browser.lift(); return
        from inventory_browser import InventoryBrowser
        self.browser = InventoryBrowser(self)

    def set_busy(self, busy):
        self.equipment.configure(state='disabled' if busy else 'readonly')
        self.scope_box.configure(state='disabled' if busy else 'readonly')
        if busy and self.browser and self.browser.winfo_exists(): self.browser.destroy()
        self.target.configure(state='disabled' if busy else 'readonly')
        self.slider.configure(state='normal' if not busy and self.preview and self.variable else 'disabled')

    def reset_target(self, message):
        self.preview = None
        self.info = None
        self.candidates = []
        self.target.set('')
        self.target.configure(values=[])
        self.value.set('')
        self.unit.set('')
        self.slider.configure(state='disabled')
        self.range_text.set(message)

    def select_item(self, _event=None):
        if self.host.busy:
            return
        i = self.equipment.current()
        if i < 0:
            return
        self.source = deepcopy(self.items[i]['item'])
        self.index = None
        self.slots.delete(*self.slots.get_children())
        labels = {'Primary Trait': '主词条', 'Primary Attribute': '主属性（固定）', 'Secondary Trait': '副词条', 'Masterwork Trait': '精通词条'}
        for index, trait in enumerate(self.source['traits']):
            self.slots.insert('', 'end', iid=str(index), values=(labels.get(trait.get('slotType'), trait.get('slotType', '')),
                              trait_label(trait), trait_value_text(trait)))
        self.reset_target('选择一条词条后，列出这件装备实际允许的候选类型。')
        if not self.items[i].get('editable', True):
            self.reset_target(self.items[i].get('edit_reason') or '该类型已支持读取与筛选，本轮只供查看；已有装备的类型编辑尚未开放。')
        elif self.items[i].get('copy_only'):
            self.reset_target(self.items[i]['edit_reason'])

    def select_slot(self, _event=None):
        if self.host.busy or not self.slots.selection():
            return
        mutations = self.source.get('mutationNames') or []
        from replacement_service import is_awakened_ring
        awakened = is_awakened_ring(self.source)
        if (any(m in mutations for m in ['Mutation.Item.Cursed', 'Mutation.Item.Awakened']) and not awakened) or any(t.get('slotType') == 'Trait.Objective' for t in self.source['traits']):
            self.reset_target('诅咒任务与解除后的词条转换尚未适配；本轮保留装备与任务状态，只供查看。')
            return
        if awakened and self.source['traits'][int(self.slots.selection()[0])].get('slotType') != 'Secondary Trait':
            self.reset_target('已解咒戒指首轮仅支持副词条同款替代品；主词条和主属性保留。')
            return
        if self.source.get('lootClassName') == 'Augment':
            from owned_augment_model import availability
            policy = availability(self.source)
            if not policy['editable']:
                self.reset_target(policy['reason'])
                return
        if self.source.get('lootClassName') not in {'Weapon', 'Ring', 'Amulet', 'Charm', 'Augment', 'Banner', 'Consumable'}:
            self.reset_target('该类型本轮只供查看；已有装备的词条编辑尚未开放。')
            return
        self.index = int(self.slots.selection()[0])
        self.reset_target('正在计算该位置允许的类型与正常数值范围……')
        source, index, config = deepcopy(self.source), self.index, self.host.current_draft()
        def calculate():
            working = deepcopy(source) if awakened else prepare_slot(config, source, index)
            return working, request({'action': 'inspect', 'item': working, 'index': index})
        self.host.start_job('正在核对原游戏候选词条库。', calculate, self.finish_inspect)

    def finish_inspect(self, result):
        self.working, self.info = result
        self.candidates = [c for c in self.info['candidates'] if c.get('supported') and c['traitName'] != self.working['traits'][self.index]['traitName']]
        self.target.configure(values=[c['label'] for c in self.candidates])
        if self.info.get('primary_fixed'):
            self.range_text.set('这件装备的主词条类型固定。只为原游戏具有随机主词条库的装备开放主词条替换。')
        elif not self.candidates:
            self.range_text.set(self.info.get('reason') or '此位置暂没有可替换的候选类型；条件效果需单独验证。')
        else:
            self.range_text.set(f'可选 {len(self.candidates)} 种类型，已按其他词条的互斥规则筛选。')
        if self.info.get('augment_profile'):
            p = self.info['augment_profile']
            self.range_text.set(f'强化物：{p["color"]}，耗能 {p["tier_power_cost"]}；' + self.range_text.get())
        self.host.message.set('候选类型已载入。选择目标类型后可调整正常范围内的数值。')

    def select_target(self, _event=None):
        if self.host.busy or self.target.current() < 0:
            return
        candidate = self.candidates[self.target.current()]
        payload = {'action': 'preview', 'item': deepcopy(self.working), 'index': self.index,
                   'targetTraitName': candidate['traitName'], 'targetCategoryName': candidate['category']}
        self.host.start_job('正在生成保留原档次的数值。', lambda: request(payload), self.finish_preview)

    def finish_preview(self, result):
        self.preview = result
        rows = [r for r in result['ranges'] if r['varying']]
        self.variable = rows[0] if rows else None
        self.default_quality = result['quality']
        self.slider.configure(state='normal' if self.variable else 'disabled')
        self.updating = True
        self.slider.set(result['quality'])
        self.updating = False
        self.update_value(result['quality'])
        ranges = '；'.join(f'{r["min"] * r["multiplier"]:g}～{r["max"] * r["multiplier"]:g}{r["unit"]}' for r in result['ranges'] if r['varying'])
        suffix = '；多项数值随档次联动' if len(rows) > 1 else ''
        self.range_text.set('正常范围：' + (ranges or '固定数值') + '。默认保留原词条的大致档次' + suffix + '。')
        if result.get('augment_profile'):
            p = result['augment_profile']
            self.range_text.set(f'强化物：{p["color"]}，耗能 {p["tier_power_cost"]}；' + self.range_text.get())
        self.host.message.set('可拖动滑条或直接输入数值，再加入草稿。数值会按游戏精度核对。')

    def update_value(self, quality):
        if self.variable:
            row = self.variable
            self.value.set(f'{number_for_quality(row, quality) * row["multiplier"]:g}')
            self.unit.set(row['unit'])
        else:
            self.value.set(trait_value_text(self.preview['targetTrait']))
            self.unit.set('')

    def slide(self, value):
        if not self.updating and not self.host.busy and self.preview:
            self.update_value(float(value))

    def use_original_quality(self):
        if not self.host.busy and self.preview:
            self.slider.set(self.default_quality)
            self.update_value(self.default_quality)

    def add(self):
        if self.host.busy or not self.preview:
            return
        if 'Mutation.Item.Awakened' in (self.source.get('mutationNames') or []):
            self.host.message.set('已解咒戒指请点击“制作同款替代品”；本轮不加入本地覆盖草稿。')
            return
        payload = {'action': 'preview', 'item': deepcopy(self.working), 'index': self.index,
                   'targetTraitName': self.preview['targetTraitName'], 'targetCategoryName': self.preview['category'],
                   'quality': float(self.slider.get())}
        if self.variable:
            try:
                payload['desiredValue'] = float(self.value.get().strip().rstrip('%')) / self.variable['multiplier']
            except ValueError:
                self.host.message.set('请输入正常范围内的数字。')
                return
        config, source, index = self.host.current_draft(), deepcopy(self.source), self.index
        label = self.items[self.equipment.current()]['label']
        def calculate():
            preview = request(payload)
            return stage_replacement(config, source, index, preview, label)
        self.host.start_job('正在核对范围、互斥规则与完整草稿。', calculate, self.finish_add)

    def finish_add(self, config):
        self.host.draft = config
        self.host.enabled.set(True)
        self.refresh()
        self.host.refresh_rules()
        self.host.message.set('类型修改已加入草稿。确认后退出游戏，点击“保存并安装”。')

    def prepare_copy(self):
        if self.host.busy or not self.preview:
            return
        from replacement_service import availability, prepare
        source, index = deepcopy(self.source), self.index
        reason = availability(source, index)
        if reason:
            self.host.message.set(reason)
            return
        payload = {'targetTraitName': self.preview['targetTraitName'],
                   'targetCategoryName': self.preview['category'], 'quality': float(self.slider.get())}
        if self.variable:
            try:
                payload['desiredValue'] = float(self.value.get().strip().rstrip('%')) / self.variable['multiplier']
            except ValueError:
                self.host.message.set('请输入正常范围内的数字。')
                return
        self.host.start_job('正在核对整件属性并制作同款方案；不会修改游戏或原件。',
                            lambda: prepare(source, index, payload), self.finish_copy)

    def finish_copy(self, plan):
        self.host.replacement_tab.refresh(plan)
        self.host.notebook.select(self.host.replacement_tab)
        self.host.message.set('同款方案已制作，尚未安装。原件保留；查看方案后可在退出游戏时安装。')

    def remove(self):
        if self.host.busy or not self.pending.selection():
            return
        del self.host.draft['traitReplacements'][int(self.pending.selection()[0])]
        self.refresh()
        self.reset_target('草稿已更新，请重新选择待修改词条。')
        self.host.changed()
