"""One item's secondary draft; calculation and staging never install or write game state."""
from copy import deepcopy
from localized_widgets import tk
from localized_widgets import ttk

import replacement_service as service
from equipment_names import equipment_name
from trait_types import number_for_quality, trait_label, trait_value_text
import ui_theme


class MultiReplacementEditor(tk.Toplevel):
    def __init__(self, panel, source, *, initial_edits=None, on_apply=None, primary=False):
        super().__init__(panel.host.root)
        self.panel, self.host, self.source = panel, panel.host, deepcopy(source)
        self.on_apply=on_apply
        self.primary=primary
        self.slot_type='Primary Trait' if primary else 'Secondary Trait'
        self.slot_label='随机主词条' if primary else '副词条'
        self.edits, self.choices, self.options = [], {}, []
        self.index = self.info = self.variable = None
        self.busy = self.updating = False
        self.title(('随机主词条编辑 · ' if primary else '整件副词条编辑 · ') + equipment_name(source))
        ui_theme.dark_titlebar(self)
        self.geometry('980x660'); self.minsize(900, 600)
        self.transient(self.host.root)
        self.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(self, padding=14); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=equipment_name(source) + ' · '+self.slot_label+'方案',
                  font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=source['id'], foreground=ui_theme.MUTED).pack(anchor='w', pady=(3, 8))
        ttk.Label(frame, text=('一次只修改一条已适配的随机主词条；其他词条、主属性和原件保留。' if primary else
                             '逐条设置后，一次制作整件方案并生成一件新物品。原件、主词条、主属性和精通词条保留。'),
                  wraplength=930).pack(anchor='w')
        holder = ttk.Frame(frame); holder.pack(fill='both', expand=True, pady=10)
        self.tree = ttk.Treeview(holder, columns=('slot', 'old', 'oldvalue', 'new', 'value'),
                                 show='headings', height=7, selectmode='browse')
        ui_theme.tree_tags(self.tree)
        for key, title, width in [('slot', '词条位置', 85), ('old', '原词条', 230),
                                  ('oldvalue', '原值', 85), ('new', '本方案新词条', 260), ('value', '新值', 90)]:
            self.tree.heading(key, text=title); self.tree.column(key, width=width, minwidth=60)
        scroll = ttk.Scrollbar(holder, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True); scroll.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self.choose_slot)
        self.tree.bind('<Button-1>', lambda _: 'break' if self.busy or self.host.busy else None)
        self.tree.bind('<KeyPress>', lambda _: 'break' if self.busy or self.host.busy else None)
        row = ttk.Frame(frame); row.pack(fill='x', pady=5)
        ttk.Label(row, text='替换为').pack(side='left')
        self.target = ttk.Combobox(row, state='readonly', width=55)
        self.target.pack(side='left', fill='x', expand=True, padx=8)
        self.target.bind('<<ComboboxSelected>>', self.choose_target)
        self.restore = ttk.Button(row, text='还原该条', command=self.remove)
        self.restore.pack(side='left')
        self.range_text = tk.StringVar(value='先选一条'+self.slot_label+'。')
        ttk.Label(frame, textvariable=self.range_text, foreground=ui_theme.TEXT, wraplength=930).pack(anchor='w', pady=5)
        row = ttk.Frame(frame); row.pack(fill='x', pady=5)
        ttk.Label(row, text='正常范围内选值').pack(side='left')
        self.slider = ttk.Scale(row, from_=0, to=.999, command=self.slide)
        self.slider.pack(side='left', fill='x', expand=True, padx=8)
        self.value, self.unit = tk.StringVar(), tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.value, width=10); self.entry.pack(side='left')
        ttk.Label(row, textvariable=self.unit, width=5).pack(side='left', padx=4)
        self.quality_button = ttk.Button(row, text='保留原档次', command=self.original_quality)
        self.quality_button.pack(side='left')
        row = ttk.Frame(frame); row.pack(fill='x', pady=10)
        self.apply_button = ttk.Button(row, text='加入本件方案', command=self.apply)
        self.apply_button.pack(side='left')
        self.build_button = ttk.Button(row, text='制作整件同款方案', command=self.build)
        self.build_button.configure(style='Accent.TButton')
        if on_apply:self.build_button.configure(text='保存到批量清单')
        self.build_button.pack(side='right')
        self.status = tk.StringVar(value='此窗口只编辑方案；制作完成前，关闭窗口会放弃本轮修改。')
        ttk.Label(frame, textvariable=self.status, foreground=ui_theme.TEXT, wraplength=930).pack(anchor='w', pady=6)
        ttk.Label(frame, text='候选会结合本件其他拟改词条筛选。数值受原游戏范围限制；制作方案不安装、不改变游戏。',
                  foreground=ui_theme.MUTED, wraplength=930).pack(anchor='w', pady=5)
        self.render()
        self.grab_set()
        if initial_edits:self.validate(deepcopy(initial_edits))

    def controls(self):
        self.target.configure(state='disabled' if self.busy else 'readonly')
        for widget in [self.restore, self.apply_button, self.build_button, self.quality_button]:
            widget.configure(state='disabled' if self.busy else 'normal')
        for widget in [self.slider, self.entry]:
            widget.configure(state='normal' if self.variable and not self.busy else 'disabled')

    def run(self, message, job, finish):
        if self.busy or self.host.busy:
            return
        self.busy = True; self.status.set(message); self.controls()
        def work():
            try:
                return {'value': job()}
            except Exception as error:
                return {'error': str(error)}
        def done(result):
            if not self.winfo_exists():
                return
            self.busy = False; self.controls()
            if 'error' in result:
                self.status.set('未完成：' + result['error'])
            else:
                try:finish(result['value'])
                except Exception as error:self.status.set('未完成：'+str(error))
        self.host.start_job(message, work, done)

    def render(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for n, trait in enumerate(self.source['traits']):
            if trait.get('slotType') != self.slot_type:
                continue
            choice = self.choices.get(n)
            self.tree.insert('', 'end', iid=str(n), values=(n+1, trait_label(trait), trait_value_text(trait),
                choice['label'] if choice else '保留原词条', trait_value_text(choice['targetTrait']) if choice else '—'),
                tags=('edited',) if choice else (('alternate',) if n%2 else ()))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self.status.set(f'本件方案已设置 {len(self.edits)} 条{self.slot_label}。制作后才能安装；原件保留。')

    def calculate(self,source,edits,index=None):
        if self.primary:
            return service.calculate_primary(source,[] if index is not None else edits,index=index)
        return service.calculate_many(source,edits,index=index)

    def choose_slot(self, _event=None):
        if self.busy or self.host.busy or not self.tree.selection():
            return
        self.index = int(self.tree.selection()[0]); self.info = self.variable = None
        self.target.set(''); self.target.configure(values=[]); self.value.set(''); self.unit.set('')
        source, edits, index = deepcopy(self.source), deepcopy(self.edits), self.index
        self.run('正在核对本件最终候选与互斥规则。',
                 lambda: self.calculate(source, edits, index=index), self.finish_inspect)

    def finish_inspect(self, info):
        self.info = info
        self.options = [c for c in info['candidates'] if c.get('supported') and
                        c['traitName'] != self.source['traits'][self.index]['traitName']]
        self.target.configure(values=[c['label'] for c in self.options])
        self.range_text.set(f'可选 {len(self.options)} 种类型，已结合其他拟改词条筛选。')
        current = next((e for e in self.edits if e['index'] == self.index), None)
        if current:
            match = next((n for n,c in enumerate(self.options) if c['traitName'] == current['targetTraitName'] and
                          c['category'] == current.get('targetCategoryName')), None)
            if match is not None:
                self.target.current(match); self.choose_target()
                if 'quality' in current:
                    self.slider.set(current['quality']);self.slide(current['quality'])
                if self.variable and 'desiredValue' in current:
                    self.value.set(f'{current["desiredValue"] * self.variable["multiplier"]:g}')
        self.controls()

    def choose_target(self, _event=None):
        if self.busy or self.target.current() < 0 or not self.info:
            return
        candidate = self.options[self.target.current()]
        self.variable = next((r for r in candidate['ranges'] if r['varying']), None)
        ranges = '；'.join(f'{r["min"]*r["multiplier"]:g}～{r["max"]*r["multiplier"]:g}{r["unit"]}'
                          for r in candidate['ranges'] if r['varying'])
        self.range_text.set('正常范围：' + (ranges or '固定数值') + '。默认保留原档次；多参数随档次联动。')
        self.controls(); self.original_quality()

    def original_quality(self):
        if not self.info or self.busy:
            return
        self.slider.set(self.info['quality'].get('quality', .5))
        self.slide(self.slider.get())

    def slide(self, quality):
        if self.variable and not self.busy:
            self.value.set(f'{number_for_quality(self.variable, float(quality))*self.variable["multiplier"]:g}')
            self.unit.set(self.variable['unit'])
        elif not self.variable:
            self.value.set('固定'); self.unit.set('')

    def apply(self):
        if self.busy or self.host.busy or self.index is None or self.target.current() < 0:
            return
        candidate = self.options[self.target.current()]
        edit = {'index': self.index, 'targetTraitName': candidate['traitName'],
                'targetCategoryName': candidate['category'], 'quality': float(self.slider.get())}
        if self.variable:
            try:
                edit['desiredValue'] = float(self.value.get().strip().rstrip('%')) / self.variable['multiplier']
            except ValueError:
                self.status.set('请输入正常范围内的数字。'); return
        proposed = ([edit] if self.primary else [deepcopy(e) for e in self.edits if e['index'] != self.index] + [edit])
        self.validate(proposed)

    def validate(self, proposed):
        source = deepcopy(self.source)
        def finish(result):
            self.edits = sorted(proposed, key=lambda e:e['index'])
            self.choices = {c['index']: c for c in result['choices']}
            self.render()
        self.run('正在核对整件词条、数值与强化标记。', lambda: self.calculate(source, proposed), finish)

    def remove(self):
        if self.busy or self.host.busy or self.index is None:
            return
        proposed = [deepcopy(e) for e in self.edits if e['index'] != self.index]
        if len(proposed) == len(self.edits):
            return
        if proposed:
            self.validate(proposed)
        else:
            self.edits, self.choices = [], {}; self.render()

    def build(self):
        if self.busy or self.host.busy:
            return
        if not self.edits:
            self.status.set('请先把至少一条修改加入本件方案。'); return
        source, edits = deepcopy(self.source), deepcopy(self.edits)
        if self.on_apply:
            def saved(result):
                self.on_apply(source,edits,result);self.close()
            self.run('正在核对并保存本件批量草稿；不制作生成包或安装。',
                     lambda:self.calculate(source,edits),saved)
            return
        def finish(plan):
            self.panel.refresh(plan)
            self.host.notebook.select(self.panel)
            self.host.message.set('整件同款方案已制作，尚未安装；原件与游戏未改变。')
            self.close()
        self.run('正在制作整件同款方案；不安装或修改游戏。', lambda: service.prepare_many(source, edits), finish)

    def close(self):
        if self.busy or self.host.busy:
            self.status.set('正在核对方案，请等本次计算完成后关闭。'); return
        self.panel.editor = None
        self.destroy()
