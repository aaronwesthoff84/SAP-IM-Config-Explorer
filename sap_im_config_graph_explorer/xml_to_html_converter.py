#!/usr/bin/env python3
"""
SAP Incentive Management XML to HTML Transformer
Converts SAP Incentive Management plan XML to HTML.
Usage: python sap_im_transformer.py input.xml [output.html] [--variant A|B]
"""
import sys, html as html_mod
from xml.etree import ElementTree as ET

TYPE_LABELS = {
    "DIRECT_TRANSACTION_CREDIT": "Direct Credit", "ROLLUP_TRANSACTION_CREDIT": "Rolled Credit",
    "PRIMARY_MEASUREMENT": "Primary Measurement", "SECONDARY_MEASUREMENT": "Secondary Measurement",
    "BULK_COMMISSION": "Incentive", "COMMISSION": "Commission",
    "DEPOSIT": "Deposit", "DETAIL_DEPOSIT": "Detailed Deposit",
}
TYPE_HEADING = {
    "DIRECT_TRANSACTION_CREDIT": "Credit Rule", "ROLLUP_TRANSACTION_CREDIT": "Credit Rule",
    "PRIMARY_MEASUREMENT": "Measurement Rule", "SECONDARY_MEASUREMENT": "Measurement Rule",
    "BULK_COMMISSION": "Incentive Rule", "COMMISSION": "Incentive Rule",
    "DEPOSIT": "Deposit Rule", "DETAIL_DEPOSIT": "Detailed Deposit Rule",
}
TYPE_CATEGORY = {
    "DIRECT_TRANSACTION_CREDIT": "credit", "ROLLUP_TRANSACTION_CREDIT": "credit",
    "PRIMARY_MEASUREMENT": "measurement", "SECONDARY_MEASUREMENT": "measurement",
    "BULK_COMMISSION": "incentive", "COMMISSION": "incentive",
    "DEPOSIT": "deposit", "DETAIL_DEPOSIT": "detail_deposit",
}
ACTION_LABELS = {
    "DIRECT_TRANSACTION_CREDIT_ALLGAs": "Create Credit (GA)",
    "COMMISSION_USING_FLATRATE_GAS": "Create Commission (GA)",
    "COMMISSION_USING_RATETABLE_GAS": "Create Commission Using Rate Table (GA)",
    "INCENTIVE_GAS": "Create Incentive (GA)", "INCENTIVE_STRAIGHT_GAS": "Create Incentive (GA)",
    "INCENTIVE_USING_RATETABLE_BASE_ON_MEAS_GAS": "Create Incentive (GA)",
    "PRIMARY_MEASUREMENT": "Create Primary Measurement",
    "SECONDARY_MEASUREMENT_GAS": "Create Secondary Measurement (GA)",
}
OP_SYMBOLS = {
    "ADD_OPERATOR": "+", "SUBTRACT_OPERATOR": "-", "MULTIPLY_OPERATOR": "*", "DIVISION_OPERATOR": "/",
    "ISEQUALTO_OPERATOR": "=", "NOTEQUALTO_OPERATOR": "!=",
    "GREATERTHAN_OPERATOR": ">", "GREATERTHANEQUALTO_OPERATOR": ">=",
    "LESSTHAN_OPERATOR": "<", "LESSTHANEQUALTO_OPERATOR": "<=",
    "AND_OPERATOR": " AND ", "OR_OPERATOR": " OR ", "NOT_BOOLEAN_OPERATOR": "NOT",
}
FUNC_DISP = {
    "isNull": "Is Null", "MDLT_FUNCTION": "Lookup In Table",
    "Convert Null To Value": "Convert Null To Value", "Convert String To Value": "Convert String To Value",
    "VALUE_TO_STRING": "Value To String", "_toUpperCase": "To Upper Case",
    "_lastDate": "Last Day of Month", "ifThenElse": "If Then Else",
    "MAX": "MAX", "Date Range": "Date Range",
}
SECTION_ORDER = [
    ("plans","Plans","PLAN_SET"), ("mdlts","Lookup Tables","MD_LOOKUP_TABLE_SET"),
    ("fixedvalues","Fixed Values","FIXED_VALUE_SET"), ("quotas","Quotas","QUOTA_SET"),
    ("formulas","Formulas","FORMULA_SET"), ("territories","Territories","TERRITORY_SET"),
    ("variables","Variables","VARIABLE_SET"),
]
CSS = """
            <!--
            .Body   { background-color: #F3F3F6; margin: 20; link: #FF6600; alink: #FF9900; vlink: #FF6600; font-family: Arial,Helvetica,sans-serif; font-size: 9pt; font-weight: 300; color: #666677; text-decoration: none; }
            .PageTitle    { font-family: Arial,Helvetica,sans-serif; font-size: 14pt; font-weight: 700; color: #003399;}
            .SectionTitle    { background-color: #003399; border: solid 1px #2255BB; padding: 3px;  font-family: Arial,Helvetica,sans-serif; font-size: 12pt; font-weight: 700; color: #FFFFFF;}
            .SubSectionTitle    { background-color: #3399CC; border: solid 1px #1177AA; padding: 3px;  font-family: Arial,Helvetica,sans-serif; font-size: 12pt; font-weight: 700; color: #FFFFFF;}
            .ComponentObjectTitle    { background-color: #800000; border: solid 1px #AAC5D5; padding: 3px;  font-family: Arial,Helvetica,sans-serif; font-size: 11pt; font-weight: 700; color: #008080;}
            .ObjectTitle    { background-color: #C3DFF0; border: solid 1px #AAC5D5; padding: 3px;  font-family: Arial,Helvetica,sans-serif; font-size: 10pt; font-weight: 700; color: #003399;}
            .ContentTitle    { font-family: Arial,Helvetica,sans-serif; font-size: 9pt; font-weight: 700; color: #003399;}
            .Link          { font-family: Arial,Helvetica,sans-serif !important; font-size: 9pt; font-weight: 300; color: #0088BB; text-decoration: none; }
            .Link:hover    { color: #005588 !important; text-decoration: none; }
            .LabelCell        { font-family: Arial,Helvetica,Sans-Serif; font-size: 9pt; color: #777777; font-weight: 300; padding: 6px 6px 1px 0px; vertical-align: top; text-align: right; }
            .Copyright        { font-family: Arial,Helvetica,Sans-Serif; font-size: 7pt; color: #777777; font-weight: 300; padding: 6px 6px 1px 0px; vertical-align: top; text-align: center; }
            .Value    { font-family: Arial,Helvetica,Sans-Serif; font-size: 9pt; color: #003399; font-weight: 300; padding: 6px 6px 4px 3px; vertical-align: top; }
            .ContentBox    {  background-color: #FFFFFF; border: solid 1px #EEEEEE; padding: 8px;  font-family: Arial,Helvetica,sans-serif; font-size: 9pt; font-weight: 300; color: #666666; }
            .ListTable    { background-color: #FFFFFF; }
            .ListHeaderCell    { background-color: #F3F3F6; border: 1px solid #DDDDDD; padding: 1px 3px 1px 3px; font-family: Arial,Helvetica,Sans-Serif; font-size: 9pt; color: #777777; text-decoration: none; vertical-align: bottom; }
            .ListCell    { padding: 2px 4px 2px 4px; font-family: Arial,Helvetica,Sans-Serif; font-size: 9pt; color: #003399; vertical-align: top; border-bottom: 1px solid #EEEEEE;}
            .FunctionParameter { font-family: Arial,Helvetica,Sans-Serif; font-size: 9pt; color: #666666; vertical-align: top; padding-left: 25px }
            .FunctionParameterLineNumber {font-family: Verdana,Arial,Helvetica,Sans-Serif; font-size: 7pt; color: #999999; vertical-align: top; text-align:right; padding-left:2px }
            -->
        """
