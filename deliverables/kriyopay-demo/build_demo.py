"""Rebuild the 90-second illustrative product showcase locally (Pillow + FFmpeg)."""
from pathlib import Path
import json, subprocess, sys, textwrap, wave
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / '.dev-runtime' / 'video-libs'))
import imageio_ffmpeg
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H = 1920, 1080
INK, GREEN, MINT, BG, MUTED = '#172b27', '#166b55', '#e5f3ed', '#f5f7f5', '#64766f'
FONT = Path('C:/Windows/Fonts')
def font(n, bold=False): return ImageFont.truetype(str(FONT / ('segoeuib.ttf' if bold else 'segoeui.ttf')), n)

SCENES = [
 dict(title='One connected\noperation.', section='MEET KRIYOPAY', subtitle='Finance + fleet + control', kind='hero',
      items=['Capture & review invoices','Plan & track transport','Settle & reconcile payments','Report with accountability'],
      tags=['Finance teams','Transport operators','Business owners'],
      voice='Meet KriyoPay. Connect invoice processing, transport operations, driver settlements, and financial controls in one organized workspace.'),
 dict(title='Know what\nneeds action.', section='01 / DAILY WORK', subtitle='Overview & Needs attention', kind='table',
      headers=['Priority','Action needed','Owner'], rows=[['High','Invoice extraction failed','Finance'],['High','Approval overdue','Approver'],['Today','Delivery proof missing','Fleet'],['Today','Salary balance due','Finance']],
      items=['One attention inbox','Clear ownership','Follow-ups & notifications'], tags=['Invoice review','Exceptions','Approvals','Overdue payments','Fleet follow-ups'],
      voice='Start with your overview and attention inbox. Find invoice issues, pending approvals, overdue payments, fleet follow-ups, and outstanding salaries.'),
 dict(title='Upload once.\nFields extracted.', section='02 / INVOICE INTAKE', subtitle='From document to reviewable fields', kind='invoice',
      items=['Upload or email intake','Automatic field extraction','Confidence flags & retry'], tags=['Processing status','Duplicate review','Bulk actions','AI review'],
      voice='Upload invoices or bring them in through email. Automatic extraction prepares editable fields, with confidence flags, duplicate review, and clear retry options.'),
 dict(title='Match with\nthe evidence.', section='03 / PROCUREMENT', subtitle='Invoice · Purchase order · Goods receipt', kind='flow',
      items=['Purchase orders','Goods received','Invoice matching','Resolve differences'], tags=['Vendors','Vendor aliases','Vendor portal','Credit & debit notes'],
      voice='Connect supplier invoices with purchase orders and goods receipts. Manage vendors, aliases, financial notes, and portal access while reviewing differences.'),
 dict(title='Keep people\nin control.', section='04 / REVIEW & APPROVAL', subtitle='Exceptions to reviewed decisions', kind='flow',
      items=['Flag exception','Draft follow-up','Route for approval','Record decision'], tags=['Approval rules','SLA rules','Human approval','Activity history'],
      voice='Route exceptions, prepare follow-up drafts, and apply approval and SLA rules. People make approval decisions, with activity history for accountability.'),
 dict(title='Close the loop\non payments.', section='05 / PAYMENTS', subtitle='Recorded payments & bank reconciliation', kind='table',
      headers=['Bank transaction','Recorded payment','Review'], rows=[['Supplier debit','Invoice payment','Candidate'],['Customer credit','Collection','Candidate'],['Driver debit','Salary payment','Candidate'],['Unmatched entry','Needs investigation','Review']],
      items=['Payment allocations','Duplicate protection','Confirm bank matches'], tags=['CSV / XLSX import','Customer collections','Driver payments'],
      voice='Record payments and allocations, then reconcile imported bank transactions against supplier payments, customer collections, and driver settlements, with duplicate protection.'),
 dict(title='Plan the load.\nAssign the trip.', section='06 / FLEET PLANNING', subtitle='Customers → orders → dispatch', kind='board',
      items=['Trucks & drivers','Customer directory','Transport orders','Create & assign trips'], tags=['Dispatch board','Trip list','Dedicated feature pages'],
      voice='Manage trucks, drivers, and customers. Turn transport orders into assigned trips, and coordinate the day from the dispatch board.'),
 dict(title='Updates from\nthe road.', section='07 / DRIVER EXPERIENCE', subtitle='Phone-friendly trip updates', kind='mobile',
      items=['Pickup & delivery check-ins','Odometer readings','Receipts & delivery proof','Offline save & later sync'], tags=['Delivery photo','Customer signature','Assigned trips'],
      voice='Drivers update trips from a phone: pickup and delivery, odometer readings, receipts, photos, and signatures. Save updates offline and sync later.'),
 dict(title='See where\nthe money goes.', section='08 / TRIP COST CONTROL', subtitle='Trip costs, mileage & profitability', kind='cost',
      items=['Fuel & expense budgets','Mileage monitoring','Profitability alerts'], tags=['Trip reports','Low-margin alerts','Missing-record follow-ups'],
      voice='Track fuel and trip expenses against budgets. Review mileage, profitability, and low-margin alerts to investigate unusual costs and missing records.'),
 dict(title='Every driver.\nA clear balance.', section='09 / DRIVER FINANCE', subtitle='Earnings → settlement → ledger', kind='ledger',
      items=['Monthly, trip & kilometre pay','Advances & recoveries','Approved deductions','Audited corrections & reversals'], tags=['Evidence & reviewer approval','Salary payments','Date-range ledger export'],
      voice='Calculate driver pay using monthly, trip, or kilometre policies. Track advances, approved deductions, payments, reversals, and balances in an exportable ledger.'),
 dict(title='Delivered.\nBilled. Collected.', section='10 / CUSTOMER BILLING', subtitle='Transport work to customer collections', kind='flow',
      items=['Complete trip','Prepare invoice','Record collection','Track outstanding'], tags=['Customer invoices','Trip billing context','Collection reconciliation'],
      voice='Connect completed transport work to customer invoices. Record collections, follow outstanding balances, and carry that context into reconciliation.'),
 dict(title='Clarity you\ncan share.', section='11 / REPORTS & CONTROLS', subtitle='Operational and financial visibility', kind='report',
      items=['Trip costs & salary balances','Invoice exceptions & payment status','Tax review & audit history','Date-range exports'], tags=['Operational reports','Tally export','Recorded user actions'],
      voice='Review operational and financial reports. Export trip costs, salary balances, exceptions, and payment status, with tax review, Tally exports, and audit history.'),
 dict(title='Connect tools.\nReduce chasing.', section='12 / AUTOMATION', subtitle='Integrations & reminder preferences', kind='flow',
      items=['Email intake','API & webhooks','WhatsApp workflows','Reminder rules'], tags=['Custom fields','Recipients & channels','Escalations','Notifications'],
      voice='Configure email intake, API access, webhooks, WhatsApp workflows, and custom fields. Choose reminder recipients, channels, and escalation rules for overdue work.'),
 dict(title='The right access.\nThe right setup.', section='13 / ADMINISTRATION', subtitle='Workspace controls & internal admin console', kind='table',
      headers=['Workspace','Internal admin','Control'], rows=[['Users & roles','Company onboarding','Access'],['Branches & settings','Plans & feature access','Setup'],['Billing & plan','Subscriptions & usage','Billing'],['Role permissions','Security & audit logs','History']],
      items=['View, edit, approve, pay & export','Fleet feature access','Company & subscription setup'], tags=['Staff roles','Payment records','Feature overrides'],
      voice='Control workspace roles, branches, settings, and billing. Internal admins manage companies, fleet access, plans, subscriptions, usage, payment records, and security.'),
 dict(title='Less chasing.\nMore visibility.', section='KRIYOPAY', subtitle='See the workflow that matters to your team.', kind='hero',
      items=['Invoices to reviewed records','Orders to completed trips','Earnings to settled balances','Operations to useful reports'], tags=['Book a guided walkthrough','Explore your own workflow'],
      voice='KriyoPay brings finance and transport workflows together. Explore a guided walkthrough tailored to your team, your operations, and your next stage of growth.'),
]

