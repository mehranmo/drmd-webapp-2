# app.py (partial) – Admin rev 3 (XML‑load + tweaks) up to Properties tab
# -----------------------------------------------------------------------------
# Imports (include every lib used elsewhere so later tabs keep working)
import re, math, uuid, base64, functools, traceback, io
from datetime import date
from xml.dom import minidom
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st
import xmlschema
from rdflib import Graph, Namespace

# pretty‑print / XSLT (used in Export tab later)
try:
    from lxml import etree
except ImportError:
    st.error("lxml is required. Please install it via pip install lxml.")

# -----------------------------------------------------------------------------
# Page config & global CSS tweaks (consistent typography)
st.set_page_config(layout="wide")







# -----------------------------------------------------------------------------
# Helpers & constants
DEFAULT_XSD_PATH = "./drmd.xsd"
DEFAULT_XSL_PATH = "./drmd.xsl"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SCHEMA_VERSION = "0.2.0"
ALLOWED_TITLES = ["referenceMaterialCertificate", "productInformationSheet"]  # default first
ALLOWED_ISSUERS = ["referenceMaterialProducer", "customer", "owner", "other"]

INIT_IDENT = {"issuer": "referenceMaterialProducer", "value": "", "idName": ""}
DEFAULT_PRODUCER = {
    "producerName": "",
    "producerStreet": "",
    "producerStreetNo": "",
    "producerPostCode": "",
    "producerCity": "",
    "producerCountryCode": "",
    "producerPhone": "",
    "producerFax": "",
    "producerEmail": ""
}
DEFAULT_PERSON = {
    "personName": "",
    "description": "",
    "role": "",
    "mainSigner": False,
    "cryptElectronicSeal": False,
    "cryptElectronicSignature": False,
    "cryptElectronicTimeStamp": False,
}
OFFICIAL_STMPL = {
    k: {"name": "", "content": ""} for k in [
        "intendedUse", "commutability", "storageInformation",
        "instructionsForHandlingAndUse", "metrologicalTraceability",
        "healthAndSafetyInformation", "subcontractors", "legalNotice",
        "referenceToCertificationReport",
    ]
}

# -----------------------------------------------------------------------------
# Misc helpers

@st.cache_resource
def get_default_ui_settings():
    return {
        "font_scale": 0.85,
    }


def render_ui_settings_panel():
    st.sidebar.markdown("---")
    st.sidebar.markdown("### UI Settings")

    font_scale = st.sidebar.slider(
        "🔠 Font Size (rem)", 0.6, 1.2, st.session_state.ui_font_scale, 0.05
    )
    if font_scale != st.session_state.ui_font_scale:
        st.session_state.ui_font_scale = font_scale
        st.rerun()

    if st.sidebar.button("Reset UI Settings"):
        st.session_state.ui_font_scale = get_default_ui_settings()["font_scale"]
        st.rerun()

if "ui_font_scale" not in st.session_state:
    st.session_state.ui_font_scale = get_default_ui_settings()["font_scale"]

fs = st.session_state["ui_font_scale"]
pad = round(fs * 0.6, 2)

st.markdown(
    f"""
    <style>
    html, body, [class*="css"] {{
        font-size: {fs}rem !important;
        line-height: {fs * 1.4:.2f}rem !important;
    }}

    /* Expander header */
    summary {{
        font-size: {fs}rem !important;
        font-weight: 600 !important;
    }}

    /* Labels for inputs, sliders, checkboxes, radios, etc. */
    label, div[data-baseweb="checkbox"] span, div[data-baseweb="radio"] span,
    .stSelectbox label, .stTextInput label, .stNumberInput label,
    .stTextArea label, .stSlider label, .stFileUploader label,
    .stMultiSelect label, .stRadio label {{
        font-size: {fs}rem !important;
    }}

    /* Input field text */
    input[type="text"], input[type="number"], textarea {{
        font-size: {fs}rem !important;
        padding: {pad/1.5}rem !important;
    }}

    /* Selected option in dropdowns */
    .stSelectbox div[data-testid="stSelectbox"] > div,
    .stSelectbox > div > div {{
        font-size: {fs}rem !important;
    }}

    /* Button text */
    .stButton button, .stDownloadButton button, .stFormSubmitButton button {{
        font-size: {fs}rem !important;
        padding: {pad/2}rem {pad}rem !important;
    }}

    /* Markdown text (e.g. inside st.markdown or st.write) */
    .stMarkdown p {{
        font-size: {fs}rem !important;
    }}

    /* Tooltips (info icons) */
    .stTooltip {{
        font-size: {fs * 0.9:.2f}rem !important;
    }}

    /* DataFrame table font */
    .stDataFrame div[role="table"], .stDataTable div[role="table"] {{
        font-size: {fs}rem !important;
    }}

    /* Sidebar widgets */
    section[data-testid="stSidebar"] * {{
        font-size: {fs}rem !important;
    }}

    .sticky-right {{
        position: sticky;
        top: 3.5rem; /* adjust if you have headers above */
        background: white;
        z-index: 999;
        padding-bottom: 1rem;
      }}

    </style>
    """,
    unsafe_allow_html=True,
)


def clean_text(txt: str) -> str:
    return re.sub(r"\s+", " ", txt or "").strip()

def xs_duration_hint() -> str:
    return "Enter a valid xs:duration – e.g. P1Y6M means 1 year 6 months"

# Data‑editor wrapper

def data_editor_df(df: pd.DataFrame, key: str, **kwargs) -> pd.DataFrame:
    try:
        updated = st.data_editor(df, key=key, **kwargs)
    except TypeError:
        updated = st.data_editor(df, key=key)
    if key in st.session_state and hasattr(st.session_state[key], "edited_rows"):
        for row_idx, changes in st.session_state[key].edited_rows.items():
            for col, new_val in changes.items():
                updated.at[int(row_idx), col] = new_val
    return updated

# QUDT cache (Properties tab later)
@st.cache_data
def load_qudt():
    g = Graph(); g.parse("qudt.ttl", format="turtle")
    Q = Namespace("http://qudt.org/schema/qudt/")
    res = {}
    for s in g.subjects(None, Q.QuantityKind):
        qn = s.split("/")[-1]
        res[qn] = [u.split("/")[-1] for u in g.objects(s, Q.applicableUnit)] or ["Custom"]
    return res
qudt_quantities = load_qudt()

# Factories used later (Properties tab)

def create_empty_materialProperties():
    return {
        "uuid": str(uuid.uuid4()),
        "id": "",
        "name": "",
        "description": "",
        "procedures": "",
        "isCertified": False,
        "results": [],
    }

def create_empty_result():
    return {
        "result_name": "",
        "description": "",
        "quantities": pd.DataFrame(columns=[
            "Name", "Label", "Value", "Quantity Kind", "Unit",
            "Uncertainty", "Coverage Factor", "Coverage Probability", "Distribution",
        ]),
    }

# -----------------------------------------------------------------------------
# XML → session‑state loader (comprehensive - loads all tabs and fields)