SAP_LOGO_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

class XErr(Exception):
    def __init__(self, msg, **kw):
        p = [msg]
        for k,v in kw.items():
            if v: p.append(f"{k}: {v}")
        super().__init__(" | ".join(p))

def esc(t):
    if t is None: return ""
    return html_mod.escape(str(t))
def scd(t):
    if not t: return ""
    t = t.strip()
    if t.startswith("<![CDATA[") and t.endswith("]]>"): return t[9:-3]
    return t
def gtxt(e):
    if e is None: return ""
    return scd(e.text or "")
def fd(d):
    return d if d else ""
def drange(s,e):
    s, e = fd(s), fd(e)
    if not s and not e: return ""
    if not s: return e
    if not e or "2200" in e or "2099" in e: return f"{s} - End of Time"
    return f"{s} - {e}"

def render_ref(elem):
    nm = elem.get("NAME","")
    per = elem.get("PERIOD_TYPE", elem.get("OUTPUT_REFERENCE_PERIOD_TYPE", "month"))
    off = elem.get("PERIOD_OFFSET","0")
    rid = elem.get("ID","")
    tag = elem.tag.lower() if hasattr(elem,'tag') else ""
    if rid == "STRING_FORMULA_REF": return f'<a class="Link" href="#{nm}-formula">{esc(nm)}</a>'
    if "variable" in tag: return f'<a class="Link" href="#{nm}-var">{esc(nm)}</a>'
    if "territory" in tag: return f'<a class="Link" href="#{nm}-terr">{esc(nm)}</a>'
    if "ratetable" in tag: return f'<a class="Link" href="#{nm}-rt">{esc(nm)}</a>'
    if "mdlt" in tag: return f'<a class="Link" href="#{nm}-mdlt">{esc(nm)}</a>'
    return f'<i>{esc(nm)}:{per}-{off}<sub>[From Current Position:EXPECT_ONE]</sub></i>'

def render_oref(elem):
    nm = elem.get("NAME",""); per = elem.get("PERIOD_TYPE","month"); ut = elem.get("UNIT_TYPE","")
    return f"<b>[{esc(nm)}, {per}{', ' + ut if ut else ''}]</b>"

def _rop(elem, depth=0):
    if elem is None: return ""
    tag = elem.tag.lower() if hasattr(elem,'tag') else ""
    if tag=="parameter_list": return ""
    if "_operator" in tag: return _r_op(elem, depth)
    if tag=="function": return _r_func(elem, depth)
    if tag=="event_type_expression": return _r_evtype(elem, depth)
    if any(x in tag for x in ["measurement_ref","incentive_ref","rule_element_ref"]): return render_ref(elem)
    if "variable_ref" in tag: return f'<a class="Link" href="#{elem.get("NAME","")}-var">{esc(elem.get("NAME",""))}</a>'
    if "territory_ref" in tag: return f'<a class="Link" href="#{elem.get("NAME","")}-terr">{esc(elem.get("NAME",""))}</a>'
    if "output_reference" in tag: return render_oref(elem)
    if "mdlt_ref" in tag: return f'<a class="Link" href="#{elem.get("NAME","")}-mdlt">{esc(elem.get("NAME",""))}</a>'
    if "hold_ref" in tag:
        nm=elem.get("NAME",""); per=elem.get("PERIOD_TYPE",""); rls=elem.get("RELEASE_TYPE","")
        return rls if rls else (nm + (f" ( {per} )" if per else ""))
    if "ratetable_ref" in tag: return f'<a class="Link" href="#{elem.get("NAME","")}-rt">{esc(elem.get("NAME",""))}</a>'
    if tag=="data_field": return gtxt(elem)
    if tag=="string_literal": t=gtxt(elem); return "NULL" if t.upper()=="NULL" else t
    if tag=="value": d=elem.get("DECIMAL_VALUE",""); u=elem.get("UNIT_TYPE",""); return f"{d} {u}".strip()
    if tag=="boolean": return elem.get("VALUE","")
    if tag=="credit_type": return gtxt(elem)
    t=gtxt(elem); return esc(t) if t else ""

