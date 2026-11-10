#!/usr/bin/env python3
"""Generate exactly 10 presentation + 4 graded Project Card slides.

Usage:
 python NLPTRIO_build_submission.py
 python NLPTRIO_build_submission.py --results nlptrio_results
Export PowerPoint to PDF with LibreOffice, or let this script do it automatically.
"""
import argparse, json, os, re, subprocess, csv
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

W,H=13.333,7.5
NAVY='102C44'; INK='16344E'; TEAL='008F85'; CYAN='1DB8A8'; GRAY='5C7184'; BG='F6F8FC'; WHITE='FFFFFF'; LINE='D8E5EE'; AMBER='BA7D18'; YELLOW='FFF3D7'; ERR='B64D51'; LIGHT='E7F6F3'; PALE='EAF0F6'; REDBG='FCEBEC'; LIGHTNAVY='1B4263'
FONTS='Aptos'

def rgb(h):return RGBColor.from_string(h)
def rect(s,x,y,w,h,fill=WHITE,border=None,radius=False):
 sh=s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x),Inches(y),Inches(w),Inches(h))
 sh.fill.solid();sh.fill.fore_color.rgb=rgb(fill)
 if border:sh.line.color.rgb=rgb(border);sh.line.width=Pt(.75)
 else:sh.line.fill.background()
 if radius:
  try:sh.adjustments[0]=0.09
  except:pass
 return sh

def text(s,txt,x,y,w,h,sz=15,color=INK,bold=False,align='left',valign='top',margin=0.02,italic=False):
 box=s.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)); tf=box.text_frame;tf.clear();tf.word_wrap=True
 tf.margin_left=Inches(margin);tf.margin_right=Inches(margin);tf.margin_top=Inches(margin);tf.margin_bottom=Inches(0)
 tf.vertical_anchor={'top':MSO_ANCHOR.TOP,'mid':MSO_ANCHOR.MIDDLE,'bottom':MSO_ANCHOR.BOTTOM}[valign]
 for i,line in enumerate(str(txt).split('\n')):
  p=tf.paragraphs[0] if i==0 else tf.add_paragraph()
  p.alignment={'left':PP_ALIGN.LEFT,'center':PP_ALIGN.CENTER,'right':PP_ALIGN.RIGHT}[align]
  p.space_after=Pt(0);p.space_before=Pt(0);p.line_spacing=1.14
  r=p.add_run();r.text=line;r.font.name=FONTS;r.font.size=Pt(sz);r.font.bold=bold;r.font.italic=italic;r.font.color.rgb=rgb(color)
 return box

def label(s,txt,x,y,w,sz=10,color=TEAL):return text(s,txt.upper(),x,y,w,.28,sz,color,True)
def card(s,x,y,w,h,fill=WHITE):return rect(s,x,y,w,h,fill,LINE,True)
def rule(s,x,y,w,color=LINE):return rect(s,x,y,w,.012,color)

def bullet(s,items,x,y,w,size=14,leading=.49,mark=TEAL):
 for i,it in enumerate(items):
  yy=y+i*leading
  rect(s,x,yy+.13,.075,.075,mark)
  text(s,it,x+.18,yy,w-.18,leading-.01,size)

def slide(prs,n,title_,subtitle='',appendix=False):
 s=prs.slides.add_slide(prs.slide_layouts[6]);s.background.fill.solid();s.background.fill.fore_color.rgb=rgb(BG)
 rect(s,0,0,W,.11,TEAL if not appendix else NAVY)
 label(s,'NLPTRIO · CSE 484 · NOV 12, 2026' if not appendix else 'GRADED APPENDIX · PROJECT CARD',.54,.24,7.5,9)
 text(s,title_,.56,.63,12.25,.54,26,NAVY,True)
 if subtitle:text(s,subtitle,.58,1.19,12.1,.35,11.5,GRAY)
 rule(s,.55,7.11,12.21)
 text(s,'NLPTRIO · TEAM 13   |   Gabil Rahimli · Mustafa Başaran · Samet Alkan',.56,7.18,10.4,.19,8.5,GRAY)
 text(s,f'{n:02d} / 14',11.95,7.16,.74,.2,8.5,GRAY,align='right')
 return s