def load_xml_into_state(xml_bytes: bytes):
    try:
        tree = ET.parse(io.BytesIO(xml_bytes))
        root = tree.getroot()

        # Define namespaces
        ns = {
            "drmd": "https://example.org/drmd",
            "dcc": "https://ptb.de/dcc",
            "si": "https://ptb.de/si",
            "ds": "http://www.w3.org/2000/09/xmldsig#"
        }

        # Try to extract namespace from root tag if possible
        ns_match = re.match(r'\{(.*?)\}', root.tag)
        if ns_match:
            ns["drmd"] = ns_match.group(1)

        # Load title and unique identifier
        title_elem = root.find(".//drmd:titleOfTheDocument", ns)
        if title_elem is not None and title_elem.text:
            st.session_state.title_option = title_elem.text.strip() if title_elem.text.strip() in ALLOWED_TITLES else ALLOWED_TITLES[0]

        uid_elem = root.find(".//drmd:uniqueIdentifier", ns)
        if uid_elem is not None and uid_elem.text:
            st.session_state.persistent_id = uid_elem.text.strip()
            st.session_state.persistent_id_value = uid_elem.text.strip()

        # Load validity
        validity_elem = root.find(".//drmd:validity", ns)
        if validity_elem is not None:
            if validity_elem.find("drmd:untilRevoked", ns) is not None:
                st.session_state.validity_type = "Until Revoked"
            elif validity_elem.find("drmd:timeAfterDispatch", ns) is not None:
                st.session_state.validity_type = "Time After Dispatch"
                period_elem = validity_elem.find("drmd:timeAfterDispatch/drmd:period", ns)
                if period_elem is not None and period_elem.text:
                    st.session_state.raw_validity_period = period_elem.text.strip()
                dd_elem = validity_elem.find("drmd:timeAfterDispatch/drmd:dispatchDate", ns)
                if dd_elem is not None and dd_elem.text:
                    try:
                        st.session_state.date_of_issue = date.fromisoformat(dd_elem.text.strip())
                    except ValueError:
                        st.session_state.date_of_issue = date.today()
            elif validity_elem.find("drmd:specificTime", ns) is not None:
                st.session_state.validity_type = "Specific Time"
                spec_elem = validity_elem.find("drmd:specificTime", ns)
                if spec_elem is not None and spec_elem.text:
                    try:
                        st.session_state.specific_time = date.fromisoformat(spec_elem.text.strip())
                    except ValueError:
                        st.session_state.specific_time = date.today()

        # Load identifications
        idents = []
        for ident_elem in root.findall(".//drmd:identifications/drmd:identification", ns):
            issuer = ident_elem.find("drmd:issuer", ns)
            value = ident_elem.find("drmd:value", ns)
            name_elem = ident_elem.find("drmd:name/dcc:content", ns)
            idents.append({
                "issuer": issuer.text.strip() if issuer is not None and issuer.text else "referenceMaterialProducer",
                "value": value.text.strip() if value is not None and value.text else "",
                "idName": " ".join(name_elem.text.split()) if name_elem is not None and name_elem.text else ""
            })
        if idents:
            st.session_state.identifications = idents
        else:
            st.session_state.identifications = [INIT_IDENT.copy()]

        # Load Producers
        prods = []
        for prod_elem in root.findall(".//drmd:referenceMaterialProducer", ns):
            name_elem = prod_elem.find("drmd:name/dcc:content", ns)
            contact_elem = prod_elem.find("drmd:contact", ns)
            street = streetNo = postCode = city = country = phone = fax = email = ""
            if contact_elem is not None:
                # Get location information
                loc = contact_elem.find("dcc:location", ns)
                if loc is not None:
                    street = loc.find("dcc:street", ns).text.strip() if loc.find("dcc:street", ns) is not None and loc.find("dcc:street", ns).text else ""
                    streetNo = loc.find("dcc:streetNo", ns).text.strip() if loc.find("dcc:streetNo", ns) is not None and loc.find("dcc:streetNo", ns).text else ""
                    postCode = loc.find("dcc:postCode", ns).text.strip() if loc.find("dcc:postCode", ns) is not None and loc.find("dcc:postCode", ns).text else ""
                    city = loc.find("dcc:city", ns).text.strip() if loc.find("dcc:city", ns) is not None and loc.find("dcc:city", ns).text else ""
                    country = loc.find("dcc:countryCode", ns).text.strip() if loc.find("dcc:countryCode", ns) is not None and loc.find("dcc:countryCode", ns).text else ""
                phone = contact_elem.find("dcc:phone", ns).text.strip() if contact_elem.find("dcc:phone", ns) is not None and contact_elem.find("dcc:phone", ns).text else ""
                fax = contact_elem.find("dcc:fax", ns).text.strip() if contact_elem.find("dcc:fax", ns) is not None and contact_elem.find("dcc:fax", ns).text else ""
                email = contact_elem.find("dcc:eMail", ns).text.strip() if contact_elem.find("dcc:eMail", ns) is not None and contact_elem.find("dcc:eMail", ns).text else ""
            prods.append({
                "producerName": name_elem.text.strip() if name_elem is not None and name_elem.text else "",
                "producerStreet": street,
                "producerStreetNo": streetNo,
                "producerPostCode": postCode,
                "producerCity": city,
                "producerCountryCode": country,
                "producerPhone": phone,
                "producerFax": fax,
                "producerEmail": email
            })
        if prods:
            st.session_state.producers = prods

        # Load Responsible Persons
        rps = []
        for rp_elem in root.findall(".//drmd:respPersons/dcc:respPerson", ns):
            person_elem = rp_elem.find("dcc:person/dcc:name/dcc:content", ns)
            name = person_elem.text.strip() if person_elem is not None and person_elem.text else ""
            desc_elems = rp_elem.findall("dcc:description/dcc:content", ns)
            description = " ".join([d.text.strip() for d in desc_elems if d is not None and d.text]) if desc_elems else ""
            role_elem = rp_elem.find("dcc:role", ns)
            role = role_elem.text.strip() if role_elem is not None and role_elem.text else ""
            mainSigner_elem = rp_elem.find("dcc:mainSigner", ns)
            mainSigner = (mainSigner_elem.text.strip().lower() == "true") if mainSigner_elem is not None and mainSigner_elem.text else False
            cryptElectronicSeal_elem = rp_elem.find("dcc:cryptElectronicSeal", ns)
            cryptElectronicSeal = (cryptElectronicSeal_elem.text.strip().lower() == "true") if cryptElectronicSeal_elem is not None and cryptElectronicSeal_elem.text else False
            cryptElectronicSignature_elem = rp_elem.find("dcc:cryptElectronicSignature", ns)
            cryptElectronicSignature = (cryptElectronicSignature_elem.text.strip().lower() == "true") if cryptElectronicSignature_elem is not None and cryptElectronicSignature_elem.text else False
            cryptElectronicTimeStamp_elem = rp_elem.find("dcc:cryptElectronicTimeStamp", ns)
            cryptElectronicTimeStamp = (cryptElectronicTimeStamp_elem.text.strip().lower() == "true") if cryptElectronicTimeStamp_elem is not None and cryptElectronicTimeStamp_elem.text else False
            rps.append({
                "personName": name,
                "description": description,
                "role": role,
                "mainSigner": mainSigner,
                "cryptElectronicSeal": cryptElectronicSeal,
                "cryptElectronicSignature": cryptElectronicSignature,
                "cryptElectronicTimeStamp": cryptElectronicTimeStamp
            })
        if rps:
            st.session_state.responsible_persons = rps

        # Load Materials
        mats = []
        for mat_elem in root.findall(".//drmd:materials/drmd:material", ns):
            name_elem = mat_elem.find("drmd:name/dcc:content", ns)
            desc_elem = mat_elem.find("drmd:description/dcc:content", ns)
            sample_elem = mat_elem.find("drmd:minimumSampleSize/dcc:itemQuantity/si:realListXMLList/si:valueXMLList", ns)

            # Build material dictionary with all required keys
            mat = {
                "uuid": str(uuid.uuid4()),
                "name": name_elem.text.strip() if name_elem is not None and name_elem.text else "",
                "description": " ".join(desc_elem.text.split()) if desc_elem is not None and desc_elem.text else "",
                "materialClass": "",
                "minimumSampleSize": sample_elem.text.strip() if sample_elem is not None and sample_elem.text else "",
                "itemQuantities": "",
                "isCertified": mat_elem.get("isCertified", "false").lower() == "true",
                "identifications": []
            }

            # Load material identifications
            for mid in mat_elem.findall(".//drmd:identifications/drmd:identification", ns):
                issuer = mid.find("drmd:issuer", ns)
                value = mid.find("drmd:value", ns)
                name_elem = mid.find("drmd:name/dcc:content", ns)

                mat["identifications"].append({
                    "issuer": issuer.text.strip() if issuer is not None and issuer.text else "referenceMaterialProducer",
                    "idName": name_elem.text.strip() if name_elem is not None and name_elem.text else "",
                    "value": value.text.strip() if value is not None and value.text else ""
                })

            if not mat["identifications"]:
                mat["identifications"].append(INIT_IDENT.copy())

            mats.append(mat)

        if mats:
            st.session_state.materials = mats
        else:
            st.session_state.materials = [{"uuid": str(uuid.uuid4()), "name": "", "description": "", "materialClass": "",
                                          "minimumSampleSize": "", "itemQuantities": "", "isCertified": False,
                                          "identifications": [INIT_IDENT.copy()]}]

        # Load Statements
        official_keys = ["intendedUse", "commutability", "storageInformation",
                        "instructionsForHandlingAndUse", "metrologicalTraceability",
                        "healthAndSafetyInformation", "subcontractors",
                        "legalNotice", "referenceToCertificationReport"]
        official_statements = {key: {"name": "", "content": ""} for key in official_keys}
        custom_statements = []

        statements_elem = root.find(".//drmd:statements", ns)
        if statements_elem is not None:
            for child in statements_elem:
                # Get the local tag name
                tag = child.tag.split("}")[1] if "}" in child.tag else child.tag
                # Extract the optional name
                name_elem = child.find("dcc:name/dcc:content", ns)
                name_text = clean_text(name_elem.text) if name_elem is not None and name_elem.text else ""
                # Extract all direct dcc:content children (excluding the one inside dcc:name)
                contents = []
                for elem in child.findall("dcc:content", ns):
                    if elem.text:
                        contents.append(clean_text(elem.text))
                content_text = "\n".join(contents)

                if tag in official_keys:
                    official_statements[tag] = {"name": name_text, "content": content_text}
                elif tag == "statement":
                    custom_statements.append({"name": name_text, "content": content_text})

        st.session_state.official_statements = official_statements
        st.session_state.custom_statements = custom_statements

        # Load Material Properties
        mps = []
        mp_list_elem = root.find("drmd:materialPropertiesList", ns)
        if mp_list_elem is not None:
            for mp_elem in mp_list_elem.findall("drmd:materialProperties", ns):
                mp_dict = {}
                # isCertified attribute
                mp_dict["isCertified"] = True if mp_elem.attrib.get("isCertified", "false").lower() == "true" else False
                # Optional attribute id
                mp_dict["id"] = mp_elem.attrib.get("id", "").strip()
                # Name (required)
                name_elem = mp_elem.find("drmd:name/dcc:content", ns)
                mp_dict["name"] = clean_text(name_elem.text) if name_elem is not None and name_elem.text else ""
                # Description (optional)
                desc_elem = mp_elem.find("drmd:description/dcc:content", ns)
                mp_dict["description"] = clean_text(desc_elem.text) if desc_elem is not None and desc_elem.text else ""
                # Procedures (optional)
                proc_elem = mp_elem.find("drmd:procedures/dcc:content", ns)
                mp_dict["procedures"] = clean_text(proc_elem.text) if proc_elem is not None and proc_elem.text else ""

                # Results (required)
                results = []
                results_elem = mp_elem.find("drmd:results", ns)
                if results_elem is not None:
                    for res_elem in results_elem.findall("dcc:result", ns):
                        res_dict = {}
                        res_name_elem = res_elem.find("dcc:name/dcc:content", ns)
                        res_dict["result_name"] = clean_text(res_name_elem.text) if res_name_elem is not None and res_name_elem.text else ""
                        res_desc_elem = res_elem.find("dcc:description/dcc:content", ns)
                        res_dict["description"] = clean_text(res_desc_elem.text) if res_desc_elem is not None and res_desc_elem.text else ""
                        # Quantities
                        quantities = []
                        data_elem = res_elem.find("dcc:data", ns)
                        if data_elem is not None:
                            list_elem = data_elem.find("dcc:list", ns)
                            if list_elem is not None:
                                for quant_elem in list_elem.findall("dcc:quantity", ns):
                                    quant = {}
                                    # Get quantity name
                                    qname_elem = quant_elem.find("dcc:name/dcc:content", ns)
                                    quant["Name"] = clean_text(qname_elem.text) if qname_elem is not None and qname_elem.text else ""
                                    # We'll leave Label and Quantity Type as empty for now
                                    quant["Label"] = ""
                                    quant["Quantity Type"] = ""
                                    # Get real value
                                    real_elem = quant_elem.find("si:real", ns)
                                    if real_elem is not None:
                                        value_elem = real_elem.find("si:value", ns)
                                        quant["Value"] = float(value_elem.text.strip()) if value_elem is not None and value_elem.text and value_elem.text.strip().replace('.', '', 1).isdigit() else None
                                        unit_elem = real_elem.find("si:unit", ns)
                                        quant["Unit"] = unit_elem.text.strip() if unit_elem is not None and unit_elem.text else ""
                                        # Measurement uncertainty
                                        mu_elem = real_elem.find("si:measurementUncertaintyUnivariate/si:expandedMU", ns)
                                        if mu_elem is not None:
                                            val_mu = mu_elem.find("si:valueExpandedMU", ns)
                                            quant["Uncertainty"] = float(val_mu.text.strip()) if val_mu is not None and val_mu.text and val_mu.text.strip().replace('.', '', 1).isdigit() else None
                                            cf_elem = mu_elem.find("si:coverageFactor", ns)
                                            quant["Coverage Factor"] = float(cf_elem.text.strip()) if cf_elem is not None and cf_elem.text and cf_elem.text.strip().replace('.', '', 1).isdigit() else None
                                            cp_elem = mu_elem.find("si:coverageProbability", ns)
                                            quant["Coverage Probability"] = float(cp_elem.text.strip()) if cp_elem is not None and cp_elem.text and cp_elem.text.strip().replace('.', '', 1).isdigit() else None
                                            dist_elem = mu_elem.find("si:distribution", ns)
                                            quant["Distribution"] = dist_elem.text.strip() if dist_elem is not None and dist_elem.text else ""
                                    quantities.append(quant)
                        # Convert list of quantities to a DataFrame
                        df_quant = pd.DataFrame(quantities, columns=["Name", "Label", "Value", "Quantity Type", "Unit", "Uncertainty", "Coverage Factor", "Coverage Probability", "Distribution"])
                        res_dict["quantities"] = df_quant
                        results.append(res_dict)
                mp_dict["results"] = results
                # Assign a new UUID for internal use
                mp_dict["uuid"] = str(uuid.uuid4())
                mps.append(mp_dict)
        if mps:
            st.session_state.materialProperties = mps

        # Extract all <comment> elements separately
        comments = []
        for comment_elem in root.findall(".//drmd:comment", ns):
            if comment_elem.text:
                comments.append(comment_elem.text.strip())
        st.session_state.comment = "\n".join(comments) if comments else ""

        # Extract all <document> elements with metadata
        embedded_files = []
        for doc_elem in root.findall(".//drmd:document", ns):
            file_name = doc_elem.find("dcc:fileName", ns).text if doc_elem.find("dcc:fileName", ns) is not None else "unknown"
            mime_type = doc_elem.find("dcc:mimeType", ns).text if doc_elem.find("dcc:mimeType", ns) is not None else "application/octet-stream"
            base64_data = doc_elem.find("dcc:dataBase64", ns).text if doc_elem.find("dcc:dataBase64", ns) is not None else ""

            # Convert base64 data to bytes for download
            file_bytes = base64.b64decode(base64_data) if base64_data else b""

            embedded_files.append({
                "name": file_name,
                "mimeType": mime_type,
                "data": file_bytes  # Store file as bytes
            })

        # Store extracted files
        if embedded_files:
            st.session_state.embedded_files = embedded_files

        st.session_state.template_loaded = True
        st.sidebar.success("XML template loaded ✔")

    except Exception as e:
        st.sidebar.error(f"Failed to load template: {e}")
        # Print detailed error for debugging
        st.sidebar.error(f"Error details: {traceback.format_exc()}")

        # Display the XML structure for debugging
        try:
            tree = ET.parse(io.BytesIO(xml_bytes))
            root = tree.getroot()
            st.sidebar.expander("XML Structure (for debugging)").code(ET.tostring(root, encoding='unicode', method='xml')[:1000] + "...")
        except Exception as debug_e:
            st.sidebar.error(f"Could not parse XML for debugging: {debug_e}")