def _r_op(op_elem, depth=0):
    oid = op_elem.get("ID","")
    ind = "  "*depth
    L=[]
    kids = [c for c in op_elem if c.tag.lower()!="parameter_list"]
    sym = OP_SYMBOLS.get(oid, oid)
    if oid=="NOT_BOOLEAN_OPERATOR":
        if kids: L=[f'{ind}<b>NOT</b> (', f'{ind}{_rop(kids[0], depth)}', f'{ind})']
        else: L=[f'{ind}<b>NOT</b>']
    elif oid in ("AND_OPERATOR","OR_OPERATOR"):
        conn = f"<b>{sym}</b>" if depth==0 else sym.strip()
        for i,c in enumerate(kids):
            ct=_rop(c,depth)
            if ct.strip(): L.append(f'{ind}({ct})' if depth==0 and i==0 else f'{ind}{ct}')
            if i<len(kids)-1: L.append(f'{ind}{conn}')
    else:
        for i,c in enumerate(kids):
            ct=_rop(c,depth)
            if ct.strip(): L.append(f'{ind}{ct}')
            if i<len(kids)-1: L.append(f'{ind}{sym}')
    return "\n".join(L)

def _r_func(func_elem, depth=0):
    fid = func_elem.get("ID","")
    disp = FUNC_DISP.get(fid, fid)
    ind = "  "*depth
    if fid=="MDLT_FUNCTION":
        L=[f'{ind}Lookup In Table', f'{ind}( ', f'{ind}<table>']
        mr=func_elem.find("MDLT_REF")
        if mr is not None:
            L.append(f'{ind}<tr>')
            L.append(f'{ind}<td valign="top" style="right-padding: 10px" class="FunctionParameterLineNumber">Lookup Table Name</td>')
            L.append(f'{ind}<td class="FunctionParameter"><a class="Link" href="#{mr.get("NAME","")}-mdlt">{esc(mr.get("NAME",""))}</a><br></td>')
            L.append(f'{ind}</tr>')
        rn=2
        for c in func_elem:
            if c.tag.lower()=="mdlt_ref": continue
            L.append(f'{ind}<tr><td valign="top" style="right-padding: 10px" class="FunctionParameterLineNumber">{rn}</td>')
            L.append(f'{ind}<td class="FunctionParameter">{_rop(c,depth+1)}</td></tr>')
            rn+=1
        L.append(f'{ind}</table>'); L.append(f'{ind})')
        return "\n".join(L)
    L=[f'{ind}{disp}', f'{ind}(']
    for c in func_elem:
        ct=_rop(c,depth+1)
        if ct.strip(): L.append(f'{ind}  {ct}')
    L.append(f'{ind})')
    return "\n".join(L)

def render_expr(expr_elem, depth=0):
    if expr_elem is None: return ""
    tag=expr_elem.tag.lower() if hasattr(expr_elem,'tag') else ""
    if "_operator" in tag: return _r_op(expr_elem,depth)
    if tag=="function": return _r_func(expr_elem,depth)
    if tag=="event_type_expression": return _r_evtype(expr_elem,depth)
    kids=list(expr_elem)
    if kids: return render_expr(kids[0],depth)
    return esc(gtxt(expr_elem))

def _r_evtype(ev_elem, depth=0):
    ind="  "*depth; L=[]
    kids=ev_elem.findall("EVENT_TYPE_EXPRESSION")
    if kids:
        pw=ev_elem.get("PAREN_WRAPPED","false").lower()=="true"
        if pw: L.append(f'{ind}(')
        for i,c in enumerate(kids):
            L.append(_r_evtype(c,depth+1))
            if i<len(kids)-1:
                sibs=list(ev_elem)
                try:
                    ni=sibs.index(c)+1
                    if ni<len(sibs):
                        ns=sibs[ni]
                        if "_operator" in (ns.tag.lower() if hasattr(ns,'tag') else ""):
                            oid=ns.get("ID","")
                            sym=OP_SYMBOLS.get(oid,"")
                            if oid in ("AND_OPERATOR","OR_OPERATOR"): L.append(f'{ind}<b>{sym}</b>')
                            else: L.append(f'{ind}{sym}')
                except (ValueError,IndexError): pass
        if pw: L.append(f'{ind})')
    else:
        et=ev_elem.find("EVENT_TYPE")
        if et is not None:
            L.append(f'{ind}SalesTransaction.eventType.eventTypeId')
            L.append(f'{ind}='); L.append(f'{ind}{esc(gtxt(et))}')
        else:
            for c in ev_elem:
                tag=c.tag.lower() if hasattr(c,'tag') else ""
                if "_operator" in tag: L.append(_r_op(c,depth))
                elif tag=="function": L.append(_r_func(c,depth))
    return "\n".join(L)

