from pathlib import Path
import json
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output' / 'pdf' / 'KriyoPay_Pricing_and_Features.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
for name, file in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf'),('Arial-Italic','ariali.ttf')]:
    pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/' + file))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold',italic='Arial-Italic',boldItalic='Arial-Bold')
assert 0x20B9 in pdfmetrics.getFont('Arial').face.charToGlyph
W,H=A4
M=42
CW=W-2*M
INK=HexColor('#172b27'); GREEN=HexColor('#166b55'); MINT=HexColor('#e5f3ed')
BG=HexColor('#f5f7f5'); LINE=HexColor('#dce5df'); GRAY=HexColor('#52665f'); GOLD=HexColor('#b97b25')
C=canvas.Canvas(str(OUT),pagesize=A4)
C.setTitle('KriyoPay | Pricing & Features | Client Proposal')
C.setAuthor('KriyoPay')
C.setSubject('Basic, Pro and Enterprise pricing, product features and implementation scope')
C.setKeywords('KriyoPay, invoice automation, accounts payable, pricing, Tally, fleet')
checks=[]

def box(x,y,w,h,fill=BG,stroke=None,r=10):
    C.setFillColor(fill)
    C.setStrokeColor(stroke or fill)
    C.roundRect(x,H-y-h,w,h,r,stroke=bool(stroke),fill=1)

def txt(s,x,y,size=10,bold=False,color=INK):
    C.setFont('Arial-Bold' if bold else 'Arial',size)
    C.setFillColor(color)
    C.drawString(x,H-y-size,s)

def para(s,x,y,w,size=10,leading=None,color=GRAY,bold=False):
    style=ParagraphStyle('p',fontName='Arial-Bold' if bold else 'Arial',fontSize=size,
                         leading=leading or size*1.42,textColor=color,spaceAfter=0)
    p=Paragraph(s,style)
    _,h=p.wrap(w,H)
    if y+h>H-55:
        raise ValueError(f'Content overflows at {y+h}: {s[:90]}')
    p.drawOn(C,x,H-y-h)
    checks.append({'page':C.getPageNumber(),'y':round(y,1),'bottom':round(y+h,1),'text':s[:75]})
    return y+h

def rule(y):
    C.setStrokeColor(LINE);C.setLineWidth(.7);C.line(M,H-y,W-M,H-y)

def footer(n):
    rule(H-43)
    txt('KriyoPay  |  Commercial proposal  |  23 October 2026',M,H-32,7.2,color=GRAY)
    C.setFont('Arial',7.2);C.drawRightString(W-M,25,f'{n:02d} / 08')

def brand(y=25):
    box(M,y,22,22,GREEN,r=6)
    txt('K',M+5,y+1,15,True,white)
    txt('KriyoPay',M+31,y-1,20,True)

def page(n,kicker,title,sub):
    C.setFillColor(white);C.rect(0,0,W,H,stroke=0,fill=1)
    brand()
    txt(kicker.upper(),M,81,8.5,True,GREEN)
    para(title,M,101,CW,26,30,INK,True)
    para(sub,M,143,CW,10.2,14.4)
    footer(n)

def bullets(items,x,y,w,size=10,gap=9):
    for head,body in items:
        box(x,y+5,4,4,GREEN,r=1)
        y=para(f'<b>{escape(head)}</b> {escape(body)}',x+13,y,w-13,size,color=INK)+gap
    return y

def note(s,y,fill=MINT):
    style=ParagraphStyle('note',fontName='Arial',fontSize=9,leading=12.7,textColor=INK)
    p=Paragraph(s,style);_,h=p.wrap(CW-26,H)
    box(M,y,CW,h+23,fill)
    p.drawOn(C,M+13,H-y-11-h)
    return y+h+23

def table(rows,y,widths,fs=9.2,rowpad=10):
    style=ParagraphStyle('cell',fontName='Arial',fontSize=fs,leading=fs*1.3,textColor=INK)
    head=ParagraphStyle('head',parent=style,fontName='Arial-Bold',textColor=white)
    data=[[Paragraph(str(cell),head if i==0 else style) for cell in row] for i,row in enumerate(rows)]
    t=Table(data,colWidths=widths,hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),GREEN),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),9),
        ('TOPPADDING',(0,0),(-1,-1),rowpad),('BOTTOMPADDING',(0,0),(-1,-1),rowpad),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[white,BG]),
        ('LINEBELOW',(0,1),(-1,-1),.35,LINE),
    ]))
    _,h=t.wrap(CW,H)
    if y+h>H-57:raise ValueError(f'Table overflow on page {C.getPageNumber()}: {y+h}')
    t.drawOn(C,M,H-y-h)
    return y+h

