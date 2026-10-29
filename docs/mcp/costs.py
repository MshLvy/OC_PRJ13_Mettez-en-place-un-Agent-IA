"""Financial model only; no API client, video processing or infrastructure action."""
import json,math,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parent
INPUTS={'date':'2026-10-29','currency':'EUR HT unless USD explicitly stated','usd_per_eur':1.1133,'fx_source':'S22, ECB 2026-10-28','storage_usd_per_gb_month':0.00695,'storage_source':'S12, starts at 6.95 USD/TB/month, decimal GB, no free-tier deduction','dev_day_eur':600,'review_day_eur':350,'legal_day_eur':900,'hours_per_day':7,'contingency':0.25,'frame_interval_seconds':2,'source_mbps':2,'thumbnail_kb':25,'metadata_kb':2,'copies':2,'new_catalogue_fraction_month':0.10,'model_cpu_seconds_frame':0.25,'decode_core_hours_video_hour':0.15,'processing_overhead':1.3,'review_minutes_new_video':10,'rights_setup_eur':0,'rights_month_eur':0}
WORK=[('Cadrage et exigences/droits',2),('Corpus et outillage annotation',3),('Vision 2D limitée',6),('Séquences et index exact',4),('MCP et sécurité',3),('Interface et contexte',2),('Tests et exploitation',4)]
def build(dev=24,review=5,legal=2):
 base=dev*INPUTS['dev_day_eur']+review*INPUTS['review_day_eur']+legal*INPUTS['legal_day_eur']
 return {'dev_days':dev,'review_days':review,'legal_days':legal,'subtotal_eur':base,'contingency_eur':base*0.25,'total_eur':base*1.25}
def scenario(name,n,minutes,vm,maintenance):
 h=n*minutes/60;frames=h*3600/2
 source=h*2*3600/8/1000 # Mbps -> decimal GB
 thumbs=frames*25/1000000;metadata=frames*2/1000000
 stored=2*(source+thumbs+metadata);storage=stored*INPUTS['storage_usd_per_gb_month']
 initial_cpu=1.3*(h*0.15+frames*0.25/3600)
 monthly_new=n*0.1
 human=maintenance*600/7+monthly_new*10/60*350/7
 usd=vm+storage
 total=human+usd/INPUTS['usd_per_eur']+INPUTS['rights_month_eur']
 return {'name':name,'videos':n,'minutes_each':minutes,'catalogue_video_hours':h,'sampled_frames':int(frames),'source_gb':source,'thumbnails_gb':thumbs,'metadata_gb':metadata,'stored_gb_two_copies':stored,'initial_cpu_core_hours':initial_cpu,'monthly_cpu_core_hours':initial_cpu*0.1,'cpu_sensitivity_initial_core_hours':[1.3*(h*0.05+frames*0.1/3600),1.3*(h*0.5+frames*1/3600)],'vm_usd_month':vm,'storage_usd_month':storage,'infrastructure_usd_month':usd,'infrastructure_eur_month':usd/INPUTS['usd_per_eur'],'maintenance_hours_month':maintenance,'human_eur_month':human,'opex_eur_month':total,'initial_search_calls_if_one_per_video':n,'metadata_refresh_calls_per_30d':math.ceil(n/50)}
def calculate():
 data={'inputs':INPUTS,'work_packages_dev_days':WORK,'build_low':build(18,3,1),'build_central':build(),'build_high':build(32,8,3),'alternative_pgn':build(8,3,1),'scenarios':[scenario('A - MVP 20 vidéos',20,20,24,2),scenario('B - catalogue 200 vidéos',200,30,44,4)],'scale_initial_extra_review_eur':180*10/60*350/7,'rights_sensitivity_month_eur':[0,200,1000],'claimed_inference_benchmark':False}
 data['first_year_eur']={'A':data['build_central']['total_eur']+INPUTS['rights_setup_eur']+12*data['scenarios'][0]['opex_eur_month'],'B':data['build_central']['total_eur']+INPUTS['rights_setup_eur']+data['scale_initial_extra_review_eur']+12*data['scenarios'][1]['opex_eur_month']}
 return data
if __name__=='__main__':
 data=calculate();(ROOT/'costs.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 with (ROOT/'costs.csv').open('w') as f:
  writer=csv.writer(f,lineterminator="\n");writer.writerow(['metric','unit','A','B'])
  for key,unit in [('catalogue_video_hours','hours'),('sampled_frames','frames'),('stored_gb_two_copies','GB'),('initial_cpu_core_hours','core-hours hypothesis'),('monthly_cpu_core_hours','core-hours hypothesis'),('infrastructure_usd_month','USD/month'),('human_eur_month','EUR/month'),('opex_eur_month','EUR/month')]:writer.writerow([key,unit,*[round(s[key],6) for s in data['scenarios']]])
 print(json.dumps({'central':data['build_central'],'opex':[s['opex_eur_month'] for s in data['scenarios']],'storage':[s['stored_gb_two_copies'] for s in data['scenarios']]},indent=2))
