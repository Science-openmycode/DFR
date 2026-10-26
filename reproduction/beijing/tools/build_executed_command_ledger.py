"""Build a read-only historical command/document crosswalk; never run experiments."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
BATCH=ROOT/'data_results/simple_runs/roads_8_16_20261016'
DOC=ROOT/'RUN_20261016_CN.md'


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def basename(s):return str(s).replace('\\','/').rsplit('/',1)[-1].lower()


def entrypoint(argv):
    return next((basename(x) for x in argv if basename(x).endswith(('.py','.ps1'))),basename(argv[0]))


def category(argv):
    name=entrypoint(argv)
    text=' '.join(argv).lower()
    if any(x in text for x in ('pip install','prepare_remote_','prepare_mtnet_deployment.py','fetch_routes.py','detect_resources.py')):
        return None
    if name.startswith(('setup_','fetch_','prepare_remote_')):return None
    if 'pytest' in text or 'compileall' in text:return None
    if 'train_native_mtnet' in name or name.startswith('run_mtnet_gpu'):return '训练与原生生成'
    if name.startswith('synthesize') or name.startswith('generate_') or 'generate_mtnet' in name:return '测量与原生生成'
    if 'ablation' in name:return '消融实验'
    if 'stage_' in name or 'convert_native' in name or 'register_mtnet' in name or 'finalize_mtnet' in name:return '原生表示与评价准备'
    if any(x in name for x in ('fmm.exe','stmatch.exe','route.py','route_cell','route-cell')):return '公共路由'
    if 'evaluate' in name or 'run_tstr' in name or 'audit_v2_runner' in name or 'run_physical' in name or 'run_road' in name:return '指标评估'
    if any(x in name for x in ('validate_','check_measurement','prepare_roads','prepare_tstr','bind_dataset','prepare_public','prepare_ubodt','bind_matcher')):return '预处理与实验核验'
    # Unknown commands are retained explicitly, not silently dropped.
    return '其它已保存的实验命令'


def walk(obj,prefix=''):
    if isinstance(obj,dict):
        for key,value in obj.items():
            here=prefix+'.'+key if prefix else key
            if key in ('command','argv','executed_command'):
                if isinstance(value,list) and value and all(isinstance(x,(str,int,float)) for x in value):
                    yield here,[str(x) for x in value],obj
                elif isinstance(value,str) and value.strip():yield here,[value],obj
            elif isinstance(value,(dict,list)):yield from walk(value,here)
    elif isinstance(obj,list):
        for i,value in enumerate(obj):
            if isinstance(value,(dict,list)):yield from walk(value,f'{prefix}[{i}]')


def option(argv,key):
    try:return argv[argv.index(key)+1]
    except (ValueError,IndexError):return None


def documents(text):
    lines=text.splitlines();blocks=[];section='';inside=False;code=[];start=0;quote='';quote_line=0
    for i,line in enumerate(lines):
        if line.startswith('##'):section=line
        if line.startswith('```'):
            if not inside:
                inside=True;start=i+2;code=[]
                j=i-1
                while j>=0 and not lines[j].strip():j-=1
                end=j
                while j>=0 and lines[j].strip() and not lines[j].startswith(('```','#')):j-=1
                quote='\n'.join(lines[j+1:end+1]) or section
                quote_line=j+2 if quote!=section else next((k+1 for k,v in enumerate(lines[:i]) if v==section),1)
            else:
                blocks.append(dict(start=start,code='\n'.join(code),quote=quote,quote_line=quote_line,section=section))
                inside=False
        elif inside:code.append(line)
    return blocks


def method_router(file,argv):
    method=option(argv,'--method') or option(argv,'--m')
    router=option(argv,'--router') or option(argv,'--r')
    parts=file.parts
    for name in ('SPRT','PrivTrace','DPStd','DPTraj-PM','MTR-DFR','MTNet','DPMM'):
        if name in parts:method=method or name
    for name in ('Origin','Nearest','FMM','FMM_io_v2','STMatch','MM2-MDP'):
        if name in parts:router=router or name
    return method,router


def match_doc(argv,file,blocks):
    name=entrypoint(argv);method,router=method_router(file,argv)
    alias={'run_physical_experiment.py':'evaluate_physical.py','synthesize_dataset.py':'synthesize.py',
           'generate_train_measurement.py':'synthesize_train.py','fmm.exe':'route.py','stmatch.exe':'route.py',
           'run_tstr_experiment.py':'evaluate_tstr.py'}
    target=alias.get(name,name)
    if name=='audit_v2_runner.py':target='evaluate_tstr.py' if option(argv,'--stage')=='tstr' else 'evaluate_coordinates.py'
    candidates=[]
    train_only=any(x in file.parts for x in ('routes_train','measurements_train','native_train'))
    for b in blocks:
        for n,line in enumerate(b['code'].splitlines()):
            if target not in line:continue
            if line.lstrip().startswith(('#','scp ')):continue
            if train_only and not any(x in line+b['quote'] for x in ('--train-only','/train','\\train','训练','TRAIN_')):
                continue
            score=10
            if method and method in line:score+=5
            if router and router in line:score+=4
            if '--train-only' in argv and '--train-only' in line:score+=3
            if '--metric-protocol' in argv and 'audit-v2' in line:score+=3
            candidates.append((score,b,n,line))
    if not candidates:return None
    _,b,n,line=max(candidates,key=lambda x:x[0])
    sentences=re.split(r'(?<=[。！？])',b['quote'])
    # Quote only an exact original experimental sentence, not transfer details.
    safe=[s.strip() for s in sentences if s.strip() and not any(w in s.lower() for w in ('迁移','scp','zip','解包','传输','安装','导出包'))]
    quote=safe[0] if safe else b['section']
    source_text=DOC.read_text(encoding='utf-8-sig')
    quote_line=source_text[:source_text.index(quote)].count('\n')+1 if quote else b['quote_line']
    return dict(document=DOC.as_posix(),line=b['start']+n,command=line,
                quote=quote,quote_line=quote_line,section=b['section'],
                relation='SAME_ENTRYPOINT_NEEDS_ARGUMENT_REVIEW' if target==name else 'CHILD_COMMAND_ONLY_NOT_OUTER_INVOCATION')


def render(argv):
    if len(argv)==1:return argv[0]
    return '& '+' '.join("'"+x.replace("'","''")+"'" for x in argv)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,required=True)
    a=p.parse_args()
    if a.out_dir.exists():raise FileExistsError('Ledger snapshots are append-only; choose another directory')
    text=DOC.read_text(encoding='utf-8-sig');blocks=documents(text)
    roots=[BATCH,ROOT/'data_results/preprocessing/beijing_road_8_16_20261016',ROOT/'command_execution_observations']
    records={};unreadable=[];missing=[];scanned=0;excluded=0
    for base in roots:
        for f in sorted(base.rglob('*.json')):
            if any(x in f.parts for x in ('score_snapshot_20261016_1928','scoring_audit_20261016')):continue
            try:obj=json.loads(f.read_text(encoding='utf-8-sig'))
            except Exception as e:unreadable.append(dict(path=f.as_posix(),error=str(e)));continue
            scanned+=1;found=False
            for field,argv,parent in walk(obj):
                group=category(argv)
                if group is None:excluded+=1;continue
                found=True
                key=json.dumps(argv,ensure_ascii=False)
                evidence=dict(path=f.as_posix(),sha256=sha(f),field=field,
                    saved_status=parent.get('status'),saved_returncode=parent.get('returncode'),
                    seconds=parent.get('elapsed_seconds',parent.get('elapsed_sec',parent.get('seconds'))))
                if key in records:records[key]['evidence'].append(evidence);continue
                method,router=method_router(f,argv)
                remote=any(('D:/MTR/' in x.replace('\\','/') or 'C:/Users/PC/' in x.replace('\\','/')) for x in argv)
                records[key]=dict(id='CMD-'+hashlib.sha256(key.encode()).hexdigest()[:12],category=group,method=method,router=router,
                    argv=argv,host='服务器（由保存路径判断）' if remote else '本机或未保存主机信息',
                    working_directory=parent.get('cwd',parent.get('working_directory')),
                    evidence=[evidence],document_match=match_doc(argv,f,blocks))
            if not found and isinstance(obj,dict) and f.name in ('manifest.json','route_manifest.json','measurement_manifest.json','validation.json','input_binding.json','full_preparation_manifest.json'):
                missing.append(dict(path=f.as_posix(),sha256=sha(f),status=obj.get('status'),note='产物/检查记录存在，但未保存可直接提取的实际命令；不能从计划或现行脚本倒推成历史实跑命令。'))
    entries=sorted(records.values(),key=lambda x:(x['category'],x['method'] or '',x['router'] or '',x['id']))
    a.out_dir.mkdir(parents=True)
    totals=dict(unique_saved_commands=len(entries),evidence_records=sum(len(x['evidence']) for x in entries),
                scanned_json=scanned,excluded_migration_or_test_command_records=excluded,
                commands_without_matching_doc=sum(x['document_match'] is None for x in entries),
                metadata_without_command=len(missing),unreadable_json=len(unreadable))
    ledger=dict(schema='executed-command-document-crosswalk-v1',created_local=datetime.now().astimezone().isoformat(),
        scope='2026-10-16/17 active frozen-road batch and its preprocessing only; not a claim to reconstruct all older conversations',
        source_document=dict(path=DOC.as_posix(),sha256=sha(DOC)),totals=totals,entries=entries,
        metadata_without_command=missing,unreadable=unreadable)
    (a.out_dir/'ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8')
    out=['# 实验实跑命令与说明文档逐条对照账本','',
        '_2026-10-17起建立；只记录实验与评价准备，不记录迁移、传输、安装或机器占用检查。_','','---','',
        '## 📋 先看结论','',
        '这是一份历史证据账本，不是待运行计划，也不是新的实验结果。每条均列出说明文档原句、说明中的命令、产物实际保存的完整命令及证据。当前说明文档的引文是本次归档时的版本，不能证明这些文字在实验启动前已经存在。',
        '',f"本次扫描{scanned}份JSON，提取{len(entries)}条不同的已保存命令，关联{totals['evidence_records']}处记录。相同命令的重复记录已合并；这些数目不是独立实验数、执行次数或完成实验数。",'',
        '范围为当前15730条冻结道路数据集批次（训练12584、测试3146）及其预处理。更早GSRT/旧17123或10040输入的所有历史终端命令尚未完整恢复，绝不把它们混入当前账本。也不将仍等待的DPMM控制器视为已运行的全量DPMM。','',
        '说明文档：'+f'[{DOC.name}]({DOC.as_posix()})',
        '',f"本次说明文档SHA-256：`{ledger['source_document']['sha256']}`。每条引文及其行号已同时写入ledger.json，后续文档改行号时以保存的原句为准。",'',
        '## 🔐 防止以后记错的执行规则','',
        '1. 每次启动实验前先读本账本和RUN文档，不依赖聊天记忆；先登记将执行的文档原句、完整命令、主机和工作目录。',
        '2. 原样执行已登记命令，M、R、评估分开；参数需要变化时先修改计划并写明原因，不把“相同用途”当“命令一致”。',
        '3. 执行后追加实际argv、真实退出码、开始/结束或单机墙钟耗时、最终manifest与结果哈希。失败和中断也保留。',
        '4. 新记录只追加，不改写旧实跑命令。缺命令、缺原句、只保存子进程、缺退出码都明确标出；没有证据不能宣布完成。','',
        '本历史账本仅提取现存记录，没有为了补齐命令重新跑实验。没有保存的外层CLI、运行目录、失败尝试和历史时序不从现行脚本推测。','',
        '## 📍 各类记录索引','']
    for group,count in sorted(Counter(x['category'] for x in entries).items()):out.append(f'- {group}：{count}条不同的已保存命令')
    current=None
    for r in entries:
        if r['category']!=current:
            current=r['category'];out+=['',f"## 📚 {current}",'']
        label=' / '.join(x for x in (r['method'],r['router'],entrypoint(r['argv'])) if x)
        out += [f"### {r['id']} · {label}",'',f"运行位置：{r['host']}。",'',
                '工作目录：'+(f"`{r['working_directory']}`（执行记录保存）" if r['working_directory'] else '历史记录未保存，不能按当前目录倒推。'), '']
        d=r['document_match']
        if d:
            out += [f"说明文档原句（[{DOC.name}:{d['quote_line']}]({DOC.as_posix()}:{d['quote_line']})）：",'']
            out += ['> '+s for s in d['quote'].splitlines()]
            out += ['',f"说明中的命令（第{d['line']}行）：",'','```powershell',d['command'],'```','']
            if d['relation']=='CHILD_COMMAND_ONLY_NOT_OUTER_INVOCATION':
                out += ['对照结论：保存的是内部程序/子进程命令，只关联到上述外层入口用途；不能据此声称外层命令逐字执行过，也未自动判为参数一致。','']
            else:out += ['对照结论：找到同名入口的说明命令；以下实际argv原样保留，参数、配置和路径仍需逐项审核。本账本不自动宣称两者一致。','']
        else:out += ['说明文档原句：未找到对应入口的明确命令段落。不能用别处用途相似的句子替代；此条列为文档缺口。','']
        out += ['实际保存的完整命令：','','```powershell',render(r['argv']),'```','',
                '说明：数组形式的argv只做PowerShell安全引用显示，参数内容不改写；临时目录和旧绝对路径保持原样，不能把这段历史命令直接当作可重跑指令。','',
                '执行证据：','']
        for e in r['evidence']:
            extra=f"；保存状态={e['saved_status']}；保存退出码={e['saved_returncode']}"
            if e['seconds'] is not None:extra+=f"；保存耗时={e['seconds']}秒"
            out += [f"- [{Path(e['path']).relative_to(ROOT).as_posix()}]({e['path']})，字段`{e['field']}`{extra}。",
                    f"  文件SHA-256：`{e['sha256']}`"]
        out += ['','未保存退出码显示None，意思是没有该项证据，不等于成功退出。产物保存命令也不单独证明算法、评分定义或整个实验已经正确。','']
    out += ['## ⚠️ 记录缺口与限制','',f"有{len(missing)}份产物/检查清单未保存实际命令。以下逐份列出，不从运行计划补造“已运行命令”：",'']
    for m in missing:out += [f"- [{Path(m['path']).relative_to(ROOT).as_posix()}]({m['path']})：{m['note']}"]
    out += ['',f"另有{totals['commands_without_matching_doc']}条已保存命令未找到明确的说明命令段落。正文已逐条标出，不把它们当作已对齐。",'',
            '历史失败尝试如果没有保留argv或终端记录，不能保证已全部覆盖。本文不把缺失记录说成“从未发生”，也不把产物数当命令次数。测试命令与迁移命令按用户要求不计入本文。', '',
            '机器可读证据：'+f'[ledger.json]({(a.out_dir/"ledger.json").resolve().as_posix()})','']
    (a.out_dir/'EXECUTED_EXPERIMENT_COMMANDS_CN.md').write_text('\n'.join(out),encoding='utf-8')
    print(json.dumps(totals,ensure_ascii=False))


if __name__=='__main__':main()