# 01 - cover
C.setFillColor(white);C.rect(0,0,W,H,fill=1,stroke=0)
brand(35)
txt('INVOICE-TO-PAYMENT CONTROL FOR INDIAN BUSINESSES',M,101,8.5,True,GREEN)
para('Every invoice.<br/>A clearer path to approval.',M,130,CW,35,41,INK,True)
para('Capture supplier invoices, match purchases and receipts, route approvals and prepare a reviewed accounting handoff.',M,232,445,12,18)
box(M,303,CW,192,GREEN,r=14)
txt('FROM DOCUMENT TO DECISION',M+20,323,8,True,HexColor('#b9e6d2'))
steps=[('01','Capture'),('02','Match'),('03','Approve'),('04','Export')]
for i,(num,label) in enumerate(steps):
    x=M+20+i*121
    box(x,359,29,29,HexColor('#34816b'),r=8)
    txt(num,x+7,365,10,True,white)
    txt(label,x,401,15,True,white)
    if i<3:
        C.setStrokeColor(HexColor('#7cb5a0'));C.line(x+42,H-374,x+109,H-374)
para('Record actual payments and retain the review trail throughout the process.',M+20,449,CW-40,9.8,14,white)
for i,(h,b) in enumerate([
    ('CONTROL','Compare invoices with purchase orders and goods receipts.'),
    ('COLLABORATION','Bring finance, approvers and suppliers into a shared workflow.'),
    ('CONNECTION','Prepare reviewed exports for your accounting system.')]):
    x=M+i*(CW+15)/3
    txt(h,x,529,8.3,True,GREEN)
    para(b,x,551,(CW-30)/3,10.2,15)
rule(640)
txt('Pricing & features',M,662,20,True)
para('Basic  ₹2,999/month     Pro  ₹7,999/month<br/>Enterprise  from ₹19,999/month',M,697,CW,12,19,INK,True)
para('Client discussion proposal. Proposed inclusions and rates are subject to written scope and availability confirmation. Applicable taxes are additional.',M,754,CW,8.3,11.6)
footer(1);C.showPage()

# 02 - pricing
page(2,'Plans & pricing','Choose the capacity your team needs.','Three proposed plans. A complete core workflow, with more automation and integration depth as you grow.')
gap=12;cardw=(CW-2*gap)/3
plans=[('BASIC','₹2,999','₹29,990 / year','250 invoices / month','5 internal users','Tally CSV export','For small finance teams'),
       ('PRO','₹7,999','₹79,990 / year','1,000 invoices / month','15 internal users','1 accounting connector','For growing finance teams'),
       ('ENTERPRISE','₹19,999','From ₹1,99,990 / year','3,000 invoices / month','40 internal users','Up to 2 connectors','For integration-led teams')]
for i,(name,price,annual,inv,seats,conn,best) in enumerate(plans):
    x=M+i*(cardw+gap);dark=i==1;fill=GREEN if dark else BG;fg=white if dark else INK
    box(x,200,cardw,279,fill,stroke=None if dark else LINE)
    txt(name,x+14,219,10,True,white if dark else GREEN)
    if i==2:txt('FROM',x+14,244,7,True,GRAY)
    txt(price,x+14,258,25,True,fg)
    txt('/ month',x+14,293,9,color=HexColor('#cae7db') if dark else GRAY)
    para(annual,x+14,320,cardw-28,9.4,13,fg,True)
    for j,s in enumerate([inv,seats,conn]):para(s,x+14,359+j*24,cardw-28,9.2,12,fg)
    para(best,x+14,443,cardw-28,8.1,11,HexColor('#cae7db') if dark else GRAY)
