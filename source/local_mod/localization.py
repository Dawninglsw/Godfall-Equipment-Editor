"""Presentation language only; item identifiers and saved rules are never translated."""
import json
import re
from pathlib import Path
import weakref
from runtime_paths import HERE,load_settings,save_settings

_language=load_settings().get('language','zh-CN')
_widgets=weakref.WeakSet()
_game_words=None


def language():return _language
def register(widget):_widgets.add(widget)


def set_language(value,*,persist=True):
    global _language
    if value not in {'zh-CN','en'}:raise ValueError('Unsupported language')
    if persist:save_settings({'language':value})
    _language=value
    for widget in list(_widgets):
        try:widget.refresh_language()
        except Exception:pass


def game_words():
    global _game_words
    if _game_words is not None:return _game_words
    result={}
    try:
        names=json.loads((HERE/'chinese_item_names.json').read_bytes())['names']
        for value in names.values():
            if value.get('name') and value.get('english'):result[value['name']]=value['english']
        zh=json.loads((HERE/'chinese_trait_labels.json').read_bytes())['labels']
        en=json.loads((HERE/'english_trait_labels.json').read_bytes())['labels']
        for key,value in zh.items():
            if key in en:result[value['label']]=en[key]['label']
    except (OSError,ValueError,KeyError):pass
    _game_words=sorted(result.items(),key=lambda row:len(row[0]),reverse=True)
    return _game_words


def tr(value):
    if not isinstance(value,str):return value
    if language()!='en':
        # Names cached while English was active still render correctly after switching back.
        for chinese,english in game_words():
            if english and english in value:
                value=re.sub(r'(?<![A-Za-z0-9_.-])'+re.escape(english)+r'(?![A-Za-z0-9_.-])',lambda _:chinese,value)
        return value
    if not any('\u4e00'<=c<='\u9fff' for c in value):return value
    original=value;stripped=value.strip()
    if stripped in UI:return value.replace(stripped,UI[stripped])
    for source,target in sorted(UI.items(),key=lambda row:len(row[0]),reverse=True):
        if source in value:value=value.replace(source,target)
    for source,target in game_words():
        if source in value:value=value.replace(source,target)
    return value.replace('：',': ').replace('；','; ').replace('，',', ').replace('。','. ').replace('“','"').replace('”','"').replace('～','–')