# -----------------------------------------------------------------------------
# Robust session‑state initialisation (covers all tabs)
SESSION_DEFAULTS = {
    "identifications": [INIT_IDENT.copy()],
    "materials": [{"uuid": str(uuid.uuid4()), "name": "", "description": "", "materialClass": "",
                    "minimumSampleSize": "", "itemQuantities": "", "isCertified": False,
                    "identifications": [INIT_IDENT.copy()]}],
    "materialProperties": [],
    "producers": [DEFAULT_PRODUCER.copy()],
    "responsible_persons": [DEFAULT_PERSON.copy()],
    "official_statements": OFFICIAL_STMPL.copy(),
    "custom_statements": [],
    "materials_df": pd.DataFrame(columns=["Material Name", "Description", "Minimum Sample Size", "Unit"]),
    "mp_tables": [],
    "selected_quantity": "", "selected_unit": "", "coverage_factor": 2.0,
    "coverage_probability": 0.95, "distribution": "normal",
    "title_option": "referenceMaterialCertificate",  # default
    "persistent_id": "",
    "persistent_id_value": "",
    "validity_type": "Until Revoked", "raw_validity_period": "",
    "date_of_issue": date.today(), "specific_time": date.today(),
    "template_loaded": False,
}
for k, v in SESSION_DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# -----------------------------------------------------------------------------
# Sidebar utilities
st.sidebar.header("DRMD Generator")
st.sidebar.markdown(
    f"<span style='font-size:0.75rem'>Schema v{SCHEMA_VERSION}</span>",
    unsafe_allow_html=True,
)
xml_template = st.sidebar.file_uploader("Load XML file", type=["xml"])
if xml_template and not st.session_state.template_loaded:
    load_xml_into_state(xml_template.getvalue())

if st.sidebar.button("Reset All"):
    st.session_state.clear(); st.rerun()

# -----------------------------------------------------------------------------
# Main Tabs list
tabs = st.tabs([
    "Administrative Data", "Materials", "Properties", "Statements",
    "Comments & Documents", "Digital Signature", "Validate & Export","Help"
])

