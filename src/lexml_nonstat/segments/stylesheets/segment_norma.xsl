<?xml version="1.0" encoding="UTF-8"?>
<!--
  segment_norma.xsl — plan §6.2, for STATUTORY output, adapting
  `scripts/GeraCSVporArtigoPorAgrupador.xsl`.

  Two things are taken from the community stylesheet and one is deliberately
  not. Taken: selecting on dispositivo element *names*, and building the
  breadcrumb from `ancestor::*/NomeAgrupador`. Not taken: its `calculaPos`
  interval numbering, which addresses a segment by a computed position rather
  than by its `id`. This project's addressing channel is the `id` — schema
  pattern-constrained for dispositivos (amendment A-6.1) — so the urn column
  carries `@id` and nothing is computed.

  Rows come out in **document order** — `ParteInicial`'s regions, then each
  Artigo with its Caput and Paragrafos, then `ParteFinal` — matching the
  Python reader, which walks `Norma`'s children in order for the same reason.

  A `Caput`'s `Rotulo` echoes its `Artigo`'s (amendment A-6.4). It is emitted
  in the Rotulo column, because a reader wants the caption, and it is not
  counted twice in any text column, because the source said it once.
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

 <xsl:template name="dispositivo">
  <xsl:param name="urn"/>
  <xsl:value-of select="lower-case(local-name())"/><xsl:text>,</xsl:text>
  <xsl:value-of select="count(ancestor::*[self::Artigo or self::Caput
                                          or self::Paragrafo or self::Inciso]) + 1"/>
  <xsl:text>,</xsl:text>
  <xsl:call-template name="escape"><xsl:with-param name="text" select="string(Rotulo)"/></xsl:call-template>
  <xsl:text>,</xsl:text>
  <xsl:variable name="crumb">
   <xsl:for-each select="ancestor::*[self::Artigo or self::Caput
                                     or self::Paragrafo or self::Inciso]">
    <xsl:value-of select="normalize-space(string(Rotulo))"/>
    <xsl:if test="position() != last()"><xsl:text> | </xsl:text></xsl:if>
   </xsl:for-each>
  </xsl:variable>
  <xsl:call-template name="escape"><xsl:with-param name="text" select="string($crumb)"/></xsl:call-template>
  <xsl:text>,</xsl:text>
  <xsl:call-template name="escape">
   <xsl:with-param name="text" select="normalize-space(string-join(
     (descendant::p | descendant::li[not(ol|ul)]), ' '))"/>
  </xsl:call-template>
  <xsl:text>,</xsl:text>
  <xsl:value-of select="concat($urn,'!',@id)"/>
  <xsl:text>&#10;</xsl:text>
  <xsl:for-each select="Caput | Paragrafo | Inciso">
   <xsl:call-template name="dispositivo"><xsl:with-param name="urn" select="$urn"/></xsl:call-template>
  </xsl:for-each>
 </xsl:template>

 <xsl:template match="/">
  <xsl:text>Tipo,Nivel,Rotulo,Breadcrumb,Texto,urn&#10;</xsl:text>
  <xsl:variable name="urn" select="/LexML/Metadado/Identificacao/@URN"/>
  <xsl:for-each select="/LexML/Norma/*">
   <xsl:choose>
    <xsl:when test="self::ParteInicial or self::ParteFinal">
     <xsl:for-each select="descendant-or-self::*[self::Epigrafe or self::Ementa
        or self::Preambulo or self::FormulaPromulgacao
        or self::Assinatura or self::LocalDataFecho]">
      <xsl:value-of select="concat(lower-case(substring(local-name(),1,1)),
                                   substring(local-name(),2))"/>
      <xsl:text>,0,,,</xsl:text>
      <xsl:call-template name="escape">
       <xsl:with-param name="text" select="normalize-space(string(.))"/>
      </xsl:call-template>
      <xsl:text>,</xsl:text>
      <xsl:value-of select="concat($urn,'!',@id)"/><xsl:text>&#10;</xsl:text>
     </xsl:for-each>
    </xsl:when>
    <xsl:when test="self::Articulacao">
     <xsl:for-each select="Artigo">
      <xsl:call-template name="dispositivo"><xsl:with-param name="urn" select="$urn"/></xsl:call-template>
     </xsl:for-each>
    </xsl:when>
   </xsl:choose>
  </xsl:for-each>
 </xsl:template>
</xsl:stylesheet>