def _ap_lbl(fid, idx, child):
    tag=child.tag.lower() if hasattr(child,'tag') else ""
    if tag=="output_reference":
        if fid in ("PRIMARY_MEASUREMENT","SECONDARY_MEASUREMENT_GAS"): return "Measurement Output"
        return "Incentive Output" if ("INCENTIVE" in fid or "BULK" in fid) else "Credit Output"
    if fid=="DIRECT_TRANSACTION_CREDIT_ALLGAs":
        lbs=[None,"Input Value","Hold Type","Credit Type","Allow Duplicates","Rollable"]
        if idx<len(lbs) and lbs[idx]: return lbs[idx]
    elif fid in ("PRIMARY_MEASUREMENT","SECONDARY_MEASUREMENT_GAS"):
        if idx==1: return "Increment Value"
    elif "INCENTIVE" in fid:
        lbs=[None,"Input Amount","Hold Type"]
        if idx<len(lbs) and lbs[idx]: return lbs[idx]
    elif "COMMISSION" in fid:
        lbs=[None,"Input Amount","Hold Type","Credit Type"]
        if idx<len(lbs) and lbs[idx]: return lbs[idx]
    if tag=="hold_ref": return "Hold Type"
    if tag=="credit_type": return "Credit Type"
    if tag=="ratetable_ref": return "Rate Table"
    if tag=="data_field": return "Input Value"
    if tag=="string_literal": return "Generic Attribute"
    if tag=="value": return "Value"
    if tag=="function": return "Value"
    if any(x in tag for x in ["measurement_ref","incentive_ref"]): return "Input Amount"
    if "rule_element_ref" in tag: return "Generic Attribute"
    if "_operator" in tag: return "Input Amount"
    if tag=="boolean": return "Generic Boolean"
    return f"Parameter {idx}"

def render_action(func_elem, depth=0):
    fid=func_elem.get("ID","")
    al=ACTION_LABELS.get(fid, f"Create {fid}" if not fid.startswith("Create ") else fid)
    ind="  "*depth
    L=[f'{ind}{al}', f'{ind}( ', f'{ind}<table>']
    pi=0
    for child in func_elem:
        tag=child.tag.lower() if hasattr(child,'tag') else ""
        if tag=="parameter_list": continue
        lbl=_ap_lbl(fid, pi, child)
        L.append(f'{ind}<tr>')
        L.append(f'{ind}<td valign="top" style="right-padding: 10px" class="FunctionParameterLineNumber">{esc(lbl)}</td>')
        if tag=="output_reference":
            L.append(f'{ind}<td class="FunctionParameter">{render_oref(child)}</td>')
        elif tag=="function":
            fid2=child.get("ID","")
            border=fid2=="MDLT_FUNCTION"
            val=render_action(child,depth+1) if any(x in fid2 for x in ["INCENTIVE","COMMISSION","MEASUREMENT","CREDIT"]) else _r_func(child,depth+1)
            sty='style="border: 1px solid #EEEEEE;" class="FunctionParameter"' if border else 'class="FunctionParameter"'
            L.append(f'{ind}<td {sty}>{val}</td>')
        elif "_operator" in tag:
            L.append(f'{ind}<td style="border: 1px solid #EEEEEE;" class="FunctionParameter">{_r_op(child,depth)}</td>')
        elif any(x in tag for x in ["measurement_ref","incentive_ref"]):
            L.append(f'{ind}<td class="FunctionParameter">{render_ref(child)}</td>')
        elif "rule_element_ref" in tag:
            L.append(f'{ind}<td class="FunctionParameter">{render_ref(child)}</td>')
        elif tag=="data_field":
            L.append(f'{ind}<td class="FunctionParameter">{gtxt(child)}</td>')
        elif tag=="string_literal":
            t=gtxt(child); L.append(f'{ind}<td class="FunctionParameter">{"NULL" if t.upper()=="NULL" else t}</td>')
        elif tag=="value":
            d=child.get("DECIMAL_VALUE",""); u=child.get("UNIT_TYPE","")
            L.append(f'{ind}<td class="FunctionParameter">{(d+chr(32)+u).strip()}</td>')
        elif tag=="hold_ref":
            nm=child.get("NAME",""); per=child.get("PERIOD_TYPE",""); rls=child.get("RELEASE_TYPE","")
            v=rls if rls else (nm + (f" ( {per} )" if per else ""))
            L.append(f'{ind}<td class="FunctionParameter">{v}</td>')
        elif tag=="credit_type":
            L.append(f'{ind}<td class="FunctionParameter">{gtxt(child)}</td>')
        elif tag=="boolean":
            L.append(f'{ind}<td class="FunctionParameter">{child.get("VALUE","")}</td>')
        elif "ref" in tag:
            L.append(f'{ind}<td class="FunctionParameter">{render_ref(child)}</td>')
        else:
            L.append(f'{ind}<td class="FunctionParameter">{esc(gtxt(child))}</td>')
        L.append(f'{ind}</tr>')
        pi+=1
    L.append(f'{ind}</table>')
    L.append(f'{ind})')
    return "\n".join(L)

