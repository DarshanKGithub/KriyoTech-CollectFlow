"""Build the slower walkthrough from real UI captures and labeled feature cards."""
import json, math, subprocess, textwrap, wave
from pathlib import Path
from PIL import Image, ImageDraw
from build_demo import SCENES, draw_scene, font, FFMPEG, INK, GREEN, BG

BASE=Path(__file__).resolve().parent
OUT=BASE/'revised'
OUT.mkdir(exist_ok=True)
for name in ['frames','audio','clips']: (OUT/name).mkdir(exist_ok=True)

def live(title, image, voice, crop=None, note='ACTUAL PRODUCT · SAMPLE WORKFLOW'):
 return dict(title=title,image=image,voice=voice,crop=crop,note=note)

STEPS=[
 dict(card=0,voice='Welcome to KriyoPay. Let us take a slower look at how the product connects invoice processing, transport operations, and financial control.'),
 live('Your workspace, at a glance','01-overview.jpg','This is the actual KriyoPay workspace. The dashboard brings invoice activity, open exceptions, and pending approvals into one place.',crop=[0,0,1600,570]),
 live('1. Choose a sample invoice','DEMO-VIDEO-INVOICE.png','For this demonstration, we use a clearly marked sample invoice. It contains two tyre services, a taxable value of twelve thousand rupees, and a total of fourteen thousand, one hundred and sixty rupees.',note='SYNTHETIC INVOICE · NO PAYMENT DUE'),
 live('2. Upload the invoice','02-invoice-upload.jpg','Open Invoices and choose Upload invoice. Select the document. KriyoPay creates the invoice record and queues extraction automatically.',crop=[270,0,1600,250]),
 live('3. Extraction runs in the background','04-extracting.jpg','The status changes to Extracting. There is no separate extraction button to press after upload. Processing time depends on the document and the extraction provider.',crop=[270,0,1600,405]),
 live('4. Review the extracted result','05-extracted.jpg','Here is the extracted supplier, invoice number, date, and total. This recording needed one retry after a provider timeout. Waiting time has been shortened in this video.',crop=[270,0,1600,405]),
 live('5. Check the fields against the source','06-review-fields.jpg','Open Review to inspect the extracted fields and line items. Confidence is only a model estimate. Your team still checks the source document before proceeding.',crop=[415,154,1185,848]),
 live('6. Correct a field, then save','07-reviewed-tax.jpg','In this example, the line tax needs correction. We enter eighteen percent and two thousand, one hundred and sixty rupees, then save. Human review remains part of the workflow.',crop=[415,154,1185,848]),
 dict(card=3,voice='After review, compare the invoice with purchase orders and goods receipts. Vendor records, aliases, financial notes, and the vendor portal keep supporting information organized.'),
 dict(card=4,voice='Differences go into the exception workflow. Follow-up drafts, approval rules, and service-level reminders help the right person take the next action. Approval remains a human decision.'),
 live('7. Set up trucks and drivers','08-fleet-setup.jpg','Now let us move to transportation. Add each truck and driver once. For this walkthrough, we use clearly labeled demo records with no real driver contact details.'),
 live('8. Plan a transport trip','09-trip-form.jpg','Choose the truck and driver. Enter a trip reference, pickup location, delivery location, and starting odometer. A transport order can be linked when needed.'),
 live('9. Save and track the trip','10-trip-created.jpg','Save the trip to create an operational record. The trip list gives the team a place to open the journey, update its status, and follow the work.'),
 live('10. Start the journey','11-trip-started.jpg','When the vehicle leaves, start the trip. The status change is recorded in the product, so the operations team can see that the journey is in progress.'),
 live('11. Review trip details','12-trip-detail.jpg','The trip page keeps the route, driver, revenue, expenses, and follow-ups together. Delivery updates and supporting evidence help connect operations with finance.'),
 dict(card=7,voice='The phone-friendly driver view supports check-ins, odometer readings, receipts, and delivery proof. Drivers can save updates when connectivity is poor and sync them later.'),
 dict(card=8,voice='Review fuel spending, recorded expenses, and trip profitability. Budgets and mileage alerts help your team investigate unusual costs and missing information.'),
 dict(card=9,voice='Driver finance tracks earnings, advances, recoveries, approved deductions, and payments. Monthly, per-trip, and per-kilometre policies support a clear settlement balance and ledger export.'),
 dict(card=10,voice='Connect completed trips with customer invoices and collections. Track outstanding amounts and keep the transport context available during payment review.'),
 dict(card=5,voice='Record supplier payments, customer collections, and driver payments. Import bank transactions and review suggested matches. Reconciliation records do not execute a bank transfer.'),
 dict(card=11,voice='Use reports to review trip costs, salary balances, invoice exceptions, and payment status. Export by date range, review tax information, and follow the audit history.'),
 dict(card=12,voice='Configure email intake, API connections, webhooks, and WhatsApp workflows. Reminder preferences control recipients, channels, and escalation. External integrations require setup.'),
 dict(card=13,voice='Roles control who can view, edit, approve, pay, and export. Administrators manage companies, feature access, plans, subscriptions, usage, and workspace settings.'),
 dict(card=14,voice='That is KriyoPay. A connected workspace for invoices, transportation, and financial visibility. The next step is a guided walkthrough using the workflows that matter most to your team.'),
]

