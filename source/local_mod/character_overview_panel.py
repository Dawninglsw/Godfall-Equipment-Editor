"""Game-like, read-only armor/preset cards backed by the inventory snapshot."""
from localized_widgets import tk
from tkinter import font as tkfont
from localized_widgets import ttk

from equipment_names import equipment_name
from inventory_snapshot import load_snapshot
from character_overview_model import preset_view,snapshot_caption,item_details,RARITY_COLORS,AFFINITIES
import ui_theme

UNSET=object()


class SlotCard(tk.Canvas):
    def __init__(self,parent,entry,command,*,small=False):
        super().__init__(parent,width=100 if small else 160,height=38 if small else 46,
                         background=ui_theme.SURFACE,highlightthickness=0,cursor='hand2',takefocus=True)
        self.entry,self.command,self.selected,self.small=entry,command,False,small
        self.bind('<Configure>',lambda _:self.paint())
        self.bind('<Button-1>',lambda _:self.command(entry['key']))
        self.bind('<Return>',lambda _:self.command(entry['key']))
        self.bind('<space>',lambda _:self.command(entry['key']))
        self.name_font=tkfont.Font(family='Microsoft YaHei UI',size=9 if small else 10,weight='bold')
        self.paint()

    def paint(self):
        self.delete('all');width=max(self.winfo_width(),int(self.cget('width')));height=int(self.cget('height'))
        item=self.entry['item'];color=RARITY_COLORS.get(item.get('rarityIdentifier'),ui_theme.MUTED) if item else ui_theme.LINE
        self.create_rectangle(1,1,width-2,height-2,fill=ui_theme.SELECT if self.selected else ui_theme.CARD,
                              outline=ui_theme.ACCENT if self.selected else ui_theme.LINE,width=2 if self.selected else 1)
        self.create_rectangle(2,2,5,height-3,fill=color,outline='')
        label=self.entry['label']
        if item and not self.small:label+=f' · 强化{item.get("masterworkUpgradeRank") or 0}'
        self.create_text(10,11,anchor='w',text=label,fill=ui_theme.MUTED,font=('Microsoft YaHei UI',8))
        node=self.entry.get('node')
        if node:
            shade=AFFINITIES.get(node.get('affinityRequirement'),AFFINITIES[0])[1]
            self.create_oval(width-15,7,width-8,14,fill=shade,outline='')
        names={'empty':'未插入' if self.small else '未装备','preset_unread':'未读取配装',
               'item_unread':'详情未读取','conflict':'记录冲突'}
        name=equipment_name(item) if item else names.get(self.entry['state'],'未读取')
        limit=width-22
        if self.name_font.measure(name)>limit:
            while name and self.name_font.measure(name+'…')>limit:name=name[:-1]
            name+='…'
        self.create_text(10,27 if self.small else 32,anchor='w',text=name,
                         fill=color if item else ui_theme.MUTED,font=self.name_font)


