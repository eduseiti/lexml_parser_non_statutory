<?xml version="1.0" encoding="UTF-8"?>
<!--
  segment_generico.xsl — plan §6.2's reference stylesheet for FLAT output.

  Flat `generico` output carries its hierarchy in the `id` path (§2.3), so an
  ancestor is "any Agrupamento whose id is a proper prefix of mine". That is
  the `starts-with($myid, concat(@id,'_'))` test below, and sorting those
  ancestors by `string-length(@id)` puts them in root-to-leaf order. Both are
  gone from the nested stylesheet, which is the strongest single argument for
  the maintainers' change (§11).

  Rule A (every intermediate level materialised) is what makes the prefix test
  sufficient; Rule B (leaf-only text) is `descendant::p` plus the `li[not(ol|ul)]`
  guard against counting a parent list item twice.

  A region — front matter, back matter, the body preamble — has no
  `Bloco nome="nivel"`, and is emitted with level 0 to match the Python API.
-->
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="3.0"
  xpath-default-namespace="http://www.lexml.gov.br/1.0">
 <xsl:output method="text" omit-xml-declaration="yes"/>

 <xsl:template name="escape">
  <xsl:param name="text"/>
  <xsl:choose>
   <xsl:when test="contains($text,'&quot;') or contains($text,',') or contains($text,'&#10;')">
    <xsl:text>&quot;</xsl:text>
    <xsl:value-of select="replace($text,'&quot;','&quot;&quot;')"/>
    <xsl:text>&quot;</xsl:text>
   </xsl:when>
   <xsl:otherwise><xsl:value-of select="$text"/></xsl:otherwise>
  </xsl:choose>
 </xsl:template>

 <xsl:template match="/">
  <xsl:text>Tipo,Nivel,Rotulo,Breadcrumb,Texto,urn&#10;</xsl:text>
  <xsl:variable name="urn" select="/LexML/Metadado/Identificacao/@URN"/>
  <xsl:for-each select="//PartePrincipal/Agrupamento">
   <xsl:variable name="myid" select="@id"/>
   <xsl:variable name="anc"
     select="//PartePrincipal/Agrupamento[starts-with($myid, concat(@id,'_'))]"/>
   <xsl:value-of select="@nome"/><xsl:text>,</xsl:text>
   <xsl:value-of select="if (Bloco[@nome='nivel']) then Bloco[@nome='nivel'] else '0'"/>
   <xsl:text>,</xsl:text>
   <xsl:call-template name="escape">
    <xsl:with-param name="text" select="string(Bloco[@nome='rotulo'])"/>
   </xsl:call-template>
   <xsl:text>,</xsl:text>
   <xsl:variable name="crumb">
    <xsl:for-each select="$anc">
     <xsl:sort select="string-length(@id)"/>
     <xsl:value-of select="normalize-space(string-join(
       (Bloco[@nome='rotulo'], Bloco[@nome='nomeAgrupador']), ' '))"/>
     <xsl:if test="position() != last()"><xsl:text> | </xsl:text></xsl:if>
    </xsl:for-each>
   </xsl:variable>
   <xsl:call-template name="escape"><xsl:with-param name="text" select="string($crumb)"/></xsl:call-template>
   <xsl:text>,</xsl:text>
   <xsl:variable name="own" select="normalize-space(string-join(
     (descendant::p | descendant::li[not(ol|ul)] | descendant::td | descendant::th), ' '))"/>
   <xsl:variable name="kids" select="normalize-space(string-join(
     for $d in //PartePrincipal/Agrupamento[starts-with(@id, concat($myid,'_'))]
       return normalize-space(string-join(
         ($d/descendant::p | $d/descendant::li[not(ol|ul)]
          | $d/descendant::td | $d/descendant::th), ' ')), ' '))"/>
   <xsl:call-template name="escape">
    <xsl:with-param name="text" select="normalize-space(concat($own,' ',$kids))"/>
   </xsl:call-template>
   <xsl:text>,</xsl:text>
   <xsl:value-of select="concat($urn,'!',@id)"/>
   <xsl:text>&#10;</xsl:text>
  </xsl:for-each>
 </xsl:template>
</xsl:stylesheet>
