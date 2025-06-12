# Digital Reference Material Document (DRMD) Generator

This project is a generator and supporting tools for the Digital Reference Material Document (DRMD) project. The DRMD project aims to create a standardized digital format for reference material certificates. This initiative is led by the Bundesanstalt für Materialforschung und -prüfung (BAM) and receives partial funding from the QI-Digital project under the BMWK.

## Project Overview

The Digital Reference Material Document (DRMD) project establishes a standardized digital format for reference material certificates, developed by the Bundesanstalt für Materialforschung und -prüfung (BAM) and supported by the QI-Digital project from BMWK. The DRMD schema is based on the existing Digital Calibration Certificate (DCC) schema and complies with the requirements of the ISO 33401 standard for reference material certificates.

## Schema Information

The DRMD schema is designed to encapsulate all necessary data for reference material certificates, ensuring consistency and adherence to international standards.

**Key Features:**

*   **Administrative Data:** Core information about the document, items, producer information, responsible persons, and relevant statements.
*   **Measurement Results:** Structured representation of measurement data, including certified values and uncertainties.

## Documentation

The development of the DRMD is partially funded and supported by the QI-Digital project from BMWK. Further documentation and project details can be found [here](link-to-drmd-documentation).

## Dependencies

The DRMD schema builds upon the existing DCC schema. You can find the DCC schema [here](link-to-dcc-schema).

## External Standards

*   **ISO 33401:** The DRMD schema is designed to meet the requirements of the ISO 33401 standard for reference material certificates.

## Usage

### XML Schema Definition (XSD)

*   `drmd.xsd`: This file defines the structure of the DRMD. This file is essential for creating and validating XML documents that conform to the DRMD specifications.

### XSLT Stylesheet

*   `drmd.xsl`: This file is an XSLT stylesheet that can be used to transform DRMD XML documents into human-readable HTML format. To use this stylesheet, reference it in your XML document as follows:
```xml
<?xml-stylesheet type="text/xsl" href="drmd.xsl"?>
```


### Docker

To build the Docker image:

```bash
docker build -t drmd-webapp .
```

To run the container:

```bash
docker run -p 8501:8501 drmd-webapp
```
=======