y=table([
    ['Commercial detail','Basic','Pro','Enterprise'],
    ['Standard onboarding','Included','₹4,999 once','From ₹19,999 once'],
    ['Baseline company scope','1 workspace','1 workspace','1 workspace; more quoted'],
    ['First-response target*','2 business days','1 business day','4 business hours, critical incidents'],
],505,[CW*.34,CW*.21,CW*.21,CW*.24],8.5,10)
note('<b>Annual value:</b> pay for 10 months and receive 12 months of subscription access. Invoice allowances still reset monthly. Enterprise figures are starting allocations; final scope is quoted.',y+19)
para('* Business hours: Monday-Friday, 9:30am-6pm IST, excluding published holidays. Response targets are not resolution guarantees. Accounting connections require setup and customer acceptance. All prices exclude applicable taxes.',M,744,CW,8.1,11.5)
C.showPage()

# 03 - comparison
page(3,'Feature comparison','See what each plan includes.','Proposed entitlements. Connection-dependent capabilities are activated after configuration and acceptance.')
rows=[['Capability','Basic','Pro','Enterprise'],
['Upload + reviewed AI extraction','Included','Included','Included'],
['Supplier records + supporting files','Included','Included','Included'],
['Purchase orders + partial GRNs','Included','Included','Included'],
['Invoice / PO / receipt matching','Included','Included','Included'],
['Duplicate screening + exceptions','Included','Included','Included'],
['Multi-level approvals + activity history','Included','Included','Included'],
['Configured email / Gmail intake','Included','Included','Included'],
['Vendor portal + questions','Included','Included','Included'],
['Payment recording + partial payments','Included','Included','Included'],
['Credit / debit notes','Included','Included','Included'],
['Standard reports + Tally CSV','Included','Included','Included'],
['Custom fields + supported bulk actions','-','Included','Included'],
['Eligible rule-based auto-approval','-','Validated rules','Validated rules'],
['Statement reconciliation, CSV / XLSX','-','Exact matching','Exact matching'],
['Tax checks + month-end checklist','-','Included','Included'],
['Reviewed Tally accounting XML','-','Included','Included'],
['Standard accounting connections','CSV only','1 connector','Up to 2'],
['Read-only API + supported webhooks','-','Included','Included'],
['Available advanced operational reports','-','Included','Included'],
['Fleet & Trips module','-','Optional add-on','25 vehicles / 500 trips'],
['Named implementation contact','-','-','Included'],
['Quarterly adoption review','-','-','Included']]
y=table(rows,194,[CW*.49,CW*.15,CW*.17,CW*.19],8.1,5.5)
para('GRN = goods receipt note. AI results require human review. API coverage is read-only; webhooks cover supported events. Tax checks screen format/arithmetic and do not verify government records or file returns.',M,y+17,CW,8.2,11.5)
C.showPage()

# 04 - workflow detail
page(4,'Basic & Pro in practice','A useful workflow at every stage.','Give people a clear next action, from a new supplier document to an approved accounting export.')
col=(CW-26)/2
box(M,195,col,37,MINT);box(M+col+26,195,col,37,GREEN)
txt('BASIC  |  Control daily invoices',M+12,205,10.5,True,GREEN)
txt('PRO  |  Scale the finance workflow',M+col+38,205,10.5,True,white)
y1=bullets([
('Capture with review.','Upload documents or use configured intake. Check extracted values before relying on them.'),
('Match what was received.','Compare the invoice, purchase order and partial goods receipts. Resolve quantity or amount differences.'),
('Route decisions.','Use supported multi-level approvals, rejection and correction steps. Preserve the activity history.'),
('Work with suppliers.','Receive portal submissions and resolve questions around invoice information.'),
('Track settlement.','Record payment references, partial payments and remaining balances.'),
('Prepare the handoff.','Export reviewed Tally-ready CSV with configured ledger mappings.')],M,251,col,9.6,13)
y2=bullets([
('Handle more work together.','Process larger invoice volumes with more users, custom fields and supported bulk actions.'),
('Apply supported rules.','Use eligible auto-approval only after rules and financial controls are validated.'),
('Reconcile statements.','Import mapped CSV/XLSX statements and review exact amount matches against recorded transactions.'),
('Review month end.','Use operational tax flags, the review checklist and available reports to focus follow-up work.'),
('Connect accounting.','Add one supported TallyPrime, ERPNext or Zoho Books connection after acceptance testing.'),
('Share supported data.','Use read-only API access and signed outgoing webhooks within verified coverage.')],M+col+26,251,col,9.6,13)
y=max(y1,y2)+15
note('<b>Example:</b> a supplier invoices 100 units, but only 80 are received. The matching workflow highlights the difference so the team can investigate and record a review decision before proceeding.',y)
para('Configured Gmail intake is bounded and read-only. Vendor portal access uses controlled links. Financial exports create accounting records; payment recording does not initiate a bank transfer.',M,742,CW,8.2,11.5)
C.showPage()

