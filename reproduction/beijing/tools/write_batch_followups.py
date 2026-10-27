"""Write batch-specific supplementary commands; never execute experiments."""
import json


def write_followups(root,out,base,config,rewrite):
    prefix=out.relative_to(root).as_posix();result='results/'+base['batch']
    plan=json.loads((root/'supplement/sweeps/plan.json').read_text(encoding='utf-8'))
    for cell in plan['cells']:
        cell['directory']=rewrite(cell['directory'])
        if 'post_directory' in cell:cell['post_directory']=rewrite(cell['post_directory'])
        cell['config']=prefix+'/configs/'+cell['config']
        for step in cell.get('steps',[]):step['command']=rewrite(step['command'])
    (out/'sweeps_plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    releases={}
    for method in ('SPRT','PrivTrace','DPTraj-PM','DPStd'):
        parent=f'{result}/reproduction_checked_20261024'
        lineage=f'{parent}/measurements_train/{method}/lineage.json'
        for router in ('Origin','Nearest','FMM','STMatch','MM2-MDP'):
            coordinates=(f'{parent}/measurements_train/{method}/measurement.pkl' if router=='Origin' else
                         f'{parent}/coordinate_views_train/{method}/{router}/coordinates.pkl')
            releases[method+' + '+router]=dict(coordinates=coordinates,lineage=lineage)
    native=f'{result}/reproduction_native_20261024/train'
    releases['DPMM']=dict(coordinates=f'{native}/DPMM_view/coordinates.pkl',lineage=f'{native}/DPMM_view/lineage.json')
    releases['MTNet']=dict(coordinates=f'{native}/MTNet_view/coordinates.pkl',lineage=f'{native}/MTNet_deployment/lineage.json')
    dfr=f'{result}/reproduction_dfr_length_20261024'
    releases['MTR-DFR']=dict(coordinates=f'{dfr}/train_view/MTR-DFR/coordinates.pkl',lineage=f'{dfr}/native_train/MTR-DFR/lineage.json')
    (out/'training_releases.json').write_text(json.dumps(releases,indent=2),encoding='utf-8')
    attack_config=f'{prefix}/attack_ready.json'
    commands=[
        ('Algorithm ablations',f'run_dfr_ablation_frozen.py --config {config} --out {result}/ablation/ablation'),
        ('Ablation figure',f'tools/plot_executed_results.py --script legacy/plotting/regenerate_figures.py --figure ablation --results {result}/ablation/ablation/results.csv --out-dir {result}/ablation/figures'),
        ('Prepare training-only attack inputs',f'prepare_attack_inputs.py --config {config} --releases {prefix}/training_releases.json --out {result}/attack_inputs --out-config {attack_config}'),
        ('Membership attacks',f'experiments/privacy_attack.py --config {attack_config} --batch attacks'),
        ('Attack figure',f'experiments/plot.py --config {attack_config} --experiment privacy_attack --batch attacks'),
        ('Ordered interface attack',f'evaluation/run_bound_ordered_attack.py --config {attack_config} --out {result}/ordered_attack'),
    ]
    for kind in ('k','budget','endpoint_diagnostic'):
        commands.append((kind+' aggregation',f'tools/collect_portable_sweeps.py --kind {kind} --config {config} --plan {prefix}/sweeps_plan.json --out {result}/summaries/{kind}'))
    commands.append(('Budget figures',f'supplement/budget/render.py --source {result}/summaries/budget/summary.json --out {result}/figures/budget'))
    text='# Supplementary experiments for this batch\n\nRun the generated synthesis, routing, native scoring, TSTR and sweep commands first. Each command below reads this batch only. The 23-entry release map lists expected outputs; preparation checks that they exist.\n'
    for title,command in commands:text+=f'\n## {title}\n\n```powershell\n.venv/Scripts/python.exe {command}\n```\n'
    target=out/'commands/SUPPLEMENT_COMMANDS.md';target.write_text(text,encoding='utf-8')
    return dict(supplement=target.relative_to(root).as_posix(),sweep_cells=len(plan['cells']),training_releases=len(releases))