# -----------------------------------------------------------------------------
# TAB 0 – Administrative Data (unchanged from rev2 except duration help)
# -----------------------------------------------------------------------------
with tabs[0]:
    with st.expander("Basic Information", expanded=True):
        col1, col2, col3 = st.columns([3, 3, 1])
        with col1:
            st.selectbox(
                "Title of the Document",
                ALLOWED_TITLES,
                key="title_option",
                format_func=lambda x: " ".join(re.findall(r"[A-Z][^A-Z]*", x)).title(),
            )
        # Initialize persistent_id_value if it doesn't exist
        if "persistent_id_value" not in st.session_state:
            st.session_state.persistent_id_value = ""

        # Define the callback function to generate UUID
        def generate_uuid():
            st.session_state.persistent_id_value = str(uuid.uuid4())

        with col2:
            # Use the value parameter to set the text input's value from session state
            st.text_input(
                "Persistent Document Identifier",
                value=st.session_state.persistent_id_value,
                key="persistent_id",
                help="A globally unique, permanent identifier (e.g. UUID).",
            )
            # Update the session state when the text input changes
            if "persistent_id" in st.session_state:
                st.session_state.persistent_id_value = st.session_state.persistent_id

        with col3:
            # Add some vertical spacing
            st.write("")
            # Create the button with the callback
            if st.button("Generate", key="pid_gen", on_click=generate_uuid):
                pass

        # RM Unique Identifier block (single, non-changeable issuer)
        st.markdown("")
        st.markdown("RM unique identifier:")

        # Ensure we have exactly one identification with fixed issuer
        if not st.session_state.identifications:
            st.session_state.identifications = [INIT_IDENT.copy()]
        elif len(st.session_state.identifications) > 1:
            st.session_state.identifications = [st.session_state.identifications[0]]

        # Force issuer to be referenceMaterialProducer
        st.session_state.identifications[0]["issuer"] = "referenceMaterialProducer"

        ident = st.session_state.identifications[0]
        col1, col2, col3 = st.columns([2, 3, 3])
        with col1:
            # Disabled selector but keeps the same style
            st.selectbox("Issuer", ALLOWED_ISSUERS,
                        index=ALLOWED_ISSUERS.index("referenceMaterialProducer"),
                        key="single_ident_issuer", disabled=True)
        with col2:
            ident["idName"] = st.text_input("RM Name", ident.get("idName", ""), key="single_ident_name")
        with col3:
            ident["value"] = st.text_input("RM Code", ident.get("value", ""), key="single_ident_value")

        st.markdown("")

        # Period of Validity row with new help text
        cols = st.columns([3, 3, 3])
        with cols[0]:
            v_type = st.selectbox("Period of Validity", ["Until Revoked", "Time After Dispatch", "Specific Time"], key="validity_type")
        if v_type == "Time After Dispatch":
            with cols[1]:
                st.text_input("Duration", key="raw_validity_period", placeholder="P1Y6M", help=xs_duration_hint())
            with cols[2]:
                st.date_input("Dispatch Date", key="date_of_issue")
        elif v_type == "Specific Time":
            with cols[1]:
                st.date_input("Date", key="specific_time")
            cols[2].markdown(" ")
        else:
            cols[1].markdown(" "); cols[2].markdown(" ")

     # Reference Material Producer and Responsible Persons section remains unchanged.
    with st.expander("Reference Material Producer and Responsible Persons", expanded=True):
        with st.container():
            for idx, prod in enumerate(st.session_state.producers):
                # Use a container with a header instead of an expander
                st.markdown(f"###### Reference Material Producer")
                with st.container():
                    # Name and contact info
                    col1, col2 = st.columns(2)
                    with col1:
                        prod["producerName"] = st.text_input("Name", value=prod.get("producerName", ""), key=f"producerName_{idx}")
                        prod["producerEmail"] = st.text_input("Email", value=prod.get("producerEmail", ""), key=f"producerEmail_{idx}")
                        prod["producerPhone"] = st.text_input("Phone", value=prod.get("producerPhone", ""), key=f"producerPhone_{idx}")

                    # Address info in a more compact layout
                    with col2:
                        addr_cols = st.columns([3, 1])
                        with addr_cols[0]:
                            prod["producerStreet"] = st.text_input("Street", value=prod.get("producerStreet", ""), key=f"producerStreet_{idx}")
                        with addr_cols[1]:
                            prod["producerStreetNo"] = st.text_input("No.", value=prod.get("producerStreetNo", ""), key=f"producerStreetNo_{idx}")

                        city_cols = st.columns([1, 2, 1])
                        with city_cols[0]:
                            prod["producerPostCode"] = st.text_input("Post Code", value=prod.get("producerPostCode", ""), key=f"producerPostCode_{idx}")
                        with city_cols[1]:
                            prod["producerCity"] = st.text_input("City", value=prod.get("producerCity", ""), key=f"producerCity_{idx}")
                        with city_cols[2]:
                            prod["producerCountryCode"] = st.text_input("Country", value=prod.get("producerCountryCode", ""), key=f"producerCountryCode_{idx}")
                        prod["producerFax"] = st.text_input("Fax", value=prod.get("producerFax", ""), key=f"producerFax_{idx}")

                    # if st.button("Remove", key=f"remove_prod_{idx}"):
                    #     st.session_state.producers.pop(idx)
                    #     st.rerun()

                # Add a separator between producers

            # if st.button("Add Producer", key="add_prod"):
            #     st.session_state.producers.append({
            #         "producerName": "",
            #         "producerStreet": "",
            #         "producerStreetNo": "",
            #         "producerPostCode": "",
            #         "producerCity": "",
            #         "producerCountryCode": "",
            #         "producerPhone": "",
            #         "producerFax": "",
            #         "producerEmail": ""
            #     })
            #     st.rerun()
        st.markdown("---")

        with st.container():
            for idx, rp in enumerate(st.session_state.responsible_persons):
                # Use a container with a header instead of an expander
                st.markdown(f"###### Responsible Person {idx+1}")
                with st.container():
                    cols = st.columns([2, 2, 2])
                    with cols[0]:
                        rp["personName"] = st.text_input("Name", value=rp.get("personName", ""), key=f"rp_name_{idx}")
                        rp["role"] = st.text_input("Role", value=rp.get("role", ""), key=f"rp_role_{idx}")
                    with cols[1]:
                        rp["description"] = st.text_area("Description", value=rp.get("description", ""), height=100, key=f"rp_desc_{idx}")
                    with cols[2]:
                        rp["mainSigner"] = st.checkbox("Main Signer", value=rp.get("mainSigner", False), key=f"rp_mainSigner_{idx}")
                        rp["cryptElectronicSeal"] = st.checkbox("Electronic Seal", value=rp.get("cryptElectronicSeal", False), key=f"rp_cryptSeal_{idx}")
                        rp["cryptElectronicSignature"] = st.checkbox("Electronic Signature", value=rp.get("cryptElectronicSignature", False), key=f"rp_cryptSig_{idx}")
                        rp["cryptElectronicTimeStamp"] = st.checkbox("Electronic TimeStamp", value=rp.get("cryptElectronicTimeStamp", False), key=f"rp_cryptTS_{idx}")
                    if st.button(f"Remove", key=f"remove_rp_{idx}"):
                        st.session_state.responsible_persons.pop(idx)
                        st.rerun()

                # Add a separator between responsible persons
                st.markdown("---")
            if st.button("Add Responsible Person", key="add_rp"):
                st.session_state.responsible_persons.append({
                    "personName": "",
                    "description": "",
                    "role": "",
                    "mainSigner": False,
                    "cryptElectronicSeal": False,
                    "cryptElectronicSignature": False,
                    "cryptElectronicTimeStamp": False
                })
                st.rerun()
def export_administrative_identifications(ns_drmd, ns_dcc):
    # For identifications, ensure the issuer is valid.
    idents_elem = ET.Element(f"{{{ns_drmd}}}identifications")
    for ident in st.session_state.identifications:
        ident_elem = ET.SubElement(idents_elem, f"{{{ns_drmd}}}identification", attrib={"refType": "basic_certificateIdentification"})
        # Check the issuer; if it's not allowed, default to "referenceMaterialProducer".
        issuer_val = ident.get("issuer", "referenceMaterialProducer")
        if issuer_val not in ALLOWED_ISSUERS:
            issuer_val = "referenceMaterialProducer"
        ET.SubElement(ident_elem, f"{{{ns_drmd}}}issuer").text = issuer_val
        # For the identification value, if empty, default to "N/A".
        value_text = ident.get("value", "").strip() or "N/A"
        ET.SubElement(ident_elem, f"{{{ns_drmd}}}value").text = value_text
        if ident.get("idName", "").strip():
            name_elem = ET.SubElement(ident_elem, f"{{{ns_drmd}}}name")
            add_if_valid(name_elem, "content", ident.get("idName", ""), ns_dcc)
    return idents_elem