def draw_scene(index):
 s=SCENES[index]; im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im)
 def rect(box,fill, radius=22,outline=None): d.rounded_rectangle(box,radius,fill=fill,outline=outline,width=2)
 def txt(x,y,t,n=26,fill=INK,bold=False): d.text((x,y),t,font=font(n,bold),fill=fill,spacing=12)
 def wrapped(x,y,t,n,width,fill=INK,bold=False):
  # Pixel-width wrapping keeps cards clear at full HD.
  words=t.split(); lines=[]; line=''
  for word in words:
   cand=(line+' '+word).strip()
   if d.textlength(cand,font=font(n,bold))>width and line: lines.append(line); line=word
   else: line=cand
  lines.append(line)
  for j,line in enumerate(lines): txt(x,y+j*(n+12),line,n,fill,bold)
  return len(lines)*(n+12)
 def chip(x,y,t):
  w=int(d.textlength(t,font=font(20)))+32; rect((x,y,x+w,y+42),MINT,21); txt(x+16,y+6,t,20,GREEN); return w
 rect((64,48,112,96),GREEN,13); txt(76,50,'K',30,'white',True)
 txt(126,48,'KriyoPay',32,INK,True); txt(1535,60,'PRODUCT SHOWCASE',18,MUTED,True)
 txt(70,177,s['section'],20,GREEN,True)
 txt(66,232,s['title'],60,INK,True)
 if s['kind'] not in ['hero']:
  y=465
  for item in s['items']:
   d.ellipse((73,y+10,82,y+19),fill=GREEN)
   y+=wrapped(101,y,item,25,490,MUTED)+24
 else:
  wrapped(72,448,'Connected finance and fleet workflows, with people in control.',29,490,MUTED)
 # App-style illustrative product canvas. Not a recording of the production UI.
 rect((640,174,1850,884),'#dfe8e2',30)
 rect((630,164,1840,874),'white',30)
 rect((630,164,1840,229),INK,25)
 d.rectangle((630,201,1840,229),fill=INK)
 txt(661,182,'KriyoPay / '+ ('Workspace' if index!=13 else 'Administration'),20,'white',True)
 txt(1533,185,'ILLUSTRATIVE VIEW',16,'#b9d8ca',True)
 txt(672,267,s['subtitle'],30,INK,True)
 txt(672,316,'Sample workspace · Demo data',18,MUTED)
 k=s['kind']
 if k in ['hero','flow']:
  for j,item in enumerate(s['items']):
   x=674+(j%2)*558; y=385+(j//2)*198
   rect((x,y,x+526,y+166),BG,20, '#e4e9e5')
   rect((x+22,y+23,x+77,y+78),GREEN,16); txt(x+37,y+32,str(j+1),25,'white',True)
   wrapped(x+100,y+40,item,28,385,INK,True)
  txt(675,814,'CONNECTED RECORDS  /  CLEAR NEXT ACTIONS',18,GREEN,True)
 elif k=='table':
  cols=[675,1045,1495]; ys=390
  rect((664,374,1806,435),MINT,12)
  for x,t in zip(cols,s['headers']): txt(x,388,t,22,GREEN,True)
  for j,row in enumerate(s['rows']):
   y=455+j*86
   for col,(x,t) in enumerate(zip(cols,row)): wrapped(x,y,t,22,350 if col<2 else 290,INK,col==0)
   d.line((677,y+66,1780,y+66),fill='#e4e9e5',width=2)
 elif k=='invoice':
  rect((674,374,1108,808),BG,14,'#e4e9e5'); txt(705,400,'SUPPLIER INVOICE',24,INK,True)
  txt(705,455,'INV-DEMO-024',28,GREEN,True)
  for j,w in enumerate([300,235,280,190,300]): d.rounded_rectangle((705,525+j*37,705+w,537+j*37),5,fill='#d8e2dc')
  txt(705,741,'Source document',20,MUTED)
  for j,(label,value) in enumerate([('Invoice number','INV-DEMO-024'),('Invoice total','₹ 1,18,000'),('Field confidence','98% · Reviewable'),('Workflow status','Needs review')]):
   y=375+j*111; txt(1150,y,label,20,MUTED); txt(1150,y+34,value,28,GREEN if j>1 else INK,True)
 elif k=='board':
  for j,(head,route,truck,status) in enumerate([('PLANNED','Pune → Mumbai','MH 12 AB 2048','Driver assigned'),('IN TRANSIT','Nashik → Pune','MH 15 CD 3012','Pickup recorded'),('DELIVERED','Mumbai → Surat','MH 04 EF 6801','Proof received')]):
   x=674+j*376; rect((x,376,x+350,806),BG,18); txt(x+22,399,head,21,GREEN,True)
   rect((x+15,459,x+335,712),'white',16,'#e4e9e5'); txt(x+33,485,route,25,INK,True); txt(x+33,537,truck,22,MUTED); wrapped(x+33,610,status,22,270,GREEN)
 elif k=='mobile':
  rect((722,364,1012,842),INK,36); rect((737,397,997,816),BG,23)
  txt(759,425,'My trip',27,INK,True); txt(759,470,'Pune → Mumbai',20,MUTED)
  for j,t in enumerate(['Check in','Add receipt','Delivery proof','Sync updates']):
   rect((754,527+j*64,981,575+j*64),GREEN if j==3 else 'white',12); txt(773,538+j*64,t,20,'white' if j==3 else GREEN,True)
  for j,(h,b) in enumerate([('CAPTURE','Times, readings & evidence'),('KEEP MOVING','Save while offline'),('SYNC LATER','Upload when connected')]):
   y=405+j*137; txt(1090,y,h,20,GREEN,True); wrapped(1090,y+37,b,28,670,INK,True)
 elif k=='cost':
  for j,(lab,val) in enumerate([('Trip revenue','₹ 45,000'),('Recorded costs','₹ 32,500'),('Trip margin','₹ 12,500')]):
   x=674+j*377; rect((x,376,x+350,504),MINT if j==2 else BG,18); txt(x+23,395,lab,20,MUTED); txt(x+23,435,val,34,GREEN,True)
  for j,(lab,ratio,amt) in enumerate([('Fuel',.82,'₹ 18,000'),('Tolls & expenses',.4,'₹ 8,500'),('Driver costs',.28,'₹ 6,000')]):
   y=557+j*86; txt(676,y,lab,22,INK,True); rect((910,y+3,1575,y+28),'#e7eee9',12); rect((910,y+3,910+int(665*ratio),y+28),GREEN,12); txt(1610,y,amt,23,INK,True)
  txt(677,819,'Budget variance and mileage alerts support investigation.',20,MUTED)
 elif k=='ledger':
  rect((674,370,1803,474),MINT,18); txt(701,387,'OUTSTANDING BALANCE',18,GREEN,True); txt(701,415,'₹ 9,000',34,GREEN,True); txt(1310,411,'Sample monthly settlement',22,MUTED)
  for j,(label,value) in enumerate([('Opening balance','₹ 2,000'),('Earnings','+ ₹ 30,000'),('Advance recovery','− ₹ 2,000'),('Approved deduction','− ₹ 1,000'),('Payments recorded','− ₹ 20,000')]):
   y=506+j*62; txt(700,y,label,23,INK); txt(1505,y,value,24,GREEN,True); d.line((700,y+47,1775,y+47),fill='#e4e9e5',width=1)
 elif k=='report':
  txt(680,380,'TRIP COSTS BY PERIOD',19,GREEN,True)
  for j,h in enumerate([110,165,138,240,197,275]):
   x=700+j*88; rect((x,740-h,x+55,740),GREEN if j==5 else '#add3c2',9); txt(x,755,'P'+str(j+1),18,MUTED)
  for j,t in enumerate(['Operational reports','Tax & invoice review','Audit history','Export by date range']):
   y=398+j*100; rect((1300,y,1780,y+76),BG,14); txt(1324,y+21,t,25,INK,True)
 # Compact feature strip and the continuous 90-second timeline.
 x=70; y=920
 for t in s['tags']:
  width=int(d.textlength(t,font=font(20)))+32
  if x+width>1840: x=70; y+=48
  x+=chip(x,y,t)+12
 txt(70,1022,'KRIYOPAY  /  FINANCE & FLEET',17,MUTED,True)
 txt(1370,1022,'Illustrative screens · Sample data',17,MUTED)
 txt(1765,1018,f'{index+1:02d} / 15',19,GREEN,True)
 d.rectangle((0,1072,W,1080),fill='#e4e9e5')
 d.rectangle((0,1072,int(W*index/15),1080),fill=GREEN)
 return im

def prepare():
 (ROOT/'frames').mkdir(exist_ok=True); (ROOT/'audio').mkdir(exist_ok=True)
 for i in range(15): draw_scene(i).save(ROOT/'frames'/f'{i:02}.png')
 (ROOT/'scenes.json').write_text(json.dumps(SCENES,ensure_ascii=False,indent=2),encoding='utf-8')
 # Full transcript and an accurate disclosure travel with the client asset.
 lines=['# KriyoPay — 90-second product showcase','','Format: 1920 × 1080, 24 fps, 90 seconds, English narration and burned-in captions.','','This is an animated feature overview using illustrative screens and sample data, not a live product recording. Feature groups are summarized; this is not a detailed demonstration of every interaction. External integrations require configuration. Payment records and reconciliation do not imply execution of bank transfers.','']
 for i,s in enumerate(SCENES):
  lines += [f'## {i*6:02d}–{(i+1)*6:02d}s — {s["section"]}', '',s['voice'],'','Coverage: '+ '; '.join(s['items']+s['tags'])+'.','']
 (ROOT/'STORYBOARD.md').write_text('\n'.join(lines),encoding='utf-8')
 def stamp(t): return f'00:{t//60:02d}:{t%60:02d},000'
 (ROOT/'captions.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(i*6)} --> {stamp((i+1)*6)}\n{s["voice"]}' for i,s in enumerate(SCENES)),encoding='utf-8')
 print('Prepared 15 scene plates, narration script, captions and storyboard.')

