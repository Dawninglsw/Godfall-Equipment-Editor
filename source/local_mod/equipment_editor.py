"""Local equipment editor. Draft edits never change the running game."""
from copy import deepcopy
import queue
import threading
from localized_widgets import tk
from tkinter import filedialog
from localized_widgets import ttk

from editor_model import (HERE, display_number, effect_metadata, export_config,
                          load_config, parse_display_value, rule_key, save_catalogue,
                          validate_config)
from settings_service import disable_patch, install_draft, installed_config, restore_verified_release, scan_catalogue
from settings_service import configuration_summary
import settings_service as settings_operations
from settings_service import editor_config, full_settings_backups, restore_full_settings
from primal_drop_settings import primal_label, primal_preferences, with_primal
from primal_drop_panel import PrimalDropPanel
from trait_type_panel import TraitTypePanel
from replacement_panel import ReplacementPanel
from uncurse_panel import UncursePanel
import ui_theme
from character_overview_panel import CharacterOverviewPanel
from localization import language,set_language,tr


class Settings:
    def __init__(self, root):
        self.root = root
        self.config_bytes = (HERE/'overrides.json').read_bytes()
        self.draft = editor_config(load_config(HERE/'overrides.json'))
        self.catalogue = save_catalogue(self.draft)
        self.busy, self.selected_rule = False, None
        self.events, self.buttons, self.entries = queue.Queue(), [], []
        root.title(tr('众神陨落-装备编辑器'))
        root.geometry('1040x820')
        root.minsize(930, 800)
        root.protocol('WM_DELETE_WINDOW', self.close)
        ui_theme.apply(root)
        frame = ttk.Frame(root, padding=(20, 14),style='App.TFrame')
        frame.pack(fill='both', expand=True)
        heading = ttk.Frame(frame,style='App.TFrame')
        heading.pack(fill='x')
        from branding import header_portrait
        self.header_avatar=header_portrait(root)
        if self.header_avatar:ttk.Label(heading,image=self.header_avatar,style='AppMuted.TLabel').pack(side='left',padx=(0,8))
        ttk.Label(heading, text='众神陨落-装备编辑器', style='Title.TLabel').pack(side='left')
        self.drop_editor = None
        self.batch_shortcut=self.button(heading,'批量词条编辑',lambda:self.replacement_tab.open_batch())
        self.batch_shortcut.configure(style='Accent.TButton');self.batch_shortcut.pack(side='right')
        ttk.Button(heading, text='打开新掉落词条编辑', command=self.open_drop_editor).pack(side='right',padx=8)
        self.application_settings=None
        self.button(heading,'设置',self.open_application_settings).pack(side='right',padx=4)
        self.language_var=tk.StringVar(value='English' if language()=='en' else '简体中文')
        self.language_box=ttk.Combobox(heading,textvariable=self.language_var,values=['简体中文','English'],state='readonly',width=9)
        self.language_box.pack(side='right',padx=6)
        self.language_box.bind('<<ComboboxSelected>>',self.change_language)
        self.workflow_help = tk.StringVar(value='先编辑草稿，退出游戏后安装，下次启动时生效。')
        ttk.Label(frame, textvariable=self.workflow_help,style='AppMuted.TLabel').pack(anchor='w', pady=(2, 7))
        self.summary = tk.StringVar()
        ttk.Label(frame, textvariable=self.summary,style='Info.TLabel').pack(fill='x', pady=(0, 8))
        self.enabled = tk.BooleanVar(value=self.draft['enabled'])
        self.enable_check = ttk.Checkbutton(frame, text='启用这些装备设置', variable=self.enabled, command=self.changed,style='App.TCheckbutton')
        self.enable_check.pack(anchor='w', pady=(0, 8))
        self.notebook = ttk.Notebook(frame)
        self.notebook.pack(fill='both', expand=True)
        self.rules_tab = ttk.Frame(self.notebook, padding=14)
        self.catalogue_tab = ttk.Frame(self.notebook, padding=14)
        self.backups_tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(self.rules_tab, text='  旧数值方案  ')
        self.notebook.add(self.catalogue_tab, text='  数值资料  ')
        self.notebook.add(self.backups_tab, text='  方案与备份  ')
        self.build_rules_tab()
        self.build_catalogue_tab()
        self.build_backups_tab()
        self.message = tk.StringVar(value='当前设置已载入。编辑草稿不会改变正在运行的游戏。')
        self.type_tab = TraitTypePanel(self.notebook, self)
        self.notebook.add(self.type_tab, text='  旧词条工具  ')
        self.primal_tab = PrimalDropPanel(self.notebook, self)
        self.notebook.insert(0, self.primal_tab, text='  原始掉落  ')
        self.replacement_tab = ReplacementPanel(self.notebook, self)
        self.notebook.insert(0, self.replacement_tab, text='  同款替代品  ')
        self.uncurse_tab = UncursePanel(self.notebook, self)
        self.notebook.insert(1, self.uncurse_tab, text='  解除诅咒  ')
        self.character_tab=CharacterOverviewPanel(self.notebook,self)
        self.notebook.insert(0,self.character_tab,text='  角色与配装  ')
        self.notebook.select(self.character_tab)
        ttk.Label(frame, textvariable=self.message, wraplength=970,style='AppMuted.TLabel').pack(anchor='w', pady=(10, 7))
        footer = ttk.Frame(frame,style='App.TFrame')
        footer.pack(fill='x')
        self.install_button = self.button(footer, '保存并安装', self.install)
        self.install_button.configure(style='Accent.TButton')
        self.install_button.pack(side='left')
        disable_button=self.button(footer, '停用全部补丁', self.disable);disable_button.configure(style='QuietDanger.TButton')
        disable_button.pack(side='left', padx=10)
        self.footer_help=tk.StringVar(value='装备与掉率一起保存 · 新掉落仍正常拾取')
        ttk.Label(footer, textvariable=self.footer_help,style='AppMuted.TLabel').pack(side='right')
        self.refresh_rules()
        self.refresh_catalogue()
        self.refresh_backups()
        self.notebook.bind('<<NotebookTabChanged>>', self.workflow_changed)
        self.workflow_changed()
        root.after(100, self.poll_events)

    def button(self, parent, text, command):
        widget = ttk.Button(parent, text=text, command=command)
        self.buttons.append(widget)
        return widget

    def change_language(self,_event=None):
        if self.busy:return
        selected='en' if self.language_var.get()=='English' else 'zh-CN'
        set_language(selected)
        self.root.title(tr('众神陨落-装备编辑器'))
        self.character_tab.refresh(self.character_tab.snapshot)
        if self.replacement_tab.batch_editor and self.replacement_tab.batch_editor.winfo_exists():
            self.replacement_tab.batch_editor.refresh()
        self.workflow_changed()

    def open_application_settings(self):
        if self.busy:return
        if self.application_settings and self.application_settings.winfo_exists():self.application_settings.lift();return
        from application_settings_panel import ApplicationSettings
        self.application_settings=ApplicationSettings(self)

    def finish_initialization(self,result):
        from tkinter import messagebox
        self.busy=True
        self.language_box.configure(state='disabled')
        messagebox.showinfo(tr('初始化完成'),tr(result['message'])+'\n\n'+tr('备份目录：')+result['backup'],parent=self.root)
        def finish():
            for callback in self.root.tk.call('after','info'):self.root.after_cancel(callback)
            self.root.destroy()
        self.root.after_idle(finish)

    def entry(self, parent, **options):
        widget = ttk.Entry(parent, **options)
        self.entries.append(widget)
        return widget

    @staticmethod
    def tree(parent, columns, headings, widths, height=7):
        holder = ttk.Frame(parent)
        holder.pack(fill='both', expand=True)
        tree = ttk.Treeview(holder, columns=columns, show='headings', height=height, selectmode='browse')
        for name, title, width in zip(columns, headings, widths):
            tree.heading(name, text=title)
            tree.column(name, width=width, minwidth=60, anchor='w')
        scrollbar = ttk.Scrollbar(holder, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        return tree

    def build_rules_tab(self):
        self.rule_tree = self.tree(self.rules_tab, ('item', 'trait', 'base', 'target', 'state'),
                                   ('装备', '词条', '原值', '设定值', '状态'), (195, 250, 95, 95, 120))
        self.rule_tree.bind('<<TreeviewSelect>>', self.select_rule)
        editor = ttk.Frame(self.rules_tab)
        editor.pack(fill='x', pady=(12, 6))
        ttk.Label(editor, text='选中词条的新数值').pack(side='left')
        self.rule_value = tk.StringVar()
        self.entry(editor, textvariable=self.rule_value, width=13, font=('Microsoft YaHei UI', 11)).pack(side='left', padx=8)
        self.rule_unit = tk.StringVar()
        ttk.Label(editor, textvariable=self.rule_unit, width=5).pack(side='left')
        self.button(editor, '应用到草稿', self.apply_value).pack(side='left', padx=7)
        actions = ttk.Frame(self.rules_tab)
        actions.pack(fill='x', pady=(5, 7))
        self.button(actions, '选中词条恢复原值', self.restore_selected).pack(side='left')
        self.button(actions, '移除选中设置', self.remove_selected).pack(side='left', padx=8)
        self.button(actions, '全部恢复原值', self.restore_all).pack(side='left')
        ttk.Label(self.rules_tab, text='恢复或移除也只修改草稿，需“保存并安装”后重启游戏。\n新装备、新词条与新数值仍需在游戏里验证。',
                  foreground=ui_theme.MUTED, wraplength=880).pack(anchor='w', pady=(3, 0))

    def build_catalogue_tab(self):
        toolbar = ttk.Frame(self.catalogue_tab)
        toolbar.pack(fill='x', pady=(0, 8))
        ttk.Label(toolbar, text='搜索装备或词条').pack(side='left')
        self.search = tk.StringVar()
        self.search.trace_add('write', lambda *_: self.refresh_catalogue())
        self.entry(toolbar, textvariable=self.search, width=30).pack(side='left', padx=8)
        self.button(toolbar, '从游戏读取', self.read_game).pack(side='right')
        self.catalogue_summary = tk.StringVar()
        ttk.Label(self.catalogue_tab, textvariable=self.catalogue_summary, foreground=ui_theme.MUTED).pack(anchor='w', pady=(0, 8))
        self.catalogue_tree = self.tree(self.catalogue_tab, ('item', 'trait', 'value', 'state'),
                                        ('装备 / 编号末尾', '词条', '读到的原值', '可用状态'), (260, 270, 115, 150))
        self.catalogue_tree.bind('<<TreeviewSelect>>', self.select_catalogue)
        self.catalogue_detail = tk.StringVar(value='清单来自曾读取的装备记录，并非完整背包。先核对游戏显示，再添加新设置。')
        ttk.Label(self.catalogue_tab, textvariable=self.catalogue_detail, wraplength=900, foreground=ui_theme.MUTED).pack(anchor='w', pady=(10, 8))
        editor = ttk.Frame(self.catalogue_tab)
        editor.pack(fill='x')
        ttk.Label(editor, text='设定值').pack(side='left')
        self.new_value = tk.StringVar()
        self.entry(editor, textvariable=self.new_value, width=13, font=('Microsoft YaHei UI', 11)).pack(side='left', padx=8)
        self.new_unit = tk.StringVar()
        ttk.Label(editor, textvariable=self.new_unit, width=5).pack(side='left')
        self.button(editor, '加入修改草稿', self.add_rule).pack(side='left', padx=7)

    def build_backups_tab(self):
        actions = ttk.Frame(self.backups_tab)
        actions.pack(fill='x', pady=(0, 12))
        self.button(actions, '导出当前方案', self.export_scheme).pack(side='left')
        self.button(actions, '导入方案到草稿', self.import_scheme).pack(side='left', padx=8)
        ttk.Label(self.backups_tab, text='完整备份包含补丁、装备设置和掉率设置。恢复前也会自动备份当前状态。', wraplength=900).pack(anchor='w', pady=(0, 10))
        tabs = ttk.Notebook(self.backups_tab)
        tabs.pack(fill='both', expand=True)
        complete, legacy = ttk.Frame(tabs, padding=8), ttk.Frame(tabs, padding=8)
        tabs.add(complete, text='完整设置备份')
        tabs.add(legacy, text='旧方案草稿备份')
        self.full_backup_tree = self.tree(complete, ('date', 'drop', 'equipment', 'reason'),
                                         ('备份时间', '原始掉落', '装备设置', '原因'), (180, 190, 110, 300), height=5)
        row = ttk.Frame(complete)
        row.pack(fill='x', pady=10)
        self.button(row, '恢复选中完整备份', self.restore_full_backup).pack(side='left')
        ttk.Label(complete, text='需退出游戏；恢复后下次启动时生效。备份文件校验未通过时不会覆盖。',
                  wraplength=850, foreground=ui_theme.MUTED).pack(anchor='w')
        self.backup_tree = self.tree(legacy, ('date', 'count', 'file'),
                                    ('备份时间', '词条数', '备份编号'), (240, 120, 450), height=5)
        row = ttk.Frame(legacy)
        row.pack(fill='x', pady=(10, 12))
        self.button(row, '将选中备份载入草稿', self.load_backup).pack(side='left')
        self.button(row, '恢复原始设置', self.restore_verified).pack(side='left', padx=8)
        ttk.Label(legacy, text='旧方案仅载入草稿；未含掉率设置的方案会保留当前掉率草稿。\n“恢复原始设置”会清空装备修改并关闭掉率修改。',
                  wraplength=850, foreground=ui_theme.MUTED).pack(anchor='w')

    def current_draft(self):
        draft = deepcopy(self.draft)
        draft['enabled'] = bool(self.enabled.get())
        if hasattr(self, 'primal_tab'):
            draft['primalDrop'] = self.primal_tab.value()
        return validate_config(draft)

    def update_summary(self):
        config = self.current_draft()
        current, status = installed_config()
        counts = configuration_summary(config)
        if current is None and not config['enabled'] and not counts['rules'] and not counts['primal']['enabled']:
            pending = ' · 默认修改为空'
        else:
            pending = ' · 草稿尚未安装' if current is None or with_primal(current) != with_primal(config) else ' · 与已安装设置一致'
        self.summary.set(f'{status} · {counts["rules"]}条装备设置 · {primal_label(counts["primal"])}{pending}')
        if current is not None and settings_operations.installation_state().get('replacement_copy_trial'):
            self.summary.set(self.summary.get() + ' · 同款生成试验（一次）')

    def changed(self):
        if not self.busy:
            self.update_summary()
            self.message.set('草稿已更改。退出游戏后点击“保存并安装”才会生效。')

    def workflow_changed(self, _event=None):
        overview=self.notebook.select()==str(self.character_tab)
        self.character_tab.add_button.configure(state='normal' if self.character_tab.selected_item and not self.busy else 'disabled')
        if overview:
            self.enable_check.pack_forget()
            self.install_button.configure(text='当前为查看模式',state='disabled')
            self.workflow_help.set('查看各套战甲的装备与强化物；选中物品可查看完整词条或加入批量编辑。')
            self.footer_help.set('仅查看记录 · 不切换游戏中的配装')
            return
        self.enable_check.pack(anchor='w',pady=(0,8),before=self.notebook)
        self.install_button.configure(state='disabled' if self.busy else 'normal')
        self.footer_help.set('装备与掉率一起保存 · 新掉落仍正常拾取')
        if self.notebook.select() == str(self.uncurse_tab):
            self.install_button.configure(text='安装解咒计划')
            self.workflow_help.set('选中一件装备，退出后安装解咒计划；下次启动自动尝试完成当前诅咒目标。')
            return
        replacement = self.notebook.select() == str(self.replacement_tab)
        self.install_button.configure(text='安装同款生成' if replacement else '保存并安装')
        self.workflow_help.set('制作同款新物品并保留原件，正常拾取保存后可停用生成补丁。' if replacement
                               else '先编辑草稿，退出游戏后安装，下次启动时生效。')

    def refresh_rules(self):
        selected = self.selected_rule
        self.rule_tree.delete(*self.rule_tree.get_children())
        installed, _ = installed_config()
        current = {rule_key(r): r for r in installed['items']} if installed else {}
        for index, rule in enumerate(self.draft['items']):
            effect = rule['lootEffectName']
            parameter = rule['magnitudeName']
            meta = effect_metadata(effect, parameter)
            unit = meta['unit'] if meta['unit'] in {'%', '秒'} else ''
            state = '已安装' if current.get(rule_key(rule)) == rule else '草稿待安装'
            self.rule_tree.insert('', 'end', iid=str(index), values=(rule.get('label', rule['gameplayTag']),
                                  rule.get('traitLabel', meta['label']),
                                  display_number(rule['baseline'], effect, parameter) + unit,
                                  display_number(rule['value'], effect, parameter) + unit, state))
        if selected is not None and selected < len(self.draft['items']):
            self.rule_tree.selection_set(str(selected))
        self.update_summary()

    def select_rule(self, _event=None):
        if self.busy:
            return
        selection = self.rule_tree.selection()
        self.selected_rule = int(selection[0]) if selection else None
        if self.selected_rule is not None:
            rule = self.draft['items'][self.selected_rule]
            self.rule_value.set(display_number(rule['value'], rule['lootEffectName'], rule['magnitudeName']))
            self.rule_unit.set(effect_metadata(rule['lootEffectName'], rule['magnitudeName'])['unit'])

    def apply_value(self):
        if not self.busy and self.selected_rule is not None and self.commit_rule_edit():
            self.changed()

    def commit_rule_edit(self):
        if self.selected_rule is None:
            return True
        rule = self.draft['items'][self.selected_rule]
        try:
            rule['value'] = parse_display_value(self.rule_value.get(), rule['lootEffectName'], rule['magnitudeName'])
        except ValueError as error:
            self.message.set(str(error))
            return False
        self.refresh_rules()
        return True

    def restore_selected(self):
        if self.busy or self.selected_rule is None:
            return
        rule = self.draft['items'][self.selected_rule]
        rule['value'] = rule['baseline']
        self.refresh_rules()
        self.select_rule()
        self.changed()

    def remove_selected(self):
        if self.busy or self.selected_rule is None:
            return
        del self.draft['items'][self.selected_rule]
        self.selected_rule = None
        self.refresh_rules()
        self.changed()

    def restore_all(self):
        if self.busy:
            return
        for rule in self.draft['items']:
            rule['value'] = rule['baseline']
        self.refresh_rules()
        self.select_rule()
        self.changed()

    def refresh_catalogue(self):
        if not hasattr(self, 'catalogue_tree'):
            return
        search = self.search.get().casefold()
        self.catalogue_tree.delete(*self.catalogue_tree.get_children())
        for index, entry in enumerate(self.catalogue['items']):
            rule = entry['rule']
            if search and search not in (rule['label'] + rule['traitLabel'] + rule['id']).casefold():
                continue
            meta = {}
            try:
                meta = effect_metadata(rule['lootEffectName'], rule['magnitudeName'])
                unit = meta['unit'] if meta['unit'] in {'%', '秒'} else ''
                value = display_number(rule['baseline'], rule['lootEffectName'], rule['magnitudeName']) + unit
            except ValueError:
                value = str(rule['baseline'])
            self.catalogue_tree.insert('', 'end', iid=str(index), values=(rule['label'] + ' / ' + rule['id'][-8:],
                                       rule['traitLabel'], value, ('实验性参数' if meta.get('experimental') else '可加入，待核对') if entry['supported'] else '暂不开放'))
        total = len({e['rule']['id'] for e in self.catalogue['items']})
        self.catalogue_summary.set(f'已整理{total}件装备的{len(self.catalogue["items"])}个数值；这是部分缓存记录，可能包含旧配装。')

    def select_catalogue(self, _event=None):
        if self.busy:
            return
        selected = self.catalogue_tree.selection()
        if not selected:
            return
        entry = self.catalogue['items'][int(selected[0])]
        rule = entry['rule']
        detail = entry['source_status'] if entry['supported'] else entry['reason']
        self.catalogue_detail.set(f'{rule["label"]} · {rule["traitLabel"]}\n{detail}。装备编号末尾：{rule["id"][-12:]}')
        try:
            self.new_value.set(display_number(rule['baseline'], rule['lootEffectName'], rule['magnitudeName']))
            self.new_unit.set(effect_metadata(rule['lootEffectName'], rule['magnitudeName'])['unit'])
        except ValueError:
            self.new_value.set('')
            self.new_unit.set('')

    def add_rule(self):
        if self.busy:
            return
        if self.draft.get('traitReplacements'):
            self.message.set('当前是类型修改方案，请先导出保存；旧数值方案需单独使用。')
            return
        selected = self.catalogue_tree.selection()
        if not selected:
            self.message.set('先在清单中选中一条装备词条。')
            return
        entry = self.catalogue['items'][int(selected[0])]
        if not entry['supported']:
            self.message.set(entry['reason'])
            return
        rule = deepcopy(entry['rule'])
        try:
            rule['value'] = parse_display_value(self.new_value.get(), rule['lootEffectName'], rule['magnitudeName'])
        except ValueError as error:
            self.message.set(str(error))
            return
        for index, existing in enumerate(self.draft['items']):
            if rule_key(existing) == rule_key(rule):
                existing['value'] = rule['value']
                self.selected_rule = index
                break
        else:
            candidate = deepcopy(self.draft)
            candidate['items'].append(rule)
            try:
                validate_config(candidate)
            except ValueError as error:
                self.message.set(str(error))
                return
            self.draft = candidate
            self.selected_rule = len(self.draft['items']) - 1
        self.refresh_rules()
        self.notebook.select(self.rules_tab)
        self.select_rule()
        self.changed()

    def read_game(self):
        if not self.busy:
            self.start_job('正在读取兵器库与战甲配装快照，通常约半分钟；不修改游戏。', scan_catalogue, self.finish_scan)

    def finish_scan(self, result):
        self.catalogue = save_catalogue(self.current_draft())
        self.refresh_catalogue()
        self.type_tab.scope.set('当前配装')
        self.type_tab.refresh()
        self.character_tab.refresh(self.type_tab.snapshot)
        self.replacement_tab.inspect_snapshot(self.type_tab.snapshot)
        self.message.set(result['message'])

    def export_scheme(self):
        if self.busy or not self.commit_rule_edit():
            return
        path = filedialog.asksaveasfilename(parent=self.root, title='导出装备修改方案', defaultextension='.json',
                                           initialfile='Godfall装备方案.json', filetypes=[('装备修改方案', '*.json')])
        if path:
            try:
                export_config(path, self.current_draft())
                self.message.set('方案已导出。导出不会安装或修改游戏。')
            except (OSError, ValueError) as error:
                self.message.set('导出未完成：' + str(error))

    def load_draft(self, path):
        try:
            loaded = load_config(path)
            if 'primalDrop' not in loaded:
                loaded['primalDrop'] = self.current_draft()['primalDrop']
            self.draft = loaded
            self.enabled.set(self.draft['enabled'])
            self.selected_rule = None
            self.primal_tab.refresh()
            self.refresh_rules()
            self.type_tab.refresh()
            self.notebook.select(self.type_tab if self.draft.get('traitReplacements') else self.rules_tab)
            self.message.set('方案已载入草稿。请检查类型和数值；尚未安装。')
        except (OSError, ValueError) as error:
            self.message.set('未能载入方案：' + str(error))

    def import_scheme(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.root, title='导入装备修改方案', filetypes=[('装备修改方案', '*.json')])
        if path:
            self.load_draft(path)

    def refresh_backups(self):
        from datetime import datetime, timedelta, timezone
        display_zone = timezone(timedelta(hours=8))
        self.backup_paths = []
        self.full_backup_rows = full_settings_backups()
        self.full_backup_tree.delete(*self.full_backup_tree.get_children())
        for i, backup in enumerate(self.full_backup_rows):
            config = backup['effective_config']
            when = datetime.fromisoformat(backup['created_utc']).astimezone(display_zone).strftime('%Y-%m-%d %H:%M')
            self.full_backup_tree.insert('', 'end', iid=str(i), values=(when,
                primal_label(primal_preferences(config)) + ('' if backup['active_package'] else '（补丁停用）'),
                f"{configuration_summary(config)['rules']}条", backup['reason']))
        self.backup_tree.delete(*self.backup_tree.get_children())
        for path in sorted((HERE/'config_backups').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                config = load_config(path)
            except (OSError, ValueError):
                continue
            index = len(self.backup_paths)
            self.backup_paths.append(path)
            self.backup_tree.insert('', 'end', iid=str(index), values=(datetime.fromtimestamp(path.stat().st_mtime, display_zone).strftime('%Y-%m-%d %H:%M'),
                                   configuration_summary(config)['rules'], path.stem[:16]))

    def load_backup(self):
        if not self.busy:
            selection = self.backup_tree.selection()
            if selection:
                self.load_draft(self.backup_paths[int(selection[0])])

    def install(self):
        if self.notebook.select()==str(self.character_tab):
            self.message.set('当前页面仅查看配装；请在批量编辑或对应工具中安装方案。')
            return
        if self.notebook.select() == str(self.uncurse_tab):
            self.uncurse_tab.install()
            return
        if self.notebook.select() == str(self.replacement_tab):
            self.replacement_tab.install()
            return
        if not self.busy and self.commit_rule_edit():
            config, expected = self.current_draft(), self.config_bytes
            self.start_job('正在备份、核对并安装。游戏须保持关闭。', lambda: install_draft(config, expected), self.finish_install)

    def finish_install(self, result):
        self.config_bytes = result['config_bytes']
        if 'config' in result:
            self.draft = deepcopy(result['config'])
            self.enabled.set(self.draft['enabled'])
        self.primal_tab.refresh()
        self.refresh_rules()
        self.type_tab.refresh()
        self.character_tab.refresh(self.type_tab.snapshot)
        self.replacement_tab.refresh()
        self.uncurse_tab.refresh()
        self.refresh_backups()
        self.message.set(result['message'])

    def disable(self):
        if not self.busy:
            self.start_job('正在核对并停用本地补丁。游戏须保持关闭。', disable_patch, self.finish_disable)

    def restore_verified(self):
        if not self.busy:
            expected = self.config_bytes
            self.start_job('正在恢复原始装备设置。游戏须保持关闭。',
                           lambda: restore_verified_release(expected), self.finish_restore)

    def finish_restore(self, result):
        self.draft = deepcopy(result['config'])
        self.enabled.set(self.draft['enabled'])
        self.selected_rule = None
        self.finish_install(result)

    def restore_full_backup(self):
        if self.busy or not self.full_backup_tree.selection():
            return
        row = self.full_backup_rows[int(self.full_backup_tree.selection()[0])]
        expected = self.config_bytes
        self.start_job('正在核对完整备份并恢复装备与掉率设置。游戏须保持关闭。',
                       lambda: restore_full_settings(row['manifest_path'], expected), self.finish_restore)

    def finish_disable(self, result):
        self.refresh_rules()
        self.primal_tab.refresh_status()
        self.refresh_backups()
        self.replacement_tab.refresh()
        self.message.set(result['message'])

    def start_job(self, message, function, finish):
        self.busy = True
        self.language_box.configure(state='disabled')
        self.message.set(message)
        for button in self.buttons:
            button.configure(state='disabled')
        for entry in self.entries:
            entry.configure(state='disabled')
        self.enable_check.configure(state='disabled')
        self.type_tab.set_busy(True)
        self.primal_tab.set_busy(True)
        def work():
            try:
                self.events.put((True, function(), finish))
            except Exception as error:
                self.events.put((False, str(error), finish))
        threading.Thread(target=work, daemon=True).start()

    def poll_events(self):
        try:
            success, result, finish = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.language_box.configure(state='readonly')
            for button in self.buttons:
                button.configure(state='normal')
            for entry in self.entries:
                entry.configure(state='normal')
            self.enable_check.configure(state='normal')
            self.type_tab.set_busy(False)
            self.primal_tab.set_busy(False)
            if success:
                try:
                    finish(result)
                except Exception as error:
                    self.message.set('处理结果未能载入：' + str(error))
            else:
                self.message.set('未完成：' + result)
                self.primal_tab.refresh_status()
                self.refresh_backups()
                self.update_summary()
            self.workflow_changed()
        self.root.after(100, self.poll_events)

    def open_drop_editor(self):
        if self.busy:return
        if self.drop_editor and self.drop_editor.root.winfo_exists():
            self.drop_editor.root.lift()
            return
        from ground_drop_editor import GroundDropEditor
        self.drop_editor = GroundDropEditor(tk.Toplevel(self.root))

    def close(self):
        if self.busy or (self.drop_editor and self.drop_editor.root.winfo_exists() and self.drop_editor.busy):
            self.message.set('正在完成当前操作，结束后可以关闭窗口。')
        else:
            self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    Settings(root)
    root.mainloop()
