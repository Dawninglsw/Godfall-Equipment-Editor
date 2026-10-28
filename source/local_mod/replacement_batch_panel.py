"""Nonmodal reviewed list of up to eight independently guarded item plans."""
from copy import deepcopy
from pathlib import Path
from localized_widgets import tk
from localized_widgets import ttk

import replacement_service as single
import replacement_batch_service as service
from settings_service import installation_state
from inventory_snapshot import load_snapshot,load_rows
from replacement_batch_details import details_from_preview
import ui_theme

MESSAGES = {'waiting':'等待正常掉落', 'inventory_not_ready':'等待兵器库载入',
            'source_changed_or_missing':'原件变化或未找到', 'replacement_already_owned':'已有同款，已跳过',
            'already_generated_previous_run':'此前已生成，不重复', 'generated_waiting_for_pickup':'已生成，需拾取核对',
            'generation_failed_original_rewards_preserved':'本件生成失败，原奖励保留',
            'waiting_nonempty_reward':'等待正常装备奖励', 'waiting_smaller_reward':'掉落包容量不足，等下一轮',
            'waiting_single_player':'等待单人奖励', 'waiting_grounded_equipment':'等待可落地装备',
            'batch_child_error':'本件已停止，其他物品继续'}

HINTS = {'source_changed_or_missing':'请重新读取原件并制作方案；其余物品仍会独立处理。',
         'waiting_smaller_reward':'继续正常获取下一轮掉落即可，无需重新安装。',
         'generation_failed_original_rewards_preserved':'本次生成已停止，请保留本件方案和提示以便检查；其余物品仍独立处理。',
         'batch_child_error':'本次生成已停止，请保留本件方案和提示以便检查；其余物品仍独立处理。',
         'already_generated_previous_run':'已使用过本件方案，不会再次补发；可读取兵器库核对记录中的编号。',
         'replacement_already_owned':'背包已存在符合完整目标属性的同款，因此跳过额外生成。'}