# Data Model classes
class Plan:
    def __init__(self,e): self.e=e; self.name=e.get("NAME",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE",""); self.desc=e.get("DESCRIPTION",""); self.cn=[]
    @property
    def anchor(self): return f"{self.name}-plan"
    def render(self, v, cm, rm):
        L=[f'<a name="{self.anchor}"></a>', f'<h2 class="SubSectionTitle">{esc(self.name)}</h2>']
        L.append('<table border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Effective Date Range</td><td class="Value">{esc(drange(self.st,self.en))}</td></tr>')
        L.append(f'<tr><td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td></tr>')
        L.append('</table><p></p>')
        pcs=[cm[c] for c in self.cn if c in cm]
        L.append('<table width="100%" border="0" cellpadding="0" cellspacing="5"><tr>')
        for h in ["Plan Components","Credit Rules","Measurement Rules","Incentive Rules","Deposit Rules","Detailed Deposit Rules"]:
            L.append(f'<td class="ContentTitle">{h}</td>')
        L.append('</tr><tr>')
        clinks=[]; cats={k:[] for k in ["credit","measurement","incentive","deposit","detail_deposit"]}
        for pc in pcs:
            ca=f"{pc.name}-plan-{self.name}"
            clinks.append(f'<a class="Link" href="#{ca}">{esc(pc.name)}</a>')
            for rn in pc.rn:
                if rn in rm:
                    r=rm[rn]; cat=TYPE_CATEGORY.get(r.rt,"credit")
                    ra=f"{r.name}-rule-{pc.name}-{self.name}"
                    link=f'<a class="Link" href="#{ra}">{esc(r.name)}</a>'
                    if link not in cats[cat]: cats[cat].append(link)
        L.append(f'<td valign="top">{"<br>".join(clinks)}</td>')
        for ck in ["credit","measurement","incentive","deposit","detail_deposit"]:
            L.append(f'<td valign="top">{"<br>".join(cats[ck])}</td>')
        L.append('</tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#plans">Plans</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        if v=="B": L.append('<tr><td class="Copyright">Copyright</td></tr>')
        L.append('</table>')
        return "\n".join(L)

class PComp:
    def __init__(self,e): self.e=e; self.name=e.get("NAME",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE",""); self.desc=e.get("DESCRIPTION",""); self.rn=[]
    def render(self, v, pn, rm):
        L=[f'<a name="{self.name}-plan-{pn}"></a>', f'<h2 class="ComponentObjectTitle">{esc(self.name)}</h2>']
        es=fd(self.st); ee=fd(self.en)
        if not ee or "2200" in ee or "2099" in ee: ee="End of Time"
        L.append('<table border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td></tr>')
        L.append(f'<tr><td class="LabelCell">Effective</td><td class="Value">{esc(es)} to {esc(ee)}</td></tr>')
        L.append('</table><p></p>')
        cr=[rm[rn] for rn in self.rn if rn in rm]
        L.append('<table width="100%" border="0" cellpadding="0" cellspacing="5"><tr>')
        for h in ["Credit Rules","Measurement Rules","Incentive Rules","Deposit Rules","Detailed Deposit Rules"]:
            L.append(f'<td class="ContentTitle">{h}</td>')
        L.append('</tr><tr>')
        cats={k:[] for k in ["credit","measurement","incentive","deposit","detail_deposit"]}
        for r in cr:
            cat=TYPE_CATEGORY.get(r.rt,"credit")
            ra=f"{r.name}-rule-{self.name}-{pn}"
            cats[cat].append(f'<a class="Link" href="#{ra}">{esc(r.name)}</a>')
        for ck in ["credit","measurement","incentive","deposit","detail_deposit"]:
            L.append(f'<td valign="top">{"<br>".join(cats[ck])}</td>')
        L.append('</tr></table>')
        return "\n".join(L)

class Rule:
    def __init__(self,e): self.e=e; self.name=e.get("NAME",""); self.rt=e.get("TYPE",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE",""); self.eca=e.get("ISEVENTCONDITIONACTION",e.get("ECA",""))
    @property
    def heading(self): return f"{TYPE_HEADING.get(self.rt,'Rule')}: {self.name}"
    def render(self, v, pn, cn):
        anchor=f"{self.name}-rule-{cn}-{pn}"
        L=[f'<a name="{anchor}"></a>', f'<h2 class="ObjectTitle">{esc(self.heading)}</h2>']
        L.append('<table border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Type</td><td class="Value">{esc(TYPE_LABELS.get(self.rt,self.rt))}</td></tr>')
        if self.rt in ("DIRECT_TRANSACTION_CREDIT","ROLLUP_TRANSACTION_CREDIT"):
            ev="true" if self.eca and self.eca.lower()=="true" else "false"
            L.append(f'<tr><td class="LabelCell">ECA</td><td class="Value">{ev}</td></tr>')
        es=fd(self.st); ee=fd(self.en)
        if not ee or "2200" in ee or "2099" in ee: ee="End of Time"
        L.append(f'<tr><td class="LabelCell">Effective Date Range</td><td class="Value">{esc(es)} - {esc(ee)}</td></tr>')
        L.append('</table>')
        if self.rt=="DIRECT_TRANSACTION_CREDIT":
            evt=self.e.find("EVENT_TYPE_EXPRESSION")
            if evt is not None:
                L.append('<p></p><span class="ContentTitle">Event Type</span><p></p>')
                L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
                L.append(_r_evtype(evt)); L.append('</td></tr></table>')
        cond=self.e.find("CONDITION_EXPRESSION")
        if cond is not None and len(cond):
            L.append('<p></p><span class="ContentTitle">Condition</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(cond)); L.append('</td></tr></table>')
        terr=self.e.find("TERRITORY_EXPRESSION")
        if terr is not None and len(terr):
            L.append('<p></p><span class="ContentTitle">Territory</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(terr)); L.append('</td></tr></table>')
        L.append('<p></p><span class="ContentTitle">Actions</span><p></p><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
        aes=self.e.find("ACTION_EXPRESSION_SET")
        if aes is not None:
            for ae in aes.findall("ACTION_EXPRESSION"):
                func=ae.find("FUNCTION")
                if func is not None: L.append(render_action(func))
        else:
            acts=self.e.find("ACTIONS")
            if acts is not None:
                for act in acts.findall("ACTION"):
                    gf=act.find("GA_FUNCTION")
                    if gf is not None:
                        func=gf.find("FUNCTION")
                        if func is not None: L.append(render_action(func))
        L.append('</td></tr></table>')
        ca=f"{cn}-plan-{pn}"
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#{ca}">{esc(cn)}</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        if v=="B": L.append('<tr><td class="Copyright">Copyright</td></tr>')
        L.append('</table>')
        return "\n".join(L)

class MDLT:
    def __init__(self,e):
        self.e=e; self.name=e.get("NAME",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE","")
        self.dims=[]; dn=e.find("DIM_NAMES")
        if dn is not None:
            for d in dn.findall("DIM_NAME"): self.dims.append(d.get("NAME",""))
        self.cells=[]; ce=e.find("CELLS")
        if ce is not None:
            for c in ce.findall("CELL"): self.cells.append(c)
    @property
    def anchor(self): return f"{self.name}-mdlt"
    def _edt(self):
        es=fd(self.st); ee=fd(self.en)
        if not ee or "2200" in ee or "2099" in ee: ee="End of Time"
        L=['<p></p><span class="ContentTitle">Effective Date Range</span><p></p>']
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr></table>')
        return "\n".join(L)
    def render(self, v):
        L=[f'<a name="{self.anchor}"></a>', f'<h2 class="ObjectTitle">{esc(self.name)}</h2>', self._edt()]
        L.append('<p></p><span class="ContentTitle">Cells</span><p></p>')
        L.append('<table class="ListTable"><tr>')
        for h in ["Title","Component","Value"]: L.append(f'<td class="ListHeaderCell">{h}</td>')
        L.append('</tr>')
        for cell in self.cells:
            dv={}
            for d in cell.findall("DIM_VALUE"): dv[d.get("DIM_NAME","")]=d.get("VALUE","")
            title=", ".join(f"{k}={v}" for k,v in dv.items())
            comp=", ".join(self.dims)
            ve=cell.find("VALUE")
            val=f'{ve.get("DECIMAL_VALUE","")} {ve.get("UNIT_TYPE","")}'.strip() if ve is not None else ""
            L.append('<tr>')
            L.append(f'<td class="ListCell">{esc(title)}</td><td class="ListCell">{esc(comp)}</td><td class="ListCell">{esc(val)}</td>')
            L.append('</tr>')
        L.append('</table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#mdlts">Lookup Tables</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        if v=="B": L.append('<tr><td class="Copyright">Copyright</td></tr>')
        L.append('</table>')
        return "\n".join(L)

class FV:
    def __init__(self,e):
        self.e=e; self.name=e.get("NAME",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE","")
        fv=e.find("FIXED_VALUE_VALUE") or e.find("VALUE")
        if fv is not None: self.dv=fv.get("DECIMAL_VALUE",""); self.ut=fv.get("UNIT_TYPE","")
        else: self.dv=self.ut=""
    @property
    def anchor(self): return f"{self.name}-fv"
    def render(self, v):
        es=fd(self.st); ee=fd(self.en)
        if not ee or "2200" in ee or "2099" in ee: ee="End of Time"
        val=f"{self.dv} {self.ut}".strip()
        L=[f'<a name="{self.anchor}"></a>', f'<h2 class="ObjectTitle">{esc(self.name)}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table class="ListTable"><tr>')
        for h in ["Start Date","End Date","Value"]: L.append(f'<td class="ListHeaderCell">{h}</td>')
        L.append('</tr><tr>')
        L.append(f'<td class="ListCell">{esc(es)}</td><td class="ListCell">{esc(ee)}</td><td class="ListCell">{esc(val)}</td>')
        L.append('</tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#fixedvalues">Fixed Values</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        if v=="B": L.append('<tr><td class="Copyright">Copyright</td></tr>')
        L.append('</table>')
        return "\n".join(L)

class Quota:
    def __init__(self,e):
        self.e=e; self.name=e.get("NAME",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE","")
        self.positions=list(e.findall("QUOTA_VALUE"))
    @property
    def anchor(self): return f"{self.name}-quota"
    def render(self, v):
        es=fd(self.st); ee=fd(self.en)
        if not ee or "2200" in ee or "2099" in ee: ee="End of Time"
        L=[f'<a name="{self.anchor}"></a>', f'<h2 class="ObjectTitle">{esc(self.name)}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr></table>')
        for pos in self.positions:
            pn=pos.get("POSITION_NAME",pos.get("NAME","")); sp=pos.get("EFFECTIVE_START_DATE",""); ep=pos.get("EFFECTIVE_END_DATE","")
            ve=pos.find("VALUE")
            vl=f'{ve.get("DECIMAL_VALUE","")} {ve.get("UNIT_TYPE","")}'.strip() if ve is not None else pos.get("QUOTA_VALUE","")
            L.append(f'<p></p><span class="ContentTitle">{esc(pn)}</span><p></p>')
            L.append('<table class="ListTable"><tr>')
            for h in ["Start Period","End Period","Value"]: L.append(f'<td class="ListHeaderCell">{h}</td>')
            L.append('</tr><tr>')
            L.append(f'<td class="ListCell">{esc(sp)}</td><td class="ListCell">{esc(ep)}</td><td class="ListCell">{esc(vl)}</td>')
            L.append('</tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#quotas">Quotas</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        if v=="B": L.append('<tr><td class="Copyright">Copyright</td></tr>')
        L.append('</table>')
        return "\n".join(L)

class Formula:
    def __init__(self,e):
        self.e=e; self.name=e.get("NAME",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE","")
        self.rt=e.get("RETURN_TYPE",""); self.desc=e.get("DESCRIPTION","")
    @property
    def anchor(self): return f"{self.name}-formula"
    def render(self, v):
        es=fd(self.st); ee=fd(self.en)
        if not ee or "2200" in ee or "2099" in ee: ee="End of Time"
        L=[f'<a name="{self.anchor}"></a>', f'<h2 class="ObjectTitle">{esc(self.name)}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr></table>')
        L.append('<p></p><span class="ContentTitle">Return Type</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Return Type</td><td class="Value">{esc(self.rt)}</td>')
        L.append('</tr></table>')
        if self.desc:
            L.append('<p></p><span class="ContentTitle">Description</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
            L.append(f'<td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td>')
            L.append('</tr></table>')
        expr=self.e.find("EXPRESSION")
        if expr is not None and len(expr):
            L.append('<p></p><span class="ContentTitle">Formula</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(expr)); L.append('</td></tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#formulas">Formulas</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        if v=="B": L.append('<tr><td class="Copyright">Copyright</td></tr>')
        L.append('</table>')
        return "\n".join(L)

class Territory:
    def __init__(self,e):
        self.e=e; self.name=e.get("NAME",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE","")
        self.desc=e.get("DESCRIPTION","")
    @property
    def anchor(self): return f"{self.name}-terr"
    def render(self, v):
        es=fd(self.st); ee=fd(self.en)
        if not ee or "2200" in ee or "2099" in ee: ee="End of Time"
        L=[f'<a name="{self.anchor}"></a>', f'<h2 class="ObjectTitle">{esc(self.name)}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr></table>')
        L.append('<p></p><span class="ContentTitle">Description</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td>')
        L.append('</tr></table>')
        expr=self.e.find("EXPRESSION")
        if expr is not None and len(expr):
            L.append('<p></p><span class="ContentTitle">Territory</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(expr)); L.append('</td></tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#territories">Territories</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        if v=="B": L.append('<tr><td class="Copyright">Copyright</td></tr>')
        L.append('</table>')
        return "\n".join(L)

class Variable:
    def __init__(self,e):
        self.e=e; self.name=e.get("NAME",""); self.st=e.get("EFFECTIVE_START_DATE",""); self.en=e.get("EFFECTIVE_END_DATE","")
        self.vt=e.get("VARIABLE_TYPE",""); self.pt=e.get("PERIOD_TYPE",""); self.dv=e.get("DEFAULT_VALUE","")
        self.assignments=list(e.findall("VARIABLE_ASSIGNMENT"))
    @property
    def anchor(self): return f"{self.name}-var"
    def render(self, v):
        es=fd(self.st); ee=fd(self.en)
        if not ee or "2200" in ee or "2099" in ee: ee="End of Time"
        L=[f'<a name="{self.anchor}"></a>', f'<h2 class="ObjectTitle">{esc(self.name)}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr></table>')
        L.append('<p></p><span class="ContentTitle">Variable</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Type</td><td class="Value">{esc(self.vt)}</td></tr>')
        if self.pt: L.append(f'<tr><td class="LabelCell">Period Type</td><td class="Value">{esc(self.pt)}</td></tr>')
        L.append(f'<tr><td class="LabelCell">Default</td><td class="Value">{esc(self.dv)}</td></tr>')
        L.append('</table>')
        L.append('<p></p><span class="ContentTitle">Assignments</span><p></p>')
        L.append('<table class="ListTable"><tr>')
        for h in ["Plan","Owner","Owner Type","Assignment"]: L.append(f'<td class="ListHeaderCell">{h}</td>')
        L.append('</tr>')
        if self.assignments:
            for va in self.assignments:
                L.append('<tr>')
                L.append(f'<td class="ListCell">{esc(va.get("PLAN_NAME",""))}</td>')
                L.append(f'<td class="ListCell">{esc(va.get("OWNER_NAME",""))}</td>')
                L.append(f'<td class="ListCell">{esc(va.get("OWNER_TYPE",""))}</td>')
                L.append(f'<td class="ListCell">{esc(va.get("ASSIGNMENT_VALUE",""))}</td>')
                L.append('</tr>')
        else:
            L.append('<tr><td class="ListCell"></td><td class="ListCell"></td><td class="ListCell"></td><td class="ListCell"></td></tr>')
        L.append('</table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#variables">Variables</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        if v=="B": L.append('<tr><td class="Copyright">Copyright</td></tr>')
        L.append('</table>')
        return "\n".join(L)

class Transformer:
    def __init__(self, variant="A"):
        self.v=variant; self.plans=[]; self.comps={}; self.rules={}
        self.mdlts=[]; self.fvs=[]; self.quotas=[]; self.formulas=[]; self.terrs=[]; self.vars=[]
        self.ver=""
    def parse(self, path):
        try:
            tree=ET.parse(path); root=tree.getroot()
        except ET.ParseError as e: raise XErr(f"XML parse error", details=str(e))
        if root.tag!="DATA_IMPORT": raise XErr(f"Expected DATA_IMPORT, got {root.tag}")
        self.ver=root.get("VERSION","")
        for se in root:
            tag=se.tag
            try:
                if tag=="PLAN_SET":
                    for pe in se.findall("PLAN"):
                        p=Plan(pe)
                        for cr in pe.findall("COMPONENT_REF"): 
                            cn=cr.get("NAME","")
                            if cn: p.cn.append(cn)
                        comps=pe.find("COMPONENTS")
                        if comps is not None:
                            for c in comps.findall("COMPONENT"):
                                cn=c.get("NAME","")
                                if cn and cn not in p.cn: p.cn.append(cn)
                        self.plans.append(p)
                elif tag=="PLANCOMPONENT_SET":
                    for ce in se.findall("PLANCOMPONENT"):
                        c=PComp(ce)
                        rre=ce.find("RULE_REFS")
                        if rre is not None:
                            for rr in rre.findall("RULE_REF"):
                                rn=rr.get("NAME","")
                                if rn: c.rn.append(rn)
                        for rr in ce.findall("RULE_REF"):
                            rn=rr.get("NAME","")
                            if rn and rn not in c.rn: c.rn.append(rn)
                        self.comps[c.name]=c
                elif tag=="RULE_SET":
                    for re in se.findall("RULE"): self.rules[re.get("NAME","")]=Rule(re)
                elif tag=="MD_LOOKUP_TABLE_SET":
                    for e in se.findall("MD_LOOKUP_TABLE"): self.mdlts.append(MDLT(e))
                elif tag=="FIXED_VALUE_SET":
                    for e in se.findall("FIXED_VALUE"): self.fvs.append(FV(e))
                elif tag=="QUOTA_SET":
                    for e in se.findall("QUOTA"): self.quotas.append(Quota(e))
                elif tag=="FORMULA_SET":
                    for e in se.findall("FORMULA"): self.formulas.append(Formula(e))
                elif tag=="TERRITORY_SET":
                    for e in se.findall("TERRITORY"): self.terrs.append(Territory(e))
                elif tag=="VARIABLE_SET":
                    for e in se.findall("VARIABLE"): self.vars.append(Variable(e))
            except Exception as e:
                raise XErr(f"Parse error in {tag}", details=str(e)) from e
        if self.v=="B": return
        if self.ver>="17.0" or len(self.plans)>=2: self.v="B"; return
        for r in self.rules.values():
            bu=r.e.get("BUSINESS_UNITS","")
            if bu and bu not in ("__ALL_BU__",""): self.v="B"; break
    def _so(self, a):
        return {"plans":self.plans,"mdlts":self.mdlts,"fixedvalues":self.fvs,
                "quotas":self.quotas,"formulas":self.formulas,"territories":self.terrs,
                "variables":self.vars}.get(a,[])
    def html(self):
        v=self.v; L=['<!DOCTYPE HTML>','<html>','<head>',
            '<META http-equiv="Content-Type" content="text/html; charset=UTF-8">',
            '<title>SAP Incentive Management Plan Summary</title>',
            f'<style type="text/css">{CSS}</style>','</head>','<body class="Body">']
        if v=="B": L.append(f'<p style="text-align: center;"><img src="data:image/png;base64,{SAP_LOGO_B64}" alt="SAP"></p>')
        L.append('<p></p><span class="PageTitle">SAP Incentive Management Plan Summary</span><p></p><p></p>')
        L.append(self._idx()); L.append('<a name="Top"></a>')
        for anchor,dname,sname in SECTION_ORDER:
            objs=self._so(anchor)
            if not objs:
                if anchor in ("quotas","territories"): continue
                L.append(f'<a name="{anchor}"></a><h1 class="SectionTitle">{dname} (0)</h1><p></p>')
                continue
            L.append(f'<a name="{anchor}"></a>')
            L.append(f'<h1 xmlns:java="http://xml.apache.org/xalan/java" class="SectionTitle" width="100%">{dname}</h1><p></p>')
            for obj in objs:
                try:
                    if anchor=="plans":
                        L.append(obj.render(v,self.comps,self.rules)); L.append('<p></p>')
                        for cn in obj.cn:
                            if cn in self.comps:
                                comp=self.comps[cn]
                                L.append(comp.render(v,obj.name,self.rules)); L.append('<p></p>')
                                for rn in comp.rn:
                                    if rn in self.rules:
                                        L.append(self.rules[rn].render(v,obj.name,cn)); L.append('<p></p>')
                    else:
                        L.append(obj.render(v)); L.append('<p></p>')
                except Exception as e:
                    on=getattr(obj,'name','?')
                    raise XErr("Render error", obj_name=on, obj_type=type(obj).__name__, details=str(e)) from e
        L.append('</body></html>')
        return "\n".join(L)
    def _idx(self):
        L=[]
        for anchor,dname,sname in SECTION_ORDER:
            objs=self._so(anchor); cnt=len(objs)
            if cnt==0 and anchor not in ("quotas","territories"): continue
            L.append(f'<a class="Link" href="#{anchor}"><b>{dname}</b></a>')
            if cnt>0: L.append(f'            ({cnt})')
            L.append('<br>')
            if cnt>0:
                L.append('<table width="100%" border="0" cellpadding="0" cellspacing="0"><tr>')
                if anchor=="plans":
                    lnks=[f'<a style="padding: 10px" class="Link" href="#{p.anchor}">{esc(p.name)}</a>' for p in objs]
                    L.append(f'<td style="padding: 15px; vertical-align: top; overflow: hidden;">{"<br>".join(lnks)}<br></td>')
                    L.append('<td style="padding: 15px; vertical-align: top; overflow: hidden;"></td>')
                elif anchor=="fixedvalues":
                    lnks=[f'<a style="padding: 10px" class="Link" href="#{o.anchor}">{esc(o.name)}</a>' for o in objs]
                    L.append(f'<td style="padding: 15px; vertical-align: top; overflow: hidden;">{"<br>".join(lnks)}<br></td>')
                elif anchor in ("quotas","territories"):
                    lnks=[f'<a style="padding: 10px" class="Link" href="#{o.anchor}">{esc(o.name)}</a>' for o in objs]
                    if lnks:
                        L.append(f'<td style="padding: 15px; vertical-align: top; overflow: hidden;">{"<br>".join(lnks)}<br></td>')
                        L.append('<td style="padding: 15px; vertical-align: top; overflow: hidden;"></td>')
                    else: L.append('<td></td>')
                else:
                    ipc=max(1,min(10,cnt//3+1))
                    for i in range(0,cnt,ipc):
                        chunk=objs[i:i+ipc]
                        cl=[f'<a style="padding: 10px" class="Link" href="#{o.anchor}">{esc(o.name)}</a>' for o in chunk]
                        L.append(f'<td style="padding: 15px; vertical-align: top; overflow: hidden;">{"<br>".join(cl)}<br></td>')
                L.append('</tr></table>')
            L.append('<p></p>')
        return "\n".join(L)
    def transform(self, xp, hp):
        try:
            self.parse(xp); hc=self.html()
            with open(hp,"w",encoding="utf-8") as f: f.write(hc)
            return True,f"OK: {xp} -> {hp} (Variant {self.v})"
        except XErr as e: return False,str(e)
        except Exception as e: return False,f"Error: {e}"

def main():
    if len(sys.argv)<2:
        print("Usage: python sap_im_transformer.py input.xml [output.html] [--variant A|B]"); sys.exit(1)
    ip=sys.argv[1]; op=None; variant="auto"
    for a in sys.argv[2:]:
        if a.startswith("--variant="):
            vv=a.split("=")[1].upper()
            if vv in ("A","B"): variant=vv
        elif not a.startswith("--"): op=a
    if op is None: op=ip[:-4]+".html" if ip.lower().endswith(".xml") else ip+".html"
    t=Transformer(variant="A" if variant=="auto" else variant)
    ok,msg=t.transform(ip,op)
    if ok: print(msg)
    else: print(f"ERROR: {msg}", file=sys.stderr); sys.exit(1)

if __name__=="__main__": main()
