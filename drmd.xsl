<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:drmd="https://example.org/drmd"
    xmlns:dcc="https://ptb.de/dcc"
    xmlns:si="https://ptb.de/si"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#">

    <!-- Output as HTML -->
    <xsl:output method="html" indent="yes" />

    <!-- Root template -->
    <xsl:template match="/">
      <html>
        <head>
          <title>
            <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:titleOfTheDocument" />
          </title>
          <style>
            body { font-family: Arial, sans-serif; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; }
            th { background-color: #f2f2f2; text-align: left; }
            h1, h2, h3, h4 { color: #333; }
            .divider { margin: 20px 0; border-top: 1px solid #ddd; }
          </style>
        </head>
        <body>
          <h1>
            <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:titleOfTheDocument" />
          </h1>
          <h2>Administrative Data</h2>
          <h3>Core Data</h3>
          <table>
            <tr>
              <th>Title</th>
              <td>
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:titleOfTheDocument" />
              </td>
            </tr>
            <tr>
              <th>Unique Identifier</th>
              <td>
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:uniqueIdentifier" />
              </td>
            </tr>
            <!-- Validity information -->
            <xsl:if test="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:validity">
              <tr>
                <th>Period of Validity</th>
                <td>
                  <xsl:choose>
                    <xsl:when test="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:validity/drmd:untilRevoked">
                      <xsl:text>Until revocation from the producer</xsl:text>
                    </xsl:when>
                    <!-- If other options exist (for example, timeAfterDispatch or specificTime), add additional when clauses here -->
                    <xsl:otherwise>
                      <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:validity/*"/>
                    </xsl:otherwise>
                  </xsl:choose>
                </td>
              </tr>
              <xsl:if test="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:validity/drmd:dateOfIssue">
                <tr>
                  <th>Date of Issue</th>
                  <td>
                    <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:validity/drmd:dateOfIssue"/>
                  </td>
                </tr>
              </xsl:if>
              <xsl:if test="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:validity/drmd:dateOfCertificateApproval">
                <tr>
                  <th>Date of Certificate Approval</th>
                  <td>
                    <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:coreData/drmd:validity/drmd:dateOfCertificateApproval"/>
                  </td>
                </tr>
              </xsl:if>
            </xsl:if>
          </table>

          <h3>Reference Material Producer</h3>
          <table>
            <tr>
              <th>Name</th>
              <td>
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:name/dcc:content[@lang='en']" />
              </td>
            </tr>
            <tr>
              <th>Contact</th>
              <td>
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:contact/dcc:location/dcc:street" />
                ,
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:contact/dcc:location/dcc:streetNo" /><br/>
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:contact/dcc:location/dcc:postCode" />
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:contact/dcc:location/dcc:city" />
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:contact/dcc:location/dcc:countryCode" /><br/>
                <xsl:text>Phone: </xsl:text>
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:contact/dcc:phone" /><br/>
                <xsl:text>Fax: </xsl:text>
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:contact/dcc:fax" /><br/>
                <xsl:text>Email: </xsl:text>
                <xsl:value-of select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:referenceMaterialProducer/drmd:contact/dcc:eMail" /><br/>
              </td>
            </tr>
          </table>

          <h3>Materials</h3>
          <!-- Loop through each material (formerly "item") -->
          <xsl:for-each select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:materials/drmd:material">
            <table>
              <tr>
                <th>Name</th>
                <td>
                  <xsl:value-of select="drmd:name/dcc:content[@lang='en']" />
                </td>
              </tr>
              <tr>
                <th>Description</th>
                <td>
                  <xsl:for-each select="drmd:description/dcc:content[@lang='en']">
                    <xsl:value-of select="." />
                    <br/>
                  </xsl:for-each>
                </td>
              </tr>
              <tr>
                <th>Minimum Sample Size</th>
                <td>
                  <xsl:for-each select="drmd:minimumSampleSize/dcc:itemQuantity/si:realListXMLList">
                    <xsl:value-of select="si:valueXMLList" />
                    <xsl:text> </xsl:text>
                    <xsl:value-of select="si:unitXMLList" />
                    <br/>
                  </xsl:for-each>
                </td>
              </tr>
            </table>
          </xsl:for-each>

          <h3>Statements</h3>
          <!-- Process each statement -->
          <xsl:for-each select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:statements/*">
            <h4>
              <xsl:value-of select="dcc:name/dcc:content[@lang='en']" />
            </h4>
            <p>
              <xsl:for-each select="dcc:content[@lang='en']">
                <xsl:value-of select="."/><br/>
              </xsl:for-each>
            </p>
          </xsl:for-each>

          <h3>Responsible Persons</h3>
          <table>
            <tr>
              <th>Name</th>
              <th>Role</th>
            </tr>
            <xsl:for-each select="drmd:digitalReferenceMaterialDocument/drmd:administrativeData/drmd:respPersons/dcc:respPerson">
              <tr>
                <td>
                  <xsl:value-of select="dcc:person/dcc:name/dcc:content[@lang='en']" />
                </td>
                <td>
                  <xsl:value-of select="dcc:role" />
                </td>
              </tr>
            </xsl:for-each>
          </table>

          <div class="divider"></div>
          <!-- New section for Materials Properties (formerly measurementResults) -->
          <h2>Materials Properties</h2>
          <!-- Loop through each materialsProperties element -->
          <xsl:for-each select="drmd:digitalReferenceMaterialDocument/drmd:materialPropertiesList/drmd:materialProperties">
            <xsl:variable name="isCertified" select="@isCertified" />
            <xsl:choose>
              <xsl:when test="$isCertified='true'">
                <h3>
                  <span style="color:green; font-weight:bold;">&#10004; Certified </span>
                  <xsl:value-of select="drmd:results/dcc:result/dcc:name/dcc:content[@lang='en']" />
                </h3>
                <h3>Certified Values</h3>
                <p>
                  <xsl:for-each select="drmd:results/dcc:result/dcc:description/dcc:content[@lang='en']">
                    <xsl:value-of select="."/><br/>
                  </xsl:for-each>
                </p>
                <table>
                  <tr>
                    <th>Property</th>
                    <th>Property Value</th>
                    <th>Property Unit</th>
                    <th>Uncertainty Value</th>
                  </tr>
                  <xsl:apply-templates select="drmd:results/dcc:result/dcc:data/dcc:list/dcc:quantity" />
                </table>
                <hr/>
              </xsl:when>
              <xsl:when test="$isCertified='false'">
                <h3>
                  <xsl:value-of select="drmd:results/dcc:result/dcc:name/dcc:content[@lang='en']" />
                </h3>
                <h3>Informative Values</h3>
                <p>
                  <xsl:for-each select="drmd:results/dcc:result/dcc:description/dcc:content[@lang='en']">
                    <xsl:value-of select="."/><br/>
                  </xsl:for-each>
                </p>
                <table>
                  <tr>
                    <th>Property</th>
                    <th>Property Value</th>
                    <th>Property Unit</th>
                    <th>Uncertainty Value</th>
                  </tr>
                  <xsl:apply-templates select="drmd:results/dcc:result/dcc:data/dcc:list/dcc:quantity" />
                </table>
                <hr/>
              </xsl:when>
            </xsl:choose>
          </xsl:for-each>
        </body>
      </html>
    </xsl:template>

    <!-- Template for quantities (used in materials properties table) -->
    <xsl:template match="dcc:quantity">
      <tr>
        <td>
          <xsl:value-of select="dcc:name/dcc:content[@lang='en']" />
        </td>
        <td>
          <xsl:value-of select="si:real/si:value" />
        </td>
        <td>
          <xsl:value-of select="si:real/si:unit" />
        </td>
        <td>
          <xsl:value-of select="si:real/si:measurementUncertaintyUnivariate/si:expandedMU/si:valueExpandedMU" />
        </td>
      </tr>
    </xsl:template>

    <!-- If you need to process procedure elements (formerly method), add a template here -->

</xsl:stylesheet>