def prepare():
 for i,s in enumerate(STEPS):
  if 'card' in s:
   im=draw_scene(s['card'])
  else:
   p=BASE/'live'/s['image']
   if not p.exists(): continue
   source=Image.open(p).convert('RGB')
   if s.get('crop'): source=source.crop(s['crop'])
   im=Image.new('RGB',(1920,1080),BG); d=ImageDraw.Draw(im)
   d.text((68,28),'KriyoPay',font=font(32,True),fill=GREEN)
   d.text((330,30),s['title'],font=font(31,True),fill=INK)
   d.text((70,940),s['note'],font=font(20,True),fill=GREEN)
   source.thumbnail((1780,790),Image.Resampling.LANCZOS)
   x=(1920-source.width)//2; y=118+(790-source.height)//2
   im.paste(source,(x,y))
   d.rounded_rectangle((x-2,y-2,x+source.width+2,y+source.height+2),radius=6,outline='#cbd8cf',width=2)
  im.save(OUT/'frames'/f'{i:02}.png')
 (OUT/'scenes.json').write_text(json.dumps(STEPS,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Prepared slower narration and available workflow scenes.',flush=True)

def render():
 elapsed=0; story=['# KriyoPay — slower product walkthrough','','Actual UI screen captures show the sample invoice upload, extraction, review, and sample trip workflow. These are edited sequences of real workflow states, not a continuous screen recording. Feature-summary cards are labeled illustrative. No real payment was made. One invoice extraction retry was needed after a provider timeout. Waiting time is shortened.','']; subs=[]
 def ts(t):
  ms=round(t*1000); return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
 for i,s in enumerate(STEPS):
  path=OUT/'frames'/f'{i:02}.png'
  if not path.exists(): raise RuntimeError('Missing real capture for '+s['title'])
  wav=OUT/'audio'/f'{i:02}.wav'
  with wave.open(str(wav)) as w: speech=w.getnframes()/w.getframerate()
  duration=math.ceil((speech+1.8)*24)/24
  lines=textwrap.wrap(s['voice'],103)
  vf='fade=t=in:st=0:d=0.25,drawbox=x=0:y=982:w=1920:h=98:color=0x172b27:t=fill'
  # One or two short caption sentences at a time, aligned across the narration.
  chunks=textwrap.wrap(s['voice'],170)
  for ci,chunk in enumerate(chunks):
   start=.5+speech*ci/len(chunks); end=.5+speech*(ci+1)/len(chunks)
   if ci==len(chunks)-1: end=duration
   for li,line in enumerate(textwrap.wrap(chunk,103)):
    fn=f'{i:02}-{ci}-{li}.txt'; (OUT/'frames'/fn).write_text(line,encoding='utf-8')
    vf+=f",drawtext=fontfile='C\\:/Windows/Fonts/segoeui.ttf':textfile='frames/{fn}':fontcolor=white:fontsize=26:x=(w-text_w)/2:y={997+li*36}:enable='between(t,{start:.3f},{end:.3f})'"
   subs.append(f'{len(subs)+1}\n{ts(elapsed+start)} --> {ts(elapsed+end)}\n{chunk}')
  vf+=f',fade=t=out:st={duration-.25}:d=0.25'
  subprocess.run([FFMPEG,'-y','-loglevel','error','-loop','1','-framerate','24','-i',str(path),'-i',str(wav),'-vf',vf,'-af','adelay=500|500,volume=1.5,apad','-t',str(duration),'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2',str(OUT/'clips'/f'{i:02}.mp4')],cwd=OUT,check=True)
  title=s.get('title',SCENES[s.get('card',0)]['section']); story += [f'## {ts(elapsed)} — {title}','',s['voice'],'']
  elapsed+=duration; print(f'Rendered {i+1}/{len(STEPS)}; timeline {elapsed:.1f}s',flush=True)
 listing=OUT/'clips'/'concat.txt'; listing.write_text('\n'.join(f"file '{i:02}.mp4'" for i in range(len(STEPS))))
 subprocess.run([FFMPEG,'-y','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(OUT/'KriyoPay-Slow-Product-Walkthrough.mp4')],check=True)
 (OUT/'STORYBOARD.md').write_text('\n'.join(story),encoding='utf-8')
 (OUT/'captions.srt').write_text('\n\n'.join(subs),encoding='utf-8')
 print(f'Done. Duration approximately {elapsed/60:.2f} minutes.',flush=True)

if __name__=='__main__':
 import sys
 render() if '--render' in sys.argv else prepare()