class BatchReplacementPanel(tk.Toplevel):
    def __init__(self, panel):
        super().__init__(panel.host.root)
        self.panel, self.host = panel, panel.host
        self.entries, self.plan = service.load_draft(), service.load_plan()
        self.editor,self.browser=None,None
        self.traces, self.busy = {}, False
        self.owned, self.owned_from_history = {}, False
        if self.plan and installation_state().get('replacement_batch_trial',{}).get('batch_id')==self.plan['batch_id']:
            try:
                self.owned=service.matches_in_snapshot(self.plan,load_snapshot())
                self.owned_from_history=any(self.owned.values())
            except (OSError,ValueError,KeyError,TypeError):
                self.owned={}
        self.title('多件装备批量方案'); self.geometry('1040x710'); self.minsize(960, 650)
        ui_theme.dark_titlebar(self)
        self.transient(self.host.root); self.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(self, padding=14); frame.pack(fill='both', expand=True)
        heading=ttk.Frame(frame);heading.pack(fill='x')
        ttk.Label(heading, text='多件装备，一份生成方案', font=('Microsoft YaHei UI',14,'bold')).pack(side='left')
        legacy=ttk.Button(heading,text='加入当前同款方案',command=self.add_current);legacy.pack(side='right')
        self.count=tk.StringVar()
        ttk.Label(heading,textvariable=self.count,style='Muted.TLabel').pack(side='right',padx=12)
        ttk.Label(frame, text='从兵器库筛选并多选加入，在此逐件编辑副词条；每批最多8件，独立核对并保留原件。\n'
                  '制作批量方案不安装。安装一次后，正常单人掉落中逐件生成；容量不足的物品等下一轮，正常奖励保留。',
                  wraplength=1000).pack(anchor='w', pady=8)
        panes=ttk.Panedwindow(frame,orient='vertical');panes.pack(fill='both',expand=True)
        holder = ttk.Frame(panes);panes.add(holder,weight=1)
        self.tree = ttk.Treeview(holder, columns=('name','rank','before','target','state'), show='headings',height=5,selectmode='browse')
        for key,title,width in [('name','装备',180),('rank','强化',50),('before','修改前',245),('target','修改后',245),('state','处理情况',220)]:
            self.tree.heading(key,text=title); self.tree.column(key,width=width,minwidth=60,stretch=key in {'before','target','state'})
        self.tree.column('rank',minwidth=45,anchor='center');ui_theme.tree_tags(self.tree)
        scroll = ttk.Scrollbar(holder,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set); self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self.select)
        self.tree.bind('<Button-1>',lambda _: 'break' if self.busy or self.host.busy else None)
        detail_frame=ttk.LabelFrame(panes,text='选中装备：完整属性与词条对照',padding=8);panes.add(detail_frame,weight=2)
        self.detail = tk.StringVar()
        ttk.Label(detail_frame,textvariable=self.detail,wraplength=970,foreground=ui_theme.TEXT).pack(anchor='w',pady=(0,6))
        text_frame=ttk.Frame(detail_frame);text_frame.pack(fill='both',expand=True)
        self.detail_box=tk.Text(text_frame,height=6,width=1,wrap='word',relief='flat',
                                font=('Microsoft YaHei UI',10),state='disabled')
        ui_theme.detail_text(self.detail_box)
        detail_scroll=ttk.Scrollbar(text_frame,orient='vertical',command=self.detail_box.yview)
        self.detail_box.configure(yscrollcommand=detail_scroll.set)
        self.detail_box.pack(side='left',fill='both',expand=True);detail_scroll.pack(side='right',fill='y')
        self.detail_box.tag_configure('changed',foreground=ui_theme.SUCCESS)
        self.detail_box.tag_configure('kept',foreground=ui_theme.MUTED)
        self.detail_box.tag_configure('heading',font=('Microsoft YaHei UI',10,'bold'))
        self.buttons=[legacy]
        for number,actions in enumerate([[('从兵器库加入',self.open_browser),('编辑副词条',self.edit_selected),
                         ('编辑随机主词条',lambda:self.edit_selected(primary=True)),('移除选中',self.remove)],
                        [('制作批量方案',self.prepare),('安装批量生成',self.install),('读取处理结果',self.read_status),
                         ('读取兵器库核对',self.read_inventory)]]):
            row = ttk.Frame(frame); row.pack(fill='x',pady=3)
            ttk.Label(row,text='选择与编辑' if number==0 else '制作与核对',style='Section.TLabel',width=19).pack(side='left')
            for title,command in actions:
                button=ttk.Button(row,text=title,command=command,
                                  style='Accent.TButton' if title in {'从兵器库加入','制作批量方案'} else 'QuietDanger.TButton' if title=='移除选中' else 'TButton')
                button.pack(side='left',padx=(0,6));self.buttons.append(button)
        self.status=tk.StringVar(value='批量清单自动保存，与单件方案、当前游戏补丁分别保存。')
        ttk.Label(frame,textvariable=self.status,wraplength=980,style='Info.TLabel').pack(fill='x',pady=8)
        ttk.Label(frame,text='“已生成”不等于已拾取保存。正常拾取后读取兵器库；已生成的物品不会因重新开游戏再次补发。',
                  wraplength=1000,foreground=ui_theme.MUTED).pack(anchor='w')
        self.refresh()
        if self.plan and self.entries==self.plan['entries']:
            active=installation_state().get('replacement_batch_trial',{}).get('batch_id')==self.plan['batch_id']
            self.status.set('此批量方案已安装；请正常获得装备后读取结果。' if active else
                            f'已制作 {len(self.entries)} 件批量方案，尚未安装；先查看各件修改。')
            if self.owned_from_history:
                self.status.set('已载入上次兵器库中的同款记录；需要查看最新情况时，点击“读取兵器库核对”。')

    def run(self,message,job,finish):
        if self.busy or self.host.busy:return
        self.busy=True;self.status.set(message)
        for button in self.buttons:button.configure(state='disabled')
        def work():
            try:return {'value':job()}
            except Exception as error:return {'error':str(error)}
        def done(result):
            if not self.winfo_exists():return
            self.busy=False
            for button in self.buttons:button.configure(state='normal')
            if 'error' in result:self.status.set('未完成：'+result['error'])
            else:finish(result['value'])
        self.host.start_job(message,work,done)

    def refresh(self):
        previous=self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        active=self.plan and installation_state().get('replacement_batch_trial',{}).get('batch_id')==self.plan['batch_id']
        self.count.set(f'{len(self.entries)} / 8 件 · {sum(len(e["changes"]) for e in self.entries)} 条修改')
        for n,entry in enumerate(self.entries):
            label=('原始·' if entry.get('primal') else '已解咒·' if entry.get('awakened') else '')+entry['label']
            text='；'.join(c['target_trait']+' '+c['target_value'] for c in entry['changes']) or '尚未设置修改'
            before='；'.join(c['source_trait']+' '+c['source_value'] for c in entry['changes'])
            state=self.row_state(entry,active)
            tags=('alternate',) if n%2 else ()
            if state.startswith('已拾取'):tags+=('confirmed',)
            self.tree.insert('', 'end', iid=str(n),values=(label,entry.get('upgrade_rank',0),before,text,state),tags=tags)
        if self.entries:
            selected=previous[0] if previous and self.tree.exists(previous[0]) else '0'
            self.tree.selection_set(selected);self.select()
        else:
            self.detail.set('清单为空。可切回主窗口制作单件方案，再点“加入当前同款方案”。')
            self.write_details([])

    def row_state(self,entry,active=None):
        if entry.get('editable_draft'):return '草稿待制作' if entry['changes'] else '待编辑词条'
        trace=self.traces.get(entry['trial_id'],{})
        ids=self.owned.get(entry['trial_id'],[])
        generated=trace.get('generatedId')
        if ids:
            matched=generated if generated in ids else ids[0]
            if self.owned_from_history:return '上次清单有同款 '+matched[-12:]
            if generated in ids and trace.get('status') in {'generated_waiting_for_pickup','already_generated_previous_run'}:
                return '已拾取 '+matched[-12:]
            return '背包已有同款 '+matched[-12:]
        if trace:return MESSAGES.get(trace.get('status'),'等待处理记录')
        if self.plan and entry in self.plan['entries']:
            if active is None:active=installation_state().get('replacement_batch_trial',{}).get('batch_id')==self.plan['batch_id']
            return '已安装，等处理记录' if active else '批量方案已制作'
        return '清单待制作'

    def select(self,_event=None):
        selected=self.tree.selection()
        if not selected:return
        entry=self.entries[int(selected[0])]
        try:details=details_from_preview(entry,service.read_preview(entry))
        except Exception as error:
            self.detail.set('详情未载入：'+str(error));self.write_details([]);return
        self.detail.set(details['summary'])
        sections=[]
        for row in details['rows']:
            sections.append((row['title']+(' · 修改\n' if row['changed'] else ' · 保留\n'),'heading'))
            if row['changed']:
                sections.extend([('修改前：'+row['before']+'\n','kept'),('修改后：'+row['after']+'\n\n','changed')])
            else:sections.append((row['before']+'\n\n','kept'))
        sections.append(('原件编号：'+details['source_id']+'\n方案编号：'+details['trial_id']+
                         '\n以上为制作方案时的属性。实际入库物品请用“读取兵器库核对”确认。','kept'))
        trace=self.traces.get(entry['trial_id'],{})
        sections.append(('\n\n处理情况：'+self.row_state(entry),'heading'))
        if trace.get('generatedId'):sections.append(('\n记录中的物品编号：'+trace['generatedId'],'kept'))
        if trace.get('status') in HINTS:sections.append(('\n'+HINTS[trace['status']],'kept'))
        self.write_details(sections)

    def write_details(self,sections):
        self.detail_box.configure(state='normal');self.detail_box.delete('1.0','end')
        for text,tag in sections:self.detail_box.insert('end',text,tag)
        self.detail_box.configure(state='disabled');self.detail_box.yview_moveto(0)

    def open_browser(self):
        if self.busy or self.host.busy:return
        if self.browser and self.browser.winfo_exists():self.browser.lift();return
        self.snapshot=load_snapshot();self.browser_rows=load_rows(self.snapshot)
        self.scope=tk.StringVar(value='兵器库全部' if self.snapshot else '历史记录（未确认）')
        from inventory_browser import InventoryBrowser
        self.browser=InventoryBrowser(self,on_choose=self.add_rows,multiple=True)

    def add_rows(self,rows):
        if self.busy or self.host.busy:raise ValueError('正在处理，请稍后加入。')
        identities={entry['source_id'] for entry in self.entries};added=[]
        for row in rows:
            if row['item']['id'] in identities:continue
            added.append(service.entry_from_item(row['item']));identities.add(row['item']['id'])
        if not added:raise ValueError('选中物品都已在清单中。')
        proposed=self.entries+added
        if len(proposed)>service.MAX_ITEMS:raise ValueError('每批最多8件，本次没有加入，请减少选择。')
        service.save_draft(proposed);self.entries=proposed;self.refresh()
        self.status.set(f'已加入 {len(added)} 件，重复项跳过。选中后编辑词条；尚未制作或安装。')

    def edit_selected(self,*,primary=False):
        if self.busy or self.host.busy or not self.tree.selection():return
        if self.editor and self.editor.winfo_exists():self.editor.lift();return
        entry=self.entries[int(self.tree.selection()[0])];identity=entry['source_id']
        try:
            source,edits=service.edit_request(entry)
            slot='Primary Trait' if primary else 'Secondary Trait'
            if any(source['traits'][edit['index']]['slotType']!=slot for edit in edits):
                raise ValueError('本件已有另一类词条修改；随机主词条与副词条目前不能混改。可保留该方案，或移除后重新加入原件。')
            if primary and not any(t['slotType']=='Primary Trait' and not single.availability(source,n) for n,t in enumerate(source['traits'])):
                reason=single.random_primary_support(source).get('reason','缺少随机主词条')
                raise ValueError('本件主词条不可编辑：'+reason)
        except Exception as error:self.status.set('未打开：'+str(error));return
        def saved(source,edits,result):
            replacement=service.edited_entry(source,edits,result)
            if not any(e['source_id']==identity for e in self.entries):raise ValueError('本件已从其他窗口移除。')
            proposed=[replacement if e['source_id']==identity else e for e in self.entries]
            service.save_draft(proposed);self.entries=proposed;self.refresh()
            self.status.set('本件修改已保存到批量草稿；其他物品保留，尚未制作或安装。')
        from replacement_multi_panel import MultiReplacementEditor
        self.editor=MultiReplacementEditor(self,source,initial_edits=edits,on_apply=saved,primary=primary)

    def add_current(self):
        if self.busy or self.host.busy:return
        plan=single.load_plan()
        if not plan:self.status.set('请先在主窗口制作一件同款方案。');return
        try:
            entry=service.entry_from_plan(plan)
            if len(self.entries)>=service.MAX_ITEMS:raise ValueError('每批最多8件，请先完成当前批次。')
            if any(e['source_id']==entry['source_id'] for e in self.entries):raise ValueError('这件原件已在批量清单中；需要更新时先移除旧行。')
            proposed=self.entries+[entry];service.save_draft(proposed)
        except Exception as error:self.status.set('未加入：'+str(error));return
        self.entries=proposed;self.refresh();self.status.set(f'已加入 {len(self.entries)} 件；请重新制作批量方案后再安装。')

    def remove(self):
        if self.busy or self.host.busy or not self.tree.selection():return
        index=int(self.tree.selection()[0]);proposed=[e for n,e in enumerate(self.entries) if n!=index]
        try:service.save_draft(proposed)
        except Exception as error:self.status.set('未移除：'+str(error));return
        self.entries=proposed;self.refresh();self.status.set('清单已更新，旧批量方案保持原样；请重新制作后安装。')

    def prepare(self):
        if not self.entries:self.status.set('请先加入单件同款方案。');return
        entries=deepcopy(self.entries)
        def finish(plan):
            self.plan=plan;self.entries=deepcopy(plan['entries']);self.traces={};self.refresh()
            self.status.set(f'已制作 {len(plan["entries"])} 件批量方案，尚未安装。退出游戏后可安装一次。')
        self.run('正在逐件重新计算并打包；不安装或修改游戏。',lambda:service.prepare(entries),finish)

    def install(self):
        if not self.plan:self.status.set('请先制作批量方案。');return
        if self.entries!=self.plan['entries']:self.status.set('清单已变化，请先重新制作批量方案。');return
        plan=deepcopy(self.plan)
        def finish(result):
            self.host.finish_install(result);self.status.set(result['message']);self.refresh()
        self.run('正在备份并安装批量方案；游戏须关闭。',lambda:service.install(plan),finish)

    def read_status(self):
        if not self.plan:self.status.set('尚无批量方案。');return
        plan=deepcopy(self.plan)
        def finish(trace):
            if not trace:self.status.set('暂未读到本批次处理记录；请在单人关卡正常获得装备后再读取。');return
            self.traces={r['trialId']:r for r in trace['items']};self.refresh()
            self.status.set('各件状态已更新；生成记录本身不代表拾取保存，请再读取兵器库。')
        self.run('正在只读核对本批次处理记录，约半分钟。',lambda:service.read_status(plan),finish)

    def read_inventory(self):
        if not self.plan:self.status.set('尚无批量方案。');return
        plan=deepcopy(self.plan)
        if installation_state().get('replacement_batch_trial',{}).get('batch_id')!=plan['batch_id']:
            self.status.set('当前没有安装此批量方案，未将旧清单算作新件。');return
        def work():
            from settings_service import scan_catalogue
            scan_catalogue();return service.matches_in_snapshot(plan,load_snapshot())
        def finish(found):
            self.owned=found;self.owned_from_history=False;self.refresh()
            confirmed=sum(bool(found.get(e['trial_id'])) for e in self.entries)
            self.status.set(f'本次兵器库有 {confirmed}/{len(self.entries)} 件符合目标；有同款不等于本次新生成，来源以处理记录核对。')
        self.run('正在只读刷新兵器库并逐件核对。',work,finish)

    def close(self):
        if self.busy or self.host.busy:self.status.set('正在处理，请等本次操作完成后关闭。');return
        if self.editor and self.editor.winfo_exists():self.status.set('请先保存或关闭本件编辑窗口。');return
        if self.browser and self.browser.winfo_exists():self.browser.destroy()
        self.panel.batch_editor=None;self.destroy()