UI={
 '不限主词条':'Any primary type','有随机主词条':'Has random primaries','无随机主词条':'No random primaries',
 '随机主词条优先':'Random primaries first',
 '有随机主词条；是否可编辑以本件校验为准。':'Has random primaries; edit availability is checked separately for this item.',
 '无随机主词条。':'No random primaries.',
 '随机主词条状态未确认：记录或原生模板不完整。':'Random-primary status unknown: incomplete item data or native template.',
 '本件主词条不可编辑':'This primary cannot be edited',
 '固定主属性与精通词条保持原样。':'Fixed main stats and mastery traits are kept.',
 '随机主词条同款试验；强化等级、原始标记和精通词条保留，本件仍需核对新生成结果。':'Random-primary copy trial; upgrade rank, primal markers and mastery are kept. Verify the generated item in game.',
 '该物品类型尚未开放随机主词条':'Random-primary editing is not supported for this item family',
 '随机主词条支持强化0至5级':'Random-primary editing supports upgrade ranks 0 to 5',
 '随机主词条仅支持普通或单一原始变体':'Random-primary editing supports ordinary or single-Primal variants only',
 '请选择随机主词条':'Select a random primary trait',
 '缺少原生主词条槽位':'Native primary slots are missing',
 '主词条数量与模板不一致':'The primary count does not match the native template',
 '主词条位置的原生候选库不一致，保持保护':'Primary slots have different native libraries and remain protected',
 '缺少原件实际标签':'The source selected tags are missing',
 '固定主词条不能替换类型':'Fixed primary types cannot be replaced',
 '原主词条与本件随机库不符':'Source primaries do not match this item\'s native random library',
 '从兵器库筛选并多选加入，在此逐件编辑副词条；每批最多8件，独立核对并保留原件。\n制作批量方案不安装。安装一次后，正常单人掉落中逐件生成；容量不足的物品等下一轮，正常奖励保留。':'Add multiple items from the armory, then edit each one. Up to 8 items; originals are kept.\nPreparing does not install. After one install, obtain single-player loot normally; overflow waits for the next drop.',
 '路径与运行设置':'Paths & Runtime','本地目录与运行环境':'Local Paths & Runtime','Godfall 游戏目录':'Godfall game folder',
 'Node.js 运行环境':'Node.js runtime','选择…':'Browse…','保存目录设置':'Save Paths','验证目录与版本':'Validate Paths & Build','安装基础读取组件':'Install Base Reader',
 '免安装包优先使用自带运行环境。更改目录后，请重新打开工具；不会自动安装补丁。':'Portable packages use their bundled runtime. Reopen the tool after changing paths. No patch is installed automatically.',
 '选择游戏根目录，不要选择存档或账号数据目录。':'Choose the game root folder, not a save or account-data folder.',
 '目录设置已保存，重新打开工具后生效；当前补丁未改变。':'Paths saved. Reopen the tool to apply them. The installed patch is unchanged.',
 '目录及游戏版本核对通过；运行环境 ':'Paths and game build verified. Runtime: ',
 '请选择包含 Aperion 文件夹的 Godfall 游戏目录。':'Select the Godfall game folder containing the Aperion folder.',
 '未找到 Node.js 运行环境，请选择 node.exe。':'Node.js was not found. Select node.exe.',
 '游戏版本尚未验证，已停止准备；未安装任何补丁。':'This game build is not verified. Preparation stopped; no patch installed.',
 'Node.js 运行环境无效。':'Invalid Node.js runtime.',
 '此工具目录已经绑定另一份游戏安装，请为另一份游戏使用新的解压目录。':'This tool folder is linked to another game installation. Use a fresh extracted tool folder for the other installation.',
 '请先保存目录设置并重新打开工具，再安装读取组件。':'Save the paths and reopen the tool before installing the reader.',
 '正在安装基础读取组件；请保持游戏关闭。':'Installing the base reader. Keep the game closed.',
 '批量方案':'batch plan','原始·':'Primal · ','本件方案已设置 ':'This item draft has ',
 '制作后才能安装；原件保留。':'Prepare it before installing. The original is retained.',
 '角色与装备管理':'Godfall Loadout Workshop','Godfall 装备与掉落设置':'Godfall Loadout Workshop',
 '角色与配装':'Character','战甲与配装':'Armor & Loadouts','同款替代品':'Item Copies','解除诅咒':'Cleanse',
 '原始掉落':'Primal Loot','旧数值方案':'Legacy Values','数值资料':'Reference','方案与备份':'Backups','旧词条工具':'Legacy Traits',
 '批量词条编辑':'Batch Editor','打开新掉落词条编辑':'Ground Loot Editor','设置':'Settings',
 '刷新角色配装':'Refresh Loadouts','定位当前配装':'Locate Active','加入批量编辑':'Add to Batch',
 '查看各套战甲的装备与强化物；选中物品可查看完整词条或加入批量编辑。':'Browse armor presets and augments. Select an item for its full traits or add it to a batch.',
 '当前为查看模式':'View Only','仅查看记录 · 不切换游戏中的配装':'Read-only view · does not change your in-game loadout',
 '当前设置已载入。编辑草稿不会改变正在运行的游戏。':'Settings loaded. Editing a draft does not change the running game.',
 '查看各套战甲的装备与强化物':'Browse armor equipment and augments','上次游戏记录':'Previous session snapshot',
 '本次游戏读取':'Current session snapshot','套战甲':'armor sets','清单有缺项':'partial snapshot','战甲':'Armor',
 '强化物 · 按实际节点编号':'Augments · actual node numbers','记录中的使用配装':'active in snapshot','配装':'Loadout',
 '武器 1':'Weapon 1','武器 2':'Weapon 2','戒指 1':'Ring 1','戒指 2':'Ring 2',
 '生命石':'Lifestone','旗帜':'Banner','护符':'Amulet','符咒':'Charm','戒指':'Ring','武器':'Weapon','强化物':'Augment',
 '节点':'Node','未插入':'Empty','未装备':'Empty','未读取配装':'Preset not read','详情未读取':'Details unavailable','记录冲突':'Conflicting records',
 '选择一件装备':'Select an item','尚未读取配装':'No loadout snapshot','未读取':'Not read','选择装备与强化物 · 筛选和排序':'Choose Items · Filters & Sorting',
 '此配装的该槽位未保存装备。':'This slot is empty in the selected preset.',
 '未读到这套配装，不能把它当作空配装。':'This preset was not read. Its contents are unknown.',
 '已保存装备编号，但这次未读到完整详情；请刷新角色配装。':'An item ID is saved, but details are missing. Refresh the loadout snapshot.',
 '同一槽位有重复记录，请刷新后再查看。':'Duplicate slot records found. Refresh the loadout snapshot.',
 '在此查看不会切换游戏中的战甲或配装。':'Browsing here does not change armor or presets in the game.',
 '读取后显示战甲保存的装备与强化物。':'Read a snapshot to browse saved gear and augments.',
 '点击“刷新角色配装”读取，或从左侧选择战甲。':'Refresh the snapshot or select an armor set on the left.',
 '尚未读取角色配装；请点击“刷新角色配装”。':'No character snapshot. Click Refresh Loadouts.',
 '主词条':'Primary Traits','副词条':'Secondary Traits','精通词条':'Masterwork Traits','主属性':'Main Attribute','诅咒目标':'Curse Objective',
 '解咒进度':'Curse Progress','已解除诅咒':'Cleansed','已解咒':'Cleansed','诅咒':'Cursed','原始':'Primal',
 '传奇':'Legendary','史诗':'Epic','稀有':'Rare','罕见':'Uncommon','普通':'Common','品质':'Rarity',
 '攻击力':'Attack Power','护盾量':'Overshield','回复量':'Healing','威力':'Might','灵气':'Spirit','活力':'Vitality',
 '物理':'Physical','气系':'Air','冰系':'Water','火系':'Fire','土系':'Earth','虚空':'Void','伤害类型':'Damage Type',
 '等级':'Level','强化':'Rank','装备编号':'Item ID','编号末尾':'ID suffix','槽位':'Slot','红色':'Red','绿色':'Green','蓝色':'Blue','通用':'Neutral','槽':' slot',
 '筛选条件':'Filters','读取范围':'Scope','名称 / 编号':'Name / ID','清空条件':'Reset Filters','已有词条':'Existing trait',
 '全部类型':'All types','全部品质':'All rarities','全部形态':'All variants','仅原始装备':'Primal only','非原始装备':'Non-primal',
 '仅诅咒装备':'Cursed only','全部武器':'All weapons','长剑':'Longsword','双剑':'Dual Blades','巨剑':'Greatsword','长柄武器':'Polearm','战锤':'Warhammer',
 '全部颜色':'All colors','仅收藏':'Favorites','全部装备':'All items','已保存到配装':'Saved in a preset','未保存到配装':'Not saved in a preset',
 '全部战甲':'All armor sets','当前配装':'Active preset','当前战甲全部配装':'Active armor presets','所有战甲配装':'All armor presets',
 '兵器库全部':'Entire armory','历史记录（未确认）':'History (unverified)','名称':'Name','类型':'Type',
 '品质从高到低':'Rarity: high to low','等级从高到低':'Level: high to low','强化从高到低':'Upgrade: high to low','原始装备优先':'Primal first',
 '选中并查看词条':'View Selected Item','加入批量清单':'Add to Batch','加入选中物品':'Add Selected Items',
 '按 Ctrl 或 Shift 多选。':'Use Ctrl / Shift to select multiple items. ',
 '配装或背包变化后请在主窗口重新读取。':'Refresh the snapshot after changing gear or inventory.',
 '选中装备后可查看配装位置和完整编号。':'Select an item to see preset bindings and its full ID.',
 '未确认归属的历史记录':'Unverified history','本次界面快照':'Current snapshot','上次游戏快照':'Previous snapshot',
 '可制作同款':'Copy supported','可查看并编辑':'Editable','仅查看':'Read only','未保存到配装':'Not in a saved preset',
 '多件装备批量方案':'Batch Item Copies','多件装备，一份生成方案':'Multiple Items · One Batch',
 '加入当前同款方案':'Add Current Single Plan','从兵器库加入':'Add from Armory','编辑副词条':'Edit Secondaries',
 '编辑随机主词条':'Edit Random Primary','移除选中':'Remove Selected','制作批量方案':'Prepare Batch','安装批量生成':'Install Batch',
 '读取处理结果':'Read Generation Status','读取兵器库核对':'Verify in Armory','选择与编辑':'Select & Edit','制作与核对':'Prepare & Verify',
 '选中装备：完整属性与词条对照':'Selected Item · Full Properties & Changes','修改前':'Before','修改后':'After','处理情况':'Status',
 '装备':'Item','保留':'Kept','修改':'Changed','待编辑词条':'Choose traits','草稿待制作':'Draft: not prepared','清单待制作':'Not prepared',
 '批量方案已制作':'Batch prepared','已安装，等处理记录':'Installed; awaiting status','上次清单有同款':'Match in previous snapshot',
 '背包已有同款':'Matching item owned','已拾取':'Acquired','尚未设置修改':'No edits selected',
 '已生成，需拾取核对':'Generated; verify pickup','等待正常掉落':'Waiting for normal loot','等待兵器库载入':'Waiting for inventory',
 '原件变化或未找到':'Source changed or missing','已有同款，已跳过':'Matching item owned; skipped',
 '此前已生成，不重复':'Previously generated; no duplicate','本件生成失败，原奖励保留':'Generation failed; normal rewards kept',
 '等待正常装备奖励':'Waiting for gear rewards','掉落包容量不足，等下一轮':'Reward list full; waiting for next drop',
 '等待单人奖励':'Waiting for single-player loot','等待可落地装备':'Waiting for ground loot','本件已停止，其他物品继续':'This item stopped; other items continue',
 '原件编号':'Original item ID','方案编号':'Plan ID','计划编号':'Plan ID','记录中的物品编号':'Recorded item ID',
 '本件拟改词条':'Planned traits','原词条':'Original trait','新词条':'New trait','新数值':'New value','原值':'Original value','新值':'New value','位置':'Slot',
 '整件副词条编辑':'Edit Item Secondaries','随机主词条编辑':'Edit Random Primary','词条位置':'Trait slot','本方案新词条':'Planned trait',
 '替换为':'Replace with','还原该条':'Reset Trait','正常范围内选值':'Value within normal range','保留原档次':'Keep Roll Quality',
 '加入本件方案':'Apply to Item Draft','制作整件同款方案':'Prepare Item Copy','保存到批量清单':'Save to Batch',
 '正常范围':'Normal range','固定数值':'Fixed value','固定':'Fixed','可选':'Available',
 '启用这些装备设置':'Enable legacy overrides','保存并安装':'Save & Install','停用全部补丁':'Disable All Patches',
 '先编辑草稿，退出游戏后安装，下次启动时生效。':'Edit drafts first. Close the game to install; changes load on the next start.',
 '装备与掉率一起保存 · 新掉落仍正常拾取':'Settings saved together · pick up new loot normally',
 '当前本地补丁已安装':'Local patch installed','原始掉落修改关闭':'Primal bonus off','与已安装设置一致':'Matches installed settings',
 '草稿尚未安装':'Draft not installed','默认修改为空':'Default overrides empty','条装备设置':' gear overrides',
 '未完成':'Failed','未加入':'Not added','未打开':'Cannot open','详情未载入':'Details unavailable',
 '请先制作批量方案。':'Prepare a batch first.','请先加入单件同款方案。':'Add items or a single-item plan first.',
 '请先在主窗口制作一件同款方案。':'Prepare a single-item plan or add items from the armory.',
 '清单已变化，请先重新制作批量方案。':'The list changed. Prepare the batch again before installing.',
 '本件修改已保存到批量草稿；其他物品保留，尚未制作或安装。':'Item edits saved to the batch draft. Other items kept; no package installed.',
 '此批量方案已安装；请正常获得装备后读取结果。':'Batch installed. Obtain normal loot, then read the results.',
 '已载入上次兵器库中的同款记录；需要查看最新情况时，点击“读取兵器库核对”。':'Previous armory matches loaded. Click Verify in Armory for a fresh check.',
 '批量清单自动保存，与单件方案、当前游戏补丁分别保存。':'The batch draft is saved separately from the single plan and installed patch.',
 '“已生成”不等于已拾取保存。正常拾取后读取兵器库；已生成的物品不会因重新开游戏再次补发。':'Generated does not mean acquired. Pick up normally, then verify the armory. Restarting does not generate another copy.',
 '以上为制作方案时的属性。实际入库物品请用“读取兵器库核对”确认。':'These are planned properties. Use Verify in Armory to confirm the acquired item.',
 '候选会结合本件其他拟改词条筛选。数值受原游戏范围限制；制作方案不安装、不改变游戏。':'Candidates account for the other planned traits. Values stay within game ranges. Preparing a plan does not install it.',
 '逐条设置后，一次制作整件方案并生成一件新物品。原件、主词条、主属性和精通词条保留。':'Edit one or more secondary traits to create one new item. The original, primary traits, main stat, and mastery are retained.',
 '一次只修改一条已适配的随机主词条；其他词条、主属性和原件保留。':'Edit one supported random primary. Other traits, main stats, and the original are kept.',
 '正在逐件重新计算并打包；不安装或修改游戏。':'Recalculating and packing each item. The game is unchanged.',
 '正在备份并安装批量方案；游戏须关闭。':'Backing up and installing the batch. The game must be closed.',
 '正在只读刷新兵器库并逐件核对。':'Reading the armory and checking each item.',
 '正在只读核对本批次处理记录，约半分钟。':'Reading batch status; this may take about 30 seconds.',
 '正在核对本件最终候选与互斥规则。':'Checking candidates and trait exclusions.',
 '正在核对整件词条、数值与强化标记。':'Validating traits, values, and upgrade markers.',
 '正在核对并保存本件批量草稿；不制作生成包或安装。':'Validating and saving this item draft. No package is installed.',
 '正在读取兵器库与战甲配装快照，通常约半分钟；不修改游戏。':'Reading armory and armor presets, usually about 30 seconds. The game is unchanged.',
 '原始装备的额外奖励机会':'Extra Primal Reward Chance','启用原始额外奖励调整':'Enable primal bonus adjustment',
 '已安装':'Installed','未安装':'Not installed','已停用':'Disabled','已制作':'Prepared','已设置':'Configured','已加入':'Added',
 '制作同款替代品':'Prepare Item Copy','安装同款生成':'Install Copy Plan','刷新方案状态':'Refresh Plan','检查生成状态':'Read Generation Status',
 '选择物品与词条':'Choose Item & Trait','保留原件，制作修改后的同款新物品':'Keep the Original · Create a Modified Copy',
 '一键解除所选装备的诅咒（试验）':'Cleanse Selected Item (Experimental)','为选中装备制作计划':'Prepare Cleanse Plan',
 '安装解咒计划':'Install Cleanse Plan','检查解咒状态':'Read Cleanse Status','导出当前方案':'Export Plan',
 '导入方案到草稿':'Import as Draft','完整设置备份':'Full Backups','旧方案草稿备份':'Legacy Draft Backups',
 '备份时间':'Backup time','装备设置':'Gear settings','原因':'Reason','恢复选中完整备份':'Restore Selected Backup',
 '将选中备份载入草稿':'Load Selected Draft','恢复原始设置':'Restore Defaults','选中词条的新数值':'Value for selected trait',
 '应用到草稿':'Apply to Draft','选中词条恢复原值':'Reset Selected Value','移除选中设置':'Remove Override','全部恢复原值':'Reset All Values',
 '搜索装备或词条':'Search items or traits','从游戏读取':'Read from Game','加入修改草稿':'Add to Draft','设定值':'Target value','状态':'Status',
 '原始数值':'Original value','加入类型修改草稿':'Add Legacy Override','移除选中草稿':'Remove Selected Draft',
 'Godfall 新掉落词条编辑':'Godfall Ground Loot Editor','新掉落词条编辑':'Ground Loot Editor','读取地上的装备':'Read Ground Loot',
 '词条 / 颜色条件':'Trait / Color Filters','清空筛选':'Reset Filters','仅看可编辑':'Editable only','查看候选与原因':'Candidates & Details',
 '写入这件掉落':'Write Selected Drop','撤回本次修改（拾取前）':'Undo Before Pickup','备份与验证记录':'Backups & Verification',
 '记录：已正常拾取':'Record: Picked Up','可选记录：重启后仍保留':'Record: Retained After Restart','记录：未保留':'Record: Not Retained',
 '本次目标':'Target','核对状态':'Verification','读取状态':'Read status','距离':'Distance','不限词条':'Any trait',
 '异常状态强度':'Ailment power','减益状态强度':'Ailment power','减益状态持续时间':'Ailment duration',
 '暴击几率':'Critical hit chance','暴击率':'Critical hit chance','暴击伤害':'Critical hit damage',
 '武器技艺伤害':'Weapon technique damage','武器技艺充能速度':'Weapon technique charge speed','碎魂累积':'Soulshatter buildup',
 '时机攻击伤害':'Timing attack damage','弱点伤害':'Weakpoint damage','临时生命值获得量':'Overhealth gained',
 '秒':' s','分钟':' min','条修改':' edits','条副词条':' secondary traits','条随机主词条':' random primary traits',
 '件':' items','条':' traits','仅查看':'Read only','当前·':'Active · ',
}

