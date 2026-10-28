"""Arsenal-style picker for the trait panel. Filters never modify draft or gear."""
from localized_widgets import tk
from localized_widgets import ttk
from inventory_snapshot import FAMILIES, RARITIES, SCOPES, SORTS, filter_rows
from equipment_names import equipment_name
from random_primary_catalogue import FILTERS
import browser_preferences as preferences
import ui_theme


class InventoryBrowser(tk.Toplevel):
    def __init__(self, panel, *, on_choose=None, multiple=False):
        super().__init__(panel)
        self.panel = panel
        self.on_choose,self.multiple=on_choose,multiple
        self.pref_job=None
        self.protocol('WM_DELETE_WINDOW',self.destroy)
        self.title('选择装备与强化物 · 筛选和排序')
        ui_theme.dark_titlebar(self)
        self.geometry('1100x700')
        self.minsize(960, 620)
        self.transient(panel.winfo_toplevel())
        self.rows, self.visible = panel.browser_rows, []
        self.scope = tk.StringVar(value=panel.scope.get())
        self.query, self.traits = tk.StringVar(), tk.StringVar()
        self.family, self.rarity = tk.StringVar(value='全部类型'), tk.StringVar(value='全部品质')
        self.primal, self.sort = tk.StringVar(value='全部形态'), tk.StringVar(value='名称')
        self.random_primary = tk.StringVar(value='不限主词条')
        self.color, self.weapon = tk.StringVar(value='全部颜色'), tk.StringVar(value='全部武器')
        self.favorite = tk.BooleanVar(value=False)
        self.equipped, self.plate = tk.StringVar(value='全部装备'), tk.StringVar(value='全部战甲')
        self.minimum, self.maximum = tk.StringVar(), tk.StringVar()
        self.status, self.detail = tk.StringVar(), tk.StringVar(value='选中装备后可查看配装位置和完整编号。')
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill='both', expand=True)
        filters=ttk.LabelFrame(frame,text='筛选条件',padding=(8,4));filters.pack(fill='x',pady=(0,8))
        row = ttk.Frame(filters); row.pack(fill='x')
        ttk.Label(row, text='读取范围').pack(side='left')
        self.combo(row, self.scope, SCOPES, 19)
        ttk.Label(row, text='名称 / 编号').pack(side='left', padx=(8, 0))
        ttk.Entry(row, textvariable=self.query).pack(side='left', padx=6, fill='x', expand=True)
        ttk.Button(row, text='清空条件', command=self.clear).pack(side='right')
        row = ttk.Frame(filters); row.pack(fill='x', pady=8)
        self.combo(row, self.family, ['全部类型', *FAMILIES.values()], 9)
        self.combo(row, self.rarity, ['全部品质', *RARITIES.values()], 9)
        self.combo(row, self.primal, ['全部形态', '仅原始装备', '非原始装备', '仅诅咒装备', '已解除诅咒'], 12)
        self.random_primary_box=self.combo(row, self.random_primary, FILTERS, 21)
        self.weapon_box=self.combo(row, self.weapon, ['全部武器', '长剑', '双剑', '巨剑', '长柄武器', '战锤'], 10)
        self.color_box=self.combo(row, self.color, ['全部颜色', '红色', '绿色', '蓝色'], 9)
        self.favorite_box=ttk.Checkbutton(row, text='仅收藏', variable=self.favorite)
        self.favorite_box.pack(side='left', padx=8)
        row = ttk.Frame(filters); row.pack(fill='x')
        ttk.Label(row, text='已有词条').pack(side='left')
        ttk.Entry(row, textvariable=self.traits, width=21).pack(side='left', padx=6, fill='x', expand=True)
        self.combo(row, self.equipped, ['全部装备', '已保存到配装', '未保存到配装'], 14)
        ttk.Label(row, text='等级').pack(side='left')
        ttk.Entry(row, textvariable=self.minimum, width=4).pack(side='left', padx=4)
        ttk.Label(row, text='～').pack(side='left')
        ttk.Entry(row, textvariable=self.maximum, width=4).pack(side='left', padx=4)
        self.combo(row, self.sort, SORTS, 21)
        row = ttk.Frame(frame); row.pack(fill='x', pady=8)
        self.plate_ids = {'全部战甲': ''}
        for plate in (panel.snapshot or {}).get('manifest', {}).get('plates', []):
            label = equipment_name(plate['gameplayTag']) + ' / ' + plate['id'][-8:]
            self.plate_ids[label] = plate['id']
        ttk.Label(row, text='战甲').pack(side='left')
        self.combo(row, self.plate, list(self.plate_ids), 29)
        ttk.Label(row, textvariable=self.status, foreground=ui_theme.MUTED).pack(side='left', padx=10)
        holder = ttk.Frame(frame); holder.pack(fill='both', expand=True)
        columns = ('name', 'family', 'rarity', 'level', 'rank', 'where', 'id', 'state')
        self.tree = ttk.Treeview(holder, columns=columns, show='headings', selectmode='extended')
        ui_theme.tree_tags(self.tree)
        for col, title, width in zip(columns, ['名称', '类型', '品质', '等级', '强化', '配装位置', '编号末尾', '状态'],
                                      [220, 70, 75, 50, 50, 230, 110, 105]):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=45, stretch=col in {'name', 'where'})
        scroll = ttk.Scrollbar(holder, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True); scroll.pack(side='right', fill='y')
        self.tree.tag_configure('readonly', foreground=ui_theme.MUTED)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.tree.bind('<Double-1>', lambda event:None if event.state & 5 else self.choose())
        ttk.Label(frame, textvariable=self.detail, wraplength=1030, foreground=ui_theme.TEXT).pack(anchor='w', pady=8)
        row = ttk.Frame(frame); row.pack(fill='x')
        ttk.Button(row, text='加入选中物品' if multiple else '选中并查看词条', command=self.choose,
                   style='Accent.TButton' if multiple else 'TButton').pack(side='right')
        if not on_choose:ttk.Button(row,text='加入批量清单',command=self.add_to_batch,style='Accent.TButton').pack(side='right',padx=6)
        ttk.Label(row, text='按 Ctrl 或 Shift 多选。'+
                  '配装或背包变化后请在主窗口重新读取。', foreground=ui_theme.MUTED).pack(side='left')
        self.variables={name:getattr(self,name) for name in ['scope','query','traits','family','rarity','primal','sort',
                        'color','weapon','favorite','equipped','minimum','maximum','random_primary']}
        saved=preferences.load()
        for key,variable in self.variables.items():
            if key in saved:variable.set(saved[key])
        restored=next((label for label,identity in self.plate_ids.items() if identity==saved.get('plate_id')),'全部战甲')
        self.plate.set(restored)
        for variable in [self.scope, self.query, self.traits, self.family, self.rarity, self.primal, self.sort,
                         self.color, self.weapon, self.favorite, self.equipped, self.plate, self.minimum, self.maximum,self.random_primary]:
            variable.trace_add('write', lambda *_: self.refresh())
        self.refresh()

    @staticmethod
    def combo(parent, variable, values, width):
        box = ttk.Combobox(parent, textvariable=variable, values=values, width=width, state='readonly')
        box.pack(side='left', padx=(5, 7))
        return box

    def clear(self):
        self.query.set(''); self.traits.set(''); self.minimum.set(''); self.maximum.set('')
        self.family.set('全部类型'); self.rarity.set('全部品质'); self.primal.set('全部形态')
        self.random_primary.set('不限主词条')
        self.color.set('全部颜色'); self.weapon.set('全部武器'); self.favorite.set(False)
        self.equipped.set('全部装备'); self.plate.set('全部战甲'); self.sort.set('名称')

    @staticmethod
    def locations(row):
        return '；'.join(dict.fromkeys(('当前·' if b['current'] else '') + equipment_name(b['tag']) +
                                      f' 配装{b["preset"]+1}' for b in row['bindings'])) or ('历史记录，未确认归属' if row['origin'] == 'history' else '未保存到配装')

    def refresh(self):
        selected = self.tree.selection()
        identities={self.visible[int(i)]['item']['id'] for i in selected if int(i)<len(self.visible)}
        focus=self.tree.focus()
        focused_id=self.visible[int(focus)]['item']['id'] if focus and int(focus)<len(self.visible) else None
        self.weapon_box.pack_forget();self.color_box.pack_forget()
        if self.family.get()=='武器':self.weapon_box.pack(side='left',padx=(5,7),before=self.favorite_box)
        if self.family.get()=='强化物':self.color_box.pack(side='left',padx=(5,7),before=self.favorite_box)
        try:
            low, high = int(self.minimum.get() or 0), int(self.maximum.get() or 999)
            if not 0 <= low <= high <= 999: raise ValueError()
        except ValueError:
            self.status.set('等级范围请输入 0～999 的整数。'); return
        self.visible = filter_rows(self.rows, scope=self.scope.get(), query=self.query.get(), family=self.family.get(),
            rarity=self.rarity.get(), primal=self.primal.get(), favorite=self.favorite.get(), trait_query=self.traits.get(),
            random_primary=self.random_primary.get(),
            sort=self.sort.get(), subtype=self.weapon.get() if self.family.get()=='武器' else '全部武器',
            color=self.color.get() if self.family.get()=='强化物' else '全部颜色', equipped=self.equipped.get(),
            minimum_level=low, maximum_level=high, plate_id=self.plate_ids.get(self.plate.get(), ''))
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.visible):
            item = row['item']
            self.tree.insert('', 'end', iid=str(index), values=(row['label'], row['family'],
                ('原始·' if row['primal'] else '') + row['rarity'], item.get('tierIdentifier', '—'),
                item.get('masterworkUpgradeRank', 0), self.locations(row), item['id'][-10:],
                '可制作同款' if row.get('copy_only') else '可查看并编辑' if row['editable'] else '仅查看'),
                tags=(('alternate',) if index%2 else ())+(() if row['editable'] else ('readonly',)))
            if item['id'] in identities:self.tree.selection_add(str(index))
            if item['id']==focused_id:self.tree.focus(str(index))
        self.update_status()
        if self.pref_job:self.after_cancel(self.pref_job)
        self.pref_job=self.after(250,self.save_preferences)
        if not self.visible:
            self.detail.set('此范围没有匹配装备。尚未读取时，请安装读取组件后重新读取；历史记录需要单独选择。')
        elif not self.tree.selection():
            self.detail.set('选中装备后可查看配装位置和完整编号。')

    def select(self, _=None):
        selected = self.tree.selection()
        self.update_status()
        if not selected:
            if self.visible:self.detail.set('选中装备后可查看配装位置和完整编号。')
            return
        focused=self.tree.focus()
        index=focused if focused in selected else selected[0]
        row = self.visible[int(index)]
        self.update_status()
        self.detail.set((f'已选择 {len(selected)} 件 · ' if len(selected)>1 else '')+self.locations(row) + '\n' + row['item']['id'] +
                        ('\n' + (row.get('edit_reason') or '该类型本轮支持读取与筛选，词条编辑尚未开放。') if not row['editable'] else
                         '\n' + row['edit_reason'] if row.get('edit_reason') else '')+
                        '\n'+('有随机主词条；是否可编辑以本件校验为准。' if row.get('random_primary') is True else
                               '无随机主词条。' if row.get('random_primary') is False else '随机主词条状态未确认：记录或原生模板不完整。'))

    def choose(self):
        selected = self.tree.selection()
        if not selected or self.panel.host.busy: return
        if self.on_choose:
            rows=[self.visible[int(index)] for index in selected]
            try:self.on_choose(rows)
            except Exception as error:self.status.set('未加入：'+str(error));return
            self.destroy();return
        if len(selected)>1:
            self.status.set(f'已选择 {len(selected)} 件，请点击“加入批量清单”；查看单件词条时请选择一件。');return
        row = self.visible[int(selected[0])]
        self.panel.scope.set(self.scope.get())
        self.panel.apply_rows(self.visible, selected_id=row['item']['id'])
        self.destroy()

    def add_to_batch(self):
        selected=self.tree.selection()
        if not selected or self.panel.host.busy:return
        try:
            owner=self.panel.host.replacement_tab
            owner.open_batch()
            owner.batch_editor.add_rows([self.visible[int(index)] for index in selected])
        except Exception as error:self.status.set('未加入：'+str(error));return
        self.destroy()

    def update_status(self):
        context=('未确认归属的历史记录' if self.scope.get().startswith('历史') else
                 '上次游戏快照' if self.panel.snapshot and not self.panel.snapshot.get('live_process') else '本次界面快照')
        self.status.set(f'{len(self.visible)} 件 · 已选 {len(self.tree.selection())} 件 · '+context)

    def save_preferences(self):
        self.pref_job=None
        if not hasattr(self,'variables'):return
        values={key:variable.get() for key,variable in self.variables.items()}
        values['plate_id']=self.plate_ids.get(self.plate.get(),'')
        try:preferences.save(values)
        except OSError:self.status.set('筛选仍可使用，本次条件保存未完成。')

    def destroy(self):
        if self.pref_job:self.after_cancel(self.pref_job);self.pref_job=None
        self.save_preferences()
        super().destroy()