# 05 - integrations
page(5,'Enterprise & accounting','Connect with an acceptance plan.','Map the customer environment, test a representative workflow and review outcomes before activating financial writes.')
y=bullets([
('Capacity for larger teams.','Start with 3,000 invoices and 40 users monthly, then agree a larger allocation if needed.'),
('Two standard connections.','Configure up to two supported accounting connections for the baseline company scope.'),
('Structured implementation.','Include a mapping workshop, acceptance checklist, training and an implementation contact.'),
('Reviewable exchange.','Use import staging, approved export snapshots, sync history and conflict handling within supported coverage.')],M,194,CW,10,9)
y=table([
['System','Supported scope and setup considerations'],
['TallyPrime','Reviewed CSV/XML and supported accounting reads/writes. Customer Tally endpoint and ledgers must be configured. Inventory PO/receipt writes are outside current coverage.'],
['ERPNext','Supported imports and outbound draft documents. Validate company, item, account and tax mappings. Withholding export limitations apply.'],
['Zoho Books','Supported vendor, PO, bill and payment records. Goods receipts use a separate Zoho Inventory connection. Withholding export limitations apply.'],
['Dynamics 365 Finance','Available for separately scoped discovery and validation. Customer entities, dimensions, journals and metadata determine implementation effort.'],
],y+9,[CW*.23,CW*.77],9.2,11)
note('<b>Included connection does not mean universal two-way sync.</b> Final resource coverage, credentials, accounting mappings and any extra implementation work are agreed in writing. The customer supplies third-party licenses and access.',y+19)
para('Existing posted financial records are not silently overwritten. An uncertain remote write requires reconciliation before another attempt. Additional legal entities, consolidated reporting and bespoke integration work are separate scopes.',M,736,CW,8.5,12)
C.showPage()

# 06 - fleet
page(6,'Fleet & Trips','Bring trip operations into financial view.','An optional transport workflow for tracking trip revenue, reviewed costs, driver earnings and collections.')
box(M,195,CW,89,GREEN)
txt('INCLUDED WITH ENTERPRISE',M+17,211,9,True,HexColor('#c9e8dc'))
txt('25 active vehicles  |  500 new trips / month',M+17,236,18,True,white)
para('Pro add-on: ₹2,999 / month for the same starting allowance.',M+17,263,CW-34,9,12,white)
col=(CW-24)/2
y1=bullets([
('Vehicle and driver records.','Maintain the operational directory and supported assignments.'),
('Trip milestones.','Track transport orders, dispatch progress and delivery proof.'),
('Reviewed trip costs.','Capture fuel, toll, repair and other expense evidence for review.'),
('Trip performance.','Review operational margin reports using recorded income and approved costs.')],M,310,col,10,15)
y2=bullets([
('Driver earnings.','Apply supported per-trip or per-kilometre pay policies.'),
('Advances and recovery.','Review advances, recoveries and driver settlement balances.'),
('Customer collections.','Track transport customer invoices, receipts and outstanding amounts.'),
('Follow-ups.','Keep missing documents and unresolved settlement work visible.')],M+col+24,310,col,10,15)
y=max(y1,y2)+15
note('<b>Separate financial views:</b> transport customer receivables and driver settlements remain distinct from supplier accounts payable. Supplier bills consume the AP allowance; new trips consume the fleet allowance.',y)
txt('Scope to agree before activation',M,677,12,True)
para('The fleet module and usage allowances require acceptance and configuration. GPS hardware, live vehicle tracking, route optimization, statutory payroll and bank transfer execution are outside this offer. Larger fleets and trip volumes are quoted.',M,703,CW,9.4,14)
C.showPage()

