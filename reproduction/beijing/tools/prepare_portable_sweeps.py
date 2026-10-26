"""Write fully expanded K/budget commands; preparation only, no experiment execution."""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    base=json.loads((ROOT/'configs/beijing.json').read_text(encoding='utf-8'))
    out=ROOT/'supplement/sweeps';out.mkdir(parents=True,exist_ok=True)
    cells=[]
    for kind,values in [('k',[24,48,96,192,384,768]),('budget',[.2,.4,.7,1,1.4,2,3]),('endpoint_diagnostic',[96,384,768])]:
        lines=[f'# {kind}：独立的逐条实验命令','','工作目录始终是交付根目录，不依赖服务器盘符。先安装README指定环境。已完成的正式实验不重跑；以下用于其他机器的新批次复现。每组生成、表示转换、评分独立执行，后一步读取前一步输出，不覆盖既有目录。', '', '每份使用15730条全集与相同公开输出数量。种子20260719—20260723；诊断只用20260719，标记为非私有端点准确测量，不进入同预算DP比较。', '']
        for value in values:
            for seed in ([20260719] if kind=='endpoint_diagnostic' else range(20260719,20260724)):
                name=f'{kind}_{str(value).replace(".","p")}_seed_{seed}'
                config=copy.deepcopy(base);config.update(batch=name,seed=seed,epsilon=value if kind=='budget' else 1.4)
                config['paths']['output']='results/portable_sweeps'
                config['paths']['edge_cache']=config['paths']['metric_cache']
                cfg=f'supplement/sweeps/{name}.json'
                (ROOT/cfg).write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
                b=f'results/portable_sweeps/{name}'
                raw=f'{b}/native/MTR-DFR/seed_{seed}_length/road_routes.pkl.gz'
                route=f'{b}/representation/synthetic_routes.pkl.gz'
                generator='synthesize_dfr.py' if kind=='budget' else ('synthesize_k.py' if kind=='k' else 'supplement/k_original/synthesize_endpoint_diagnostic.py')
                command=f'.venv/Scripts/python.exe {generator} --config {cfg} --length-aware'
                if kind!='budget':command+=f' --endpoint-partition resources/endpoint_partitions/partition{value}.json'
                commands=[command,
                    f'.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes {raw} --network resources/network/network.shp --expected-slots 15730 --out {b}/representation',
                    f'.venv/Scripts/python.exe evaluate.py --config {cfg} --method MTR-DFR --router Origin --input {route} --out {b}/road_scores',
                    f'.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes {route} --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir {b}/physical',
                    f'.venv/Scripts/python.exe evaluate_coordinates.py --config {cfg} --method MTR-DFR --router Origin --input {route} --metric-protocol audit-v2 --out {b}/coordinate_scores',
                    f'.venv/Scripts/python.exe evaluate_road_tasks.py --config {cfg} --method MTR-DFR --router Origin --input {route} --score-manifest {b}/road_scores/manifest.json --out {b}/road_tasks']
                lines+=['',f'## {name}','']
                records=[]
                for stage,cmd in zip(['generation','representation','road_scores','physical','coordinate_scores','road_tasks'],commands):
                    lines+=['```powershell',cmd,'```','',f'产物：{b}/'+ ('native/MTR-DFR' if stage=='generation' else stage)+'；失败时保留该步骤日志与部分产物，不继续评分。','']
                    records.append({'stage':stage,'command':cmd,'line':len(lines)-4})
                cells.append({'name':name,'kind':kind,'value':value,'seed':seed,'config':cfg,'directory':b,'steps':records})
        doc=out/(kind+'_COMMANDS_CN.md');doc.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        digest=hashlib.sha256(doc.read_bytes()).hexdigest()
        for cell in cells:
            if cell['kind']==kind:cell.update(document=doc.relative_to(ROOT).as_posix(),document_sha256=digest)
    (out/'plan.json').write_text(json.dumps({'status':'COMMAND_PLAN_NOT_EXECUTED','cells':cells},indent=2),encoding='utf-8')
    print(json.dumps({'cells':len(cells),'commands':sum(len(c['steps']) for c in cells),'experiments_executed':0}))


if __name__=='__main__':prepare()
