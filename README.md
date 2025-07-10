# Digital Reference Material Document (DRMD) Generator

The DRMD Generator is a Streamlit application for creating **Digital Reference Material Documents** that conform to the DRMD XML schema (version 0.2.0). It guides you through each certificate section and produces a standards‑compliant XML file.

## Application Overview
- **Administrative Data** – document title, persistent identifier, validity period and producer information.
- **Materials** – define one or more materials, minimum sample sizes and identifications.
- **Properties** – describe measurement property sets, certified values and units.
- **Statements** – official statements such as intended use and traceability.
- **Comments & Documents** – attach external files or additional remarks.
- **Digital Signature** – optional XML Signature and timestamp.
- **Validate & Export** – run schema validation and download the finished XML.

## How to Use
1. *(Optional)* Load an existing DRMD XML file — all fields populate automatically.
2. Work through each tab, filling in required information. Hover over the ⓘ icons for inline help.
3. Generate the Persistent Identifier (UUID) or enter your own.
4. In **Validate & Export**, click **Validate** to check the XML against `drmd.xsd` and then **Download** to save.

## Dependencies
- Python 3.8+
- `streamlit`
- `pandas`
- `rdflib`
- `xmlschema`
- `lxml`

## External Standards and Documentation
- Based on the Digital Calibration Certificate (DCC) schema.
- Conforms to **ISO 33401** for reference material certificates.
- Full DRMD schema and additional documentation are available from [link-to-drmd-documentation]. The original DCC schema can be found [here](link-to-dcc-schema).

## Docker
To build the container:
```bash
docker build -t drmd-webapp .
```
Run it with:
```bash
docker run -p 8501:8501 drmd-webapp
```
