"""Selectable local directories and explicit first-reader installation."""
from pathlib import Path
from tkinter import filedialog,messagebox
from localized_widgets import tk,ttk
import ui_theme
from localization import language,set_language,tr
from runtime_paths import game_directory,node_executable,load_settings,save_settings,HERE,ROOT


class ApplicationSettings(tk.Toplevel):
    def __init__(self,host):
        super().__init__(host.root);self.host=host;self.title('路径与运行设置');self.geometry('740x550');self.minsize(710,520);self.transient(host.root)
        ui_theme.dark_titlebar(self)
        frame=ttk.Frame(self,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='本地目录与运行环境',font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w',pady=(0,12))
        self.game=tk.StringVar(value=str(game_directory()));self.node=tk.StringVar(value=str(node_executable()))
        for title,variable,browse in [('Godfall 游戏目录',self.game,self.browse_game),('Node.js 运行环境',self.node,self.browse_node)]:
            row=ttk.Frame(frame);row.pack(fill='x',pady=5)
            ttk.Label(row,text=title,width=18).pack(side='left')
            ttk.Entry(row,textvariable=variable).pack(side='left',fill='x',expand=True,padx=7)
            ttk.Button(row,text='选择…',command=browse).pack(side='right')
        ttk.Label(frame,text='免安装包优先使用自带运行环境。更改目录后，请重新打开工具；不会自动安装补丁。',
                  wraplength=650,style='Muted.TLabel').pack(anchor='w',pady=12)
        self.message=tk.StringVar(value='选择游戏根目录，不要选择存档或账号数据目录。')
        ttk.Label(frame,textvariable=self.message,wraplength=650).pack(anchor='w',pady=8)
        actions=ttk.Frame(frame);actions.pack(fill='x',side='bottom')
        ttk.Button(actions,text='保存目录设置',command=self.save,style='Accent.TButton').pack(side='right')
        ttk.Button(actions,text='验证目录与版本',command=self.validate).pack(side='left')
        from settings_service import installation_state,installed_config
        active,_=installed_config()
        if active is None or not installation_state().get('inventory_readout'):
            ttk.Button(actions,text='安装基础读取组件',command=self.install_reader).pack(side='left',padx=8)
        reset=ttk.LabelFrame(frame,text='初始化',padding=10);reset.pack(fill='x',pady=10)
        ttk.Label(reset,text='备份后清空清单、草稿、历史记录和个人设置；保留基础读取组件，关闭其他本工具修改。\n初始化前请退出游戏并关闭其他编辑窗口。完成后工具会关闭，重新打开时进行首次设置。',wraplength=670).pack(anchor='w')
        ttk.Button(reset,text='初始化工具',command=self.initialize,style='QuietDanger.TButton').pack(anchor='e',pady=(8,0))

    def browse_game(self):
        value=filedialog.askdirectory(parent=self,title='Select Godfall game folder')
        if value:self.game.set(value)
    def initialize(self):
        if self.host.busy:return
        def popups(parent):
            result=[]
            for child in parent.winfo_children():
                if child.winfo_class()=='Toplevel' and child!=self:result.append(child)
                result.extend(popups(child))
            return result
        if popups(self.host.root):
            self.message.set('请先关闭其他编辑或筛选窗口，再初始化。');return
        from build_local_mod import game_running
        if game_running():self.message.set('请先正常退出游戏，再初始化工具。');return
        prompt='将备份并清空本工具的清单、草稿、历史记录和个人设置，保留基础读取组件并关闭其他本工具修改。未保存的子窗口输入会丢弃。游戏存档及已保存物品不会删除。完成后工具关闭，重新打开时进行首次设置。是否继续？'
        if not messagebox.askyesno(tr('初始化工具'),tr(prompt),parent=self,default='no'):return
        from reset_service import initialize_profile
        draft=self.host.current_draft()
        self.destroy()
        self.host.start_job('正在备份并初始化工具，请保持游戏关闭。',lambda:initialize_profile(draft),self.host.finish_initialization)
    def browse_node(self):
        value=filedialog.askopenfilename(parent=self,title='Select node.exe',filetypes=[('Node.js','node.exe')])
        if value:self.node.set(value)
    def checked(self):
        from prepare_resources import validate_installation
        game=Path(self.game.get()).resolve();node=Path(self.node.get()).resolve()
        state_path=HERE/'installed_patch.json'
        if state_path.exists():
            import json
            state=json.loads(state_path.read_bytes())
            if Path(state['destination']).resolve().parent!=(game/'Aperion/Content/Paks').resolve():
                raise ValueError('此工具目录已经绑定另一份游戏安装，请为另一份游戏使用新的解压目录。')
        return game,node,validate_installation(game,node)
    def validate(self):
        try:
            _,_,report=self.checked();self.message.set('目录及游戏版本核对通过；运行环境 '+report['node_version'])
        except Exception as error:self.message.set(str(error))
    def save(self):
        try:
            game,node,_=self.checked();save_settings({'game_directory':str(game),'node_executable':str(node)})
            self.message.set('目录设置已保存，重新打开工具后生效；当前补丁未改变。')
        except Exception as error:self.message.set(str(error))
    def install_reader(self):
        if self.host.busy:return
        try:
            game,node,_=self.checked()
            if game!=game_directory().resolve() or node!=node_executable().resolve():
                raise ValueError('请先保存目录设置并重新打开工具，再安装读取组件。')
            from settings_service import install_draft
            config=self.host.current_draft();expected=self.host.config_bytes
            self.host.start_job('正在安装基础读取组件；请保持游戏关闭。',lambda:install_draft(config,expected),self.host.finish_install)
            self.destroy()
        except Exception as error:self.message.set(str(error))
