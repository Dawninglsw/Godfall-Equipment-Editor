"""First-run resource preparation for the portable, clean-profile distribution."""
from pathlib import Path
import json
import runpy
import sys
import threading
import tkinter as tk
from tkinter import filedialog,ttk,messagebox

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(HERE))
from runtime_paths import game_directory,node_executable,save_settings,load_settings


def ready():
    if not load_settings().get('game_directory'):return False
    import hashlib
    from prepare_resources import EXPECTED_UI,EXPECTED_TABLES,digest,validate_installation
    resources=ROOT/'analysis/extracted'
    original=resources/'main.c05310c4.chunk.js'
    tables=resources/'source_data.json'
    if not (original.is_file() and digest(original)==EXPECTED_UI and tables.is_file() and
            (not EXPECTED_TABLES or digest(tables)==EXPECTED_TABLES) and
            all((HERE/name).is_file() for name in ['chinese_item_names.json','chinese_trait_labels.json','english_trait_labels.json'])):return False
    try:validate_installation(game_directory(),node_executable())
    except (OSError,ValueError):return False
    return True


def first_run():
    root=tk.Tk();root.title('Godfall Equipment Editor · First Run / 首次运行');root.geometry('760x400')
    import ui_theme;ui_theme.apply(root)
    frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='众神陨落-装备编辑器 / Godfall Equipment Editor',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Choose your game folder. Original resources stay on your computer.\n选择游戏目录；原版资源只在本机准备，不会改写游戏。').pack(anchor='w',pady=12)
    game=tk.StringVar(value=str(game_directory()));node=tk.StringVar(value=str(node_executable()))
    selected=tk.StringVar(value='English' if load_settings().get('language','en')=='en' else '简体中文')
    for title,var,is_game in [('Game folder / 游戏目录',game,True),('Node.js runtime / 运行环境',node,False)]:
        row=ttk.Frame(frame);row.pack(fill='x',pady=6)
        ttk.Label(row,text=title,width=24).pack(side='left');ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True,padx=8)
        def browse(variable=var,folder=is_game):
            value=filedialog.askdirectory(parent=root) if folder else filedialog.askopenfilename(parent=root,filetypes=[('Node.js','node.exe')])
            if value:variable.set(value)
        ttk.Button(row,text='Browse… / 选择',command=browse).pack(side='right')
    ttk.Combobox(frame,textvariable=selected,values=['English','简体中文'],state='readonly',width=16).pack(anchor='w',pady=8)
    status=tk.StringVar(value='No patch is installed by this step. / 本步骤不安装补丁。')
    ttk.Label(frame,textvariable=status,wraplength=690).pack(anchor='w',pady=8)
    completed={'ok':False};pending=[]
    def start():
        button.configure(state='disabled');status.set('Preparing local resources… / 正在准备本地资源…')
        game_value,node_value=game.get(),node.get();lang='en' if selected.get()=='English' else 'zh-CN'
        def work():
            try:
                from prepare_resources import prepare
                prepare(game_value,node_value)
                save_settings({'game_directory':str(Path(game_value).resolve()),'node_executable':str(Path(node_value).resolve()),'language':lang})
                pending.append(None)
            except Exception as error:
                from localization import tr,set_language
                set_language(lang,persist=False);pending.append(tr(str(error)))
        threading.Thread(target=work,daemon=True).start()
    button=ttk.Button(frame,text='Verify & Prepare / 验证并准备',command=start);button.pack(anchor='e',pady=8)
    def poll():
        if pending:
            error=pending.pop()
            if error:status.set(error);button.configure(state='normal')
            else:completed['ok']=True;root.destroy();return
        root.after(100,poll)
    poll();root.mainloop();return completed['ok']


if __name__=='__main__':
    try:
        from branding import ensure_app_branding,set_process_identity
        set_process_identity();ensure_app_branding()
        if not ready() and not first_run():raise SystemExit(0)
        # Config is loaded by the application after first-run selection.
        import localization
        localization._game_words=None
        localization.set_language(load_settings().get('language','en'),persist=False)
        target='ground_drop_editor.py' if '--ground-loot' in sys.argv else 'settings_panel.py'
        runpy.run_path(str(HERE/target),run_name='__main__')
    except Exception:
        import traceback
        log=HERE/'startup_error.log';log.write_text(traceback.format_exc(),encoding='utf-8')
        messagebox.showerror('Godfall Equipment Editor','Startup failed. See startup_error.log.\n启动失败，请查看 startup_error.log。')