def render():
 clips=ROOT/'clips'; clips.mkdir(exist_ok=True)
 for i,s in enumerate(SCENES):
  wav=ROOT/'audio'/f'{i:02}.wav'
  with wave.open(str(wav)) as audio: duration=audio.getnframes()/audio.getframerate()
  tempo=max(1,duration/5.65)
  # Soft fades and slow camera movement give the cards a restrained animated treatment.
  vf="scale=1960:1102,crop=1920:1080:x='20+10*sin(t/3)':y=10,fade=t=in:st=0:d=0.22,fade=t=out:st=5.78:d=0.22"
  # Captions are kept outside the product canvas in a dark lower third.
  caption_lines=textwrap.wrap(s['voice'],width=105)
  vf+=",drawbox=x=0:y=985:w=1920:h=87:color=0x172b27:t=fill"
  for line_no,line in enumerate(caption_lines):
   cap=ROOT/'frames'/f'{i:02}-{line_no}.txt'; cap.write_text(line,encoding='utf-8')
   vf+=f",drawtext=fontfile='C\\:/Windows/Fonts/segoeui.ttf':textfile='frames/{i:02}-{line_no}.txt':fontcolor=white:fontsize=25:x=(w-text_w)/2:y={997+line_no*35}"
  vf+=f",drawbox=x=0:y=1072:w={int(1920*(i+1)/15)}:h=8:color=0x166b55:t=fill"
  cmd=[FFMPEG,'-y','-loglevel','error','-loop','1','-framerate','24','-i',str(ROOT/'frames'/f'{i:02}.png'),'-i',str(wav),'-vf',vf,'-af',f'atempo={tempo:.5f},apad,atrim=0:6,afade=t=out:st=5.85:d=0.15','-t','6','-r','24','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',str(clips/f'{i:02}.mp4')]
  subprocess.run(cmd,cwd=ROOT,check=True); print(f'Rendered scene {i+1}/15',flush=True)
 listing=clips/'concat.txt'; listing.write_text('\n'.join(f"file '{i:02}.mp4'" for i in range(15)))
 subprocess.run([FFMPEG,'-y','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-t','90','-movflags','+faststart',str(ROOT/'KriyoPay-90-Second-Showcase.mp4')],check=True)
 print('Finished 90-second showcase.',flush=True)

if __name__=='__main__':
 if '--render' in sys.argv: render()
 else: prepare()
