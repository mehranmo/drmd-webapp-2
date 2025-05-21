import re
import math
import streamlit as st
import xml.etree.ElementTree as ET
from datetime import date
import pandas as pd
import xmlschema

import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom
from rdflib import Graph, Namespace
import functools
import uuid
import base64
import traceback


# Set page layout to wide.
st.set_page_config(layout="wide")

# Use lxml for XSLT transformation and pretty printing.
try:
    from lxml import etree
except ImportError:
    st.error("lxml is required. Please install it via pip install lxml.")

# Inject custom CSS so that tables span the full width.
st.markdown("""
<style>
table {
    width: 100% !important;
}
div[data-baseweb="table"] {
    width: 100% !important;
}
</style>
""", unsafe_allow_html=True)



import re

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

# ------------------------------
# Helper: xs:duration hint
# ------------------------------
def xs_duration_hint():
    return "Enter a valid xs:duration (e.g. P2Y6M for 2 years 6 months)"

# ------------------------------
# Helper: Data Editor that updates the DataFrame in session_state.
# Accepts extra keyword arguments.
# ------------------------------
def data_editor_df(df, key, **kwargs):
    try:
        updated_df = st.data_editor(df, key=key, **kwargs)
    except TypeError:
        updated_df = st.data_editor(df, key=key)
    if key in st.session_state and hasattr(st.session_state[key], "edited_rows"):
        edits = st.session_state[key].edited_rows  # Format: {row_index: {column: new_value}}
        df_updated = df.copy()
        for row_str, changes in edits.items():
            try:
                idx = int(row_str)
                for col, new_val in changes.items():
                    df_updated.at[idx, col] = new_val
            except Exception as e:
                st.error(f"Error updating row {row_str}: {e}")
        return df_updated
    return updated_df

# ------------------------------
# Constants & Default Paths
# ------------------------------
DEFAULT_XSD_PATH = "./drmd.xsd"
DEFAULT_XSL_PATH = "./drmd.xsl"
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
ALLOWED_TITLES = ["productInformationSheet", "referenceMaterialCertificate"]
ALLOWED_ISSUERS = ["referenceMaterialProducer", "customer", "owner", "other"]



# ------------------------------
# QUDT Ontology Loading (cached)
# ------------------------------
@st.cache_data
def load_qudt_quantities_and_units():
    g = Graph()
    g.parse("qudt.ttl", format="turtle")  # Ensure qudt.ttl is available
    qudt = Namespace("http://qudt.org/schema/qudt/")
    # For simplicity, we extract applicable units per quantity kind.
    quantity_kinds = {}
    for s in g.subjects(None, qudt.QuantityKind):
        quantity_name = str(s).split("/")[-1]
        applicable_units = [str(unit).split("/")[-1] for unit in g.objects(s, qudt.applicableUnit)]
        quantity_kinds[quantity_name] = applicable_units if applicable_units else ["Custom"]
    return quantity_kinds

qudt_quantities = load_qudt_quantities_and_units()

# ------------------------------
# Helper Functions for Material Properties
# ------------------------------

def create_empty_materialProperties():
    return {
        "uuid": str(uuid.uuid4()),
        "id": "",
        "name": "",
        "description": "",
        "procedures": "",
        "isCertified": False,
        "results": []  # Each result is a dictionary
    }

def create_empty_result():
    return {
        "result_name": "",
        "description": "",
        "quantities": pd.DataFrame(columns=[
            "Name", "Label", "Value", "Quantity Type", "Unit",
            "Uncertainty", "Coverage Factor", "Coverage Probability", "Distribution"
        ])
    }
# ------------------------------
# Session State Initialization for Material Properties
# ------------------------------
# ------------------------------
# Session State Initialization for Material Properties
# ------------------------------
if "materialProperties" not in st.session_state:
    st.session_state.materialProperties = []  # List for materialProperties entries.
if "selected_quantity" not in st.session_state:
    st.session_state.selected_quantity = ""
if "selected_unit" not in st.session_state:
    st.session_state.selected_unit = ""
if "coverage_factor" not in st.session_state:
    st.session_state.coverage_factor = 2.0
if "coverage_probability" not in st.session_state:
    st.session_state.coverage_probability = 0.95
if "distribution" not in st.session_state:
    st.session_state.distribution = "normal"

# ------------------------------
# Session State Initialization
# ------------------------------
if "materials_df" not in st.session_state:
    st.session_state.materials_df = pd.DataFrame(columns=["Material Name", "Description", "Minimum Sample Size", "Unit"])
if "materials" not in st.session_state:
    # For our new form-based material entry, we store a list of dicts.
    st.session_state.materials = []
if "mp_tables" not in st.session_state:
    st.session_state.mp_tables = []  # Each material properties table.
if "identifications" not in st.session_state:
    st.session_state.identifications = [{"issuer": "referenceMaterialProducer", "value": "", "idName": ""}]
    # st.session_state.identifications = []

if "responsible_persons" not in st.session_state:
    st.session_state.responsible_persons = [{
        "personName": "",
        "description": "",
        "role": "",
        "mainSigner": False,
        "cryptElectronicSeal": False,
        "cryptElectronicSignature": False,
        "cryptElectronicTimeStamp": False
    }]

