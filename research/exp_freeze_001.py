"""EXP-FREEZE-001: deterministic two-candidate research freeze; production untouched."""
from __future__ import annotations
import hashlib,json,subprocess,sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import joblib
import numpy as np
import pandas as pd
RESEARCH=Path(__file__).resolve().parent;ROOT=RESEARCH.parent;sys.path[:0]=[str(ROOT),str(RESEARCH)]
import exp_model_001 as mm
import exp_tgt_002 as t2
C=RESEARCH/'contracts'/'exp_freeze_001.json';R=RESEARCH/'results';M=RESEARCH/'manifests';F=RESEARCH/'frozen_candidates'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def stable_frame_hash(df):return hashlib.sha256(pd.util.hash_pandas_object(df,index=True).values.tobytes()).hexdigest()
def markdown_table(df):
 """Small dependency-free Markdown formatter for the freeze report."""
 cols=list(df.columns); rows=[[str(x) for x in r] for r in df.fillna('').itertuples(index=False,name=None)]
 esc=lambda v:v.replace('|','\\|').replace('\n','<br>')
 out=['| '+' | '.join(esc(c) for c in cols)+' |','| '+' | '.join('---' for _ in cols)+' |']
 out.extend('| '+' | '.join(esc(v) for v in row)+' |' for row in rows)
 return '\n'.join(out)
