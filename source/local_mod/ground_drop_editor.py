"""Player-facing ground-item editor. Opening/scanning never writes the game."""
import ui_theme
from localization import tr
import queue
import threading
from localized_widgets import tk
from localized_widgets import ttk

import ground_drop_service as service
from ground_drop_filters import RARITIES, matching_indices, rarity_label, search_index
from trait_types import number_for_quality, trait_label, trait_value_text


class GroundDropEditor:
    def __init__(self, root):
        self.root, self.busy, self.snapshot, self.last = root, False, None, None
        self.row = self.slot = self.candidate = self.prepared = None
        self.events, self.buttons = queue.Queue(), []
        self.filter_index, self.filter_pending, self.filter_popup = [], None, None
        self.query = tk.StringVar()
        self.family_filter = tk.StringVar(value='全部类型')
        self.rarity_filter = tk.StringVar(value='全部品质')
        self.editable_only = tk.BooleanVar(value=False)
        self.trait_mode = tk.StringVar(value='不限词条')
        self.trait_query = tk.StringVar()
        self.color_filter = tk.StringVar(value='全部颜色')
        self.filter_count = tk.StringVar(value='读取后可筛选名称、品质、词条和强化物颜色。')
        self.filter_controls = []
        root.title(tr('Godfall 新掉落词条编辑'))
        root.geometry('1040x810')
        root.minsize(960, 780)
        root.protocol('WM_DELETE_WINDOW', self.close)
        ui_theme.apply(root)
        style = ttk.Style(root)
        style.configure('TLabel', font=('Microsoft YaHei UI', 10))
        style.configure('TButton', font=('Microsoft YaHei UI', 10), padding=(10, 5))
        style.configure('Treeview', font=('Microsoft YaHei UI', 10), rowheight=30)
        f = ttk.Frame(root, padding=(20,12))
        f.pack(fill='both', expand=True)
        ttk.Label(f, text='新掉落词条编辑', font=('Microsoft YaHei UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(f, text='先不要拾取装备。读取和选值不会修改游戏；点击“写入这件掉落”后，再正常拾取。',
                  wraplength=970).pack(anchor='w', pady=(5, 10))
        toolbar = ttk.Frame(f)
        toolbar.pack(fill='x')
        self.button(toolbar, '读取地上的装备', self.scan).pack(side='left')
        ttk.Label(toolbar, textvariable=self.filter_count, foreground=ui_theme.MUTED).pack(side='left', padx=12)
        filters = ttk.Frame(f)
        filters.pack(fill='x', pady=(7, 0))
        ttk.Label(filters, text='名称 / 编号').pack(side='left')
        self.search_entry = ttk.Entry(filters, textvariable=self.query, width=19)
        self.search_entry.pack(side='left', padx=(6, 10), fill='x', expand=True)
        self.filter_controls.append((self.search_entry, 'normal'))
        for variable, values, width in [(self.family_filter, ['全部类型', *service.SUPPORTED_CLASSES.values()], 8),
                                        (self.rarity_filter, ['全部品质', *RARITIES.values(), '未知'], 8)]:
            widget = ttk.Combobox(filters, textvariable=variable, values=values, state='readonly', width=width)
            widget.pack(side='left', padx=(0, 8))
            self.filter_controls.append((widget, 'readonly'))
        editable = ttk.Checkbutton(filters, text='仅看可编辑', variable=self.editable_only)
        editable.pack(side='left', padx=(0, 8))
        self.filter_controls.append((editable, 'normal'))
        self.button(filters, '词条 / 颜色条件', self.show_filters).pack(side='left', padx=(0, 6))
        self.button(filters, '清空筛选', self.clear_filters).pack(side='left')
        self.items = self.tree(f, ('name', 'family', 'rarity', 'tier', 'distance', 'id', 'state'),
                               ('装备', '类型', '品质', '等级', '距离', '编号末尾', '读取状态'), (225, 65, 65, 55, 70, 150, 205), 3)
        self.items.tag_configure('unavailable', foreground=ui_theme.MUTED)
        self.items.bind('<<TreeviewSelect>>', self.select_item)
        row = ttk.Frame(f)
        row.pack(fill='x', pady=(10, 4))
        ttk.Label(row, text='原词条').pack(side='left')
        self.slots = ttk.Combobox(row, state='readonly', width=60)
        self.slots.pack(side='left', padx=10, fill='x', expand=True)
        self.slots.bind('<<ComboboxSelected>>', self.select_slot)
        self.details_button = self.button(row, '查看候选与原因', self.show_candidates)
        self.details_button.pack(side='right')
        row = ttk.Frame(f)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text='替换为').pack(side='left')
        self.targets = ttk.Combobox(row, state='readonly', width=60)
        self.targets.pack(side='left', padx=10, fill='x', expand=True)
        self.targets.bind('<<ComboboxSelected>>', self.select_target)
        self.range_text = tk.StringVar(value='启动游戏，找到尚未拾取的装备后点击读取。')
        ttk.Label(f, textvariable=self.range_text, foreground=ui_theme.TEXT, wraplength=960).pack(anchor='w', pady=5)
        row = ttk.Frame(f)
        row.pack(fill='x', pady=5)
        self.keep = tk.BooleanVar(value=True)
        self.keep_check = ttk.Checkbutton(row, text='保留原档次', variable=self.keep, command=self.change_mode)
        self.keep_check.pack(side='left')
        self.slider = ttk.Scale(row, from_=0, to=.999, command=self.slide)
        self.slider.pack(side='left', fill='x', expand=True, padx=12)
        self.value = tk.StringVar()
        self.value.trace_add('write', self.value_changed)
        self.entry = ttk.Entry(row, textvariable=self.value, width=10)
        self.entry.pack(side='left')
        self.unit = tk.StringVar()
        ttk.Label(row, textvariable=self.unit, width=4).pack(side='left', padx=4)
        self.preview_text = tk.StringVar(value='选择一件装备和目标词条后，显示本次方案。')
        ttk.Label(f, textvariable=self.preview_text, wraplength=960).pack(anchor='w', pady=5)
        actions = ttk.Frame(f)
        actions.pack(fill='x', pady=(6, 10))
        self.apply_button = self.button(actions, '写入这件掉落', self.apply)
        self.apply_button.pack(side='left')
        self.restore_button = self.button(actions, '撤回本次修改（拾取前）', self.restore)
        self.restore_button.pack(side='left', padx=10)
        ttk.Separator(f).pack(fill='x', pady=5)
        ttk.Label(f, text='备份与验证记录', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', pady=(4, 2))
        self.history = self.tree(f, ('item', 'target', 'state'), ('装备 / 编号末尾', '本次目标', '核对状态'), (400, 250, 220), 2)
        self.history.bind('<<TreeviewSelect>>', self.select_history)
        row = ttk.Frame(f)
        row.pack(fill='x', pady=6)
        self.picked_button = self.button(row, '记录：已正常拾取', lambda: self.observe('picked_up'))
        self.picked_button.pack(side='left')
        self.retained_button = self.button(row, '可选记录：重启后仍保留', lambda: self.observe('restart_retained'))
        self.retained_button.pack(side='left', padx=8)
        self.not_retained_button = self.button(row, '记录：未保留', lambda: self.observe('not_retained'))
        self.not_retained_button.pack(side='left')
        ttk.Label(f, text='强化物、符咒、旗帜和生命石为新适配，尚待实测。保留情况可等正常重启时顺带检查。',
                  foreground=ui_theme.MUTED, wraplength=970).pack(anchor='w', pady=3)
        self.message = tk.StringVar(value='读取、预览和保留档次计算均为只读操作。当前未修改游戏。')
        ttk.Label(f, textvariable=self.message, wraplength=970, foreground=ui_theme.TEXT).pack(anchor='w', pady=(10, 0))
        self.refresh_history()
        self.controls()
        for variable in (self.query, self.family_filter, self.rarity_filter, self.editable_only,
                         self.trait_mode, self.trait_query, self.color_filter):
            variable.trace_add('write', self.schedule_filters)
        root.after(100, self.poll)

    def button(self, parent, text, command):
        b = ttk.Button(parent, text=text, command=command)
        self.buttons.append(b)
        return b

    @staticmethod
    def tree(parent, columns, headings, widths, height):
        holder = ttk.Frame(parent)
        holder.pack(fill='both', expand=True, pady=5)
        t = ttk.Treeview(holder, columns=columns, show='headings', selectmode='browse', height=height)
        for key, text, width in zip(columns, headings, widths):
            t.heading(key, text=text)
            t.column(key, width=width, minwidth=65)
        scroll = ttk.Scrollbar(holder, orient='vertical', command=t.yview)
        t.configure(yscrollcommand=scroll.set)
        t.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        return t

    def controls(self):
        for b in self.buttons:
            b.configure(state='disabled' if self.busy else 'normal')
        for widget, state in self.filter_controls:
            if widget.winfo_exists():
                widget.configure(state='disabled' if self.busy else state)
        self.slots.configure(state='disabled' if self.busy else 'readonly')
        self.targets.configure(state='disabled' if self.busy else 'readonly')
        self.keep_check.configure(state='disabled' if self.busy else 'normal')
        edit = not self.busy and self.candidate is not None and not self.keep.get()
        self.slider.configure(state='normal' if edit else 'disabled')
        self.entry.configure(state='normal' if edit else 'disabled')
        self.apply_button.configure(state='normal' if self.candidate and not self.busy else 'disabled')
        self.details_button.configure(state='normal' if self.slot and not self.busy else 'disabled')
        can_restore = self.last and self.last.get('state') == 'applied_and_read_back'
        self.restore_button.configure(state='normal' if can_restore and not self.busy else 'disabled')
        for b in (self.picked_button, self.retained_button, self.not_retained_button):
            b.configure(state='normal' if self.last and not self.busy else 'disabled')

    def reset_selection(self):
        self.row = self.slot = self.candidate = self.prepared = None
        self.slots.set('')
        self.targets.set('')
        self.slots.configure(values=[])
        self.targets.configure(values=[])
        self.value.set('')
        self.unit.set('')
        self.preview_text.set('选择一件装备和目标词条后，显示本次方案。')
        self.controls()

    def scan(self):
        if not self.busy:
            self.start('正在读取尚未拾取的装备，请先停在附近。', service.scan, self.finish_scan)

    def finish_scan(self, snapshot):
        self.snapshot = snapshot
        self.reset_selection()
        self.filter_index = search_index(snapshot['rows'])
        editable = sum(row.get('editable', bool(row['slots'])) for row in snapshot['rows'])
        if not snapshot['rows']:
            self.range_text.set('这次没有读到地上的可识别装备。若物品仍在地上，请停在附近再读一次。')
        elif not editable:
            self.range_text.set('已读到地上装备，目前没有可写入的词条组合；选中装备可查看具体原因。')
        else:
            self.range_text.set('选择显示“可编辑”的装备，再选择一条主词条或副词条。')
        other = snapshot.get('other_equipment_count', 0)
        suffix = f'；另读到 {other} 件暂未开放的其他装备' if other else ''
        self.message.set(f"读到 {len(snapshot['rows'])} 件装备，其中 {editable} 件可编辑{suffix}。游戏数据未改动。")
        self.apply_filters()

    def schedule_filters(self, *_args):
        if self.filter_pending is not None:
            self.root.after_cancel(self.filter_pending)
        self.filter_pending = self.root.after(150, self.apply_filters)

    def apply_filters(self):
        if self.filter_pending is not None:
            self.root.after_cancel(self.filter_pending)
            self.filter_pending = None
        if self.busy or not self.snapshot:
            return
        indices = matching_indices(self.filter_index, query=self.query.get(), family=self.family_filter.get(),
                                   rarity=self.rarity_filter.get(), editable_only=self.editable_only.get(),
                                   trait_mode=self.trait_mode.get(), trait_query=self.trait_query.get(), color=self.color_filter.get())
        previous = self.items.selection()
        keep = previous[0] if previous and int(previous[0]) in indices else None
        if keep is None:
            self.reset_selection()
        self.items.delete(*self.items.get_children())
        for i in indices:
            row = self.snapshot['rows'][i]
            rec = row['record']
            self.items.insert('', 'end', iid=str(i), values=(row['name'], row.get('family_label', '装备'),
                              rarity_label(rec['item']), f"{rec['item']['tierIdentifier']:g}",
                              f"{rec['distance_game_units']/100:.1f}米", rec['item']['id'][-12:], row.get('state_label', '可编辑')),
                              tags=() if row.get('editable', True) else ('unavailable',))
        editable = sum(self.snapshot['rows'][i].get('editable', False) for i in indices)
        extra = []
        if self.trait_mode.get() != '不限词条' and self.trait_query.get().strip():
            extra.append('已筛选可替换词条' if self.trait_mode.get() == '可替换为' else '已筛选现有词条')
        if self.color_filter.get() != '全部颜色':
            extra.append(self.color_filter.get() + '强化物')
        suffix = ' · ' + ' / '.join(extra) if extra else ''
        self.filter_count.set(f"显示 {len(indices)} / {len(self.filter_index)} 件 · 可编辑 {editable} 件{suffix}")
        if keep is not None:
            self.items.selection_set(keep)
            self.select_item()
        elif len(indices) == 1:
            self.items.selection_set(str(indices[0]))
            self.select_item()
        elif not indices and self.filter_index:
            self.range_text.set('当前筛选没有匹配装备。可放宽条件或点击“清空筛选”，无需重新读取。')
        elif self.row is None and indices:
            self.range_text.set('请选择一件筛选结果，再选择要替换的词条。')

    def clear_filters(self):
        if self.busy:
            return
        for variable, value in [(self.query, ''), (self.family_filter, '全部类型'),
                                (self.rarity_filter, '全部品质'), (self.editable_only, False),
                                (self.trait_mode, '不限词条'), (self.trait_query, ''), (self.color_filter, '全部颜色')]:
            variable.set(value)
        self.apply_filters()

    def show_filters(self):
        if self.busy:
            return
        if self.filter_popup is not None and self.filter_popup.winfo_exists():
            self.filter_popup.lift()
            return
        popup = self.filter_popup = tk.Toplevel(self.root)
        popup.title('词条与强化物筛选')
        popup.geometry('660x245')
        frame = ttk.Frame(popup, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='条件实时生效，并与名称、类型、品质筛选同时使用。', wraplength=610).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=12)
        mode = ttk.Combobox(row, textvariable=self.trait_mode, state='readonly', width=14,
                            values=['不限词条', '已有词条包含', '可替换为'])
        mode.pack(side='left')
        query = ttk.Entry(row, textvariable=self.trait_query, width=30)
        query.pack(side='left', padx=10, fill='x', expand=True)
        ttk.Label(frame, text='例如：暴击伤害、武器技艺伤害。“可替换为”只匹配当前工具确实可写的候选。',
                  wraplength=610).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=12)
        ttk.Label(row, text='强化物颜色').pack(side='left')
        color = ttk.Combobox(row, textvariable=self.color_filter, state='readonly', width=14,
                             values=['全部颜色', '红色', '绿色', '蓝色', '中性'])
        color.pack(side='left', padx=10)
        ttk.Label(row, text='选定颜色时只显示对应强化物。').pack(side='left')
        widgets = [(mode, 'readonly'), (query, 'normal'), (color, 'readonly')]
        self.filter_controls.extend(widgets)
        def close():
            self.filter_controls = [pair for pair in self.filter_controls if pair not in widgets]
            popup.destroy()
            self.filter_popup = None
        popup.protocol('WM_DELETE_WINDOW', close)
        ttk.Button(frame, text='关闭条件窗口', command=close).pack(anchor='e')

    def select_item(self, _event=None):
        if self.busy or not self.items.selection() or not self.snapshot:
            return
        row = self.snapshot['rows'][int(self.items.selection()[0])]
        if self.row is row:
            return
        self.reset_selection()
        self.row = row
        if not row.get('editable', True):
            self.range_text.set(row['reason'])
            self.preview_text.set('可以正常拾取这件装备；写入只对已适配的组合开放，具体原因可在候选窗口查看。')
        self.slot_rows = list(row['slots'])
        counts, labels = {}, []
        for s in self.slot_rows:
            primary = s.get('slot_type', s['trait'].get('slotType')) == 'Primary Trait'
            group = '主词条' if primary else '副词条'
            counts[group] = counts.get(group, 0) + 1
            policy = s.get('primary_policy')
            state = '（固定）' if policy and policy['reason_code'] == 'fixed_primary' else ('（当前不可写）' if not s['candidates'] else '')
            labels.append(f"{group}{counts[group]} · {trait_label(s['trait'])} {trait_value_text(s['trait'])}{state}")
        self.slots.configure(values=labels)
        if self.slot_rows:
            secondary = [i for i, s in enumerate(self.slot_rows)
                         if s.get('slot_type', s['trait'].get('slotType')) != 'Primary Trait']
            preferred = next((i for i in secondary if self.slot_rows[i]['candidates']), secondary[0] if secondary else None)
            if preferred is not None:
                self.slots.current(preferred)
                self.select_slot()
            else:
                self.range_text.set('请主动选择要查看的主词条；随机主词条新适配不会自动选中或写入。')

    def select_slot(self, _event=None):
        if self.busy or self.slots.current() < 0:
            return
        self.slot = self.slot_rows[self.slots.current()]
        self.candidate = self.prepared = None
        self.targets.set('')
        self.targets.configure(values=[trait_label(c['trait'])+('（强化物新适配）' if c.get('new_augment_support') else
                                                             f"（{self.row['family_label']}新适配）" if c.get('new_family_support') else
                                                             '（随机主词条新适配）' if c.get('new_primary_support') else
                                                             '（新适配）' if c.get('new_parameter_support') else '')
                                       for c in self.slot['candidates']])
        normal = self.slot.get('normal_candidate_count', len(self.slot['candidates']))
        self.range_text.set(f"原游戏允许的其他类型 {normal} 种，当前可写 {len(self.slot['candidates'])} 种。点“查看候选与原因”了解限制。")
        policy = self.slot.get('primary_policy')
        if policy and not policy['allowed']:
            self.range_text.set(policy['reason'])
        self.value.set('')
        self.unit.set('')
        self.preview_text.set('选择目标类型后，显示本次方案。')
        self.controls()

    def show_candidates(self):
        if self.busy or not self.slot:
            return
        slot = self.slot
        popup = tk.Toplevel(self.root)
        popup.title('候选类型与可用原因')
        popup.geometry('1080x540')
        f = ttk.Frame(popup, padding=18)
        f.pack(fill='both', expand=True)
        policy = slot.get('primary_policy')
        header = policy['reason'] if policy and not policy['allowed'] else '候选已按当前元素、原游戏类型库及其他词条互斥规则筛选。无法写入的组合会说明原因。'
        ttk.Label(f, text=header,
                  wraplength=1030).pack(anchor='w', pady=(0, 8))
        table = self.tree(f, ('type', 'range', 'state', 'reason'), ('候选类型', '正常范围', '当前状态', '原因'), (240, 170, 100, 480), 8)
        details = slot.get('all_candidates', slot['candidates'])
        for c in details:
            ranges = ' / '.join(f"{r['min']*r['multiplier']:g}～{r['max']*r['multiplier']:g}{r['unit']}"
                                for r in c.get('ranges', []) if r['varying'])
            if not ranges:
                fixed = next((r for r in c.get('ranges', []) if r['parameter'] == 'Magnitude.X'), None)
                ranges = f"{fixed['min']*fixed['multiplier']:g}{fixed['unit']}（固定）" if fixed else '待核对'
            available = c.get('available', True)
            state = ('新增可写' if any(c.get(k) for k in ('new_parameter_support', 'new_primary_support', 'new_augment_support', 'new_family_support')) else '可写入') if available else '暂不可写'
            table.insert('', 'end', values=(trait_label(c['trait']), ranges, state,
                                           c.get('reason') or '已适配；写入前会再次核对这件掉落'))
        full_text = tk.StringVar(value='选中候选后，可在这里查看完整名称与限制原因。')
        ttk.Label(f, textvariable=full_text, wraplength=1030).pack(anchor='w', pady=5)
        def show_full(_event=None):
            selection = table.selection()
            if selection:
                full_text.set(' · '.join(str(x) for x in table.item(selection[0], 'values') if x))
        table.bind('<<TreeviewSelect>>', show_full)
        row = ttk.Frame(f)
        row.pack(fill='x', pady=(10, 5))
        ttk.Label(row, text='检查常用类型').pack(side='left')
        checks = [('暴击率', 'CritChanceSecondary'), ('暴击伤害', 'CritDamageSecondary'),
                  ('武器技艺伤害', 'WeaponArtDamagePercentSecondary'), ('减益状态强度', 'AilmentPowerSecondary'),
                  ('减益状态持续时间', 'AilmentDurationSecondary')]
        if slot.get('slot_type') == 'Primary Trait':
            checks = [('北斗技艺伤害', 'Trigger.NoModularTrigger.Payoff.NorthernTechDamage.Rank.4'),
                      ('南斗技艺伤害', 'Trigger.NoModularTrigger.Payoff.ForbiddenTechDamage.Rank.4'),
                      ('南斗技艺对满血敌人的伤害', 'Trigger.NoModularTrigger.Payoff.ForbiddenTechDamageToFullHealth.Rank.5')]
        choice = ttk.Combobox(row, state='readonly', values=[x[0] for x in checks], width=28)
        choice.pack(side='left', padx=10)
        choice.current(1)
        reason = tk.StringVar()
        def explain(_event=None):
            if policy and not policy['allowed']:
                reason.set(policy['reason'])
                return
            name = checks[choice.current()][1]
            if name == slot['trait']['traitName']:
                reason.set('这是当前词条，无需替换。')
                return
            found = next((c for c in details if c['traitName'] == name), None)
            if not found:
                reason.set('不在这件装备此位置的原游戏候选库中，或与其他词条互斥。')
            else:
                reason.set(('原游戏允许，当前版本可以写入。'+('新增适配，尚待游戏内核对。' if any(found.get(k) for k in ('new_parameter_support', 'new_primary_support', 'new_augment_support', 'new_family_support')) else '')) if found.get('available', True) else
                           '原游戏允许，但当前不可写：'+found['reason'])
        choice.bind('<<ComboboxSelected>>', explain)
        ttk.Label(f, textvariable=reason, foreground=ui_theme.TEXT, wraplength=1030).pack(anchor='w', pady=5)
        explain()

    def select_target(self, _event=None):
        if self.busy or self.targets.current() < 0:
            return
        self.candidate = self.slot['candidates'][self.targets.current()]
        self.keep.set(True)
        row = next(r for r in self.candidate['ranges'] if r['varying'])
        self.range_row = row
        self.unit.set(row['unit'])
        self.range_text.set(f"正常显示范围：{row['min']*row['multiplier']:g}～{row['max']*row['multiplier']:g}{row['unit']}")
        self.slider.set(min(.999, self.candidate['default_quality']))
        self.set_value(self.candidate['default_quality'])
        self.controls()

    def set_value(self, quality):
        value = number_for_quality(self.range_row, quality) * self.range_row['multiplier']
        self.value.set(f'{value:g}')
        self.preview_text.set(f"{self.preview_name()}：{trait_label(self.slot['trait'])} → {trait_label(self.candidate['trait'])} {value:g}{self.unit.get()}")

    def preview_name(self):
        profile = self.row.get('augment_profile')
        if profile:
            return f"{self.row['name']}（{profile['color']}，耗能{profile['tier_power_cost']:g}，保留）"
        return self.row['name']

    def change_mode(self):
        if self.candidate and self.keep.get():
            self.slider.set(min(.999, self.candidate['default_quality']))
            self.set_value(self.candidate['default_quality'])
        self.controls()

    def value_changed(self, *_args):
        if self.candidate and not self.keep.get():
            self.preview_text.set(f"{self.preview_name()}：{trait_label(self.slot['trait'])} → {trait_label(self.candidate['trait'])} {self.value.get()}{self.unit.get()}（自选值，写入前再次核对）")

    def slide(self, value):
        if self.candidate and not self.keep.get():
            self.set_value(float(value))

    def apply(self):
        if self.busy:
            return
        self.apply_filters()
        if not self.candidate:
            return
        snapshot, row = self.snapshot, self.row
        index, target = self.slot['index'], self.candidate['traitName']
        try:
            value = None if self.keep.get() else float(self.value.get())
        except ValueError:
            self.message.set('请输入正常范围内的数值。')
            return
        def work():
            prepared = service.plan(snapshot, row, index, target, display_value=value)
            return service.apply(snapshot, prepared)
        self.start('正在重新核对这一个地上物品，备份后写入并读回。请先不要拾取。', work, self.finish_apply)

    def finish_apply(self, result):
        self.last = {**result, 'state': 'applied_and_read_back'}
        self.reset_selection()
        self.refresh_history()
        self.message.set('已写入并核对。现在可正常拾取这件装备，再打开详情核对。尚未自动验证重启后的保留结果。')
        self.controls()

    def restore(self):
        if not self.busy and self.last:
            last = dict(self.last)
            self.start('正在核对物品仍未拾取，并撤回这一条修改。', lambda: service.restore(last), self.finish_restore)

    def finish_restore(self, _result):
        self.last['state'] = 'restored_before_pickup'
        self.refresh_history()
        self.reset_selection()
        self.message.set('已撤回这次修改。需要再次编辑时，请重新读取地上装备。')

    def refresh_history(self):
        self.history.delete(*self.history.get_children())
        self.history_rows = service.history()
        for i, row in enumerate(self.history_rows):
            self.history.insert('', 'end', iid=str(i), values=(row['name']+' / '+row['item_id'][-10:], row['target'], row['state_label']))

    def select_history(self, _event=None):
        if not self.busy and self.history.selection():
            self.last = dict(self.history_rows[int(self.history.selection()[0])])
            self.controls()

    def observe(self, observation):
        if self.busy or not self.last:
            return
        service.record_observation(self.last, observation)
        self.last['state'] = observation
        self.refresh_history()
        self.controls()
        self.message.set('已保存你的核对结果。这是手动记录，不代表工具已经读取到服务端或实战结果。')

    def start(self, message, work, finish):
        self.busy = True
        self.message.set(message)
        self.controls()
        def run():
            try:
                self.events.put((True, work(), finish))
            except Exception as e:
                self.events.put((False, str(e), finish))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            success, result, finish = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            if success:
                try:
                    finish(result)
                except Exception as e:
                    self.message.set('操作结果已保存，但界面未能更新：'+str(e))
            else:
                self.message.set('未完成：'+str(result))
                self.refresh_history()
            self.controls()
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            self.message.set('正在完成核对或写入，请等操作结束再关闭。')
        else:
            self.root.destroy()


if __name__ == '__main__':
    from pathlib import Path
    from tkinter import messagebox
    import traceback
    root = None
    try:
        root = tk.Tk()
        ttk.Style(root).theme_use('clam')
        GroundDropEditor(root)
        root.mainloop()
    except Exception:
        log = Path(__file__).resolve().parent / 'ground_editor_startup_error.log'
        log.write_text(traceback.format_exc(), encoding='utf-8')
        if root is not None:
            messagebox.showerror('新掉落编辑未能打开', '错误已记录，请保留 ground_editor_startup_error.log 供检查。', parent=root)