# -----------------------------------------------------------------------------
# TAB 1 – Materials (unchanged from rev2)
# -----------------------------------------------------------------------------
with tabs[1]:
    # same content as rev2 for Materials
    for i, mat in enumerate(st.session_state.materials):
        with st.expander(f"Material {i+1}", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                mat["name"] = st.text_input("Material Name", mat["name"], key=f"mat_name_{mat['uuid']}")
                mat["materialClass"] = st.text_input("Material Class", mat["materialClass"], key=f"mat_class_{mat['uuid']}")
                mat["itemQuantities"] = st.text_input("Item Quantities", mat["itemQuantities"], key=f"mat_iq_{mat['uuid']}")
            with c2:
                mat["description"] = st.text_area("Description", mat["description"], key=f"mat_desc_{mat['uuid']}")
                mat["minimumSampleSize"] = st.text_input("Minimum Sample Size", mat["minimumSampleSize"], key=f"mat_min_{mat['uuid']}")
                mat["isCertified"] = st.checkbox("Certified", mat["isCertified"], key=f"mat_cert_{mat['uuid']}")

            st.markdown("Identification")
            # Ensure material has exactly one identification that copies from administrative data
            if not mat["identifications"]:
                mat["identifications"] = [INIT_IDENT.copy()]
            elif len(mat["identifications"]) > 1:
                mat["identifications"] = [mat["identifications"][0]]

            # Copy identification from administrative data
            if st.session_state.identifications:
                admin_ident = st.session_state.identifications[0]
                mat["identifications"][0]["issuer"] = admin_ident["issuer"]
                mat["identifications"][0]["idName"] = admin_ident["idName"]
                mat["identifications"][0]["value"] = admin_ident["value"]

            # Display as read-only with same style as administrative data
            mat_ident = mat["identifications"][0]
            col1, col2, col3 = st.columns([2, 3, 3])
            with col1:
                st.selectbox("Issuer", ALLOWED_ISSUERS,
                           index=ALLOWED_ISSUERS.index("referenceMaterialProducer"),
                           key=f"mat_{mat['uuid']}_issuer_readonly", disabled=True)
            with col2:
                st.text_input("RM Name", value=mat_ident.get("idName", ""), key=f"mat_{mat['uuid']}_name_readonly", disabled=True)
            with col3:
                st.text_input("RM Code", value=mat_ident.get("value", ""), key=f"mat_{mat['uuid']}_code_readonly", disabled=True)

            if st.button("Remove Material", key=f"rm_mat_{mat['uuid']}", disabled=len(st.session_state.materials)==1):
                st.session_state.materials.pop(i); st.rerun()

    if st.button("➕ Add Material", key="add_material"):
        st.session_state.materials.append({
            "uuid": str(uuid.uuid4()), "name": "", "description": "", "materialClass": "",
            "minimumSampleSize": "", "itemQuantities": "", "isCertified": False,
            "identifications": [INIT_IDENT.copy()],
        }); st.rerun()

# -----------------------------------------------------------------------------
# --- TAB 2 – Properties starts below (placeholder) ---
# -----------------------------------------------------------------------------

# --- Tab 2: Materials Properties (Editable Material Properties Tables) ---
with tabs[2]:

    col_left,  = st.columns([1])

    with col_left:
        # material_scroll = st.container(height=1000)
        # with material_scroll:

        #     st.subheader("Properties")


            # Loop over each materialProperties entry.
            for idx, mp in enumerate(st.session_state.materialProperties):
                # Ensure each entry has a UUID.
                mp_uuid = mp.get("uuid", str(uuid.uuid4()))
                mp["uuid"] = mp_uuid
                with st.expander(f"Properties Set {idx+1}", expanded=True):
                    # Main Material Properties data (single form)
                    with st.form(key=f"mp_main_form_{mp_uuid}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            mp["id"] = st.text_input("ID (optional)", value=mp.get("id", ""), key=f"mp_id_{mp_uuid}")
                            mp["name"] = st.text_input("Name", value=mp.get("name", ""), key=f"mp_name_{mp_uuid}")
                            mp["isCertified"] = st.checkbox("Certified", value=mp.get("isCertified", False), key=f"mp_certified_{mp_uuid}")
                        with col2:
                            mp["description"] = st.text_area("Description", value=mp.get("description", ""), key=f"mp_desc_{mp_uuid}")
                            mp["procedures"] = st.text_area("Procedures", value=mp.get("procedures", ""), key=f"mp_proc_{mp_uuid}")

                        submitted_mp = st.form_submit_button("Save Properties Set")
                        if submitted_mp:
                            st.success(f"Properties Set {idx+1} updated!")

                    # For each measurement result (non-nested forms)
                    for res_idx, result in enumerate(mp.get("results", [])):

                        col1, col2,  = st.columns([5, 2])
                        with col1:
                            st.markdown(f"Table {res_idx+1}")
                        with col2:
                            if st.button("Remove Table", disabled=len(mp["results"])==1, key=f"remove_res_{mp_uuid}_{res_idx}"):
                                mp["results"].pop(res_idx)
                                st.rerun()

                        with st.form(key=f"res_form_{mp_uuid}_{res_idx}"):
                            result["result_name"] = st.text_input("Name", value=result.get("result_name", ""), key=f"res_name_{mp_uuid}_{res_idx}")
                            result["description"] = st.text_area("Description", value=result.get("description", ""), key=f"res_desc_{mp_uuid}_{res_idx}")
                            # Use data_editor for the quantities DataFrame.
                            result["quantities"] = st.data_editor(
                                result.get("quantities", pd.DataFrame(columns=[
                                    "Name", "Label", "Value", "Quantity Kind", "Unit",
                                    "Uncertainty", "Coverage Factor", "Coverage Probability", "Distribution"
                                ])),
                                num_rows="dynamic",
                                key=f"quantities_{mp_uuid}_{res_idx}"
                            )

                            # Default uncertainty controls in one line under the table
                            st.markdown("**Default Uncertainty Values:**")
                            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                            with col1:
                                local_coverage_factor = st.number_input("Coverage Factor", min_value=1.0, max_value=10.0, value=2.0, step=0.1, key=f"local_cf_{mp_uuid}_{res_idx}")
                            with col2:
                                local_coverage_probability = st.number_input("Probability", min_value=0.0, max_value=1.0, value=0.95, step=0.01, key=f"local_cp_{mp_uuid}_{res_idx}")
                            with col3:
                                local_distribution = st.selectbox("Distribution", ["normal", "log-normal", "uniform"], index=0, key=f"local_dist_{mp_uuid}_{res_idx}")
                            with col4:
                                # Button to apply default uncertainty values to all rows
                                if st.form_submit_button("Apply to All Rows"):
                                    # Apply the local values to all rows in the current table
                                    if not result["quantities"].empty:
                                        result["quantities"]["Coverage Factor"] = local_coverage_factor
                                        result["quantities"]["Coverage Probability"] = local_coverage_probability
                                        result["quantities"]["Distribution"] = local_distribution
                                    st.rerun()


                    # Button to add a new measurement result.

                    col1, col2 = st.columns(2)

                    with col1:
                        if st.button("Add Table", key=f"add_result_{mp_uuid}"):
                            mp.setdefault("results", []).append(create_empty_result())
                            st.rerun()
                    with col2:
                        if st.button("Remove Properties Set", key=f"remove_mp_{mp_uuid}"):
                            st.session_state.materialProperties.pop(idx)
                            st.rerun()
            # Button to add a new material properties entry.
            if st.button("Add Properties Set"):
                st.session_state.materialProperties.append(create_empty_materialProperties())
                st.rerun()

    # with col_right:
    #     # Commented out quantity selection and QUDT selection
    #     # st.markdown("Quantity Selection", help="This panel shows available quantity types and their units from the QUDT ontology. Select a quantity to see applicable units.",)
    #     # st.session_state.selected_quantity = st.selectbox("Type", list(qudt_quantities.keys()) + ["Custom"], key="quantity_select")
    #     # st.session_state.selected_unit = st.selectbox("Unit", qudt_quantities.get(st.session_state.selected_quantity, ["Custom"]), key="unit_select")
    #     # st.markdown("---")

    #     # Removed uncertainty fields from right column - now they are under each table
    #     #st.write("Properties configuration panel")


def add_if_valid(parent, tag, value, ns):
    """Adds a subelement with tag to parent if value is not None, empty, or NaN.
       Returns the new element or None.
    """
    if value is None:
        return None
    try:
        # If the value is a float and is NaN, skip it.
        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:
        pass
    if str(value).strip() == "":
        return None
    elem = ET.SubElement(parent, f"{{{ns}}}{tag}")
    elem.text = str(value).strip()
    return elem

# def export_materialProperties(ns_drmd, ns_dcc, ns_si):
#     # Create the wrapping element for materialPropertiesList.
#     mp_list_elem = ET.Element(f"{{{ns_drmd}}}materialPropertiesList")
#     for mp in st.session_state.materialProperties:
#         mp_elem = ET.SubElement(mp_list_elem, f"{{{ns_drmd}}}materialProperties", attrib={
#             "isCertified": "true" if mp.get("isCertified", False) else "false"
#         })
#         if mp.get("id", "").strip():
#             mp_elem.set("id", mp.get("id").strip())
#         # Required: name
#         name_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}name")
#         add_if_valid(name_elem, "content", mp.get("name", ""), ns_dcc)
#         # Optional: description
#         if mp.get("description", "").strip():
#             desc_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}description")
#             add_if_valid(desc_elem, "content", mp.get("description", ""), ns_dcc)
#         # Optional: procedures
#         if mp.get("procedures", "").strip():
#             proc_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}procedures")
#             add_if_valid(proc_elem, "content", mp.get("procedures", ""), ns_dcc)
#         # Required: results
#         results_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}results")
#         for res in mp.get("results", []):
#             res_elem = ET.SubElement(results_elem, f"{{{ns_dcc}}}result")
#             res_name_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}name")
#             add_if_valid(res_name_elem, "content", res.get("result_name", ""), ns_dcc)
#             if res.get("description", "").strip():
#                 res_desc_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}description")
#                 add_if_valid(res_desc_elem, "content", res.get("description", ""), ns_dcc)
#             data_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}data")
#             list_elem = ET.SubElement(data_elem, f"{{{ns_dcc}}}list")
#             for _, row in res.get("quantities", pd.DataFrame()).iterrows():
#                 quantity_elem = ET.SubElement(list_elem, f"{{{ns_dcc}}}quantity", attrib={"refType": "basic_measuredValue"})
#                 qname_elem = ET.SubElement(quantity_elem, f"{{{ns_dcc}}}name")
#                 add_if_valid(qname_elem, "content", row.get("Name", ""), ns_dcc)
#                 real_elem = ET.SubElement(quantity_elem, f"{{{ns_si}}}real")
#                 add_if_valid(real_elem, "value", row.get("Value", ""), ns_si)
#                 add_if_valid(real_elem, "unit", row.get("Unit", ""), ns_si)
#                 mu_elem = ET.SubElement(real_elem, f"{{{ns_si}}}measurementUncertaintyUnivariate")
#                 # Only write expandedMU if at least one subvalue is valid.
#                 expandedMU_vals = {}
#                 for subtag, col in [("valueExpandedMU", "Uncertainty"),
#                                     ("coverageFactor", "Coverage Factor"),
#                                     ("coverageProbability", "Coverage Probability"),
#                                     ("distribution", "Distribution")]:
#                     val = row.get(col, "")
#                     if val is None or (isinstance(val, float) and math.isnan(val)) or str(val).strip() == "":
#                         continue
#                     expandedMU_vals[subtag] = val
#                 if expandedMU_vals:
#                     expMU_elem = ET.SubElement(mu_elem, f"{{{ns_si}}}expandedMU")
#                     for tag, value in expandedMU_vals.items():
#                         add_if_valid(expMU_elem, tag, value, ns_si)
#     return mp_list_elem

import math

def export_materialProperties(ns_drmd, ns_dcc, ns_si):
    # Create the wrapping element for materialPropertiesList.
    mp_list_elem = ET.Element(f"{{{ns_drmd}}}materialPropertiesList")
    for mp in st.session_state.materialProperties:
        mp_elem = ET.SubElement(mp_list_elem, f"{{{ns_drmd}}}materialProperties", attrib={
            "isCertified": "true" if mp.get("isCertified", False) else "false"
        })
        if mp.get("id", "").strip():
            mp_elem.set("id", mp.get("id").strip())
        # Required: name
        name_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}name")
        ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = mp.get("name", "")
        # Optional: description
        if mp.get("description", "").strip():
            desc_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}description")
            ET.SubElement(desc_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = mp.get("description", "")
        # Optional: procedures
        if mp.get("procedures", "").strip():
            proc_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}procedures")
            ET.SubElement(proc_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = mp.get("procedures", "")
        # Required: results
        results_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}results")
        for res in mp.get("results", []):
            res_elem = ET.SubElement(results_elem, f"{{{ns_dcc}}}result")
            res_name_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}name")
            ET.SubElement(res_name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = res.get("result_name", "")
            if res.get("description", "").strip():
                res_desc_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}description")
                ET.SubElement(res_desc_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = res.get("description", "")
            data_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}data")
            list_elem = ET.SubElement(data_elem, f"{{{ns_dcc}}}list")
            for _, row in res.get("quantities", pd.DataFrame()).iterrows():
                quantity_elem = ET.SubElement(list_elem, f"{{{ns_dcc}}}quantity", attrib={"refType": "basic_measuredValue"})
                qname_elem = ET.SubElement(quantity_elem, f"{{{ns_dcc}}}name")
                ET.SubElement(qname_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = str(row.get("Name", ""))
                real_elem = ET.SubElement(quantity_elem, f"{{{ns_si}}}real")
                ET.SubElement(real_elem, f"{{{ns_si}}}value").text = str(row.get("Value", ""))
                ET.SubElement(real_elem, f"{{{ns_si}}}unit").text = str(row.get("Unit", ""))

                # Check uncertainty values.
                expandedMU_vals = {}
                for subtag, col in [("valueExpandedMU", "Uncertainty"),
                                    ("coverageFactor", "Coverage Factor"),
                                    ("coverageProbability", "Coverage Probability"),
                                    ("distribution", "Distribution")]:
                    val = row.get(col, "")
                    if val is None or (isinstance(val, float) and math.isnan(val)) or str(val).strip() == "":
                        continue
                    expandedMU_vals[subtag] = val
                # Only create the measurementUncertaintyUnivariate element if there is valid data.
                if expandedMU_vals:
                    mu_elem = ET.SubElement(real_elem, f"{{{ns_si}}}measurementUncertaintyUnivariate")
                    expMU_elem = ET.SubElement(mu_elem, f"{{{ns_si}}}expandedMU")
                    for tag, value in expandedMU_vals.items():
                        ET.SubElement(expMU_elem, f"{{{ns_si}}}{tag}").text = str(value)
    return mp_list_elem


with tabs[3]:

    # Official Statements (using dcc:richContentType structure)
    with st.expander("ISO 17034 Statements", expanded=True):

        # Intended Use
        content_val = st.text_area("Intended Use", value=st.session_state.official_statements.get("intendedUse", {}).get("content", ""), key="official_content_intendedUse")
        st.session_state.official_statements["intendedUse"] = {"name": "Intended Use", "content": content_val}

        # Commutability
        content_val = st.text_area("Commutability", value=st.session_state.official_statements.get("commutability", {}).get("content", ""), key="official_content_commutability")
        st.session_state.official_statements["commutability"] = {"name": "Commutability", "content": content_val}

        # Storage Information
        content_val = st.text_area("Storage Information", value=st.session_state.official_statements.get("storageInformation", {}).get("content", ""), key="official_content_storageInformation")
        st.session_state.official_statements["storageInformation"] = {"name": "Storage Information", "content": content_val}

        # Instructions For Handling And Use
        content_val = st.text_area("Instructions For Handling And Use", value=st.session_state.official_statements.get("instructionsForHandlingAndUse", {}).get("content", ""), key="official_content_instructionsForHandlingAndUse")
        st.session_state.official_statements["instructionsForHandlingAndUse"] = {"name": "Instructions For Handling And Use", "content": content_val}

        # Metrological Traceability
        content_val = st.text_area("Metrological Traceability", value=st.session_state.official_statements.get("metrologicalTraceability", {}).get("content", ""), key="official_content_metrologicalTraceability")
        st.session_state.official_statements["metrologicalTraceability"] = {"name": "Metrological Traceability", "content": content_val}

        # Health And Safety Information
        content_val = st.text_area("Health And Safety Information", value=st.session_state.official_statements.get("healthAndSafetyInformation", {}).get("content", ""), key="official_content_healthAndSafetyInformation")
        st.session_state.official_statements["healthAndSafetyInformation"] = {"name": "Health And Safety Information", "content": content_val}

        # Subcontractors
        content_val = st.text_area("Subcontractors", value=st.session_state.official_statements.get("subcontractors", {}).get("content", ""), key="official_content_subcontractors")
        st.session_state.official_statements["subcontractors"] = {"name": "Subcontractors", "content": content_val}

        # Legal Notice
        content_val = st.text_area("Legal Notice", value=st.session_state.official_statements.get("legalNotice", {}).get("content", ""), key="official_content_legalNotice")
        st.session_state.official_statements["legalNotice"] = {"name": "Legal Notice", "content": content_val}

        # Reference To Certification Report
        content_val = st.text_area("Reference To Certification Report", value=st.session_state.official_statements.get("referenceToCertificationReport", {}).get("content", ""), key="official_content_referenceToCertificationReport")
        st.session_state.official_statements["referenceToCertificationReport"] = {"name": "Reference To Certification Report", "content": content_val}

    # Custom Statements (all exported as <drmd:statement>)
    with st.expander("Other Statements", expanded=True):
        for idx, cs in enumerate(st.session_state.custom_statements):
            with st.container():
                # We ignore any custom tag; the export will use <drmd:statement>
                cs_name = st.text_input(f" Statement {idx+1} - Name", value=cs.get("name", "").strip(), key=f"cs_name_{idx}")
                cs_content = st.text_area(f" Statement {idx+1} - Content", value=cs.get("content", "").strip(), key=f"cs_content_{idx}")
                st.session_state.custom_statements[idx] = {"name": cs_name, "content": cs_content}
                if st.button(f"Remove", key=f"remove_cs_{idx}"):
                    st.session_state.custom_statements.pop(idx)
                    st.rerun()
        if st.button("Add Statement", key="add_cs"):
            st.session_state.custom_statements.append({"name": "", "content": ""})
            st.rerun()


def export_statements(ns_drmd, ns_dcc):
    # Create the <drmd:statements> element.
    statements_elem = ET.Element(f"{{{ns_drmd}}}statements")

    def add_statement(element_name, label, text):
        """Adds a statement element if text is not empty.
           element_name should be one of the official ones, e.g. 'intendedUse'.
        """
        if text.strip():
            stmt = ET.SubElement(statements_elem, f"{{{ns_drmd}}}{element_name}")
            # Only add a dcc:name if a label is provided.
            if label.strip():
                name_elem = ET.SubElement(stmt, f"{{{ns_dcc}}}name")
                ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = label.strip()
            # Add one or more content elements (one per nonempty line).
            for line in text.strip().splitlines():
                if line.strip():
                    ET.SubElement(stmt, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = line.strip()

    official = st.session_state.official_statements
    add_statement("intendedUse", "Intended Use", official.get("intendedUse", {}).get("content", ""))
    add_statement("commutability", "Commutability", official.get("commutability", {}).get("content", ""))
    add_statement("storageInformation", "Storage Information", official.get("storageInformation", {}).get("content", ""))
    add_statement("instructionsForHandlingAndUse", "Handling Instructions", official.get("instructionsForHandlingAndUse", {}).get("content", ""))
    add_statement("metrologicalTraceability", "Metrological Traceability", official.get("metrologicalTraceability", {}).get("content", ""))
    add_statement("healthAndSafetyInformation", "Health and Safety Information", official.get("healthAndSafetyInformation", {}).get("content", ""))
    add_statement("subcontractors", "Subcontractors", official.get("subcontractors", {}).get("content", ""))
    add_statement("legalNotice", "Legal Notice", official.get("legalNotice", {}).get("content", ""))
    add_statement("referenceToCertificationReport", "Reference to Certification Report", official.get("referenceToCertificationReport", {}).get("content", ""))

    # For custom statements, always export using the element name "statement".
    for cs in st.session_state.custom_statements:
        if cs.get("content", "").strip():
            cs_elem = ET.SubElement(statements_elem, f"{{{ns_drmd}}}statement")
            if cs.get("name", "").strip():
                name_elem = ET.SubElement(cs_elem, f"{{{ns_dcc}}}name")
                ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = cs.get("name", "").strip()
            for line in cs.get("content", "").strip().splitlines():
                if line.strip():
                    ET.SubElement(cs_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = line.strip()

    return statements_elem

import base64

# --- Tab 4: Comments & Documents ---
with tabs[4]:

    # Single Comment (instead of multiple separate comment elements)
    st.markdown("###### Comment")
    comment = st.text_area("Enter your comment", value=st.session_state.get("comment", ""), key="comment")

    # --- Document Upload ---
    st.markdown("###### Upload Document")
    # Allow only one file upload (no multiple files)
    attachment = st.file_uploader("Attach Document", type=["pdf", "doc", "docx", "txt"], key="attachment")

    # Display currently loaded embedded document (if any)
    if st.session_state.get("embedded_files"):
        st.subheader("Existing Document from XML")
        # Only display the first one.
        file = st.session_state.embedded_files[0]
        col1, col2, col3 = st.columns([4, 2, 1])
        col1.markdown(f"📄 **{file['name']}**")
        col1.text(f"Type: {file['mimeType']}")
        col2.download_button(
            label="Download",
            data=file["data"],
            file_name=file["name"],
            mime=file["mimeType"],
            key="download_embedded"
        )
        if col3.button("❌ Remove", key="remove_embedded"):
            st.session_state.embedded_files.pop(0)
            st.rerun()

# --- Export Functions for Comments & Document ---

def export_comment(ns_drmd):
    """Generate a single <comment> element if a comment is provided."""
    comment_text = st.session_state.get("comment", "").strip()
    if comment_text:
        comment_elem = ET.Element(f"{{{ns_drmd}}}comment")
        comment_elem.text = comment_text
        return comment_elem
    return None

def export_document(ns_drmd, ns_dcc):
    """Generate a single <document> element from the uploaded attachment,
       or from embedded_files if no attachment is present.
    """
    # Prefer the attachment uploaded in the UI.
    if st.session_state.get("attachment") is not None:
        uploaded_file = st.session_state.attachment
        file_content = uploaded_file.getvalue()
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        doc_elem = ET.Element(f"{{{ns_drmd}}}document")
        ET.SubElement(doc_elem, f"{{{ns_dcc}}}fileName").text = uploaded_file.name
        ET.SubElement(doc_elem, f"{{{ns_dcc}}}mimeType").text = uploaded_file.type or "application/octet-stream"
        ET.SubElement(doc_elem, f"{{{ns_dcc}}}dataBase64").text = encoded_content
        return doc_elem
    # Otherwise, if an embedded file exists, use the first one.
    if st.session_state.get("embedded_files"):
        file = st.session_state.embedded_files[0]
        doc_elem = ET.Element(f"{{{ns_drmd}}}document")
        ET.SubElement(doc_elem, f"{{{ns_dcc}}}fileName").text = file["name"]
        ET.SubElement(doc_elem, f"{{{ns_dcc}}}mimeType").text = file["mimeType"]
        ET.SubElement(doc_elem, f"{{{ns_dcc}}}dataBase64").text = base64.b64encode(file["data"]).decode('utf-8')
        return doc_elem
    return None

    # # Process existing embedded files
    # if "embedded_files" in st.session_state:
    #     for file in st.session_state.embedded_files:
    #         doc_elem = ET.Element(f"{{{ns_drmd}}}document")

    #         ET.SubElement(doc_elem, f"{{{ns_dcc}}}fileName").text = file["name"]
    #         ET.SubElement(doc_elem, f"{{{ns_dcc}}}mimeType").text = file["mimeType"]
    #         ET.SubElement(doc_elem, f"{{{ns_dcc}}}dataBase64").text = base64.b64encode(file["data"]).decode('utf-8')

    #         document_elements.append(doc_elem)

    # return document_elements

# --- Tab 5: Digital Signature ---
with tabs[5]:
    st.write("Under construction ...")

with tabs[6]:

    # Top row with Generate XML button and validation status
    col1, col2 = st.columns([2, 3])

    with col1:
        generate_button = st.button("Generate XML", key="generate_xml", use_container_width=True)

    # Only show this placeholder initially
    with col2:
        if not generate_button:
            st.write("Click the button to generate XML from your entered data.")

    if generate_button:
        # Define namespaces and register them.
        ns_drmd = "https://example.org/drmd"
        ns_dcc = "https://ptb.de/dcc"
        ns_si = "https://ptb.de/si"
        DS_NS = "http://www.w3.org/2000/09/xmldsig#"
        ET.register_namespace("drmd", ns_drmd)
        ET.register_namespace("dcc", ns_dcc)
        ET.register_namespace("si", ns_si)
        ET.register_namespace("ds", DS_NS)

        # Create the root element.
        root = ET.Element(
            f"{{{ns_drmd}}}digitalReferenceMaterialDocument",
            attrib={"schemaVersion": SCHEMA_VERSION},
        )

        # --- Build administrativeData ---
        admin_data = ET.SubElement(root, f"{{{ns_drmd}}}administrativeData")
        # coreData: title, uniqueIdentifier, identifications, validity.
        core_data = ET.SubElement(admin_data, f"{{{ns_drmd}}}coreData")
        ET.SubElement(core_data, f"{{{ns_drmd}}}titleOfTheDocument").text = st.session_state.title_option
        ET.SubElement(core_data, f"{{{ns_drmd}}}uniqueIdentifier").text = st.session_state.persistent_id_value
        if st.session_state.identifications:
            idents_elem = ET.SubElement(core_data, f"{{{ns_drmd}}}identifications")
            for ident in st.session_state.identifications:
                ident_elem = ET.SubElement(idents_elem, f"{{{ns_drmd}}}identification", attrib={"refType": "basic_certificateIdentification"})
                ET.SubElement(ident_elem, f"{{{ns_drmd}}}issuer").text = ident["issuer"]
                # If identification value is empty, default to "N/A"
                ET.SubElement(ident_elem, f"{{{ns_drmd}}}value").text = (ident["value"].strip() or "N/A")
                if (ident["idName"] or "").strip():
                    name_elem = ET.SubElement(ident_elem, f"{{{ns_drmd}}}name")
                    ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = ident["idName"]
        # Validity (simplified example)
        validity_elem = ET.SubElement(core_data, f"{{{ns_drmd}}}validity")
        if st.session_state.validity_type == "Time After Dispatch":
            tad = ET.SubElement(validity_elem, f"{{{ns_drmd}}}timeAfterDispatch")
            ET.SubElement(tad, f"{{{ns_drmd}}}dispatchDate").text = str(st.session_state.date_of_issue)
            ET.SubElement(tad, f"{{{ns_drmd}}}period").text = st.session_state.raw_validity_period
        elif st.session_state.validity_type == "Specific Time":
            ET.SubElement(validity_elem, f"{{{ns_drmd}}}specificTime").text = str(st.session_state.specific_time)
        else:
            ET.SubElement(validity_elem, f"{{{ns_drmd}}}untilRevoked").text = "true"


        # Reference Material Producer
        if not st.session_state.producers:
            prod_elem = ET.SubElement(admin_data, f"{{{ns_drmd}}}referenceMaterialProducer")
            prod_name_elem = ET.SubElement(prod_elem, f"{{{ns_drmd}}}name")
            ET.SubElement(prod_name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = "Dummy Producer"
        else:
            for prod in st.session_state.producers:
                prod_elem = ET.SubElement(admin_data, f"{{{ns_drmd}}}referenceMaterialProducer")
                prod_name_elem = ET.SubElement(prod_elem, f"{{{ns_drmd}}}name")
                ET.SubElement(prod_name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = prod.get("producerName", "")
                contact_elem = ET.SubElement(prod_elem, f"{{{ns_drmd}}}contact")
                contact_name_elem = ET.SubElement(contact_elem, f"{{{ns_dcc}}}name")
                ET.SubElement(contact_name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = prod.get("contactName", prod.get("producerName", "Contact Name"))
                if (prod.get("producerEmail", "") or "").strip():
                    ET.SubElement(contact_elem, f"{{{ns_dcc}}}eMail").text = prod.get("producerEmail", "")
                if (prod.get("producerPhone", "") or "").strip():
                    ET.SubElement(contact_elem, f"{{{ns_dcc}}}phone").text = prod.get("producerPhone", "")
                if (prod.get("producerFax", "") or "").strip():
                    ET.SubElement(contact_elem, f"{{{ns_dcc}}}fax").text = prod.get("producerFax", "")
                if (prod.get("producerStreet", "") or prod.get("producerStreetNo", "") or prod.get("producerPostCode", "")
                    or prod.get("producerCity", "") or prod.get("producerCountryCode", "")):
                    location_elem = ET.SubElement(contact_elem, f"{{{ns_dcc}}}location")
                    if (prod.get("producerStreet", "") or "").strip():
                        ET.SubElement(location_elem, f"{{{ns_dcc}}}street").text = prod.get("producerStreet", "")
                    if (prod.get("producerStreetNo", "") or "").strip():
                        ET.SubElement(location_elem, f"{{{ns_dcc}}}streetNo").text = prod.get("producerStreetNo", "")
                    if (prod.get("producerPostCode", "") or "").strip():
                        ET.SubElement(location_elem, f"{{{ns_dcc}}}postCode").text = prod.get("producerPostCode", "")
                    if (prod.get("producerCity", "") or "").strip():
                        ET.SubElement(location_elem, f"{{{ns_dcc}}}city").text = prod.get("producerCity", "")
                    if (prod.get("producerCountryCode", "") or "").strip():
                        ET.SubElement(location_elem, f"{{{ns_dcc}}}countryCode").text = prod.get("producerCountryCode", "")

        # Responsible Persons
        if not st.session_state.responsible_persons:
            respPersons_elem = ET.SubElement(admin_data, f"{{{ns_drmd}}}respPersons")
            rp_elem = ET.SubElement(respPersons_elem, f"{{{ns_dcc}}}respPerson")
            person_elem = ET.SubElement(rp_elem, f"{{{ns_dcc}}}person")
            name_elem = ET.SubElement(person_elem, f"{{{ns_dcc}}}name")
            ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = "Dummy Person"
            ET.SubElement(rp_elem, f"{{{ns_dcc}}}role").text = "Dummy Role"
        else:
            respPersons_elem = ET.SubElement(admin_data, f"{{{ns_drmd}}}respPersons")
            for rp in st.session_state.responsible_persons:
                rp_elem = ET.SubElement(respPersons_elem, f"{{{ns_dcc}}}respPerson")
                person_elem = ET.SubElement(rp_elem, f"{{{ns_dcc}}}person")
                name_elem = ET.SubElement(person_elem, f"{{{ns_dcc}}}name")
                ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = rp.get("personName", "")
                if (rp.get("description", "") or "").strip():
                    desc_elem = ET.SubElement(rp_elem, f"{{{ns_dcc}}}description")
                    ET.SubElement(desc_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = rp.get("description", "")
                if (rp.get("role", "") or "").strip():
                    ET.SubElement(rp_elem, f"{{{ns_dcc}}}role").text = rp.get("role", "")
                if rp.get("mainSigner", False):
                    ET.SubElement(rp_elem, f"{{{ns_dcc}}}mainSigner").text = "true"
                if rp.get("cryptElectronicSeal", False):
                    ET.SubElement(rp_elem, f"{{{ns_dcc}}}cryptElectronicSeal").text = "true"
                if rp.get("cryptElectronicSignature", False):
                    ET.SubElement(rp_elem, f"{{{ns_dcc}}}cryptElectronicSignature").text = "true"
                if rp.get("cryptElectronicTimeStamp", False):
                    ET.SubElement(rp_elem, f"{{{ns_dcc}}}cryptElectronicTimeStamp").text = "true"

        # Materials: using the list from the Materials form.
        materials_elem = ET.SubElement(root, f"{{{ns_drmd}}}materials")
        if not st.session_state.materials:
            # If no material was entered, add a dummy material.
            dummy = ET.SubElement(materials_elem, f"{{{ns_drmd}}}material")
            dummy_name = ET.SubElement(dummy, f"{{{ns_drmd}}}name")
            ET.SubElement(dummy_name, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = "Dummy Material"
        else:
            for material in st.session_state.materials:
                mat_elem = ET.SubElement(materials_elem, f"{{{ns_drmd}}}material")
                name_elem = ET.SubElement(mat_elem, f"{{{ns_drmd}}}name")
                ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = material.get("name", "")
                if (material.get("description", "") or "").strip():
                    desc_elem = ET.SubElement(mat_elem, f"{{{ns_drmd}}}description")
                    ET.SubElement(desc_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = material.get("description", "")
                # minimumSampleSize (required) – using a default value "0" if empty.
                min_sample_elem = ET.SubElement(mat_elem, f"{{{ns_drmd}}}minimumSampleSize")
                iq_elem = ET.SubElement(min_sample_elem, f"{{{ns_dcc}}}itemQuantity")
                realList_elem = ET.SubElement(iq_elem, f"{{{ns_si}}}realListXMLList")
                val_elem = ET.Element(f"{{{ns_si}}}valueXMLList")
                val_elem.text = (material.get("minimumSampleSize", "").strip() or "0")
                unit_elem = ET.Element(f"{{{ns_si}}}unitXMLList")
                unit_elem.text = ""
                realList_elem.append(val_elem)
                realList_elem.append(unit_elem)
                # Optional: itemQuantities
                if (material.get("itemQuantities", "") or "").strip():
                    itemQuant_elem = ET.SubElement(mat_elem, f"{{{ns_drmd}}}itemQuantities")
                    dummy_item = ET.SubElement(itemQuant_elem, f"{{{ns_dcc}}}itemQuantity")
                    dummy_rl = ET.SubElement(dummy_item, f"{{{ns_si}}}realListXMLList")
                    ET.SubElement(dummy_rl, f"{{{ns_si}}}valueXMLList").text = material.get("itemQuantities", "")
                    ET.SubElement(dummy_rl, f"{{{ns_si}}}unitXMLList").text = ""
                # identifications (required)
                ident_elem = ET.SubElement(mat_elem, f"{{{ns_drmd}}}identifications")
                ident = material.get("identification", {"issuer": "referenceMaterialProducer", "value": "", "idName": ""})
                ident_value = (ident.get("value", "").strip() or "N/A")
                ident_entry = ET.SubElement(ident_elem, f"{{{ns_drmd}}}identification")
                ET.SubElement(ident_entry, f"{{{ns_drmd}}}issuer").text = ident.get("issuer", "referenceMaterialProducer")
                ET.SubElement(ident_entry, f"{{{ns_drmd}}}value").text = ident_value
                if (ident.get("idName", "") or "").strip():
                    idname_elem = ET.SubElement(ident_entry, f"{{{ns_drmd}}}name")
                    ET.SubElement(idname_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = ident.get("idName", "")

        # Add material properties section next.
        mp_list_elem = export_materialProperties(ns_drmd, ns_dcc, ns_si)
        root.append(mp_list_elem)

        # Add the statements section after the material properties.
        statements_elem = export_statements(ns_drmd, ns_dcc)
        root.append(statements_elem)

    # --- Additional Elements ---


        # 3️ Add a single <comment> element, if provided.
        comment_elem = export_comment(ns_drmd)
        if comment_elem is not None:
            root.append(comment_elem)

        # 4️ Add a single <document> element, if provided.
        doc_elem = export_document(ns_drmd, ns_dcc)
        if doc_elem is not None:
            root.append(doc_elem)


        if st.session_state.get("digital_signature_cert"):
            ds_elem = ET.SubElement(root, f"{{{DS_NS}}}Signature")
            ds_elem.text = st.session_state.digital_signature_cert.name

        # Pretty-print XML.
        xml_str = ET.tostring(root, encoding="utf-8")
        try:
            from xml.dom import minidom
            reparsed = minidom.parseString(xml_str)
            pretty_xml = reparsed.toprettyxml(indent="  ")
        except Exception as e:
            st.error(f"Error during pretty-printing XML: {e}")
            pretty_xml = xml_str.decode("utf-8")

        # Validate XML against schema
        is_valid = False
        validation_message = ""
        try:
            schema = xmlschema.XMLSchema(DEFAULT_XSD_PATH)
            is_valid = schema.is_valid(pretty_xml)
            if not is_valid:
                # Get error log details
                errors = schema.validate(pretty_xml, use_defaults=False)
                validation_message = str(errors)
        except Exception as e:
            validation_message = f"Schema validation failed: {e}"

        # --- XSL Transformation to HTML ---
        try:
            # Parse the XSL file
            xslt_doc = etree.parse(DEFAULT_XSL_PATH)
            transform = etree.XSLT(xslt_doc)
            # Parse the generated XML
            xml_doc = etree.fromstring(pretty_xml.encode("utf-8"))
            # Transform XML to HTML
            result_tree = transform(xml_doc)
            html_output = etree.tostring(result_tree, pretty_print=True, encoding="utf-8").decode("utf-8")
        except Exception as e:
            st.error(f"XSL Transformation Error: {e}")
            html_output = ""

        # Download buttons row
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            st.download_button("Download HTML", data=html_output, file_name="certificate.html", mime="text/html", use_container_width=True)
        with col2:
            st.download_button("Download XML", data=pretty_xml, file_name="material_properties.xml", mime="application/xml", use_container_width=True)
        with col3:
            if is_valid:
                st.success("XML is valid against the schema!")
            else:
                st.error("XML is NOT valid against the schema!")

        # HTML preview (expanded by default)
        with st.expander("HTML Preview", expanded=True):
            st.components.v1.html(html_output, height=600, scrolling=True)

        # XML content (collapsed by default)
        with st.expander("XML Content", expanded=False):
            st.text_area("Generated XML", pretty_xml, height=400)

            # Show validation errors if any
            if not is_valid and validation_message:
                st.error("Validation Errors:")
                st.code(validation_message)
# (after your existing tabs, add “Help”)


with tabs[-1]:

    st.markdown("#### Application Overview  \n"
                "The DRMD Generator is a Streamlit-based tool for creating **Digital Reference Material Documents** "
                "that conform to the DRMD XML schema. It walks you through each section of a Reference Material "
                "Certificate—metadata, materials, measurement properties, statements, signatures, and export.")

    st.markdown("#### Main Sections  \n"
                "- **Administrative Data**: Document title, persistent identifier, unique RM identifiers, validity, "
                "producer and responsible-person details.  \n"
                "- **Materials** (formerly “Items”): Define one or more materials, their class, sample size, quantities "
                "and RM identifications.  \n"
                "- **Properties**: Specify measurement-property sets, certified values, uncertainties, and units.  \n"
                "- **Statements**: Capture official statements (intended use, traceability, safety, etc.) and add any custom notes.  \n"
                "- **Comments & Documents**: Attach external files or free-form remarks.  \n"
                "- **Digital Signature**: Apply XML Signature, e-seal, and timestamp options.  \n"
                "- **Validate & Export**: Run schema validation (drmd.xsd) and download your finished XML.  \n"
                "- **Help**: You’re here — background, schema mapping, dependencies, and version notes.")

    st.markdown("#### Schema Mapping  \n"
                "All fields map 1:1 to elements in **drmd.xsd** (version in `/drmd.xsd`). "
                "Key top-level XML elements are:  \n"
                "- `<digitalReferenceMaterialDocument>` (root)  \n"
                "- `<administrativeData>`: contains `<titleOfTheDocument>`, `<persistentIdentifier>`, `<identifications>`, `<validity>`, `<referenceMaterialProducer>`, `<respPersons>`  \n"
                "- `<materials>` _(the former `<items>` element)_ with child `<material>` entries: `<name>`, `<description>`, `<materialClass>`, `<minimumSampleSize>`, `<itemQuantities>`, `<identification>`, `<isCertified>`  \n"
                "- `<measurementResults>`: holds `<materialProperty>` sets, `<result>` elements, and `<quantities>` tables.  \n"
                "- `<statements>`: wraps official and custom statements.  \n"
                "- `<ds:Signature>`: optional XML Digital Signature nodes.")

    st.markdown("#### How to Use  \n"
                "1. **Load** an existing DRMD XML (optional) — fields populate automatically.  \n"
                "2. Work through each tab, filling in all required fields. Hover over ⓘ icons for inline help.  \n"
                "3. **Generate** the Persistent Identifier (UUID) or supply your own.  \n"
                "4. In **Validate & Export**, click “Validate” to catch schema errors, then “Download” to save your XML.")

    st.markdown("#### Dependencies  \n"
                "- Python 3.8+  \n"
                "- `streamlit`  \n"
                "- `pandas`  \n"
                "- `rdflib`  \n"
                "- `xmlschema`  \n"
                "- `lxml`")

    st.markdown("#### External Standards  \n"
                "- Based on the Digital Calibration Certificate (DCC) schema.  \n"
                "- Conforms to **ISO 33401** for reference material certificates.")


    st.markdown("#### Further Documentation  \n"
                "- Full DRMD schema and docs: [link-to-drmd-documentation]  \n"
                "- Original DCC schema: [link-to-dcc-schema]")

render_ui_settings_panel()