# 07 - add-ons
page(7,'Commercial details','Clear allowances. Predictable expansion.','Choose capacity explicitly as your business grows. Additional scope is confirmed before purchase.')
y=table([
['Add-on','Proposed charge','Allowance / basis'],
['Basic invoice pack','₹999','100 additional invoices'],
['Pro invoice pack','₹2,999','500 additional invoices'],
['Enterprise invoice pack','₹4,999','1,000 additional invoices'],
['Additional internal user','₹199 / month','Per named user; capacity subject to plan'],
['Fleet & Trips on Pro','₹2,999 / month','25 active vehicles / 500 new trips'],
['Migration, extra entities or ERP work','Written quote','Scope agreed after discovery'],
['WhatsApp intake','Separate quote','Provider, setup and usage acceptance'],
],195,[CW*.36,CW*.24,CW*.40],9.2,11)
txt('How usage works',M,y+25,15,True)
y=bullets([
('Invoice allowance.','One distinct accepted supplier invoice consumes one unit. Failed uploads, rejected duplicates and field corrections do not consume another unit.'),
('AI allowance.','One extraction of up to five source pages is included per invoice. Platform-failed retries do not consume another allowance. Larger documents and user-requested re-extractions need agreed pricing.'),
('Monthly reset.','Invoice packs apply to the subscription month and do not roll over. Annual plans still receive monthly capacity.'),
('User seats.','Owners, finance users, approvers and auditors count as internal users. Vendor portal identities do not consume internal seats.'),
('Additional limits.','Storage, retention, file-size, API and webhook allowances are specified in the final service schedule; no unlimited-use promise is implied.')],M,y+55,CW,9.5,8)
note('All displayed rates are proposed and exclude applicable taxes. Invoice capacity purchases are explicit. Additional companies, third-party licenses, bespoke work and dedicated infrastructure are separately scoped.',y+11)
C.showPage()

# 08 - onboarding & close
page(8,'Your next step','Start with your real invoice workflow.','A focused demonstration and a representative pilot establish scope before a production rollout.')
timeline=[('01','Discover','Confirm monthly volumes, users, legal entities, approval steps and accounting systems.'),
          ('02','Configure','Prepare supplier data, matching settings, roles, intake and agreed accounting mappings.'),
          ('03','Validate','Walk through representative invoices, partial receipts, exceptions, approvals and exports.'),
          ('04','Activate','Confirm written scope and readiness, train the team and activate the agreed package.')]
for i,(num,h,b) in enumerate(timeline):
    y=194+i*70
    box(M,y,31,31,MINT,r=8);txt(num,M+8,y+7,11,True,GREEN)
    txt(h,M+46,y-1,13,True)
    para(b,M+46,y+22,CW-46,9.6,13.5)
txt('Confirm in the final proposal',M,492,15,True)
y=bullets([
('Commercial scope.','Plan, allowances, onboarding, integrations, support hours, taxes and third-party charges.'),
('Data and service terms.','Storage/retention, security and deployment readiness, cancellation, renewal, refunds and export arrangements.'),
('Feature acceptance.','Proposed packaging is not a declaration that every capability is available in production. Connection and fleet activation require validation.')],M,522,CW,9.5,8)
para('SSO, consolidated multi-company reporting, verified GST checks, advanced bank matching and dedicated hosting are future or separately scoped options unless expressly confirmed. Operational tax checks do not constitute statutory filings.',M,y+4,CW,8.8,12.5)
box(M,706,CW,65,GREEN)
txt('Let\'s map KriyoPay to your business.',M+16,719,18,True,white)
para('Ask your KriyoPay representative for a workflow demonstration and a written proposal.',M+16,749,CW-32,9,12,white)
C.showPage();C.save()

reader=PdfReader(OUT)
assert len(reader.pages)==8, len(reader.pages)
full='\n'.join(p.extract_text() for p in reader.pages)
for s in ['₹2,999','₹7,999','₹19,999','₹29,990','₹79,990','₹1,99,990','3,000','250']:
    assert s in full, s
assert '\u25a0' not in full
(ROOT/'tmp'/'pdfs'/'layout_checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
(ROOT/'tmp'/'pdfs'/'brochure_text.txt').write_text(full,encoding='utf-8')
print(json.dumps({'pdf':str(OUT),'pages':len(reader.pages),'bytes':OUT.stat().st_size,'text_checks':'passed','max_paragraph_bottom':max(x['bottom'] for x in checks)}))
