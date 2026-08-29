<?xml version="1.0" encoding="UTF-8"?>
<!--
  segment_generico_aninhado.xsl — plan §6.2, for NESTED output (A-R.5).

  Compare this with `segment_generico.xsl` and the case for the maintainers'
  recursive `AgrupamentoHierarquico` (§2.10, §11) is the diff: the id-prefix
  arithmetic — `starts-with($myid, concat(@id,'_'))` and the
  `string-length(@id)` sort that puts the ancestors back in order — is simply
  gone. `ancestor::AgrupamentoHierarquico` is already in document order, and
  `Rotulo`/`NomeAgrupador` are elements rather than `Bloco` conventions.

  **No `id` is read for structure**, exactly as the Python reader does not:
  `@id` appears only in the urn column, where it is copied.

  Order: children are sorted by `Bloco[@nome='ordem']`, never by position.
  §5.4 Constraint 1 forces a section's own prose *after* its subsections, so
  position is not reading order. Regions (`Agrupamento` directly under
  `PartePrincipal`) keep document order and have level 0.
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

 <!--
   A section's cumulative text, in READING order.

   `descendant::` is document order, and under Constraint 1 document order is
   not reading order: a section's own prose is serialised *after* its
   subsections. So this recurses instead — own prose first, then each child in
   `Bloco[@nome='ordem']` order — which is what the Python reader does and why
   the two agreed on the flat documents but not on the nested ones until this
   template existed.
 -->
 <xsl:template name="cumulative">
  <xsl:value-of select="normalize-space(string-join(
    (Agrupamento/descendant::p | Agrupamento/descendant::li[not(ol|ul)]
     | Agrupamento/descendant::td | Agrupamento/descendant::th), ' '))"/>
  <xsl:for-each select="AgrupamentoHierarquico">
   <xsl:sort select="number(Bloco[@nome='ordem'])"/>
   <xsl:text> </xsl:text>
   <xsl:call-template name="cumulative"/>
  </xsl:for-each>
 </xsl:template>

 <xsl:template name="row">
  <xsl:param name="urn"/>
  <xsl:variable name="raw"><xsl:call-template name="cumulative"/></xsl:variable>
  <xsl:variable name="all" select="normalize-space($raw)"/>
  <xsl:value-of select="@nome"/><xsl:text>,</xsl:text>
  <xsl:value-of select="count(ancestor::AgrupamentoHierarquico) + 1"/><xsl:text>,</xsl:text>
  <xsl:call-template name="escape"><xsl:with-param name="text" select="string(Rotulo)"/></xsl:call-template>
  <xsl:text>,</xsl:text>
  <xsl:variable name="crumb">
   <xsl:for-each select="ancestor::AgrupamentoHierarquico">
    <xsl:value-of select="normalize-space(string-join((Rotulo, NomeAgrupador), ' '))"/>
    <xsl:if test="position() != last()"><xsl:text> | </xsl:text></xsl:if>
   </xsl:for-each>
  </xsl:variable>
  <xsl:call-template name="escape"><xsl:with-param name="text" select="string($crumb)"/></xsl:call-template>
  <xsl:text>,</xsl:text>
  <xsl:call-template name="escape"><xsl:with-param name="text" select="$all"/></xsl:call-template>
  <xsl:text>,</xsl:text>
  <xsl:value-of select="concat($urn,'!',@id)"/>
  <xsl:text>&#10;</xsl:text>
 </xsl:template>

 <xsl:template name="walk">
  <xsl:param name="urn"/>
  <xsl:call-template name="row"><xsl:with-param name="urn" select="$urn"/></xsl:call-template>
  <xsl:for-each select="AgrupamentoHierarquico">
   <xsl:sort select="number(Bloco[@nome='ordem'])"/>
   <xsl:call-template name="walk"><xsl:with-param name="urn" select="$urn"/></xsl:call-template>
  </xsl:for-each>
 </xsl:template>

 <xsl:template match="/">
  <xsl:text>Tipo,Nivel,Rotulo,Breadcrumb,Texto,urn&#10;</xsl:text>
  <xsl:variable name="urn" select="/LexML/Metadado/Identificacao/@URN"/>
  <xsl:for-each select="//PartePrincipal/*[self::Agrupamento or self::AgrupamentoHierarquico]">
   <xsl:choose>
    <xsl:when test="self::Agrupamento">
     <xsl:value-of select="@nome"/><xsl:text>,0,,,</xsl:text>
     <xsl:call-template name="escape">
      <xsl:with-param name="text" select="normalize-space(string-join(
        (descendant::p | descendant::li[not(ol|ul)]
         | descendant::td | descendant::th), ' '))"/>
     </xsl:call-template>
     <xsl:text>,</xsl:text>
     <xsl:value-of select="concat($urn,'!',@id)"/><xsl:text>&#10;</xsl:text>
    </xsl:when>
    <xsl:otherwise>
     <xsl:call-template name="walk"><xsl:with-param name="urn" select="$urn"/></xsl:call-template>
    </xsl:otherwise>
   </xsl:choose>
  </xsl:for-each>
 </xsl:template>
</xsl:stylesheet>
