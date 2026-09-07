#!/usr/bin/env python3
"""
SAP Incentive Management XML to HTML Transformer
Converts SAP Incentive Management plan XML to HTML.
Usage: python sap_im_transformer.py input.xml [output.html] [--variant A|B]
"""
import hashlib
import html as html_mod
from pathlib import Path
import re
import sys
import urllib.parse
from collections import defaultdict
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
RULE_CATEGORY_ORDER = ("credit", "measurement", "incentive", "deposit", "detail_deposit")
RULE_CATEGORY_HEADINGS = {
    "credit": "Credit Rules",
    "measurement": "Measurement Rules",
    "incentive": "Incentive Rules",
    "deposit": "Deposit Rules",
    "detail_deposit": "Detailed Deposit Rules",
    "other": "Other Rules",
}
RULE_CATEGORY_INDEX = {category: index for index, category in enumerate(RULE_CATEGORY_ORDER)}
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
SUMMARY_ORDER = [
    ("plans", "Plans"),
    ("plancomponents", "Plan Components"),
    ("rules", "Rules"),
    ("formulas", "Formulas"),
    ("variables", "Variables"),
    ("mdlts", "Lookup Tables"),
    ("quotas", "Quotas"),
    ("territories", "Territories"),
    ("fixedvalues", "Fixed Values"),
]
SUMMARY_COLUMN_COUNT = 3
OBJECT_TYPE_BY_SECTION = {
    "plans": "Plan",
    "plancomponents": "PlanComponent",
    "rules": "Rule",
    "formulas": "Formula",
    "variables": "Variable",
    "mdlts": "LookupTable",
    "quotas": "Quota",
    "territories": "Territory",
    "fixedvalues": "FixedValue",
}
CSS = """
            :root {
              color-scheme: light;
              --forest-green: #2e7d32; --light-green: #81c784; --charcoal-gray: #333333;
              --neutral-white: #ffffff; --alert-red: #d32f2f; --warning-amber: #ffa000;
              --background: var(--neutral-white); --surface: #f7faf7; --surface-muted: #edf4ed;
              --text: var(--charcoal-gray); --muted-text: #59635a; --border: #c8d8ca;
            }
            :root[data-theme="dark"] {
              color-scheme: dark;
              --background: var(--charcoal-gray); --surface: #252b26; --surface-muted: #202720;
              --text: var(--neutral-white); --muted-text: #d7e4d8; --border: #748076;
            }
            .Body { background-color: var(--background); color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; font-weight: 300; margin: 20px; text-decoration: none; }
            .PageTitle { color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 36px; font-weight: 700; }
            .SectionTitle { background-color: var(--forest-green); border: solid 1px var(--light-green); color: var(--neutral-white); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 24px; font-weight: 700; padding: 6px 8px; }
            .SubSectionTitle { background-color: var(--light-green); border: solid 1px var(--forest-green); color: var(--charcoal-gray); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 18px; font-weight: 700; padding: 5px 7px; }
            .ComponentObjectTitle, .ObjectTitle { background-color: var(--surface-muted); border: solid 1px var(--border); color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 18px; font-weight: 700; padding: 5px 7px; }
            .ContentTitle { color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; font-weight: 700; }
            .Link { color: var(--forest-green); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif !important; font-size: 14px; font-weight: 600; text-decoration: none; }
            .Link:hover { color: var(--light-green) !important; text-decoration: underline; }
            .LabelCell { color: var(--muted-text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; font-weight: 300; padding: 6px 6px 1px 0; text-align: right; vertical-align: top; }
            .Value { color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; font-weight: 300; padding: 6px 6px 4px 3px; vertical-align: top; }
            .ContentBox { background-color: var(--surface); border: solid 1px var(--border); color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; font-weight: 300; padding: 8px; }
            .ListTable { background-color: var(--surface); }
            .ListHeaderCell { background-color: var(--surface-muted); border: 1px solid var(--border); color: var(--muted-text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; padding: 3px; text-decoration: none; vertical-align: bottom; }
            .ListCell { border-bottom: 1px solid var(--border); color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; padding: 2px 4px; vertical-align: top; }
            .FunctionParameter { color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; padding-left: 25px; vertical-align: top; }
            .FunctionParameterLineNumber { color: var(--muted-text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; padding-left: 2px; text-align: right; vertical-align: top; }
            .FunctionParameter[style] { border-color: var(--border) !important; }
            .SummaryTable { border-collapse: separate; border-spacing: 0 8px; table-layout: fixed; width: 100%; }
            .SummaryHeader { background-color: var(--surface-muted); border: 1px solid var(--border); color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 18px; font-weight: 700; padding: 6px 8px; text-align: left; }
            .SummaryCell { background-color: var(--surface); border-bottom: 1px solid var(--border); overflow-wrap: anywhere; padding: 8px 10px; vertical-align: top; width: 33.333%; }
            .SummaryItem { color: var(--text); font-family: Inter,"Segoe UI",Arial,Helvetica,sans-serif; font-size: 14px; }
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
    return html_mod.escape(str(t), quote=True)

def safe_anchor(name):
    if not name: return ""
    return urllib.parse.quote(str(name), safe=" -_.~")
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

def _build_paths(root: ET.Element) -> dict[int, str]:
    paths: dict[int, str] = {}
    def visit(element: ET.Element, path: str) -> None:
        paths[id(element)] = path
        tag_counts: dict[str, int] = {}
        for child in list(element):
            tag_counts[child.tag] = tag_counts.get(child.tag, 0) + 1
            visit(child, f"{path}/{child.tag}[{tag_counts[child.tag]}]")
    visit(root, f"/{root.tag}[1]")
    return paths

def normalize_identity(value: str | None) -> str:
    if value is None:
        return ""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", str(value).strip())
    return normalized.strip("-").lower()

def compute_instance_id(snapshot_id: str, source_file: str, canonical_key: str, xml_path: str, occurrence: int = 1) -> str:
    identity = "\x1f".join((snapshot_id, source_file, canonical_key, xml_path, str(occurrence)))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"node-{digest}"

def canonical_key_for(node_type: str, element: ET.Element, name: str) -> str:
    source_id = element.get("ID") or element.get("OBJECT_ID")
    identity = normalize_identity(source_id or name)
    return f"{normalize_identity(node_type)}:{identity}"

def render_metadata_rows(obj):
    rows = []
    sf = getattr(obj, "source_file", "")
    sid = getattr(obj, "source_id", "")
    xp = getattr(obj, "xml_path", "")
    is_dup = getattr(obj, "is_duplicate", False)
    dup_idx = getattr(obj, "duplicate_index", 1)
    dup_total = getattr(obj, "duplicate_total", 1)

    if sf:
        rows.append(f'<tr><td class="LabelCell">Source File</td><td class="Value">{esc(sf)}</td></tr>')
    if sid:
        rows.append(f'<tr><td class="LabelCell">Source ID</td><td class="Value">{esc(sid)}</td></tr>')
    if xp:
        rows.append(f'<tr><td class="LabelCell">XML Path</td><td class="Value">{esc(xp)}</td></tr>')
    if is_dup:
        evidence = f"Duplicate instance ({dup_idx} of {dup_total})"
        if sid:
            evidence += f" - Source ID: {sid}"
        if sf:
            evidence += f" [{sf}]"
        rows.append(f'<tr><td class="LabelCell">Duplicate Status</td><td class="Value" style="color: var(--alert-red); font-weight: bold;">{esc(evidence)}</td></tr>')
    return "".join(rows)

def render_anchor_tags(primary_anchor, obj=None, fallback_anchors=None):
    tags = []
    seen = set()
    def add(a):
        if a and a not in seen:
            seen.add(a)
            tags.append(f'<a name="{esc(a)}"></a>')

    add(primary_anchor)
    if fallback_anchors:
        for fa in fallback_anchors:
            add(fa)
    if obj is not None:
        inst_id = getattr(obj, "instance_id", "")
        if inst_id:
            add(inst_id)
        config_inst_id = getattr(obj, "config_instance_id", "")
        if config_inst_id:
            add(config_inst_id)
        sid = getattr(obj, "source_id", "")
        if sid:
            add(safe_anchor(sid))
        xp = getattr(obj, "xml_path", "")
        if xp:
            add(safe_anchor(xp))
    return "".join(tags)

def object_sort_key(obj):
    name = getattr(obj, "name", "")
    dup_idx = getattr(obj, "duplicate_index", 1)
    sf = getattr(obj, "source_file", "")
    sid = getattr(obj, "source_id", "")
    return (name.casefold(), name, dup_idx, sf, sid)

def rule_category(rule):
    return TYPE_CATEGORY.get(rule.rt, "other")

def rule_sort_key(rule):
    return (RULE_CATEGORY_INDEX.get(rule_category(rule), len(RULE_CATEGORY_ORDER)), object_sort_key(rule))

def sorted_objects(objects):
    return sorted(objects, key=object_sort_key)

def sorted_rules(rules):
    return sorted(rules, key=rule_sort_key)

def rule_categories(rules):
    categories = list(RULE_CATEGORY_ORDER)
    if any(rule_category(rule) == "other" for rule in rules):
        categories.append("other")
    return categories

def render_object_section(object_type, label, content, obj=None):
    return (
        f'<section data-object-type="{esc(object_type)}" '
        f'data-object-label="{esc(label)}">\n{content}\n</section>'
    )

def render_object_entry(object_type, label, content, obj=None):
    return (
        f'<span data-object-entry="true" data-object-type="{esc(object_type)}" '
        f'data-object-label="{esc(label)}">{content}</span>'
    )

def render_ref(elem):
    nm = elem.get("NAME","")
    per = elem.get("PERIOD_TYPE", elem.get("OUTPUT_REFERENCE_PERIOD_TYPE", "month"))
    off = elem.get("PERIOD_OFFSET","0")
    rid = elem.get("ID","")
    tag = elem.tag.lower() if hasattr(elem,'tag') else ""
    sa = safe_anchor(nm)
    if rid == "STRING_FORMULA_REF": return f'<a class="Link" href="#{esc(sa)}-formula">{esc(nm)}</a>'
    if "variable" in tag: return f'<a class="Link" href="#{esc(sa)}-var">{esc(nm)}</a>'
    if "territory" in tag: return f'<a class="Link" href="#{esc(sa)}-terr">{esc(nm)}</a>'
    if "ratetable" in tag: return f'<a class="Link" href="#{esc(sa)}-rt">{esc(nm)}</a>'
    if "mdlt" in tag: return f'<a class="Link" href="#{esc(sa)}-mdlt">{esc(nm)}</a>'
    return f'<i>{esc(nm)}:{esc(per)}-{esc(off)}<sub>[From Current Position:EXPECT_ONE]</sub></i>'

def render_oref(elem):
    nm = elem.get("NAME",""); per = elem.get("PERIOD_TYPE","month"); ut = elem.get("UNIT_TYPE","")
    return f"<b>[{esc(nm)}, {esc(per)}{', ' + esc(ut) if ut else ''}]</b>"

def _rop(elem, depth=0):
    if elem is None: return ""
    tag = elem.tag.lower() if hasattr(elem,'tag') else ""
    if tag=="parameter_list": return ""
    if "_operator" in tag: return _r_op(elem, depth)
    if tag=="function": return _r_func(elem, depth)
    if tag=="event_type_expression": return _r_evtype(elem, depth)
    if any(x in tag for x in ["measurement_ref","incentive_ref","rule_element_ref"]): return render_ref(elem)
    if "variable_ref" in tag: return f'<a class="Link" href="#{esc(safe_anchor(elem.get("NAME","")))}-var">{esc(elem.get("NAME",""))}</a>'
    if "territory_ref" in tag: return f'<a class="Link" href="#{esc(safe_anchor(elem.get("NAME","")))}-terr">{esc(elem.get("NAME",""))}</a>'
    if "output_reference" in tag: return render_oref(elem)
    if "mdlt_ref" in tag: return f'<a class="Link" href="#{esc(safe_anchor(elem.get("NAME","")))}-mdlt">{esc(elem.get("NAME",""))}</a>'
    if "hold_ref" in tag:
        nm=elem.get("NAME",""); per=elem.get("PERIOD_TYPE",""); rls=elem.get("RELEASE_TYPE","")
        v=rls if rls else (nm + (f" ( {per} )" if per else ""))
        return esc(v)
    if "ratetable_ref" in tag: return f'<a class="Link" href="#{esc(safe_anchor(elem.get("NAME","")))}-rt">{esc(elem.get("NAME",""))}</a>'
    if tag=="data_field": return esc(gtxt(elem))
    if tag=="string_literal": t=gtxt(elem); return "NULL" if t.upper()=="NULL" else esc(t)
    if tag=="value": d=elem.get("DECIMAL_VALUE",""); u=elem.get("UNIT_TYPE",""); return esc(f"{d} {u}".strip())
    if tag=="boolean": return esc(elem.get("VALUE",""))
    if tag=="credit_type": return esc(gtxt(elem))
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
            mr_name = mr.get("NAME","")
            L.append(f'{ind}<td class="FunctionParameter"><a class="Link" href="#{esc(safe_anchor(mr_name))}-mdlt">{esc(mr_name)}</a><br></td>')
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
    fixed_action_label=None
    if fid=="DIRECT_TRANSACTION_CREDIT_ALLGAs":
        fixed_action_labels=[None,"Input Value","Hold Type","Credit Type","Allow Duplicates","Rollable"]
        if idx>=len(fixed_action_labels):
            return f"Generic Attribute {idx - len(fixed_action_labels) + 1}"
        fixed_action_label=fixed_action_labels[idx]
    if tag=="output_reference":
        if fid in ("PRIMARY_MEASUREMENT","SECONDARY_MEASUREMENT_GAS"): return "Measurement Output"
        return "Incentive Output" if ("INCENTIVE" in fid or "BULK" in fid) else "Credit Output"
    if fixed_action_label: return fixed_action_label
    if fid in ("PRIMARY_MEASUREMENT","SECONDARY_MEASUREMENT_GAS"):
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

def _is_null_generic_action_value(child):
    tag=child.tag.lower() if hasattr(child, "tag") else ""
    if tag=="string_literal": value=gtxt(child)
    elif tag=="value": value=child.get("DECIMAL_VALUE") or gtxt(child)
    elif tag=="boolean": value=child.get("VALUE") or gtxt(child)
    elif tag in ("date", "date_literal", "date_value"):
        value=child.get("VALUE") or child.get("DATE_VALUE") or child.get("DATE") or gtxt(child)
    else: return False
    return value.strip().upper()=="NULL"

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
        if _is_null_generic_action_value(child):
            pi+=1
            continue
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
            L.append(f'{ind}<td class="FunctionParameter">{esc(gtxt(child))}</td>')
        elif tag=="string_literal":
            t=gtxt(child); L.append(f'{ind}<td class="FunctionParameter">{"NULL" if t.upper()=="NULL" else esc(t)}</td>')
        elif tag=="value":
            d=child.get("DECIMAL_VALUE",""); u=child.get("UNIT_TYPE","")
            L.append(f'{ind}<td class="FunctionParameter">{esc((d+chr(32)+u).strip())}</td>')
        elif tag=="hold_ref":
            nm=child.get("NAME",""); per=child.get("PERIOD_TYPE",""); rls=child.get("RELEASE_TYPE","")
            v=rls if rls else (nm + (f" ( {per} )" if per else ""))
            L.append(f'{ind}<td class="FunctionParameter">{esc(v)}</td>')
        elif tag=="credit_type":
            L.append(f'{ind}<td class="FunctionParameter">{esc(gtxt(child))}</td>')
        elif tag=="boolean":
            L.append(f'{ind}<td class="FunctionParameter">{esc(child.get("VALUE",""))}</td>')
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
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        self.desc = e.get("DESCRIPTION", "")
        self.cn = []
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    @property
    def anchor(self):
        base = f"{safe_anchor(self.name)}-plan"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor

    def render(self, v, cm_map, rm_map):
        primary = self.anchor
        fallbacks = [f"{safe_anchor(self.name)}-plan"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(primary, self, fallbacks), f'<h2 class="SubSectionTitle">{esc(self.name)}{title_extra}</h2>']
        L.append('<table border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Effective Date Range</td><td class="Value">{esc(drange(self.st, self.en))}</td></tr>')
        L.append(f'<tr><td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td></tr>')
        L.append(render_metadata_rows(self))
        L.append('</table><p></p>')

        pcs = []
        for c in self.cn:
            matching = cm_map.get(c, []) if isinstance(cm_map, dict) else []
            if isinstance(matching, list):
                for comp in matching:
                    if comp not in pcs:
                        pcs.append(comp)
            elif matching and matching not in pcs:
                pcs.append(matching)
        pcs = sorted_objects(pcs)

        referenced_rules = []
        for pc in pcs:
            for rn in pc.rn:
                matching_rules = rm_map.get(rn, []) if isinstance(rm_map, dict) else []
                if isinstance(matching_rules, list):
                    for r in matching_rules:
                        if r not in referenced_rules:
                            referenced_rules.append(r)
                elif matching_rules and matching_rules not in referenced_rules:
                    referenced_rules.append(matching_rules)

        categories = rule_categories(referenced_rules)
        L.append('<table width="100%" border="0" cellpadding="0" cellspacing="5"><tr>')
        for h in ["Plan Components"] + [RULE_CATEGORY_HEADINGS[category] for category in categories]:
            L.append(f'<td class="ContentTitle">{h}</td>')
        L.append('</tr><tr>')
        clinks = []
        cats = {category: [] for category in categories}
        for pc in pcs:
            ca = pc.anchor_under_plan(self.name)
            pc_badge = f' <small style="color:var(--alert-red);font-size:11px;">({esc(pc.source_id or f"#{pc.duplicate_index}")})</small>' if pc.is_duplicate else ''
            clinks.append(f'<a class="Link" href="#{esc(ca)}">{esc(pc.name)}{pc_badge}</a>')
            for rn in pc.rn:
                matching_rules = rm_map.get(rn, []) if isinstance(rm_map, dict) else []
                if not isinstance(matching_rules, list):
                    matching_rules = [matching_rules] if matching_rules else []
                for r in sorted_rules(matching_rules):
                    category = rule_category(r)
                    ra = r.anchor_under_component(self.name, pc.name, pc=pc)
                    r_badge = f' <small style="color:var(--alert-red);font-size:11px;">({esc(r.source_id or f"#{r.duplicate_index}")})</small>' if r.is_duplicate else ''
                    link = f'<a class="Link" href="#{esc(ra)}">{esc(r.name)}{r_badge}</a>'
                    if link not in cats[category]:
                        cats[category].append(link)
        L.append(f'<td valign="top">{"<br>".join(clinks)}</td>')
        for category in categories:
            L.append(f'<td valign="top">{"<br>".join(cats[category])}</td>')
        L.append('</tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#plans">Plans</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class PComp:
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        self.desc = e.get("DESCRIPTION", "")
        self.rn = []
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    def anchor_under_plan(self, pn):
        base = f"{safe_anchor(self.name)}-plan-{safe_anchor(pn)}"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    def anchor_standalone(self):
        base = f"{safe_anchor(self.name)}-plancomponent"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor_standalone()

    def render(self, v, pn, rm_map):
        ca = self.anchor_under_plan(pn)
        fallbacks = [f"{safe_anchor(self.name)}-plan-{safe_anchor(pn)}"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(ca, self, fallbacks), f'<h2 class="ComponentObjectTitle">{esc(self.name)}{title_extra}</h2>']
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        L.append('<table border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td></tr>')
        L.append(f'<tr><td class="LabelCell">Effective</td><td class="Value">{esc(es)} to {esc(ee)}</td></tr>')
        L.append(render_metadata_rows(self))
        L.append('</table><p></p>')

        cr = []
        for rn in self.rn:
            matching = rm_map.get(rn, []) if isinstance(rm_map, dict) else []
            if isinstance(matching, list):
                for r in matching:
                    if r not in cr:
                        cr.append(r)
            elif matching and matching not in cr:
                cr.append(matching)
        cr = sorted_rules(cr)
        categories = rule_categories(cr)
        L.append('<table width="100%" border="0" cellpadding="0" cellspacing="5"><tr>')
        for category in categories:
            h = RULE_CATEGORY_HEADINGS[category]
            L.append(f'<td class="ContentTitle">{h}</td>')
        L.append('</tr><tr>')
        cats = {category: [] for category in categories}
        for r in cr:
            category = rule_category(r)
            ra = r.anchor_under_component(pn, self.name, pc=self)
            r_badge = f' <small style="color:var(--alert-red);font-size:11px;">({esc(r.source_id or f"#{r.duplicate_index}")})</small>' if r.is_duplicate else ''
            cats[category].append(f'<a class="Link" href="#{esc(ra)}">{esc(r.name)}{r_badge}</a>')
        for category in categories:
            L.append(f'<td valign="top">{"<br>".join(cats[category])}</td>')
        L.append('</tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        plan_anchor = f"{safe_anchor(pn)}-plan"
        L.append(f'<td class="LabelCell"><a class="Link" href="#{esc(plan_anchor)}">{esc(pn)}</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

    def render_standalone(self, v, rm_map):
        ca = self.anchor_standalone()
        fallbacks = [f"{safe_anchor(self.name)}-plancomponent"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(ca, self, fallbacks), f'<h2 class="ComponentObjectTitle">{esc(self.name)}{title_extra}</h2>']
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        L.append('<table border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td></tr>')
        L.append(f'<tr><td class="LabelCell">Effective</td><td class="Value">{esc(es)} to {esc(ee)}</td></tr>')
        L.append(render_metadata_rows(self))
        L.append('</table><p></p>')

        cr = []
        for rn in self.rn:
            matching = rm_map.get(rn, []) if isinstance(rm_map, dict) else []
            if isinstance(matching, list):
                for r in matching:
                    if r not in cr:
                        cr.append(r)
            elif matching and matching not in cr:
                cr.append(matching)
        cr = sorted_rules(cr)
        if cr:
            categories = rule_categories(cr)
            L.append('<table width="100%" border="0" cellpadding="0" cellspacing="5"><tr>')
            for category in categories:
                h = RULE_CATEGORY_HEADINGS[category]
                L.append(f'<td class="ContentTitle">{h}</td>')
            L.append('</tr><tr>')
            cats = {category: [] for category in categories}
            for r in cr:
                category = rule_category(r)
                ra = r.anchor_standalone()
                r_badge = f' <small style="color:var(--alert-red);font-size:11px;">({esc(r.source_id or f"#{r.duplicate_index}")})</small>' if r.is_duplicate else ''
                cats[category].append(f'<a class="Link" href="#{esc(ra)}">{esc(r.name)}{r_badge}</a>')
            for category in categories:
                L.append(f'<td valign="top">{"<br>".join(cats[category])}</td>')
            L.append('</tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#plancomponents">Plan Components</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class Rule:
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.rt = e.get("TYPE", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        self.eca = e.get("ISEVENTCONDITIONACTION", e.get("ECA", ""))
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    @property
    def heading(self):
        return f"{TYPE_HEADING.get(self.rt, 'Rule')}: {self.name}"

    def anchor_under_component(self, pn, cn, pc=None):
        base = f"{safe_anchor(self.name)}-rule-{safe_anchor(cn)}-{safe_anchor(pn)}"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    def anchor_standalone(self):
        base = f"{safe_anchor(self.name)}-rule"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor_standalone()

    def render(self, v, pn, cn, pc=None):
        anchor = self.anchor_under_component(pn, cn, pc=pc)
        fallbacks = [f"{safe_anchor(self.name)}-rule-{safe_anchor(cn)}-{safe_anchor(pn)}"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(anchor, self, fallbacks), f'<h2 class="ObjectTitle">{esc(self.heading)}{title_extra}</h2>']
        L.append('<table border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Type</td><td class="Value">{esc(TYPE_LABELS.get(self.rt, self.rt))}</td></tr>')
        if self.rt in ("DIRECT_TRANSACTION_CREDIT", "ROLLUP_TRANSACTION_CREDIT"):
            ev = "true" if self.eca and self.eca.lower() == "true" else "false"
            L.append(f'<tr><td class="LabelCell">ECA</td><td class="Value">{esc(ev)}</td></tr>')
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        L.append(f'<tr><td class="LabelCell">Effective Date Range</td><td class="Value">{esc(es)} - {esc(ee)}</td></tr>')
        L.append(render_metadata_rows(self))
        L.append('</table>')

        if self.rt == "DIRECT_TRANSACTION_CREDIT":
            evt = self.e.find("EVENT_TYPE_EXPRESSION")
            if evt is not None:
                L.append('<p></p><span class="ContentTitle">Event Type</span><p></p>')
                L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
                L.append(_r_evtype(evt))
                L.append('</td></tr></table>')
        cond = self.e.find("CONDITION_EXPRESSION")
        if cond is not None and len(cond):
            L.append('<p></p><span class="ContentTitle">Condition</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(cond))
            L.append('</td></tr></table>')
        terr = self.e.find("TERRITORY_EXPRESSION")
        if terr is not None and len(terr):
            L.append('<p></p><span class="ContentTitle">Territory</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(terr))
            L.append('</td></tr></table>')
        L.append('<p></p><span class="ContentTitle">Actions</span><p></p><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
        aes = self.e.find("ACTION_EXPRESSION_SET")
        if aes is not None:
            for ae in aes.findall("ACTION_EXPRESSION"):
                func = ae.find("FUNCTION")
                if func is not None:
                    L.append(render_action(func))
        else:
            acts = self.e.find("ACTIONS")
            if acts is not None:
                for act in acts.findall("ACTION"):
                    gf = act.find("GA_FUNCTION")
                    if gf is not None:
                        func = gf.find("FUNCTION")
                        if func is not None:
                            L.append(render_action(func))
        L.append('</td></tr></table>')
        ca = pc.anchor_under_plan(pn) if pc is not None else f"{safe_anchor(cn)}-plan-{safe_anchor(pn)}"
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#{esc(ca)}">{esc(cn)}</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

    def render_standalone(self, v):
        anchor = self.anchor_standalone()
        fallbacks = [f"{safe_anchor(self.name)}-rule"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(anchor, self, fallbacks), f'<h2 class="ObjectTitle">{esc(self.heading)}{title_extra}</h2>']
        L.append('<table border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Type</td><td class="Value">{esc(TYPE_LABELS.get(self.rt, self.rt))}</td></tr>')
        if self.rt in ("DIRECT_TRANSACTION_CREDIT", "ROLLUP_TRANSACTION_CREDIT"):
            ev = "true" if self.eca and self.eca.lower() == "true" else "false"
            L.append(f'<tr><td class="LabelCell">ECA</td><td class="Value">{esc(ev)}</td></tr>')
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        L.append(f'<tr><td class="LabelCell">Effective Date Range</td><td class="Value">{esc(es)} - {esc(ee)}</td></tr>')
        L.append(render_metadata_rows(self))
        L.append('</table>')

        if self.rt == "DIRECT_TRANSACTION_CREDIT":
            evt = self.e.find("EVENT_TYPE_EXPRESSION")
            if evt is not None:
                L.append('<p></p><span class="ContentTitle">Event Type</span><p></p>')
                L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
                L.append(_r_evtype(evt))
                L.append('</td></tr></table>')
        cond = self.e.find("CONDITION_EXPRESSION")
        if cond is not None and len(cond):
            L.append('<p></p><span class="ContentTitle">Condition</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(cond))
            L.append('</td></tr></table>')
        terr = self.e.find("TERRITORY_EXPRESSION")
        if terr is not None and len(terr):
            L.append('<p></p><span class="ContentTitle">Territory</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(terr))
            L.append('</td></tr></table>')
        L.append('<p></p><span class="ContentTitle">Actions</span><p></p><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
        aes = self.e.find("ACTION_EXPRESSION_SET")
        if aes is not None:
            for ae in aes.findall("ACTION_EXPRESSION"):
                func = ae.find("FUNCTION")
                if func is not None:
                    L.append(render_action(func))
        else:
            acts = self.e.find("ACTIONS")
            if acts is not None:
                for act in acts.findall("ACTION"):
                    gf = act.find("GA_FUNCTION")
                    if gf is not None:
                        func = gf.find("FUNCTION")
                        if func is not None:
                            L.append(render_action(func))
        L.append('</td></tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#rules">Rules</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class MDLT:
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        self.dims = []
        dn = e.find("DIM_NAMES")
        if dn is not None:
            for d in dn.findall("DIM_NAME"):
                self.dims.append(d.get("NAME", ""))
        self.cells = []
        ce = e.find("CELLS")
        if ce is not None:
            for c in ce.findall("CELL"):
                self.cells.append(c)
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    @property
    def anchor(self):
        base = f"{safe_anchor(self.name)}-mdlt"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor

    def _edt(self):
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        L = ['<p></p><span class="ContentTitle">Effective Date Range</span><p></p>']
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr>')
        L.append(render_metadata_rows(self))
        L.append('</table>')
        return "\n".join(L)

    def render(self, v):
        primary = self.anchor
        fallbacks = [f"{safe_anchor(self.name)}-mdlt"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(primary, self, fallbacks), f'<h2 class="ObjectTitle">{esc(self.name)}{title_extra}</h2>', self._edt()]
        L.append('<p></p><span class="ContentTitle">Cells</span><p></p>')
        L.append('<table class="ListTable"><tr>')
        for h in ["Title", "Component", "Value"]:
            L.append(f'<td class="ListHeaderCell">{h}</td>')
        L.append('</tr>')
        for cell in self.cells:
            dv = {}
            for d in cell.findall("DIM_VALUE"):
                dv[d.get("DIM_NAME", "")] = d.get("VALUE", "")
            title = ", ".join(f"{k}={v}" for k, v in dv.items())
            comp = ", ".join(self.dims)
            ve = cell.find("VALUE")
            val = f'{ve.get("DECIMAL_VALUE", "")} {ve.get("UNIT_TYPE", "")}'.strip() if ve is not None else ""
            L.append('<tr>')
            L.append(f'<td class="ListCell">{esc(title)}</td><td class="ListCell">{esc(comp)}</td><td class="ListCell">{esc(val)}</td>')
            L.append('</tr>')
        L.append('</table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#mdlts">Lookup Tables</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class FV:
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        fv = e.find("FIXED_VALUE_VALUE") or e.find("VALUE")
        if fv is not None:
            self.dv = fv.get("DECIMAL_VALUE", "")
            self.ut = fv.get("UNIT_TYPE", "")
        else:
            self.dv = self.ut = ""
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    @property
    def anchor(self):
        base = f"{safe_anchor(self.name)}-fv"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor

    def render(self, v):
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        val = f"{self.dv} {self.ut}".strip()
        primary = self.anchor
        fallbacks = [f"{safe_anchor(self.name)}-fv"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(primary, self, fallbacks), f'<h2 class="ObjectTitle">{esc(self.name)}{title_extra}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table class="ListTable"><tr>')
        for h in ["Start Date", "End Date", "Value"]:
            L.append(f'<td class="ListHeaderCell">{h}</td>')
        L.append('</tr><tr>')
        L.append(f'<td class="ListCell">{esc(es)}</td><td class="ListCell">{esc(ee)}</td><td class="ListCell">{esc(val)}</td>')
        L.append('</tr></table>')
        meta_rows = render_metadata_rows(self)
        if meta_rows:
            L.append('<table border="0" cellspacing="0" cellpadding="0">')
            L.append(meta_rows)
            L.append('</table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#fixedvalues">Fixed Values</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class Quota:
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        self.positions = list(e.findall("QUOTA_VALUE"))
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    @property
    def anchor(self):
        base = f"{safe_anchor(self.name)}-quota"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor

    def render(self, v):
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        primary = self.anchor
        fallbacks = [f"{safe_anchor(self.name)}-quota"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(primary, self, fallbacks), f'<h2 class="ObjectTitle">{esc(self.name)}{title_extra}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr>')
        L.append(render_metadata_rows(self))
        L.append('</table>')
        for pos in self.positions:
            pn = pos.get("POSITION_NAME", pos.get("NAME", ""))
            sp = pos.get("EFFECTIVE_START_DATE", "")
            ep = pos.get("EFFECTIVE_END_DATE", "")
            ve = pos.find("VALUE")
            vl = f'{ve.get("DECIMAL_VALUE", "")} {ve.get("UNIT_TYPE", "")}'.strip() if ve is not None else pos.get("QUOTA_VALUE", "")
            L.append(f'<p></p><span class="ContentTitle">{esc(pn)}</span><p></p>')
            L.append('<table class="ListTable"><tr>')
            for h in ["Start Period", "End Period", "Value"]:
                L.append(f'<td class="ListHeaderCell">{h}</td>')
            L.append('</tr><tr>')
            L.append(f'<td class="ListCell">{esc(sp)}</td><td class="ListCell">{esc(ep)}</td><td class="ListCell">{esc(vl)}</td>')
            L.append('</tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#quotas">Quotas</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class Formula:
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        self.rt = e.get("RETURN_TYPE", "")
        self.desc = e.get("DESCRIPTION", "")
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    @property
    def anchor(self):
        base = f"{safe_anchor(self.name)}-formula"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor

    def render(self, v):
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        primary = self.anchor
        fallbacks = [f"{safe_anchor(self.name)}-formula"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(primary, self, fallbacks), f'<h2 class="ObjectTitle">{esc(self.name)}{title_extra}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr>')
        L.append(render_metadata_rows(self))
        L.append('</table>')
        L.append('<p></p><span class="ContentTitle">Return Type</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Return Type</td><td class="Value">{esc(self.rt)}</td>')
        L.append('</tr></table>')
        if self.desc:
            L.append('<p></p><span class="ContentTitle">Description</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
            L.append(f'<td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td>')
            L.append('</tr></table>')
        expr = self.e.find("EXPRESSION")
        if expr is not None and len(expr):
            L.append('<p></p><span class="ContentTitle">Formula</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(expr))
            L.append('</td></tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#formulas">Formulas</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class Territory:
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        self.desc = e.get("DESCRIPTION", "")
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    @property
    def anchor(self):
        base = f"{safe_anchor(self.name)}-terr"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor

    def render(self, v):
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        primary = self.anchor
        fallbacks = [f"{safe_anchor(self.name)}-terr"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(primary, self, fallbacks), f'<h2 class="ObjectTitle">{esc(self.name)}{title_extra}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr>')
        L.append(render_metadata_rows(self))
        L.append('</table>')
        if self.desc:
            L.append('<p></p><span class="ContentTitle">Description</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
            L.append(f'<td class="LabelCell">Description</td><td class="Value">{esc(self.desc)}</td>')
            L.append('</tr></table>')
        expr = self.e.find("EXPRESSION")
        if expr is not None and len(expr):
            L.append('<p></p><span class="ContentTitle">Territory</span><p></p>')
            L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr><td class="ContentBox">')
            L.append(render_expr(expr))
            L.append('</td></tr></table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#territories">Territories</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class Variable:
    def __init__(self, e):
        self.e = e
        self.name = e.get("NAME", "")
        self.st = e.get("EFFECTIVE_START_DATE", "")
        self.en = e.get("EFFECTIVE_END_DATE", "")
        self.vt = e.get("VARIABLE_TYPE", "")
        self.pt = e.get("PERIOD_TYPE", "")
        self.dv = e.get("DEFAULT_VALUE", "")
        self.assignments = list(e.findall("VARIABLE_ASSIGNMENT"))
        self.source_file = ""
        self.source_id = e.get("ID") or e.get("OBJECT_ID") or ""
        self.xml_path = ""
        self.instance_id = ""
        self.is_duplicate = False
        self.duplicate_index = 1
        self.duplicate_total = 1

    @property
    def anchor(self):
        base = f"{safe_anchor(self.name)}-var"
        if self.is_duplicate and self.duplicate_index > 1:
            return f"{base}-dup-{self.duplicate_index}"
        return base

    @property
    def primary_anchor(self):
        return self.anchor

    def render(self, v):
        es = fd(self.st)
        ee = fd(self.en)
        if not ee or "2200" in ee or "2099" in ee:
            ee = "End of Time"
        primary = self.anchor
        fallbacks = [f"{safe_anchor(self.name)}-var"] if (self.is_duplicate and self.duplicate_index == 1) else []
        title_extra = f' <small style="font-size:12px;color:var(--alert-red);">(Instance {self.duplicate_index} of {self.duplicate_total})</small>' if self.is_duplicate else ''
        L = [render_anchor_tags(primary, self, fallbacks), f'<h2 class="ObjectTitle">{esc(self.name)}{title_extra}</h2>']
        L.append('<p></p><span class="ContentTitle">Effective Date Range</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell">Start Date</td><td class="Value">{esc(es)}</td>')
        L.append(f'<td class="LabelCell">End Date</td><td class="Value">{esc(ee)}</td>')
        L.append('</tr>')
        L.append(render_metadata_rows(self))
        L.append('</table>')
        L.append('<p></p><span class="ContentTitle">Variable</span><p></p>')
        L.append('<table width="100%" border="0" cellspacing="0" cellpadding="0">')
        L.append(f'<tr><td class="LabelCell">Type</td><td class="Value">{esc(self.vt)}</td></tr>')
        if self.pt:
            L.append(f'<tr><td class="LabelCell">Period Type</td><td class="Value">{esc(self.pt)}</td></tr>')
        L.append(f'<tr><td class="LabelCell">Default</td><td class="Value">{esc(self.dv)}</td></tr>')
        L.append('</table>')
        L.append('<p></p><span class="ContentTitle">Assignments</span><p></p>')
        L.append('<table class="ListTable"><tr>')
        for h in ["Plan", "Owner", "Owner Type", "Assignment"]:
            L.append(f'<td class="ListHeaderCell">{h}</td>')
        L.append('</tr>')
        if self.assignments:
            for va in self.assignments:
                L.append('<tr>')
                L.append(f'<td class="ListCell">{esc(va.get("PLAN_NAME", ""))}</td>')
                L.append(f'<td class="ListCell">{esc(va.get("OWNER_NAME", ""))}</td>')
                L.append(f'<td class="ListCell">{esc(va.get("OWNER_TYPE", ""))}</td>')
                L.append(f'<td class="ListCell">{esc(va.get("ASSIGNMENT_VALUE", ""))}</td>')
                L.append('</tr>')
        else:
            L.append('<tr><td class="ListCell"></td><td class="ListCell"></td><td class="ListCell"></td><td class="ListCell"></td></tr>')
        L.append('</table>')
        L.append('<p></p><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>')
        L.append(f'<td class="LabelCell"><a class="Link" href="#variables">Variables</a> | <a class="Link" href="#Top">Top</a></td>')
        L.append('</tr>')
        L.append('</table>')
        return "\n".join(L)

class Transformer:
    def __init__(self, variant="A"):
        self.v = variant
        self.plans = []
        self.comps = []
        self.rules = []
        self.mdlts = []
        self.fvs = []
        self.quotas = []
        self.formulas = []
        self.terrs = []
        self.vars = []
        self._comps_by_name = defaultdict(list)
        self._rules_by_name = defaultdict(list)
        self.ver = ""
        self.parsed_files = []

    def _compute_duplicates(self):
        all_collections = [
            ("plans", self.plans),
            ("plancomponents", self.comps),
            ("rules", self.rules),
            ("mdlts", self.mdlts),
            ("fixedvalues", self.fvs),
            ("quotas", self.quotas),
            ("formulas", self.formulas),
            ("territories", self.terrs),
            ("variables", self.vars),
        ]
        for _, items in all_collections:
            groups = defaultdict(list)
            for item in items:
                groups[item.name].append(item)
            for _, members in groups.items():
                if len(members) > 1:
                    for idx, member in enumerate(members, start=1):
                        member.is_duplicate = True
                        member.duplicate_index = idx
                        member.duplicate_total = len(members)
                else:
                    for member in members:
                        member.is_duplicate = False
                        member.duplicate_index = 1
                        member.duplicate_total = 1

    def parse(self, path, source_file=None, snapshot_id="configuration"):
        if source_file is None:
            source_file = Path(path).name
        if source_file not in self.parsed_files:
            self.parsed_files.append(source_file)
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError as e:
            raise XErr(f"XML parse error", details=str(e))
        if root.tag != "DATA_IMPORT":
            raise XErr(f"Expected DATA_IMPORT, got {root.tag}")
        if not self.ver:
            self.ver = root.get("VERSION", "")

        paths = _build_paths(root)

        for se in root:
            tag = se.tag
            try:
                if tag == "PLAN_SET":
                    for pe in se.findall("PLAN"):
                        p = Plan(pe)
                        p.source_file = source_file
                        p.xml_path = paths.get(id(pe), "")
                        p.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("Plan", pe, p.name), p.xml_path)
                        p.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("Plan", pe, p.name), p.xml_path)
                        for cr in pe.findall("COMPONENT_REF"):
                            cn = cr.get("NAME", "")
                            if cn:
                                p.cn.append(cn)
                        comps = pe.find("COMPONENTS")
                        if comps is not None:
                            for c in comps.findall("COMPONENT"):
                                cn = c.get("NAME", "")
                                if cn and cn not in p.cn:
                                    p.cn.append(cn)
                        self.plans.append(p)
                elif tag == "PLANCOMPONENT_SET":
                    for ce in se.findall("PLANCOMPONENT"):
                        c = PComp(ce)
                        c.source_file = source_file
                        c.xml_path = paths.get(id(ce), "")
                        c.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("PlanComponent", ce, c.name), c.xml_path)
                        c.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("PlanComponent", ce, c.name), c.xml_path)
                        rre = ce.find("RULE_REFS")
                        if rre is not None:
                            for rr in rre.findall("RULE_REF"):
                                rn = rr.get("NAME", "")
                                if rn:
                                    c.rn.append(rn)
                        for rr in ce.findall("RULE_REF"):
                            rn = rr.get("NAME", "")
                            if rn and rn not in c.rn:
                                c.rn.append(rn)
                        self.comps.append(c)
                        self._comps_by_name[c.name].append(c)
                elif tag == "RULE_SET":
                    for re_el in se.findall("RULE"):
                        r = Rule(re_el)
                        r.source_file = source_file
                        r.xml_path = paths.get(id(re_el), "")
                        r.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("Rule", re_el, r.name), r.xml_path)
                        r.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("Rule", re_el, r.name), r.xml_path)
                        self.rules.append(r)
                        self._rules_by_name[r.name].append(r)
                elif tag == "MD_LOOKUP_TABLE_SET":
                    for e in se.findall("MD_LOOKUP_TABLE"):
                        m = MDLT(e)
                        m.source_file = source_file
                        m.xml_path = paths.get(id(e), "")
                        m.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("LookupTable", e, m.name), m.xml_path)
                        m.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("LookupTable", e, m.name), m.xml_path)
                        self.mdlts.append(m)
                elif tag == "FIXED_VALUE_SET":
                    for e in se.findall("FIXED_VALUE"):
                        fv = FV(e)
                        fv.source_file = source_file
                        fv.xml_path = paths.get(id(e), "")
                        fv.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("FixedValue", e, fv.name), fv.xml_path)
                        fv.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("FixedValue", e, fv.name), fv.xml_path)
                        self.fvs.append(fv)
                elif tag == "QUOTA_SET":
                    for e in se.findall("QUOTA"):
                        q = Quota(e)
                        q.source_file = source_file
                        q.xml_path = paths.get(id(e), "")
                        q.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("Quota", e, q.name), q.xml_path)
                        q.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("Quota", e, q.name), q.xml_path)
                        self.quotas.append(q)
                elif tag == "FORMULA_SET":
                    for e in se.findall("FORMULA"):
                        f = Formula(e)
                        f.source_file = source_file
                        f.xml_path = paths.get(id(e), "")
                        f.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("Formula", e, f.name), f.xml_path)
                        f.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("Formula", e, f.name), f.xml_path)
                        self.formulas.append(f)
                elif tag == "TERRITORY_SET":
                    for e in se.findall("TERRITORY"):
                        t = Territory(e)
                        t.source_file = source_file
                        t.xml_path = paths.get(id(e), "")
                        t.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("Territory", e, t.name), t.xml_path)
                        t.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("Territory", e, t.name), t.xml_path)
                        self.terrs.append(t)
                elif tag == "VARIABLE_SET":
                    for e in se.findall("VARIABLE"):
                        v = Variable(e)
                        v.source_file = source_file
                        v.xml_path = paths.get(id(e), "")
                        v.instance_id = compute_instance_id(snapshot_id, source_file, canonical_key_for("Variable", e, v.name), v.xml_path)
                        v.config_instance_id = compute_instance_id("configuration", source_file, canonical_key_for("Variable", e, v.name), v.xml_path)
                        self.vars.append(v)
            except Exception as e:
                raise XErr(f"Parse error in {tag}", details=str(e)) from e

        self._compute_duplicates()

        if self.v == "B":
            return
        if self.ver >= "17.0" or len(self.plans) >= 2:
            self.v = "B"
            return
        for r in self.rules:
            bu = r.e.get("BUSINESS_UNITS", "")
            if bu and bu not in ("__ALL_BU__", ""):
                self.v = "B"
                break

    def _so(self, a):
        objects = {
            "plans": self.plans,
            "plancomponents": self.comps,
            "rules": self.rules,
            "mdlts": self.mdlts,
            "fixedvalues": self.fvs,
            "quotas": self.quotas,
            "formulas": self.formulas,
            "territories": self.terrs,
            "variables": self.vars,
        }.get(a, [])
        return sorted_rules(objects) if a == "rules" else sorted_objects(objects)

    def _plan_components(self, plan):
        comps = []
        for name in plan.cn:
            matching = self._comps_by_name.get(name, [])
            for c in matching:
                if c not in comps:
                    comps.append(c)
        return sorted_objects(comps)

    def _component_rules(self, component):
        rules = []
        for name in component.rn:
            matching = self._rules_by_name.get(name, [])
            for r in matching:
                if r not in rules:
                    rules.append(r)
        return sorted_rules(rules)

    def _plan_rule_occurrences(self, plan):
        occurrences = []
        for component in self._plan_components(plan):
            for rule in self._component_rules(component):
                occurrences.append((component, rule))
        return sorted(occurrences, key=lambda item: (rule_sort_key(item[1]), object_sort_key(item[0])))

    def html(self, theme="light"):
        if theme not in {"light", "dark"}:
            raise XErr(f"Unsupported theme: {theme}")
        self._compute_duplicates()
        v = self.v
        L = [
            '<!DOCTYPE HTML>',
            f'<html data-theme="{theme}">',
            '<head>',
            '<META http-equiv="Content-Type" content="text/html; charset=UTF-8">',
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:;">',
            '<title>SAP Incentive Management Plan Summary</title>',
            f'<style type="text/css">{CSS}</style>',
            '</head>',
            '<body class="Body">',
        ]
        if v == "B":
            L.append(f'<p style="text-align: center;"><img src="data:image/png;base64,{SAP_LOGO_B64}" alt="SAP"></p>')
        L.append('<a name="Top"></a>')
        L.append('<p></p><span class="PageTitle">SAP Incentive Management Plan Summary</span><p></p><p></p>')
        L.append(self._idx())

        rendered_comps = set()
        rendered_rules = set()

        for anchor, dname, sname in SECTION_ORDER:
            objs = self._so(anchor)
            if not objs:
                if anchor in ("quotas", "territories"):
                    continue
                L.append(f'<a name="{anchor}"></a><h1 class="SectionTitle">{dname} (0)</h1><p></p>')
                continue
            L.append(f'<a name="{anchor}"></a>')
            L.append(f'<h1 xmlns:java="http://xml.apache.org/xalan/java" class="SectionTitle" width="100%">{dname}</h1><p></p>')
            for obj in objs:
                try:
                    if anchor == "plans":
                        L.append(render_object_section(OBJECT_TYPE_BY_SECTION[anchor], obj.name, obj.render(v, self._comps_by_name, self._rules_by_name), obj=obj))
                        L.append('<p></p>')
                        for comp in self._plan_components(obj):
                            rendered_comps.add(id(comp))
                            L.append(render_object_section(OBJECT_TYPE_BY_SECTION["plancomponents"], comp.name, comp.render(v, obj.name, self._rules_by_name), obj=comp))
                            L.append('<p></p>')
                        for comp, rule in self._plan_rule_occurrences(obj):
                            rendered_rules.add(id(rule))
                            L.append(render_object_section(OBJECT_TYPE_BY_SECTION["rules"], rule.name, rule.render(v, obj.name, comp.name, pc=comp), obj=rule))
                            L.append('<p></p>')
                    else:
                        object_type = OBJECT_TYPE_BY_SECTION[anchor]
                        L.append(render_object_section(object_type, obj.name, obj.render(v), obj=obj))
                        L.append('<p></p>')
                except Exception as e:
                    on = getattr(obj, 'name', '?')
                    raise XErr("Render error", obj_name=on, obj_type=type(obj).__name__, details=str(e)) from e

        # Render any unassigned Plan Components
        unrendered_comps = [c for c in self.comps if id(c) not in rendered_comps]
        if unrendered_comps:
            heading = "Plan Components" if not self.plans else "Unassigned Plan Components"
            L.append('<a name="plancomponents"></a>')
            L.append(f'<h1 class="SectionTitle">{heading} ({len(unrendered_comps)})</h1><p></p>')
            for comp in sorted_objects(unrendered_comps):
                L.append(render_object_section(OBJECT_TYPE_BY_SECTION["plancomponents"], comp.name, comp.render_standalone(v, self._rules_by_name), obj=comp))
                L.append('<p></p>')

        # Render any unassigned Rules
        unrendered_rules = [r for r in self.rules if id(r) not in rendered_rules]
        if unrendered_rules:
            heading = "Rules" if not self.plans else "Unassigned Rules"
            L.append('<a name="rules"></a>')
            L.append(f'<h1 class="SectionTitle">{heading} ({len(unrendered_rules)})</h1><p></p>')
            for rule in sorted_rules(unrendered_rules):
                L.append(render_object_section(OBJECT_TYPE_BY_SECTION["rules"], rule.name, rule.render_standalone(v), obj=rule))
                L.append('<p></p>')

        L.append('</body></html>')
        return "\n".join(L)

    def _summary_anchors(self):
        component_anchors = {}
        rule_anchors = {}
        for plan in self._so("plans"):
            for component in self._plan_components(plan):
                ca = component.anchor_under_plan(plan.name)
                component_anchors.setdefault(id(component), ca)
                component_anchors.setdefault(component.name, ca)
                for rule in self._component_rules(component):
                    ra = rule.anchor_under_component(plan.name, component.name, pc=component)
                    rule_anchors.setdefault(id(rule), ra)
                    rule_anchors.setdefault(rule.name, ra)
        for comp in self.comps:
            if id(comp) not in component_anchors:
                ca = comp.anchor_standalone()
                component_anchors.setdefault(id(comp), ca)
                component_anchors.setdefault(comp.name, ca)
        for rule in self.rules:
            if id(rule) not in rule_anchors:
                ra = rule.anchor_standalone()
                rule_anchors.setdefault(id(rule), ra)
                rule_anchors.setdefault(rule.name, ra)
        return component_anchors, rule_anchors

    def _summary_entries(self, anchor):
        component_anchors, rule_anchors = self._summary_anchors()
        entries = []
        object_type = OBJECT_TYPE_BY_SECTION[anchor]
        for obj in self._so(anchor):
            name = getattr(obj, "name", "")
            if anchor == "plancomponents":
                target = component_anchors.get(id(obj)) or component_anchors.get(name)
            elif anchor == "rules":
                target = rule_anchors.get(id(obj)) or rule_anchors.get(name)
            else:
                target = getattr(obj, "primary_anchor", getattr(obj, "anchor", None))

            disp_name = esc(name)
            if getattr(obj, "is_duplicate", False):
                details = []
                sid = getattr(obj, "source_id", "")
                sf = getattr(obj, "source_file", "")
                if sid:
                    details.append(sid)
                if sf and len(self.parsed_files) > 1:
                    details.append(sf)
                if not details:
                    details.append(f"#{getattr(obj, 'duplicate_index', 1)}")
                disp_text = f'{disp_name} <small class="SummaryDetail" style="color: var(--alert-red); font-size: 11px;">({esc(", ".join(details))})</small>'
            else:
                disp_text = disp_name

            if target:
                content = f'<a class="Link" href="#{esc(target)}">{disp_text}</a>'
            else:
                content = f'<span class="SummaryItem">{disp_text}</span>'
            entries.append(render_object_entry(object_type, name, content, obj=obj))
        return entries

    def _idx(self):
        L=['<h1 class="SectionTitle">Plan Summary</h1>', '<table class="SummaryTable">']
        for anchor,dname in SUMMARY_ORDER:
            entries=self._summary_entries(anchor)
            L.append(f'<tr><th colspan="{SUMMARY_COLUMN_COUNT}" class="SummaryHeader">{esc(dname)} ({len(entries)})</th></tr>')
            rows=[entries[i:i + SUMMARY_COLUMN_COUNT] for i in range(0, len(entries), SUMMARY_COLUMN_COUNT)] or [[]]
            for row in rows:
                L.append('<tr>')
                for entry in row:
                    L.append(f'<td class="SummaryCell">{entry}</td>')
                for _ in range(SUMMARY_COLUMN_COUNT-len(row)):
                    L.append('<td class="SummaryCell">&nbsp;</td>')
                L.append('</tr>')
        L.append('</table><p></p>')
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