# Hand-authored interface text only; game names/descriptions are generated locally.
UI.update(json.loads((HERE/'ui_english.json').read_text(encoding='utf-8')))
UI.update({'。装备编号末尾：':'. Item ID suffix: ',
 '配装位置':'Loadout Bindings',
 '制作同款新物品并保留原件，正常拾取保存后可停用生成补丁。':'Create a modified copy and keep the original. After normal pickup and saving, the generation patch can be disabled.',
 '等待处理记录':'Awaiting generation status','草稿待安装':'Draft not installed'})
UI.update({
 '众神陨落-装备编辑器':'Godfall Equipment Editor',
 '安装文件发生变化，请先核对':'Installed patch differs. Check it before installing.',
 '读取组件设置':'Reader Setup',
 '初始化':'Reset','初始化工具':'Reset Application','初始化完成':'Reset Complete','备份目录：':'Backup folder: ',
 '备份后清空清单、草稿、历史记录和个人设置；保留基础读取组件，关闭其他本工具修改。\n初始化前请退出游戏并关闭其他编辑窗口。完成后工具会关闭，重新打开时进行首次设置。':'Back up and clear inventory snapshots, drafts, history and preferences. Keep the base reader and disable other tool changes.\nClose the game and other editor windows first. The tool will close; reopening starts first-run setup.',
 '请先关闭其他编辑或筛选窗口，再初始化。':'Close other editor and filter windows before resetting.',
 '请先正常退出游戏，再初始化工具。':'Close the game normally before resetting the application.',
 '将备份并清空本工具的清单、草稿、历史记录和个人设置，保留基础读取组件并关闭其他本工具修改。未保存的子窗口输入会丢弃。游戏存档及已保存物品不会删除。完成后工具关闭，重新打开时进行首次设置。是否继续？':'Back up and clear this tool\'s inventory snapshots, drafts, history and preferences; keep the base reader and disable other tool changes. Unsaved child-window input is discarded. Game saves and acquired items are kept. The tool closes, and reopening starts first-run setup. Continue?',
 '正在备份并初始化工具，请保持游戏关闭。':'Backing up and resetting the application. Keep the game closed.',
 '初始化完成。已备份并清空工具数据；基础读取组件保留，其他本工具修改已关闭。请重新打开工具完成首次设置。':'Reset complete. Tool data was backed up and cleared; the base reader is retained and other tool changes are disabled. Reopen the tool for first-run setup.',
 '初始化完成。已备份并清空工具数据。请重新打开工具完成首次设置，并安装基础读取组件。':'Reset complete. Tool data was backed up and cleared. Reopen the tool for first-run setup and install the base reader.',
 '初始化仅适用于完整分享包的工具目录。':'Reset is available only in an extracted complete distribution.',
 '初始化路径超出本工具目录，已停止。':'Reset path is outside this tool folder. Stopped.',
 '初始化目录含链接或重定向，已停止。':'A link or redirected directory was found. Reset stopped.',
 '安装记录与游戏目录不一致，未执行初始化。':'The installation record and game path do not match. Nothing was reset.',
 '基础读取组件核对未通过，未执行初始化。':'Base reader verification failed. Nothing was reset.',
 '游戏补丁不属于可核对的本工具状态，未执行初始化。':'The game patch cannot be verified as this tool\'s state. Nothing was reset.',
 '初始化备份核对未通过。':'Reset backup verification failed.',
 '初始化前文件发生变化，已停止。':'A file changed before reset. Stopped.',
 '游戏补丁在初始化前发生变化，已停止。':'The game patch changed before reset. Stopped.',
 '检测到游戏启动，初始化已停止。':'The game started. Reset stopped.',
 '初始化期间游戏补丁发生变化，已停止。':'The game patch changed during reset. Stopped.',
 '初始化未完成，备份目录：':'Reset did not complete. Backup folder: ',
 '尚未安装可核对的兵器库读取组件。请正常退出游戏，在主窗口“设置”中点击“安装基础读取组件”，再启动游戏并刷新。':'No verified inventory reader. Close the game, open Settings, click Install Base Reader, then start the game and refresh.',
 '检测到其他本地补丁，不能自动接管。请正常退出游戏，用原工具停用其补丁，再在本工具“设置”中安装基础读取组件。':'A different local patch was found and cannot be adopted. Close the game, disable that patch using its original tool, then install the base reader in Settings.',
 '核对期间补丁发生变化，未建立读取记录。':'The patch changed during verification. No reader record created.',
 '建立记录期间补丁或安装记录发生变化，已停止。':'The patch or installation record changed. Setup stopped.',
 '请先正常退出游戏，再保存并安装':'Close the game normally before saving and installing.',
 '请先正常退出游戏，再安装本地补丁':'Close the game normally before installing the patch.',
 '请先正常退出游戏，再安装更新后的本地补丁':'Close the game normally before updating the patch.',
 '请先正常退出游戏，再停用补丁':'Close the game normally before disabling the patch.',
 '请先正常退出游戏，再恢复已验证补丁':'Close the game normally before restoring the patch.',
 '请先启动游戏，并在兵器库查看想编辑的装备':'Start the game and open the armory first.',
 '当前游戏补丁尚无兵器库读取组件。新版组件需退出后安装一次；历史记录仍可单独查看。':'The inventory reader is not installed. Close the game and install the base reader in Settings first.',
 '读取结果未通过完整性核对，请重试。':'Snapshot integrity check failed. Try reading again.',
 '设置已在别处更新，请关闭旧窗口后重新打开':'Settings changed in another window. Close this window and reopen the tool.',
 '原版界面资源与已验证版本不一致，未安装补丁。':'Original UI resources differ from the verified build. No patch installed.',
 '游戏数据表不完整。':'Incomplete game data tables.',
 '该强化物模板尚未识别':'Unknown augment template.',
 '诅咒、觉醒或关联目标的强化物尚未适配，先保留原词条':'Cursed, awakened or objective-linked augments are not supported. Keep their original traits.',
 '该强化物包含尚未适配的变体':'This augment variant is not supported.',
 '可编辑副词条与精通词条；保留颜色、耗能和主词条':'Secondary and mastery edits supported; color, power cost and primary retained.',
 '这颗强化物没有本轮可编辑的副词条':'No supported secondary trait on this augment.',
 '已解咒戒指可制作副词条同款替代品；本轮不加入本地覆盖草稿。':'Cleansed rings support secondary copies, not legacy local overrides.',
 '诅咒目标和解除后的变体关联尚在研究，当前只读。':'Cursed/objective-linked variants are read-only here.',
})