class CharacterOverviewPanel(ttk.Frame):
    def __init__(self,notebook,host):
        super().__init__(notebook,padding=12)
        self.host=host;self.snapshot=None;self.plate_id=None;self.preset_index=0
        self.cards={};self.selected_key=None;self.selected_item=None;self.view=None
        top=ttk.Frame(self);top.pack(fill='x')
        ttk.Label(top,text='战甲与配装',font=('Microsoft YaHei UI',14,'bold')).pack(side='left')
        host.button(top,'刷新角色配装',host.read_game).pack(side='right')
        host.button(top,'定位当前配装',self.locate_current).pack(side='right',padx=6)
        self.caption=tk.StringVar()
        ttk.Label(self,textvariable=self.caption,style='Muted.TLabel').pack(anchor='w',pady=(4,9))
        columns=ttk.Panedwindow(self,orient='horizontal');columns.pack(fill='both',expand=True)
        left=ttk.Frame(columns,width=116);center=ttk.Frame(columns,width=370);right=ttk.Frame(columns,width=330)
        columns.add(left,weight=0);columns.add(center,weight=3);columns.add(right,weight=3)
        ttk.Label(left,text='战甲',style='Section.TLabel').pack(anchor='w',pady=(0,6))
        self.plates=ttk.Treeview(left,show='tree',height=12,selectmode='browse');self.plates.column('#0',width=110,minwidth=88,stretch=True)
        self.plates.tag_configure('active',foreground=ui_theme.ACCENT)
        self.plates.pack(fill='both',expand=True,padx=(0,8));self.plates.bind('<<TreeviewSelect>>',self.choose_plate)
        row=ttk.Frame(center);row.pack(fill='x',padx=(4,12))
        self.preset_buttons=[]
        for index in range(3):
            button=ttk.Button(row,text=f'配装 {index+1}',command=lambda n=index:self.choose_preset(n),width=8)
            button.pack(side='left',padx=(0,5));self.preset_buttons.append(button)
        self.loadout_label=tk.StringVar()
        ttk.Label(center,textvariable=self.loadout_label,style='Muted.TLabel').pack(anchor='w',padx=4,pady=(7,5))
        self.equipment=ttk.Frame(center);self.equipment.pack(fill='x',padx=(4,12))
        self.equipment.columnconfigure((0,1),weight=1)
        ttk.Label(center,text='强化物 · 按实际节点编号',style='Section.TLabel').pack(anchor='w',padx=4,pady=(10,5))
        self.augments=ttk.Frame(center);self.augments.pack(fill='x',padx=(4,12))
        self.augments.columnconfigure((0,1,2),weight=1)
        self.name=tk.StringVar(value='选择一件装备')
        self.name_label=ttk.Label(right,textvariable=self.name,font=('Microsoft YaHei UI',16,'bold'),wraplength=310)
        self.name_label.pack(anchor='w',pady=(0,7))
        self.meta=tk.StringVar();ttk.Label(right,textvariable=self.meta,style='Muted.TLabel',wraplength=310).pack(anchor='w')
        self.stat=tk.StringVar();ttk.Label(right,textvariable=self.stat,font=('Microsoft YaHei UI',17,'bold'),wraplength=310).pack(anchor='w',pady=(10,9))
        holder=ttk.Frame(right);holder.pack(fill='both',expand=True)
        self.text=tk.Text(holder,height=13,width=1,wrap='word',font=('Microsoft YaHei UI',10),state='disabled')
        ui_theme.detail_text(self.text)
        scroll=ttk.Scrollbar(holder,orient='vertical',command=self.text.yview);self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.text.tag_configure('heading',foreground=ui_theme.ACCENT,font=('Microsoft YaHei UI',10,'bold'))
        self.text.tag_configure('muted',foreground=ui_theme.MUTED)
        self.add_button=host.button(right,'加入批量编辑',self.add_selected);self.add_button.configure(style='Accent.TButton')
        self.add_button.pack(anchor='e',pady=(9,0))
        self.refresh(host.type_tab.snapshot)

    def refresh(self,snapshot=UNSET):
        self.snapshot=load_snapshot() if snapshot is UNSET else snapshot
        self.caption.set(snapshot_caption(self.snapshot))
        self.plates.delete(*self.plates.get_children())
        if not self.snapshot:
            self.plate_id=None;self.render();return
        available=self.snapshot['manifest']['plates'];current=self.snapshot['manifest']['selectedValorplateId']
        for plate in available:
            label=equipment_name(plate['gameplayTag'])+(' ●' if plate['id']==current else '')
            self.plates.insert('','end',iid=plate['id'],text=label,tags=('active',) if plate['id']==current else ())
        if not any(p['id']==self.plate_id for p in available):
            self.plate_id=current if any(p['id']==current for p in available) else available[0]['id'] if available else None
            if self.plate_id:self.preset_index=next(p for p in available if p['id']==self.plate_id)['selectedPresetIndex']
        if self.plate_id:self.plates.selection_set(self.plate_id);self.plates.see(self.plate_id)
        self.render()

    def choose_plate(self,_event=None):
        selection=self.plates.selection()
        if not selection:return
        identity=selection[0]
        if identity!=self.plate_id:
            self.plate_id=identity
            self.preset_index=next(p for p in self.snapshot['manifest']['plates'] if p['id']==identity)['selectedPresetIndex']
            self.selected_key=None
        self.render()

    def choose_preset(self,index):
        self.preset_index=index;self.selected_key=None;self.render()

    def locate_current(self):
        if not self.snapshot:return
        self.plate_id=None;self.refresh(self.snapshot)

    def render(self):
        for parent in [self.equipment,self.augments]:
            for child in parent.winfo_children():child.destroy()
        self.cards={};self.view=preset_view(self.snapshot,self.plate_id,self.preset_index)
        plate=self.view['plate']
        for index,button in enumerate(self.preset_buttons):
            button.configure(state='normal' if plate else 'disabled',style='Accent.TButton' if index==self.preset_index else 'TButton')
        if not plate:
            self.loadout_label.set('读取后显示战甲保存的装备与强化物。');self.show_empty('尚未读取配装');return
        self.loadout_label.set(equipment_name(plate['gameplayTag'])+f' · 配装 {self.preset_index+1}'+
                              (' · 记录中的使用配装' if self.view['recorded_active'] else '')+
                              (' · 未读取' if not self.view['preset_known'] else ''))
        for group,parent,cols,small in [('equipment',self.equipment,2,False),('augments',self.augments,3,True)]:
            for index,entry in enumerate(self.view[group]):
                card=SlotCard(parent,entry,self.select_slot,small=small)
                card.grid(row=index//cols,column=index%cols,sticky='ew',padx=(0,5),pady=(0,5));self.cards[entry['key']]=card
        if self.selected_key not in self.cards:
            self.selected_key=next((key for key,card in self.cards.items() if card.entry['item']),next(iter(self.cards),None))
        if self.selected_key:self.select_slot(self.selected_key)

    def show_empty(self,title,message='点击“刷新角色配装”读取，或从左侧选择战甲。'):
        self.name.set(title);self.name_label.configure(foreground=ui_theme.MUTED);self.meta.set('');self.stat.set('');self.selected_item=None
        self.write([(message,'muted')]);self.add_button.configure(state='disabled')

    def select_slot(self,key):
        if key not in self.cards:return
        self.selected_key=key
        for identity,card in self.cards.items():card.selected=identity==key;card.paint()
        entry=self.cards[key].entry;item=entry['item']
        if not item:
            explanations={'empty':'此配装的该槽位未保存装备。','preset_unread':'未读到这套配装，不能把它当作空配装。',
                          'item_unread':'已保存装备编号，但这次未读到完整详情；请刷新角色配装。','conflict':'同一槽位有重复记录，请刷新后再查看。'}
            self.show_empty(entry['label'],explanations[entry['state']]);return
        try:details=item_details(item)
        except (ValueError,KeyError,TypeError,AttributeError):
            self.show_empty(entry['label'],'该物品记录不完整，请刷新角色配装后查看。');return
        self.selected_item=item
        self.name.set(details['name']);self.name_label.configure(foreground=details['color'])
        meta=details['meta']
        if entry.get('node'):
            node=entry['node'];meta+='\n'+entry['label']+' · '+AFFINITIES.get(node.get('affinityRequirement'),AFFINITIES[0])[0]+'槽'
        self.meta.set(meta);self.stat.set(details['stat'])
        sections=[]
        for heading,lines in details['groups']:
            sections.append((heading+'\n','heading'))
            for line in lines:sections.append(('◇ '+line+'\n\n',''))
        if not details['groups']:sections.append(('未读取到词条，请刷新角色配装。\n\n','muted'))
        sections.append(('装备编号\n'+item['id'],'muted'));self.write(sections)
        self.add_button.configure(state='disabled' if self.host.busy else 'normal')

    def write(self,sections):
        self.text.configure(state='normal');self.text.delete('1.0','end')
        for text,tag in sections:self.text.insert('end',text,tag)
        self.text.configure(state='disabled');self.text.yview_moveto(0)

    def add_selected(self):
        if self.host.busy or not self.selected_item:return
        try:
            self.host.replacement_tab.open_batch()
            self.host.replacement_tab.batch_editor.add_rows([{'item':self.selected_item}])
        except Exception as error:self.host.message.set('未加入批量清单：'+str(error))