if "producers" not in st.session_state:
    st.session_state.producers = [{"producerName": "", "producerStreet": "", "producerStreetNo": "",
                                     "producerPostCode": "", "producerCity": "", "producerCountryCode": "",
                                     "producerPhone": "", "producerFax": "", "producerEmail": ""}]

if "official_statements" not in st.session_state:
    # Each official statement is stored as a dict with optional 'name' and required 'content'
    st.session_state.official_statements = {
        "intendedUse": {"name": "", "content": ""},
        "commutability": {"name": "", "content": ""},
        "storageInformation": {"name": "", "content": ""},
        "instructionsForHandlingAndUse": {"name": "", "content": ""},
        "metrologicalTraceability": {"name": "", "content": ""},
        "healthAndSafetyInformation": {"name": "", "content": ""},
        "subcontractors": {"name": "", "content": ""},
        "legalNotice": {"name": "", "content": ""},
        "referenceToCertificationReport": {"name": "", "content": ""}
    }
if "custom_statements" not in st.session_state:
    # Custom statements will always be exported as <drmd:statement> elements.
    # We store each as a dict with keys "name" (the label) and "content" (the text).
    st.session_state.custom_statements = []

if "title_option" not in st.session_state:
    st.session_state.title_option = ALLOWED_TITLES[0]
if "unique_id" not in st.session_state:
    st.session_state.unique_id = ""
if "validity_type" not in st.session_state:
    st.session_state.validity_type = "Until Revoked"
if "raw_validity_period" not in st.session_state:
    st.session_state.raw_validity_period = ""
if "date_of_issue" not in st.session_state:
    st.session_state.date_of_issue = date.today()
if "specific_time" not in st.session_state:
    st.session_state.specific_time = date.today()
if "template_loaded" not in st.session_state:
    st.session_state.template_loaded = False



# ------------------------------
# Sidebar: Load XML Template for Editing
# ------------------------------
st.sidebar.header("Load XML Template")
xml_template = st.sidebar.file_uploader("Load XML Template", type=["xml"])

if st.sidebar.button("Reset App and All Fields", key="reset"):
    # Clear all keys from session_state.
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()



# ------------------------------
# Load XML Template (modified to load materials with all keys)