def smalltag(s,t,x,y,w,color=TEAL,bg=LIGHT):
 rect(s,x,y,w,.32,bg,radius=True);text(s,t,x+.08,y+.052,w-.16,.19,9,color,True)

def boxvalue(s,n,caption,x,y,w=2.6,h=1.05):
 card(s,x,y,w,h);text(s,n,x+.16,y+.16,w-.3,.46,27,TEAL,True);text(s,caption,x+.16,y+.73,w-.3,.2,10,GRAY)

def row(s,txts,x,y,widths,h=.49,header=False,highlight=False):
 p=x
 for t,w in zip(txts,widths):
  rect(s,p,y,w-.01,h,NAVY if header else (LIGHT if highlight else WHITE),LINE if not header else NAVY)
  text(s,str(t),p+.08,y+.12,w-.16,h-.15,11,WHITE if header else INK,header)
  p+=w

def loadjson(path):
 try:return json.loads(Path(path).read_text(encoding='utf-8'))
 except:return None

def crop(t,lim=160):
 t=re.sub(r'\s+',' ',str(t)).replace('[PET_BOUNDARY]','').strip()
 return t[:lim-1]+'…' if len(t)>lim else t

def make(args):
 res=Path(args.results)
 summ=loadjson(res/'baseline_summary.json') or {};err=loadjson(res/'baseline_error_summary.json') or {}
 audit=loadjson(res/'audit.json') or {}
 pilots=loadjson(res/'berturk_runs.json') or []
 real=bool(summ and audit.get('total_rows')==2436 and audit.get('num_pets')==70)
 # Defensive: do not accept fabricated/QA summary just because a file exists.
 if summ and not real:raise ValueError('Results must be from the real 2,436-row / 70-PET dataset. Not using QA data.')
 def mainval(model):
  m=summ.get(model,{}) if real else {}
  return f"{m.get('pooled_out_of_fold_macro_f1',0):.4f}" if m else 'PENDING'
 def interval(model):
  m=summ.get(model,{}) if real else {}
  a=m.get('pooled_95pct_pet_cluster_CI')
  return f'[{a[0]:.3f}, {a[1]:.3f}]' if a else 'Pending'
 def foldstat(model):
  m=summ.get(model,{}) if real else {}
  return f"{m.get('mean_fold_macro_f1',0):.4f} ± {m.get('std_fold_macro_f1',0):.4f}" if m else 'Pending'
 prs=Presentation();prs.slide_width=Inches(W);prs.slide_height=Inches(H)
 # 1
 s=slide(prs,1,'Can masking improve unseen-PET generalization?', 'Research question and the result that would reject our hypothesis')
 card(s,.63,1.68,12.05,2.12)
 label(s,'RESEARCH QUESTION',.88,1.96,3.5)
 text(s,'Does masking the annotated target expression in 30% of training sentences improve BERTurk macro-F1 on PETs never seen during fine-tuning?',.88,2.33,11.35,1.25,23,NAVY,True)
 card(s,.63,4.04,7.5,1.78,YELLOW);label(s,'OUR “NO” RESULT',.87,4.3,3,color=AMBER)
 text(s,'No supported improvement if the paired 95% PET-cluster bootstrap interval includes zero. A gain below +0.02 is not practically meaningful.',.87,4.68,6.98,.82,16)
 card(s,8.35,4.04,4.33,1.78,LIGHT);label(s,'UNCHANGED FROM PROPOSAL',8.6,4.3,3.7)
 text(s,'One pretrained model; controlled masking; held-out target expressions.',8.6,4.75,3.84,.7,15)
 text(s,'Original question preserved. Ambiguity-aware masking is an additional exploratory ablation.',.7,6.29,11.7,.36,11,GRAY)
 # 2
 s=slide(prs,2,'The problem: the same phrase can mean different things','Target identity is not enough; context determines the label')
 card(s,.63,1.77,5.92,3.17,LIGHT);smalltag(s,'1 · EUPHEMISTIC',.9,2.0,1.9)
 text(s,'“... birçok ünlü isim aramızdan ayrıldı.”',.91,2.64,5.34,.87,23,NAVY,True)
 text(s,'Meaning: people passed away.',.92,3.76,5.18,.42,15)
 card(s,6.78,1.77,5.91,3.17,WHITE);smalltag(s,'0 · LITERAL',7.04,2.0,1.5,bg=PALE)
 text(s,'“Gelenler olacağı gibi aramızdan ayrılanlar da olacak.”',7.04,2.53,5.35,1.17,20,NAVY,True)
 text(s,'Meaning: people leave the group.',7.04,3.94,5.15,.34,14)
 rect(s,.63,5.28,12.06,.91,NAVY,radius=True)
 text(s,'Problem with instance-level splits: the same PET can occur in both train and test → lexical memorization risk.',.94,5.54,11.39,.44,15,WHITE,True)
 text(s,'Source examples: official Turkish PET dataset card (Biyik et al., 2024; 2026).',.71,6.48,11.9,.29,10,GRAY)
 # 3
 s=slide(prs,3,'Dataset and the frozen evaluation design','Source: Turkish Potentially Euphemistic Terms · CC BY 4.0')
 for i,(v,l) in enumerate([('2,436','Annotated sentences'),('70','PET groups'),('1,457','Euphemistic (1)'),('979','Literal (0)')]):boxvalue(s,v,l,.64+i*3.09,1.70,2.89,1.09)
 label(s,'REPORTED FIRST-LOOK SPLIT (SEED 42)',.67,3.03,6)
 widths=[2.84,2.7,2.68,3.75]
 row(s,['Partition','Sentences','PET groups','Use'],.64,3.4,widths,.45,True)
 for i,data in enumerate([['Train','1,450','44','Fit dev baselines'],['Development','420','12','First-look scores'],['Test (unopened)','566','14','Frozen; no reported score']]):row(s,data,.64,3.86+i*.47,widths,.45,highlight=(i==2))
 card(s,.64,5.56,12.04,.86,LIGHT)
 text(s,'Final protocol: deterministic five-fold, PET-disjoint cross-validation on all 70 PETs; validation PETs disjoint within each fold.',.9,5.82,11.45,.49,14)
 text(s,'First-look 566-example test and the final five-fold test partitions are distinct protocols; never mix their scores.',.72,6.64,11.9,.28,10,GRAY)
 # 4
 s=slide(prs,4,'Protocol prevents target-expression leakage','One PET is assigned to the held-out side of a fold, never both sides')
 for i,(t,sub,col) in enumerate([('Training PETs','Fit classifier',NAVY),('Validation PETs','Choose epoch',AMBER),('Test PETs','Evaluate once',TEAL)]):
  x=.69+i*4.25;card(s,x,1.97,3.93,1.46);rect(s,x,1.97,.1,1.46,col)
  text(s,t,x+.33,2.19,3.3,.34,19,NAVY,True);text(s,sub,x+.33,2.72,3.18,.29,13,GRAY)
  if i<2:text(s,'→',x+3.92,2.46,.34,.4,21,TEAL,True)
 label(s,'LOCKED BEFORE MODEL RESULTS',.74,3.93,5)
 bullet(s,['5 folds; grouping variable = PET; split seed = 42.','Main metric: pooled out-of-fold macro-F1; class-level precision/recall and confusion matrices.','3 method seeds: 42, 123, 2026; 2,000 paired PET-cluster bootstrap draws.','Improvement requires a positive CI excluding zero; practical target: Δ macro-F1 ≥ +0.02.'],.81,4.34,11.75,13.4,.54)
 # 5
 s=slide(prs,5,'Baseline: measured first-look scores vs pending test scores','Never present dev numbers as test performance')
 card(s,.63,1.70,6.12,3.42);label(s,'ACTUAL FIRST-LOOK DEV RESULTS',.9,1.98,5)
 row(s,['System','Dev macro-F1'],.89,2.45,[3.46,1.97],.48,True)
 row(s,['Majority class','0.3684'],.89,2.94,[3.46,1.97],.49)
 row(s,['TF-IDF + logistic reg.','0.4603'],.89,3.44,[3.46,1.97],.49,highlight=True)
 text(s,'420 dev sentences, 12 unseen PETs; 566-example first-look test not opened.',.91,4.20,5.50,.65,12,GRAY)
 card(s,6.97,1.70,5.71,3.42)
 label(s,'FROZEN FIVE-FOLD TEST',7.25,1.98,4.95)
 row(s,['Model','OOF macro-F1','PET 95% CI'],7.18,2.45,[2.02,1.47,1.73],.47,True)
 row(s,['Majority',mainval('majority'),interval('majority')],7.18,2.93,[2.02,1.47,1.73],.49)
 row(s,['TF-IDF',mainval('tfidf_logreg'),interval('tfidf_logreg')],7.18,3.43,[2.02,1.47,1.73],.49,highlight=True)
 text(s,('Measured after new reproducible run.' if real else 'NOT RUN: execute baseline command; values must come from actual test predictions.'),7.25,4.21,5.04,.62,11,TEAL if real else AMBER,True)
 card(s,.64,5.45,12.04,.85,PALE)
 text(s,'Main baseline comparison: same training PETs, same validation/test groups; fold spread and PET-cluster interval reported separately.',.94,5.71,11.4,.43,14)
 # 6
 s=slide(prs,6,'Error analysis: where the lexical baseline fails','Dev confusion matrix reconstructed from the proposal’s rounded metrics')
 card(s,.65,1.80,5.3,3.58)
 label(s,'TF-IDF · DEVELOPMENT SET',.87,2.08,4.3)
 text(s,'Predicted 0',3.14,2.55,1.08,.27,10,GRAY,True);text(s,'Predicted 1',4.39,2.55,1.08,.27,10,GRAY,True)
 text(s,'True 0',1.01,3.09,1.07,.31,12,NAVY,True);text(s,'True 1',1.01,4.05,1.07,.31,12,NAVY,True)
 for xx,yy,num,good in [(3.04,2.9,'20',True),(4.29,2.9,'155',False),(3.04,3.85,'15',False),(4.29,3.85,'230',True)]:
  rect(s,xx,yy,1.08,.72,LIGHT if good else REDBG,radius=True)
  text(s,num,xx,yy+.16,1.08,.36,22,TEAL if good else ERR,True,align='center')
 card(s,6.18,1.80,6.5,3.58)
 if real:
  label(s,'REAL FROZEN TEST ERRORS · OOF',6.44,2.08,5.7)
  e=err.get('tfidf_logreg',{})
  examples=[]
  exfile=res/'baseline_errors_tfidf_logreg.csv'
  if exfile.exists():
   with exfile.open(newline='',encoding='utf-8') as f:examples=list(csv.DictReader(f))
  for ii,(kind,nam,ct) in enumerate([('false_positive','False positives',e.get('false_positives','?')),('false_negative','False negatives',e.get('false_negatives','?'))]):
   y=2.53+ii*1.30
   text(s,f'{ct} {nam.lower()}',6.49,y,5.73,.37,18,ERR,True)
   ex=next((k for k in examples if k.get('error_type')==kind),None)
   txt=(f"Real error [{ex.get('PET','?')}]: “{crop(ex.get('TEXT',''),110)}”" if ex else 'No error instance observed in this category.')
   text(s,txt,6.49,y+.44,5.70,.68,11.0)
 else:
  label(s,'ERROR CATEGORIES · DEV',6.44,2.08,5.7)
  text(s,'155 false positives',6.49,2.61,5.73,.4,21,ERR,True)
  text(s,'Literal contexts incorrectly predicted euphemistic.',6.51,3.12,5.72,.58,13)
  text(s,'15 false negatives',6.49,3.85,5.73,.42,21,ERR,True)
  text(s,'Euphemistic contexts incorrectly predicted literal.',6.51,4.40,5.72,.54,13)
 card(s,.65,5.65,12.03,.71,YELLOW)
 text(s,(f"FROZEN TEST: {err.get('tfidf_logreg',{}).get('total_errors','?')} misclassified examples saved; detailed category counts and one example per category exported as CSV." if real else 'TEST: ≥30 individual misclassifications and category-specific example quotes still require the baseline prediction export.'),.9,5.89,11.5,.33,12,AMBER,True)
 text(s,'Matrix inferred uniquely from the proposal’s rounded F1, label counts, and class-0 recall; not an independently saved prediction log.',.72,6.66,11.96,.26,9.6,GRAY)
 # 7
 s=slide(prs,7,'Method: one controlled change, plus a small extension','Two core conditions use identical training records, PET markers and settings')
 for i,(title,body,col) in enumerate([
  ('A. Standard BERTurk','Original PET remains visible in every training sentence.',NAVY),
  ('B. Random 30% masking','Replace whole marked PET with one [MASK] in seeded 30% of training rows.',TEAL),
  ('C. Ambiguity-aware 30%','Optional: select masking rows preferentially from PETs with both labels in train.',AMBER)]):
  x=.66+i*4.24;card(s,x,1.92,3.94,2.55)
  rect(s,x,1.92,3.94,.08,col)
  text(s,title,x+.20,2.23,3.49,.65,18,NAVY,True)
  text(s,body,x+.20,3.08,3.49,1.02,14)
 card(s,.68,4.88,12.0,1.19,LIGHT)
 label(s,'IMPORTANT CONTROLS',.95,5.09,4)
 text(s,'All conditions test original, unmasked sentences. Same 30% mask budget for B and C. No test-label information is used to choose masks.',.96,5.50,11.4,.46,14)
 text(s,'New extension responds to the teacher’s “too much benchmarking” feedback without replacing the original research question.',.73,6.44,11.88,.35,11,GRAY)
 # 8
 s=slide(prs,8,'Implementation status and BERTurk pilot','Dev score is required before claiming method progress')
 card(s,.64,1.76,6.1,3.78)
 label(s,'IMPLEMENTED IN PROJECT CODE',.92,2.01,5.5)
 bullet(s,['CSV parsing, marker validation and PET-group audit','Deterministic grouped train/dev/test partitions','Majority + word 1–2-gram TF-IDF baselines','BERTurk fine-tuning for A/B/C with mask-budget checks','Per-class outputs, grouped errors and GPU/runtime logging'],.95,2.50,5.38,13.2,.54)
 card(s,6.96,1.76,5.71,3.78,WHITE)
 label(s,'FIRST DEV NUMBER · BERTURK',7.26,2.01,5.1)
 if pilots:
  for i,p in enumerate(pilots[:3]):
   text(s,f"{p.get('condition')}  |  fold {p.get('fold')} seed {p.get('seed')}  |  best dev F1={p.get('best_val_f1',0):.4f}",7.28,2.64+i*.55,4.94,.47,12,INK,True)
  text(s,'Recorded from a completed pilot run.',7.28,4.83,4.87,.35,11,TEAL)
 else:
  text(s,'NOT YET MEASURED',7.27,2.78,4.94,.61,21,AMBER,True)
  text(s,'Run the pilot on GPU. Report a real dev macro-F1, training minutes and peak allocated GPU memory.',7.27,3.75,4.88,1.13,14)
 card(s,.64,5.81,12.03,.66,YELLOW)
 text(s,'No BERTurk improvement or GPU cost claim is made until the run produces a log.',.88,6.02,11.6,.32,13,AMBER,True)
 # 9
 s=slide(prs,9,'Concrete plan to the final','Dates, owners, ablation, risk and fallback')
 widths=[1.72,2.20,6.13,1.88]
 row(s,['By date','Owner','Deliverable','Evidence'],.68,1.76,widths,.46,True)
 lines=[
  ('Nov 10','Mustafa','Verify dataset + frozen PET splits','audit.json'),
  ('Nov 11','Gabil','Run baseline OOF + export ≥30 test errors','CSV + JSON'),
  ('Nov 11','Samet','Categorize errors, verify citations, submit PDF','error table'),
  ('Nov 15','Gabil','Standard / random / ambiguity pilot','dev F1 + GPU log'),
  ('Nov 22','Gabil + Mustafa','5-fold × 3-seed core comparison','OOF predictions'),
  ('Nov 29','Samet','PET bootstrap + context sensitivity ablation','CI + examples'),
  ('Dec 06','All three','Final report, repo cleanup, 10-min demo','reproduction')]
 for i,li in enumerate(lines):row(s,li,.68,2.23+i*.52,widths,.49,highlight=(i%2==0))
 card(s,.68,6.09,11.93,.59,PALE)
 text(s,'Risk: rare PETs/imbalanced labels and Colab budget. Fallback: preserve paired A vs B; trim exploratory C before core seeds.',.85,6.28,11.49,.29,11.5)
 # 10
 s=slide(prs,10,'What our evidence supports — and what it does not','A research project with a falsifiable hypothesis, not a benchmark leaderboard')
 card(s,.67,1.83,5.94,3.59,LIGHT);label(s,'SUPPORTED NOW',.94,2.13,5.3)
 bullet(s,['2,436 examples, 70 PETs, binary classification','Proposal dev baseline: TF-IDF macro-F1 = 0.4603','Reconstructed dev errors: 155 FP + 15 FN','PET-grouped evaluation and masking logic defined'],1.03,2.71,5.33,13.1,.57)
 card(s,6.83,1.83,5.84,3.59,WHITE);label(s,'NOT YET SUPPORTED',7.1,2.13,5.3,color=AMBER)
 bullet(s,['Any test score not in our experiment logs','A measured BERTurk performance gain','An ambiguity-aware advantage','A causal claim about improved context use'],7.16,2.71,5.21,13.1,.57,AMBER)
 rect(s,.68,5.78,11.99,.75,NAVY,radius=True)
 text(s,'Next decision: run the fixed baseline; audit ≥30 true test errors; then report the BERTurk dev pilot.',.98,6.04,11.3,.3,14,WHITE,True)
 # A1
 s=slide(prs,11,'Project Card · 1–3','Working manuscript outline · fields required by the rubric',True)
 card(s,.67,1.62,11.98,2.23);label(s,'01  TITLE & ABSTRACT · <=150 WORDS',.94,1.81,9)
 text(s,'Does Training-Time PET Masking Improve BERTurk Generalization to Unseen Turkish Euphemisms?',.94,2.19,11.42,.44,17,NAVY,True)
 abstract=('We study whether masking a potentially euphemistic term (PET) in 30% of BERTurk fine-tuning instances helps identify previously unseen Turkish PETs. '
           'Using 2,436 labelled sentences representing 70 PET groups, we compare ordinary fine-tuning with seeded target masking under PET-disjoint splits. '
           'We first evaluate majority-class and TF-IDF baselines, then compare methods using out-of-fold macro-F1 and paired PET-cluster bootstrap intervals. '
           'Our exploratory extension chooses masked instances from label-ambiguous training PETs to test whether ambiguity-aware selection differs from random masking. '
           '[METHOD RESULTS, INTERVAL AND MAIN ERROR FINDING TO BE INSERTED AFTER EXPERIMENTS.]')
 text(s,abstract,.94,2.68,11.31,1.00,11.8)
 card(s,.67,4.00,5.75,2.30);label(s,'02  RESEARCH QUESTION',.91,4.18,5.1)
 text(s,'Unchanged. Does 30% target masking increase macro-F1 on never-seen PETs? “No” if paired PET-bootstrap CI includes 0; ≥+0.02 is the practical gain threshold.',.92,4.68,5.18,1.36,12.5)
 card(s,6.62,4.00,6.03,2.30);label(s,'03  TESTABLE CONTRIBUTIONS',6.88,4.18,5.49)
 bullet(s,['PET-disjoint evaluation will expose any lexical baseline weakness.','Paired masking comparison will support or reject generalization gain.','Ambiguity-aware selection may improve or hurt random masking.'],6.91,4.63,5.42,11.2,.45)
 # A2
 s=slide(prs,12,'Project Card · 4–5','Related work with explicit differences; data processing',True)
 card(s,.65,1.59,12.02,3.67);label(s,'04  RELATED WORK · FULL REFERENCES + OUR DIFFERENCE',.92,1.78,10.9)
 refs=[
  'Gavidia, M., Lee, P., Feldman, A. & Peng, J. (2022). CATs are Fuzzy PETs. LREC, 2658–2671. aclanthology.org/2022.lrec-1.285/ — corpus/ambiguity; no Turkish masking.',
  'Biyik, H., Lee, P. & Feldman, A. (2024). Turkish Delights: A Dataset on Turkish Euphemisms. SIGTURK, 71–80. aclanthology.org/2024.sigturk-1.7/ — Turkish resource/models; not held-out-PET masking.',
  'Lee, P. & Feldman, A. (2024). Report on the Multilingual Euphemism Detection Task. FigLang, 110–114. aclanthology.org/2024.figlang-1.15/ — multilingual shared task; not train-time masking.',
  'Firsich, T. & Rios, A. (2024). Can GPT4 Detect Euphemisms across Multiple Languages? FigLang. aclanthology.org/2024.figlang-1.9/ — prompted GPT-4; not fine-tuned BERTurk.',
  'Biyik, H. C., Barak, L., Peng, J. & Feldman, A. (2026). When Semantic Overlap Is Not Enough. SIGTURK, 113–125. aclanthology.org/2026.sigturk-1.11/ — cross-lingual transfer; not target masking.',
  'Poh, W. et al. (2026). The Multilingual Euphemism Benchmark. LREC, 7307–7319. aclanthology.org/2026.lrec-1.579/ — benchmark languages/LLMs; not Turkish PET-held-out masking.',
  'Schweter, S. (2020). BERTurk: BERT Models for Turkish, v1.0. Zenodo. doi.org/10.5281/zenodo.3770924 — pretrained backbone; our comparison is a fine-tuning intervention.'
 ]
 for i,t in enumerate(refs):text(s,f'{i+1}. {t}',.91,2.20+i*.41,11.29,.40,9.7,INK)
 card(s,.65,5.46,12.02,1.26);label(s,'05  DATA · SOURCE, LICENCE, PREPROCESSING COUNTS',.92,5.63,10.5)
 text(s,'Hugging Face: hasancanbiyik/turkish-potentially-euphemistic-terms (CC BY 4.0). Original 2,436 rows / 70 PETs; label 1=1,457, label 0=979. Reported first look: train 1,450 (44 PETs), dev 420 (12), frozen test 566 (14). Masked PET span marked with [PET_BOUNDARY]; row count unchanged by masking. Source record ID 1007: “Aramızdan ayrılan arkadaşımıza yeni görev yerinde başarılar dileriz.” label 0. Final fold counts: '+( 'see audit.json.' if real else 'not audited in this environment.'),.92,6.04,11.25,.58,10.2)
 # A3
 s=slide(prs,13,'Project Card · 6–9','Method, pre-registered evaluation, results and baseline errors',True)
 card(s,.65,1.62,5.83,1.62);label(s,'06  METHOD & BASELINE',.87,1.81,5.13)
 text(s,'Majority; word 1–2-gram TF-IDF + Logistic Regression. BERTurk A: PET visible; B: 30% whole-span [MASK]; C (exploratory): train-ambiguous PET selection. Same budget, markers, seeds. GPU cost: '+(f"{pilots[0].get('elapsed_training_seconds',0)/60:.1f} min measured pilot." if pilots else 'not measured yet; planned Colab GPU.'),.88,2.17,5.27,.98,11)
 card(s,6.68,1.62,5.98,1.62);label(s,'07  EVALUATION PROTOCOL',6.94,1.81,5.38)
 text(s,'Frozen PET-grouped folds (seed 42); validation PETs disjoint. OOF macro-F1, class scores, 3 seeds (42/123/2026), 2,000 paired PET-bootstrap draws. Practical threshold +0.02; CI excludes 0 for evidence.',6.94,2.17,5.37,.96,11)
 card(s,.65,3.42,12.01,1.69);label(s,'08  RESULTS SO FAR · 95% PET-CLUSTER INTERVAL',.89,3.59,10.5)
 row(s,['System','First-look DEV (reported)','Frozen 5-fold TEST OOF','95% PET CI'],.90,4.02,[2.56,2.87,3.20,2.86],.33,header=True)
 row(s,['Majority','0.3684',mainval('majority'),interval('majority')],.90,4.38,[2.56,2.87,3.20,2.86],.31)
 row(s,['TF-IDF + LR','0.4603',mainval('tfidf_logreg'),interval('tfidf_logreg')],.90,4.72,[2.56,2.87,3.20,2.86],.31,highlight=True)
 card(s,.65,5.28,12.01,1.44);label(s,'09  ERROR ANALYSIS · ≥30 TEST ERRORS REQUIRED',.89,5.44,10.6)
 if real:
  x=err.get('tfidf_logreg',{})
  example_list=[]
  exfile=res/'baseline_errors_tfidf_logreg.csv'
  if exfile.exists():
   with exfile.open(newline='',encoding='utf-8') as f:example_list=list(csv.DictReader(f))
  snippets=[]
  for kind,short,count in [('false_positive','FP',x.get('false_positives','?')),('false_negative','FN',x.get('false_negatives','?'))]:
   one=next((a for a in example_list if a.get('error_type')==kind),None)
   if one:snippets.append(f"{short} {count}: ‘{crop(one.get('TEXT',''),95)}’ [PET: {one.get('PET')}].")
   else:snippets.append(f'{short} {count}: no examples in this category.')
  msg=f"Measured five-fold OOF: {x.get('total_errors','?')} total errors; two categories. "+' '.join(snippets)+' Full row-level errors and semantic category counts saved in baseline_errors_tfidf_logreg.csv.'
 else:
  msg='Confirmed from reported DEV summary: TF-IDF produced 155 false positives and 15 false negatives (170 errors). Their individual IDs/examples were not supplied. FROZEN TEST: category counts and ≥30 individual misclassified examples are pending export by the provided baseline script.'
 text(s,msg,.9,5.85,11.26,.74,10.9)
 # A4
 s=slide(prs,14,'Project Card · 10–12','Research lead, feedback response, risks and reproducibility',True)
 card(s,.65,1.61,12.03,1.38);label(s,'10  RESEARCH LEAD',.92,1.79,11.5)
 text(s,'Gabil Rahimli (proposed research lead; no graduate member): Biyik et al. (SIGTURK 2026) tests cross-lingual transfer; Poh et al. (LREC 2026) benchmarks multilingual euphemism detection. We instead test BERTurk training-time target masking on held-out Turkish PETs. Ablations: 0% vs uniform 30%; uniform vs ambiguity-aware 30%.',.93,2.19,11.33,.65,11.1)
 card(s,.65,3.18,12.03,1.62);label(s,'11  PLAN, BIGGEST RISK & RESPONSE TO FEEDBACK',.92,3.36,11.45)
 text(s,'Nov 10 Mustafa: audit; Nov 11 Gabil: frozen baselines; Nov 11 Samet: 30 errors, slides & upload; Nov 15 Gabil: BERTurk dev pilot; Nov 22 Gabil/Mustafa: main OOF runs; Nov 29 Samet: bootstrap/ablation; Dec 06 all: final report. Main risks: class imbalance, rare PETs, limited GPU. Fallback: prioritize core A vs B over exploratory C. Feedback: add ambiguity-aware masking as a small method contribution, not just a score comparison.',.93,3.77,11.25,.94,11)
 card(s,.65,4.99,12.03,1.73);label(s,'12  REPRODUCIBILITY & ROLES',.92,5.17,11.4)
 text(s,'Repository: NOT DECIDED YET (publish GitHub link before submission). One command: python NLPTRIO_experiments.py --phase baselines --outdir nlptrio_results. Split seed 42; fine-tuning seeds 42,123,2026; dependency versions and dataset hash exported to environment.json. Mustafa: data/splits; Gabil: baselines/BERTurk/compute; Samet: statistics/errors/demo. AI use: ChatGPT (brainstorming, coding/English), Claude (literature/layout critique); all reported values must be verified against scripts and dataset.',.93,5.57,11.30,1.02,11)
 out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);prs.save(out)
 pdf=out.with_suffix('.pdf')
 cmd=['libreoffice','-env:UserInstallation=file:///tmp/nlptrio_lo_mid_'+str(os.getpid()),'--headless','--convert-to','pdf','--outdir',str(out.parent),str(out)]
 try: r=subprocess.run(cmd,capture_output=True,text=True,timeout=100);print('LibreOffice',r.returncode,r.stdout,r.stderr)
 except Exception as exc:print('PDF conversion failed',repr(exc))
 print('Created PPTX',out,'PDF exists?',pdf.exists(),'Real baseline in deck?',real)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--results',default='nlptrio_results');ap.add_argument('--output',default='Team13_MidProject.pptx');make(ap.parse_args())