def git_state():
 try:return {'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'diff':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).splitlines()}
 except Exception:return {'commit':None,'diff':['UNAVAILABLE']}
def code_hashes():
 paths=[RESEARCH/'exp_model_001.py',RESEARCH/'exp_tgt_001.py',RESEARCH/'exp_tgt_002.py',RESEARCH/'exp_port_001.py',RESEARCH/'temporal_validation.py',ROOT/'config.py',RESEARCH/'contracts'/'exp_tgt_001.json',RESEARCH/'contracts'/'exp_tgt_002.json',RESEARCH/'contracts'/'exp_model_001.json',RESEARCH/'contracts'/'exp_port_001.json',RESEARCH/'contracts'/'exp_robust_001.json',RESEARCH/'contracts'/'exp_final_001.json',RESEARCH/'contracts'/'exp_ens_001.json',C]
 return {str(p.relative_to(ROOT)):sha(p) for p in paths}
def feature_schema():return [{'name':'mom_12_1','formula':'last_valid_close[-22] / last_valid_close[-253] - 1','lookback':'252 sessions with 1-month skip','minimum_history':253,'transform':'raw price return','dtype':'float64'},{'name':'mom_63','formula':'last_valid_close / last_valid_close[-64] - 1','lookback':'63 returns','minimum_history':64,'transform':'raw price return','dtype':'float64'},{'name':'vol_63','formula':'std of last 63 valid close-to-close returns','lookback':'63 returns','minimum_history':64,'transform':'raw volatility','dtype':'float64'}]
def main():
 R.mkdir(exist_ok=True);M.mkdir(exist_ok=True);F.mkdir(exist_ok=True);c=json.loads(C.read_text())
 # A completed freeze is write-once: verify existing artefacts and return without mutation.
 existing=[F/cid/'model.joblib' for cid in c['candidates']]
 if any(p.exists() for p in existing):
  if not all(p.exists() and (p.parent/'candidate_manifest.json').exists() for p in existing):raise RuntimeError('FROZEN_ARTIFACT_MISMATCH: partial frozen candidate set')
  for p in existing:
   m=json.loads((p.parent/'candidate_manifest.json').read_text());
   if sha(p)!=m.get('model_sha256') or m.get('candidate_id')!=p.parent.name:raise RuntimeError('FROZEN_ARTIFACT_MISMATCH')
  print('FROZEN_ARTIFACTS_READ_ONLY_REUSE');return
 mc,tc1,tc2,cal,views,features,targets=mm.load_all();cut=pd.Timestamp(c['training']['cutoff']);sel=pd.read_csv(R/'EXP-MODEL-001_procedure_selections.csv');data_hash={'exp_data_005_manifest_sha256':sha(M/'EXP-DATA-005_reproducibility.json'),'feature_input_dataframe_sha256':stable_frame_hash(features),'target_dataframe_sha256':stable_frame_hash(targets),'eligible_universe_sha256':hashlib.sha256('\n'.join(sorted(views)).encode()).hexdigest(),'ticker_count':len(views),'price_status':'PASS FOR RESEARCH','date_range':[str(cal.min().date()),str(cut.date())]}
 candidates=[];tests=[];schema=feature_schema();schema_hash=hashlib.sha256(json.dumps(schema,sort_keys=True).encode()).hexdigest()
 for cid,info in c['candidates'].items():
  path=F/cid;path.mkdir(exist_ok=True);train=targets[(targets.target_family.eq(info['target_family']))&(targets.horizon_sessions.eq(info['horizon_sessions']))&(targets.label_end<=cut)].copy();assert len(train)>0 and train.label_end.max()<=cut
  bundle1=mm.fit_arch(info['architecture'],train,mc);bundle2=mm.fit_arch(info['architecture'],train,mc)
  ref=features[features.signal_date<=cut].copy();p1,_=mm.predict_bundle(bundle1,ref);p2,_=mm.predict_bundle(bundle2,ref);top1=ref.assign(score=p1).groupby('signal_date').apply(lambda x:tuple(x.sort_values(['score','symbol'],ascending=[False,True]).head(10).symbol),include_groups=False);top2=ref.assign(score=p2).groupby('signal_date').apply(lambda x:tuple(x.sort_values(['score','symbol'],ascending=[False,True]).head(10).symbol),include_groups=False)
  deterministic=bool(np.allclose(p1,p2,rtol=0,atol=c['seeds']['reproduction_tolerance']) and top1.equals(top2));assert deterministic
  artifact={'candidate_id':cid,'version':info['version'],'architecture':info['architecture'],'bundle':bundle1,'features':c['features']['columns'],'target_family':info['target_family'],'horizon_sessions':info['horizon_sessions'],'training_cutoff':str(cut.date()),'seed_policy':c['seeds']};artifact_path=path/'model.joblib';joblib.dump(artifact,artifact_path);model_hash=sha(artifact_path)
  refout=ref[['signal_date','symbol']].copy();refout['raw_score']=p1;refout['cross_section_rank']=refout.groupby('signal_date').raw_score.rank(ascending=False,method='first');refout['selected_top10']=refout.cross_section_rank.le(10);refout.to_csv(path/'reference_predictions.csv',index=False)
  candidate={'candidate_id':cid,'candidate_version':info['version'],'status':c['status'],'model_type':info['architecture'],'model_path':str(artifact_path.relative_to(ROOT)),'model_sha256':model_hash,'training_start':str(train.signal_date.min().date()),'training_cutoff':str(cut.date()),'training_observations':len(train),'training_last_label_end':str(train.label_end.max().date()),'target_procedure':info['target_family'],'horizon_procedure':info['horizon_sessions'],'features':schema,'feature_schema_hash':schema_hash,'seed_policy':c['seeds'],'code_hashes':code_hashes(),'data_hashes':data_hash,'portfolio_contract_hash':sha(RESEARCH/'contracts'/'exp_port_001.json'),'reproduction_command':f'.\\venv\\Scripts\\python.exe research\\run_frozen_shadow.py --candidate {cid} --asof YYYY-MM-DD','known_caveats':['survivor universe','provider-dependent price history','only three price features','mom_63 dependency','macro excluded','fundamental excluded','historical evidence is not clean forward']+(['O1 sensitivity','top-stock concentration','bootstrap IC uncertainty'] if cid=='RC-LGBMR-001' else ['sector concentration','weaker stability classification','lower bootstrap P(IC>0)','ranking-objective complexity'])}
  (path/'candidate_manifest_pre_timestamp.json').write_text(json.dumps(candidate,indent=2),encoding='utf-8');candidates.append(candidate);tests.append({'candidate_id':cid,'deterministic_predictions':deterministic,'training_cutoff_pass':bool(train.label_end.max()<=cut),'top10_reproducible':bool(top1.equals(top2))})
 # Timestamp exists only after both fits, hashes and reproduction tests are complete.
 freeze=datetime.now(ZoneInfo('Europe/Istanbul')).isoformat();combined={'experiment_id':'EXP-FREEZE-001','freeze_timestamp':freeze,'timezone':'Europe/Istanbul','clean_forward_start':freeze,'status':c['status'],'ensemble_status':'REJECTED / EXCLUDED','candidates':candidates,'code_hashes':code_hashes(),'data_hashes':data_hash,'git_state':git_state(),'change_control':c['change_control'],'clean_forward':c['clean_forward'],'production_writes_allowed':False,'tests':tests}
 for candidate in candidates:
  candidate['freeze_timestamp']=freeze;candidate['clean_forward_start']=freeze;path=F/candidate['candidate_id'];(path/'candidate_manifest.json').write_text(json.dumps(candidate,indent=2),encoding='utf-8');(path/'shadow_signals.jsonl').touch(exist_ok=True);(path/'shadow_portfolio.jsonl').touch(exist_ok=True);(path/'shadow_operational_events.jsonl').touch(exist_ok=True)
 (F/'EXP-FREEZE-001_combined_manifest.json').write_text(json.dumps(combined,indent=2),encoding='utf-8');pd.DataFrame(tests).to_csv(R/'EXP-FREEZE-001_reproducibility_tests.csv',index=False)
 report=f'''# EXP-FREEZE-001 — RESEARCH CANDIDATE FREEZE & CLEAN FORWARD CONTRACT

## 1. Executive Summary

Two independent **FROZEN RESEARCH CANDIDATE / CLEAN FORWARD MONITORING** candidates were created. Neither is production-validated or forward-validated.

## 2. Historical Research Closure

Historical alpha research is closed for these candidate versions. Material model/data changes create a new version and terminate comparability of the existing clean-forward evidence.

## 3. Candidate Set

{markdown_table(pd.DataFrame(candidates)[['candidate_id','model_type','target_procedure','horizon_procedure','training_cutoff','training_observations']])}

## 4. Regression Freeze

`RC-LGBMR-001`: RAW/H60 from EXP-MODEL-001 O4 locked inner selection.

## 5. LambdaMART Freeze

`RC-LAMBDAMART-001`: BETA_RESIDUAL/H60 from EXP-MODEL-001 O4 locked inner selection.

## 6. Code / Data Hashes

Combined manifest: `research/frozen_candidates/EXP-FREEZE-001_combined_manifest.json`.

## 7. Feature Schema

{markdown_table(pd.DataFrame(schema))}

## 8. Target / Horizon Procedure

Global target/horizon remains NOT FIXED. Historical inner-only procedure is frozen; forward observations cannot reselect it.

## 9. Final Training

Training labels end on or before {cut.date()}; no post-cutoff data is used.

## 10. Seeds / Determinism

Seeds 11/29/47, median aggregation, deterministic/force-column-wise settings, n_jobs=1. Two same-input fits produced identical predictions and Top-10 selections within 1e-12.

## 11. Portfolio Contract

K=10 equal weight; 60-session holding/rebalance; existing cost/liquidity/unfilled/cash/mark/terminal contract.

## 12. Execution Contract

After-close signal; next applicable eligible open; no same-close execution.

## 13. Shadow Signal Logging

Append-only JSONL files are initialized separately per candidate. Retroactive signals are operational events, not clean-forward evidence.

## 14. Shadow Portfolio Logging

Separate append-only intended-order/portfolio JSONL files are initialized; production paper portfolios are untouched.

## 15. Clean Forward Definition

Only signals generated strictly after {freeze} are evidence. Completed configured-horizon cohorts only.

## 16. Completed Cohort Logic

Each signal records selected H and label-end completion. Pending cohorts are excluded from forward statistics.

## 17. Overlap / Dependence

20/40/60 cohorts can overlap; raw cohort counts are not independent market histories.

## 18. Change Control

{json.dumps(c['change_control'],indent=2)}

## 19. Caveat Register

{json.dumps({x['candidate_id']:x['known_caveats'] for x in candidates},indent=2)}

## 20. Reproduction Commands

`python research/run_frozen_shadow.py --candidate RC-LGBMR-001 --asof YYYY-MM-DD`  
`python research/run_frozen_shadow.py --candidate RC-LAMBDAMART-001 --asof YYYY-MM-DD`

## 21. Tests

{markdown_table(pd.DataFrame(tests))}

## 22. Production Isolation

Production writes = 0; final protected hash check required.

## 23. Phase L Gate

PASS if both candidate manifests/artifacts and deterministic validation are present.

## 24. CLEAN FORWARD START

{freeze}

## 25. SINGLE NEXT BEST ACTION

Run only the research shadow runner prospectively when new eligible data arrives; do not treat any historical reconstruction as clean-forward evidence.
''';(R/'EXP-FREEZE-001_report.md').write_text(report,encoding='utf-8')
 summary={'experiment_id':'EXP-FREEZE-001','phase_l_gate':'PASS','regression':'FROZEN','lambdamart':'FROZEN','ensemble':'EXCLUDED','forward_monitoring':'READY','freeze_timestamp':freeze,'clean_forward_start':freeze,'candidates':[x['candidate_id'] for x in candidates]};(R/'EXP-FREEZE-001_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');files=sorted(R.glob('EXP-FREEZE-001_*'));(M/'EXP-FREEZE-001_manifest.json').write_text(json.dumps({'contract_sha256':sha(C),'code_sha256':sha(Path(__file__)),'combined_freeze_manifest_sha256':sha(F/'EXP-FREEZE-001_combined_manifest.json'),'files':{p.name:sha(p) for p in files}},indent=2),encoding='utf-8');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