def export_statements(ns_drmd, ns_dcc):
    # Create the root <drmd:statements> element.
    statements_elem = ET.Element(f"{{{ns_drmd}}}statements")
    
    def add_statement(element_name, label, text):
        if text.strip():
            stmt = ET.SubElement(statements_elem, f"{{{ns_drmd}}}{element_name}")
            # Only add the dcc:name element if a label is provided.
            if label.strip():
                name_elem = ET.SubElement(stmt, f"{{{ns_dcc}}}name")
                ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = label.strip()
            # Add the content (for simplicity, as a single node)
            ET.SubElement(stmt, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = text.strip()
    
    official = st.session_state.official_statements
    # For each official statement, use its element name.
    add_statement("intendedUse", "Intended Use", official.get("intendedUse", {}).get("content", ""))
    add_statement("commutability", "Commutability", official.get("commutability", {}).get("content", ""))
    add_statement("storageInformation", "Storage Information", official.get("storageInformation", {}).get("content", ""))
    add_statement("instructionsForHandlingAndUse", "Handling Instructions", official.get("instructionsForHandlingAndUse", {}).get("content", ""))
    add_statement("metrologicalTraceability", "Metrological Traceability", official.get("metrologicalTraceability", {}).get("content", ""))
    add_statement("healthAndSafetyInformation", "Health and Safety Information", official.get("healthAndSafetyInformation", {}).get("content", ""))
    add_statement("subcontractors", "Subcontractors", official.get("subcontractors", {}).get("content", ""))
    add_statement("legalNotice", "Legal Notice", official.get("legalNotice", {}).get("content", ""))
    add_statement("referenceToCertificationReport", "Reference to Certification Report", official.get("referenceToCertificationReport", {}).get("content", ""))
    
    # Custom statements: always export as <drmd:statement>
    for cs in st.session_state.custom_statements:
        if cs.get("content", "").strip():
            cs_elem = ET.SubElement(statements_elem, f"{{{ns_drmd}}}statement")
            if cs.get("name", "").strip():
                name_elem = ET.SubElement(cs_elem, f"{{{ns_dcc}}}name")
                ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = cs.get("name", "").strip()
            ET.SubElement(cs_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = cs.get("content", "").strip()
    
    return statements_elem


# ------------------------------
def load_template_once(xml_content):
    if xml_content and not st.session_state.template_loaded:
        try:
            tree = ET.parse(xml_content)
            root = tree.getroot()
            ns = {
                "drmd": "https://example.org/drmd",
                "dcc": "https://ptb.de/dcc",
                "si": "https://ptb.de/si"
            }
            # Load title and unique identifier.
            title_elem = root.find(".//drmd:titleOfTheDocument", ns)
            if title_elem is not None and title_elem.text:
                st.session_state.title_option = title_elem.text.strip() if title_elem.text.strip() in ALLOWED_TITLES else ALLOWED_TITLES[0]
            uid_elem = root.find(".//drmd:uniqueIdentifier", ns)
            if uid_elem is not None and uid_elem.text:
                st.session_state.unique_id = uid_elem.text.strip()
            # Load validity.
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
                        st.session_state.date_of_issue = dd_elem.text.strip()
                elif validity_elem.find("drmd:specificTime", ns) is not None:
                    st.session_state.validity_type = "Specific Time"
                    spec_elem = validity_elem.find("drmd:specificTime", ns)
                    if spec_elem is not None and spec_elem.text:
                        st.session_state.specific_time = spec_elem.text.strip()
            # Load identifications.
            idents = []
            for ident_elem in root.findall(".//drmd:identifications/drmd:identification", ns):
                issuer = ident_elem.find("drmd:issuer", ns)
                value = ident_elem.find("drmd:value", ns)
                name_elem = ident_elem.find("drmd:name/dcc:content", ns)
                idents.append({
                    "issuer": issuer.text.strip() if issuer is not None and issuer.text else "",
                    "value": value.text.strip() if value is not None and value.text else "",
                    "idName": " ".join(name_elem.text.split()) if name_elem is not None and name_elem.text else ""
                })
            if idents:
                st.session_state.identifications = idents
            # Load Producers.
            prods = []
            for prod_elem in root.findall(".//drmd:referenceMaterialProducer", ns):
                name_elem = prod_elem.find("drmd:name/dcc:content", ns)
                contact_elem = prod_elem.find("drmd:contact", ns)
                street = streetNo = postCode = city = country = phone = fax = email = ""
                if contact_elem is not None:
                    contact_name = contact_elem.find("dcc:name", ns)
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
            # Load Responsible Persons (including additional fields).
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
            # Load Materials.
            mats = []
            for mat_elem in root.findall(".//drmd:materials/drmd:material", ns):
                name_elem = mat_elem.find("drmd:name/dcc:content", ns)
                desc_elem = mat_elem.find("drmd:description/dcc:content", ns)
                sample_elem = mat_elem.find("drmd:minimumSampleSize/dcc:itemQuantity/si:realListXMLList/si:valueXMLList", ns)
                # Build material dictionary with all required keys.
                mats.append({
                    "name": name_elem.text.strip() if name_elem is not None and name_elem.text else "",
                    "description": " ".join(desc_elem.text.split()) if desc_elem is not None and desc_elem.text else "",
                    "materialClass": "",
                    "minimumSampleSize": sample_elem.text.strip() if sample_elem is not None and sample_elem.text else "",
                    "itemQuantities": "",
                    "identification": {"issuer": "referenceMaterialProducer", "value": "", "idName": ""},
                    "isCertified": False
                })

            if mats:
                for mat in mats:  # where 'mats' is your list of material dictionaries
                    if "uuid" not in mat:
                        mat["uuid"] = str(uuid.uuid4())
                st.session_state.materials_df = pd.DataFrame(mats)
                st.session_state.materials = mats

            # --- Load Statements ---
            official_keys = ["intendedUse", "commutability", "storageInformation", 
                            "instructionsForHandlingAndUse", "metrologicalTraceability",
                            "healthAndSafetyInformation", "subcontractors", 
                            "legalNotice", "referenceToCertificationReport"]
            official_statements = { key: {"name": "", "content": ""} for key in official_keys }
            custom_statements = []
            
            statements_elem = root.find(".//drmd:statements", ns)
            if statements_elem is not None:
                for child in statements_elem:
                    # Get the local tag name
                    tag = child.tag.split("}")[1]
                    # Extract the optional name.
                    name_elem = child.find("dcc:name/dcc:content", ns)
                    name_text = clean_text(name_elem.text) if name_elem is not None and name_elem.text else ""
                    # Extract all direct dcc:content children (excluding the one inside dcc:name).
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
            # --- Load Material Properties ---
            mps = []
            mp_list_elem = root.find("drmd:materialPropertiesList", ns)
            if mp_list_elem is not None:
                for mp_elem in mp_list_elem.findall("drmd:materialProperties", ns):
                    mp_dict = {}
                    # isCertified attribute.
                    mp_dict["isCertified"] = True if mp_elem.attrib.get("isCertified", "false").lower() == "true" else False
                    # Optional attribute id.
                    mp_dict["id"] = mp_elem.attrib.get("id", "").strip()
                    # Name (required)
                    name_elem = mp_elem.find("drmd:name/dcc:content", ns)
                    mp_dict["name"] = clean_text(name_elem.text) if name_elem is not None else ""
                    # Description (optional)
                    desc_elem = mp_elem.find("drmd:description/dcc:content", ns)
                    mp_dict["description"] = clean_text(desc_elem.text) if desc_elem is not None else ""
                    # Procedures (optional)
                    proc_elem = mp_elem.find("drmd:procedures/dcc:content", ns)
                    mp_dict["procedures"] = clean_text(proc_elem.text) if proc_elem is not None else ""
                    
                    # Results (required)
                    results = []
                    results_elem = mp_elem.find("drmd:results", ns)
                    if results_elem is not None:
                        for res_elem in results_elem.findall("dcc:result", ns):
                            res_dict = {}
                            res_name_elem = res_elem.find("dcc:name/dcc:content", ns)
                            res_dict["result_name"] = clean_text(res_name_elem.text) if res_name_elem is not None else ""
                            res_desc_elem = res_elem.find("dcc:description/dcc:content", ns)
                            res_dict["description"] = clean_text(res_desc_elem.text) if res_desc_elem is not None else ""
                            # Quantities
                            quantities = []
                            data_elem = res_elem.find("dcc:data", ns)
                            if data_elem is not None:
                                list_elem = data_elem.find("dcc:list", ns)
                                if list_elem is not None:
                                    for quant_elem in list_elem.findall("dcc:quantity", ns):
                                        quant = {}
                                        # Get quantity name.
                                        qname_elem = quant_elem.find("dcc:name/dcc:content", ns)
                                        quant["Name"] = clean_text(qname_elem.text) if qname_elem is not None else ""
                                        # We'll leave Label and Quantity Type as empty for now.
                                        quant["Label"] = ""
                                        quant["Quantity Type"] = ""
                                        # Get real value.
                                        real_elem = quant_elem.find("si:real", ns)
                                        if real_elem is not None:
                                            value_elem = real_elem.find("si:value", ns)
                                            quant["Value"] = float(value_elem.text.strip()) if value_elem is not None and value_elem.text else None
                                            unit_elem = real_elem.find("si:unit", ns)
                                            quant["Unit"] = unit_elem.text.strip() if unit_elem is not None and unit_elem.text else ""
                                            # Measurement uncertainty.
                                            mu_elem = real_elem.find("si:measurementUncertaintyUnivariate/si:expandedMU", ns)
                                            if mu_elem is not None:
                                                val_mu = mu_elem.find("si:valueExpandedMU", ns)
                                                quant["Uncertainty"] = float(val_mu.text.strip()) if val_mu is not None and val_mu.text else None
                                                cf_elem = mu_elem.find("si:coverageFactor", ns)
                                                quant["Coverage Factor"] = float(cf_elem.text.strip()) if cf_elem is not None and cf_elem.text else None
                                                cp_elem = mu_elem.find("si:coverageProbability", ns)
                                                quant["Coverage Probability"] = float(cp_elem.text.strip()) if cp_elem is not None and cp_elem.text else None
                                                dist_elem = mu_elem.find("si:distribution", ns)
                                                quant["Distribution"] = dist_elem.text.strip() if dist_elem is not None and dist_elem.text else ""
                                        quantities.append(quant)
                            # Convert list of quantities to a DataFrame.
                            df_quant = pd.DataFrame(quantities, columns=["Name", "Label", "Value", "Quantity Type", "Unit", "Uncertainty", "Coverage Factor", "Coverage Probability", "Distribution"])
                            res_dict["quantities"] = df_quant
                            results.append(res_dict)
                    mp_dict["results"] = results
                    # Assign a new UUID for internal use.
                    mp_dict["uuid"] = str(uuid.uuid4())
                    mps.append(mp_dict)
            if mps:
                st.session_state.materialProperties = mps
            # --- End Load Material Properties ---
            

            # Extract all <comment> elements separately
            comments = []
            for comment_elem in root.findall(".//drmd:comment", ns):
                if comment_elem.text:
                    comments.append(comment_elem.text.strip())

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

            # Store extracted data in session state
            st.session_state.comments = comments
            st.session_state.embedded_files = embedded_files  # Store extracted files

            st.session_state.template_loaded = True

        except Exception as e:
            st.error(f"Error loading template: {e}")
            st.error(traceback.format_exc())



if xml_template is not None:
    load_template_once(xml_template)


# ------------------------------
# Main Tabs
# ------------------------------
tabs = st.tabs([
    "Administrative Data",
    "Materials Properties",
    "Statements",
    "Comments & Documents",
    "Digital Signature",
    "Validate & Export"
])

# ------------------------------
# Tab 1: Administrative Data (Compact Layout)
# ------------------------------
with tabs[0]:
    st.header("Administrative Data")

    # Basic Information Expander.
    with st.expander("Basic Information", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.selectbox("Title of Document", options=ALLOWED_TITLES, key="title_option")
            st.text_input("Unique Identifier", key="unique_id")
        with col2:
            validity_choice = st.selectbox("Validity Type", options=["Until Revoked", "Time After Dispatch", "Specific Time"], key="validity_type")
            if validity_choice == "Time After Dispatch":
                st.text_input("Period (e.g. P2Y6M)", key="raw_validity_period", placeholder="P2Y6M")
                st.date_input("Dispatch Date", key="date_of_issue")
            elif validity_choice == "Specific Time":
                st.date_input("Specific Time", key="specific_time")

        st.markdown("#### Identifications")
        # If there are no identifications, add a single empty identification for user entry.
        # if not st.session_state.identifications:
        #     st.session_state.identifications.append({"issuer": "referenceMaterialProducer", "value": "", "idName": ""})

        for idx, ident in enumerate(st.session_state.identifications):
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                # Use .get() so if key is missing, default is provided.
                ident["issuer"] = st.selectbox("Issuer", options=ALLOWED_ISSUERS, key=f"ident_issuer_{idx}",
                                            index=ALLOWED_ISSUERS.index(ident.get("issuer", "referenceMaterialProducer"))
                                            if ident.get("issuer", "") in ALLOWED_ISSUERS else 0)
            with col_b:
                ident["value"] = st.text_input("Value", value=ident.get("value", ""), key=f"ident_value_{idx}")
            with col_c:
                ident["idName"] = st.text_input("ID Name", value=ident.get("idName", ""), key=f"ident_name_{idx}")

        if st.button("Add Identification", key="add_ident"):
            st.session_state.identifications.append({"issuer": ALLOWED_ISSUERS[0], "value": "", "idName": ""})
            try:
                st.rerun()
            except AttributeError:
                pass



    with st.expander("Materials", expanded=True):
        st.subheader("Materials Entry")
        for i, material in enumerate(st.session_state.materials):
            # Use the material's unique UUID in the form key.
            with st.form(key=f"material_form_{material['uuid']}"):
                st.markdown(f"**Material {i+1}**")
                mat_name = st.text_input("Material Name", value=material.get("name", ""), key=f"material_name_{material['uuid']}")
                mat_desc = st.text_area("Description", value=material.get("description", ""), key=f"material_desc_{material['uuid']}")
                mat_class = st.text_input("Material Class", value=material.get("materialClass", ""), key=f"material_class_{material['uuid']}")
                min_sample = st.text_input("Minimum Sample Size", value=material.get("minimumSampleSize", ""), key=f"material_min_sample_{material['uuid']}")
                item_quant = st.text_input("Item Quantities", value=material.get("itemQuantities", ""), key=f"material_item_quant_{material['uuid']}")
                st.markdown("#### Identification (required)")
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    ident_issuer = st.selectbox("Issuer", options=ALLOWED_ISSUERS,
                                                index=ALLOWED_ISSUERS.index(material.get("identification", {}).get("issuer", "referenceMaterialProducer"))
                                                if material.get("identification", {}).get("issuer", "") in ALLOWED_ISSUERS else 0,
                                                key=f"material_ident_issuer_{material['uuid']}")
                with col_b:
                    ident_value = st.text_input("Identification Value", value=material.get("identification", {}).get("value", ""), key=f"material_ident_value_{material['uuid']}")
                with col_c:
                    ident_idName = st.text_input("Identification Name", value=material.get("identification", {}).get("idName", ""), key=f"material_ident_idName_{material['uuid']}")
                is_certified = st.checkbox("Certified", value=material.get("isCertified", False), key=f"mat_certified_{material['uuid']}")
                submit_material = st.form_submit_button("Save Material")
                if submit_material:
                    st.session_state.materials[i] = {
                        "uuid": material["uuid"],
                        "name": mat_name,
                        "description": mat_desc,
                        "materialClass": mat_class,
                        "minimumSampleSize": min_sample,
                        "itemQuantities": item_quant,
                        "identification": {
                            "issuer": ident_issuer,
                            "value": (ident_value.strip() or "N/A"),
                            "idName": ident_idName
                        },
                        "isCertified": is_certified
                    }
                    st.success(f"Material {i+1} updated!")
            if st.button(f"Remove Material {i+1}", key=f"remove_material_{material['uuid']}"):
                st.session_state.materials.pop(i)
                try:
                    st.rerun()
                except AttributeError:
                    pass
        if st.button("Add New Material", key="add_material"):
            st.session_state.materials.append({
                "uuid": str(uuid.uuid4()),
                "name": "",
                "description": "",
                "materialClass": "",
                "minimumSampleSize": "",
                "itemQuantities": "",
                "identification": {"issuer": "referenceMaterialProducer", "value": "", "idName": ""},
                "isCertified": False
            })
            try:
                st.rerun()
            except AttributeError:
                pass

    # Reference Material Producer and Responsible Persons section remains unchanged.
    with st.expander("Reference Material Producer and Responsible Persons", expanded=True):
        st.subheader("Reference Material Producers")
        with st.container():
            for idx, prod in enumerate(st.session_state.producers):
                st.markdown(f"**Producer {idx+1}**")
                cols = st.columns(2)
                with cols[0]:
                    prod["producerName"] = st.text_input("Name", value=prod.get("producerName", ""), key=f"producerName_{idx}")
                    prod["producerStreet"] = st.text_input("Street", value=prod.get("producerStreet", ""), key=f"producerStreet_{idx}")
                    prod["producerPostCode"] = st.text_input("Post Code", value=prod.get("producerPostCode", ""), key=f"producerPostCode_{idx}")
                with cols[1]:
                    prod["producerStreetNo"] = st.text_input("Street No", value=prod.get("producerStreetNo", ""), key=f"producerStreetNo_{idx}")
                    prod["producerCity"] = st.text_input("City", value=prod.get("producerCity", ""), key=f"producerCity_{idx}")
                    prod["producerCountryCode"] = st.text_input("Country Code", value=prod.get("producerCountryCode", ""), key=f"producerCountryCode_{idx}")
                    prod["producerPhone"] = st.text_input("Phone", value=prod.get("producerPhone", ""), key=f"producerPhone_{idx}")
                    prod["producerFax"] = st.text_input("Fax", value=prod.get("producerFax", ""), key=f"producerFax_{idx}")
                    prod["producerEmail"] = st.text_input("Email", value=prod.get("producerEmail", ""), key=f"producerEmail_{idx}")
                st.write("---")
            if st.button("Add Producer", key="add_prod"):
                st.session_state.producers.append({
                    "producerName": "",
                    "producerStreet": "",
                    "producerStreetNo": "",
                    "producerPostCode": "",
                    "producerCity": "",
                    "producerCountryCode": "",
                    "producerPhone": "",
                    "producerFax": "",
                    "producerEmail": ""
                })
                try:
                    st.rerun()
                except AttributeError:
                    pass

        st.subheader("Responsible Persons")
        with st.container():
            for idx, rp in enumerate(st.session_state.responsible_persons):
                st.markdown(f"**Responsible Person {idx+1}**")
                cols = st.columns(3)
                with cols[0]:
                    rp["personName"] = st.text_input("Name", value=rp.get("personName", ""), key=f"rp_name_{idx}")
                    rp["description"] = st.text_area("Description", value=rp.get("description", ""), key=f"rp_desc_{idx}")
                with cols[1]:
                    rp["role"] = st.text_input("Role", value=rp.get("role", ""), key=f"rp_role_{idx}")
                with cols[2]:
                    rp["mainSigner"] = st.checkbox("Main Signer", value=rp.get("mainSigner", False), key=f"rp_mainSigner_{idx}")
                    rp["cryptElectronicSeal"] = st.checkbox("Crypt Electronic Seal", value=rp.get("cryptElectronicSeal", False), key=f"rp_cryptSeal_{idx}")
                    rp["cryptElectronicSignature"] = st.checkbox("Crypt Electronic Signature", value=rp.get("cryptElectronicSignature", False), key=f"rp_cryptSig_{idx}")
                    rp["cryptElectronicTimeStamp"] = st.checkbox("Crypt Electronic TimeStamp", value=rp.get("cryptElectronicTimeStamp", False), key=f"rp_cryptTS_{idx}")
                if st.button(f"Remove Responsible Person {idx+1}", key=f"remove_rp_{idx}"):
                    st.session_state.responsible_persons.pop(idx)
                    try:
                        st.rerun()
                    except AttributeError:
                        pass
                st.write("---")
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
                try:
                    st.rerun()
                except AttributeError:
                    pass
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
# --- Tab 2: Materials Properties (Editable Material Properties Tables) ---
with tabs[1]:

    col_left, col_right = st.columns([3.5, 1])

    with col_left:
        material_scroll = st.container(height=1000)
        with material_scroll:

            st.subheader("Material Properties List")
            # Button to add a new material properties entry.
            if st.button("Add Material Properties"):
                st.session_state.materialProperties.append(create_empty_materialProperties())
                st.rerun()
            
            # Loop over each materialProperties entry.
            for idx, mp in enumerate(st.session_state.materialProperties):
                # Ensure each entry has a UUID.
                mp_uuid = mp.get("uuid", str(uuid.uuid4()))
                mp["uuid"] = mp_uuid
                with st.expander(f"Material Properties {idx+1}", expanded=False):
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
                        
                        submitted_mp = st.form_submit_button("Save Material Properties")
                        if submitted_mp:
                            st.success(f"Material Properties {idx+1} updated!")
                    st.markdown("### Measurement Results")
                    # Button to add a new measurement result.
                    if st.button("Add Measurement Result", key=f"add_result_{mp_uuid}"):
                        mp.setdefault("results", []).append(create_empty_result())
                        st.rerun()
                    
                    # For each measurement result (non-nested forms)
                    for res_idx, result in enumerate(mp.get("results", [])):
                        with st.form(key=f"res_form_{mp_uuid}_{res_idx}"):
                            result["result_name"] = st.text_input("Result Name", value=result.get("result_name", ""), key=f"res_name_{mp_uuid}_{res_idx}")
                            result["description"] = st.text_area("Result Description", value=result.get("description", ""), key=f"res_desc_{mp_uuid}_{res_idx}")
                            # Use data_editor for the quantities DataFrame.
                            result["quantities"] = st.data_editor(
                                result.get("quantities", pd.DataFrame(columns=[
                                    "Name", "Label", "Value", "Quantity Type", "Unit",
                                    "Uncertainty", "Coverage Factor", "Coverage Probability", "Distribution"
                                ])),
                                num_rows="dynamic",
                                key=f"quantities_{mp_uuid}_{res_idx}"
                            )
                            # Button to add a new row with defaults.
                            if st.form_submit_button("Add New Row and Apply Quantity and Unit"):
                                new_row = pd.DataFrame([{
                                    "Quantity Type": st.session_state.get("selected_quantity", ""),
                                    "Name": "",
                                    "Label": "",
                                    "Value": "",
                                    "Unit": st.session_state.get("selected_unit", ""),
                                    "Uncertainty": "",
                                    "Coverage Factor": "",
                                    "Coverage Probability": "",
                                    "Distribution": ""
                                }])
                                result["quantities"] = pd.concat([result["quantities"], new_row], ignore_index=True)
                                st.rerun()
                            # Button to apply default uncertainty values to all rows.
                            if st.form_submit_button("Apply Uncertainty to All Rows"):
                                result["quantities"]["Coverage Factor"] = st.session_state.get("coverage_factor", 2.0)
                                result["quantities"]["Coverage Probability"] = st.session_state.get("coverage_probability", 0.95)
                                result["quantities"]["Distribution"] = st.session_state.get("distribution", "normal")
                                st.rerun()
                        if st.button("Remove Result", key=f"remove_res_{mp_uuid}_{res_idx}"):
                            mp["results"].pop(res_idx)
                            st.rerun()
                        st.markdown("---")
                    
                    if st.button("Remove Material Properties", key=f"remove_mp_{mp_uuid}"):
                        st.session_state.materialProperties.pop(idx)
                        st.rerun()

        with col_right:
            st.header("Defaults & Selections")
            st.session_state.selected_quantity = st.selectbox("Quantity Type", list(qudt_quantities.keys()) + ["Custom"], key="quantity_select")
            st.session_state.selected_unit = st.selectbox("Unit", qudt_quantities.get(st.session_state.selected_quantity, ["Custom"]), key="unit_select")
            st.subheader("Default Uncertainty Values")
            # Do not reassign st.session_state keys – capture widget values.
            coverage_factor = st.number_input("Coverage Factor", value=st.session_state.get("coverage_factor", 2.0), key="coverage_factor")
            coverage_probability = st.number_input("Coverage Probability", value=st.session_state.get("coverage_probability", 0.95), key="coverage_probability")
            distribution = st.selectbox("Distribution", ["normal", "log-normal", "uniform"], key="distribution")
            # You can then use these local variables; no need to reassign into st.session_state.
            
    # ------------------------------
    # XML Export for Material Properties Tab (to be integrated in the Export Tab)
    # ------------------------------
# def export_materialProperties(ns_drmd, ns_dcc, ns_si):
#     # Create the wrapping element.
#     mp_list_elem = ET.Element(f"{{{ns_drmd}}}materialPropertiesList")
#     for mp in st.session_state.materialProperties:
#         mp_elem = ET.SubElement(mp_list_elem, f"{{{ns_drmd}}}materialProperties", attrib={
#             "isCertified": "true" if mp.get("isCertified", False) else "false"
#         })
#         if mp.get("id", "").strip():
#             mp_elem.set("id", mp.get("id").strip())
#         # Required: name
#         name_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}name")
#         ET.SubElement(name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = mp.get("name", "")
#         # Optional: description
#         if mp.get("description", "").strip():
#             desc_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}description")
#             ET.SubElement(desc_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = mp.get("description", "")
#         # Optional: procedures
#         if mp.get("procedures", "").strip():
#             proc_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}procedures")
#             ET.SubElement(proc_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = mp.get("procedures", "")
#         # Required: results
#         results_elem = ET.SubElement(mp_elem, f"{{{ns_drmd}}}results")
#         for res in mp.get("results", []):
#             res_elem = ET.SubElement(results_elem, f"{{{ns_dcc}}}result")
#             res_name_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}name")
#             ET.SubElement(res_name_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = res.get("result_name", "")
#             if res.get("description", "").strip():
#                 res_desc_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}description")
#                 ET.SubElement(res_desc_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = res.get("description", "")
#             data_elem = ET.SubElement(res_elem, f"{{{ns_dcc}}}data")
#             list_elem = ET.SubElement(data_elem, f"{{{ns_dcc}}}list")
#             for _, row in res.get("quantities", pd.DataFrame()).iterrows():
#                 quantity_elem = ET.SubElement(list_elem, f"{{{ns_dcc}}}quantity", attrib={"refType": "basic_measuredValue"})
#                 qname_elem = ET.SubElement(quantity_elem, f"{{{ns_dcc}}}name")
#                 ET.SubElement(qname_elem, f"{{{ns_dcc}}}content", attrib={"lang": "en"}).text = str(row.get("Name", ""))
#                 real_elem = ET.SubElement(quantity_elem, f"{{{ns_si}}}real")
#                 ET.SubElement(real_elem, f"{{{ns_si}}}value").text = str(row.get("Value", ""))
#                 ET.SubElement(real_elem, f"{{{ns_si}}}unit").text = str(row.get("Unit", ""))
#                 mu_elem = ET.SubElement(real_elem, f"{{{ns_si}}}measurementUncertaintyUnivariate")
#                 expMU_elem = ET.SubElement(mu_elem, f"{{{ns_si}}}expandedMU")
#                 ET.SubElement(expMU_elem, f"{{{ns_si}}}valueExpandedMU").text = str(row.get("Uncertainty", ""))
#                 ET.SubElement(expMU_elem, f"{{{ns_si}}}coverageFactor").text = str(row.get("Coverage Factor", ""))
#                 ET.SubElement(expMU_elem, f"{{{ns_si}}}coverageProbability").text = str(row.get("Coverage Probability", ""))
#                 ET.SubElement(expMU_elem, f"{{{ns_si}}}distribution").text = str(row.get("Distribution", ""))
#     return mp_list_elem

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


with tabs[2]:
    st.header("Statements")
    
    # Official Statements (using dcc:richContentType structure)
    with st.expander("Official Statements", expanded=True):
        st.subheader("Official Statements")
        for key in st.session_state.official_statements:
            st.markdown(f"**{key}**")
            # Use safe .get() for each field.
            name_val = st.text_input(f"{key} Name (optional)", value=st.session_state.official_statements.get(key, {}).get("name", ""), key=f"official_name_{key}")
            content_val = st.text_area(f"{key} Content", value=st.session_state.official_statements.get(key, {}).get("content", ""), key=f"official_content_{key}")
            st.session_state.official_statements[key] = {"name": name_val, "content": content_val}
            st.markdown("---")
    
    # Custom Statements (all exported as <drmd:statement>)
    with st.expander("Custom Statements", expanded=True):
        st.subheader("Custom Statements")
        for idx, cs in enumerate(st.session_state.custom_statements):
            with st.container():
                # We ignore any custom tag; the export will use <drmd:statement>
                cs_name = st.text_input(f"Custom Statement {idx+1} - Name (optional)", value=cs.get("name", "").strip(), key=f"cs_name_{idx}")
                cs_content = st.text_area(f"Custom Statement {idx+1} - Content", value=cs.get("content", "").strip(), key=f"cs_content_{idx}")
                st.session_state.custom_statements[idx] = {"name": cs_name, "content": cs_content}
                if st.button(f"Remove Custom Statement {idx+1}", key=f"remove_cs_{idx}"):
                    st.session_state.custom_statements.pop(idx)
                    st.rerun()
                st.markdown("---")
        if st.button("Add Custom Statement", key="add_cs"):
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
with tabs[3]:
    st.header("Comments and Attachments")

    # Single Comment (instead of multiple separate comment elements)
    st.subheader("Comment")
    comment = st.text_area("Enter your comment", value=st.session_state.get("comment", ""), key="comment")

    # --- Document Upload ---
    st.subheader("Upload Document")
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
with tabs[4]:
    st.header("Digital Signature")
    st.write("Under construction ...")

with tabs[5]:
    st.header("Validate & Export")
    st.write("Click the button below to generate the complete XML from your entered data.")
    
    if st.button("Generate XML", key="generate_xml"):
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
        root = ET.Element(f"{{{ns_drmd}}}digitalReferenceMaterialDocument", attrib={"schemaVersion": "0.1.1"})
        
        # --- Build administrativeData ---
        admin_data = ET.SubElement(root, f"{{{ns_drmd}}}administrativeData")
        # coreData: title, uniqueIdentifier, identifications, validity.
        core_data = ET.SubElement(admin_data, f"{{{ns_drmd}}}coreData")
        ET.SubElement(core_data, f"{{{ns_drmd}}}titleOfTheDocument").text = st.session_state.title_option
        ET.SubElement(core_data, f"{{{ns_drmd}}}uniqueIdentifier").text = st.session_state.unique_id
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
        
        # Materials: using the list from the Materials form.
        materials_elem = ET.SubElement(admin_data, f"{{{ns_drmd}}}materials")
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
        
        # Add the statements section.
        statements_elem = export_statements(ns_drmd, ns_dcc)
        admin_data.append(statements_elem)

    # --- Material Properties ---
         # Next: materialPropertiesList.
        mp_list_elem = export_materialProperties(ns_drmd, ns_dcc, ns_si)
        root.append(mp_list_elem)

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
            
        try:
            schema = xmlschema.XMLSchema(DEFAULT_XSD_PATH)
            if schema.is_valid(pretty_xml):
                st.success("XML is valid against the schema!")
            else:
                # Get error log details.
                errors = schema.validate(pretty_xml, use_defaults=False)
                st.error("XML is NOT valid against the schema!")
                st.text_area("Validation Errors", str(errors), height=200)
        except Exception as e:
            st.error(f"Schema validation failed: {e}")


        st.download_button("Download DRMD XML", data=pretty_xml, file_name="material_properties.xml", mime="application/xml")
        st.text_area("Generated XML", pretty_xml, height=1000)


        
        # --- XSL Transformation to HTML ---
        try:
            # Parse the XSL file.
            xslt_doc = etree.parse(DEFAULT_XSL_PATH)
            transform = etree.XSLT(xslt_doc)
            # Parse the generated XML.
            xml_doc = etree.fromstring(pretty_xml.encode("utf-8"))
            # Transform XML to HTML.
            result_tree = transform(xml_doc)
            html_output = etree.tostring(result_tree, pretty_print=True, encoding="utf-8").decode("utf-8")
        except Exception as e:
            st.error(f"XSL Transformation Error: {e}")
            html_output = ""
        
        # --- Provide Download Buttons and HTML Viewer ---
        st.download_button("Download HTML", data=html_output, file_name="certificate.html", mime="text/html")
        st.components.v1.html(html_output, height=600, scrolling=True)
        st.write("XML is generated and HTML view is shown below.")
