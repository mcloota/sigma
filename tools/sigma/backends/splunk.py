# Output backends for sigmac
# Copyright 2016-2018 Thomas Patzke, Florian Roth, Roey

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import sigma
from .base import SingleTextQueryBackend
from .mixins import MultiRuleOutputMixin

class SplunkBackend(SingleTextQueryBackend):
    """Converts Sigma rule into Splunk Search Processing Language (SPL)."""
    identifier = "splunk"
    active = True
    index_field = "index"

    # \   -> \\
    # \*  -> \*
    # \\* -> \\*
    reEscape = re.compile('("|(?<!\\\\)\\\\(?![*?\\\\]))')
    reClear = None
    andToken = " "
    orToken = " OR "
    notToken = "NOT "
    subExpression = "(%s)"
    listExpression = "(%s)"
    listSeparator = " "
    valueExpression = "\"%s\""
    nullExpression = "NOT %s=\"*\""
    notNullExpression = "%s=\"*\""
    mapExpression = "%s=%s"
    mapListsSpecialHandling = True
    mapListValueExpression = "%s IN %s"

    def generateMapItemListNode(self, key, value):
        if not set([type(val) for val in value]).issubset({str, int}):
            raise TypeError("List values must be strings or numbers")
        return "(" + (" OR ".join(['%s=%s' % (key, self.generateValueNode(item)) for item in value])) + ")"

    def generateAggregation(self, agg):
        if agg == None:
            return ""
        if agg.aggfunc == sigma.parser.condition.SigmaAggregationParser.AGGFUNC_NEAR:
            raise NotImplementedError("The 'near' aggregation operator is not yet implemented for this backend")
        if agg.groupfield == None:
            return " | stats %s(%s) as val | search val %s %s" % (agg.aggfunc_notrans, agg.aggfield or "", agg.cond_op, agg.condition)
        else:
            if agg.aggfunc_notrans == 'count':
                agg.aggfunc_notrans = 'dc'
            return " | stats %s(%s) as val by %s | search val %s %s" % (agg.aggfunc_notrans, agg.aggfield or "", agg.groupfield or "", agg.cond_op, agg.condition)

        
    def generate(self, sigmaparser):
        """Method is called for each sigma rule and receives the parsed rule (SigmaParser)"""
        columns = list()
        try:
            for field in sigmaparser.parsedyaml["fields"]:
                mapped = sigmaparser.config.get_fieldmapping(field).resolve_fieldname(field)
                if type(mapped) == str:
                    columns.append(mapped)
                elif type(mapped) == list:
                    columns.extend(mapped)
                else:
                    raise TypeError("Field mapping must return string or list")

            fields = ",".join(str(x) for x in columns)
            fields = " | table " + fields

        except KeyError:    # no 'fields' attribute
            mapped = None
            pass

        for parsed in sigmaparser.condparsed:
            query = self.generateQuery(parsed)
            before = self.generateBefore(parsed)
            after = self.generateAfter(parsed)

            result = ""
            if before is not None:
                result = before
            if query is not None:
                result += query
            if after is not None:
                result += after
            if mapped is not None:
                result += fields

            return result
    
class SplunkXMLBackend(SingleTextQueryBackend, MultiRuleOutputMixin):
    """Converts Sigma rule into XML used for Splunk Dashboard Panels"""
    identifier = "splunkxml"
    active = True
    index_field = "index"


    panel_pre = "<row><panel><title>"
    panel_inf = "</title><table><search><query>"
    panel_suf = "</query><earliest>$field1.earliest$</earliest><latest>$field1.latest$</latest><sampleRatio>1</sampleRatio>" \
                "</search><option name=\"count\">20</option><option name=\"dataOverlayMode\">none</option><option name=\"" \
                "drilldown\">row</option><option name=\"percentagesRow\">false</option><option name=\"refresh.display\">" \
                "progressbar</option><option name=\"rowNumbers\">false</option><option name=\"totalsRow\">false</option>" \
                "<option name=\"wrap\">true</option></table></panel></row>"
    dash_pre = "<form><label>MyDashboard</label><fieldset submitButton=\"false\"><input type=\"time\" token=\"field1\">" \
               "<label></label><default><earliest>-24h@h</earliest><latest>now</latest></default></input></fieldset>"
    dash_suf = "</form>"
    queries = dash_pre


    reEscape = re.compile('("|(?<!\\\\)\\\\(?![*?\\\\]))')
    reClear = SplunkBackend.reClear
    andToken = SplunkBackend.andToken
    orToken = SplunkBackend.orToken
    notToken = SplunkBackend.notToken
    subExpression = SplunkBackend.subExpression
    listExpression = SplunkBackend.listExpression
    listSeparator = SplunkBackend.listSeparator
    valueExpression = SplunkBackend.valueExpression
    nullExpression = SplunkBackend.nullExpression
    notNullExpression = SplunkBackend.notNullExpression
    mapExpression = SplunkBackend.mapExpression
    mapListsSpecialHandling = SplunkBackend.mapListsSpecialHandling
    mapListValueExpression = SplunkBackend.mapListValueExpression

    def generateMapItemListNode(self, key, value):
        return "(" + (" OR ".join(['%s=%s' % (key, self.generateValueNode(item)) for item in value])) + ")"

    def generateAggregation(self, agg):
        if agg == None:
            return ""
        if agg.aggfunc == sigma.parser.condition.SigmaAggregationParser.AGGFUNC_NEAR:
            return ""
        if agg.groupfield == None:
            return " | stats %s(%s) as val | search val %s %s" % (agg.aggfunc_notrans, agg.aggfield or "", agg.cond_op, agg.condition)
        else:
            return " | stats %s(%s) as val by %s | search val %s %s" % (agg.aggfunc_notrans, agg.aggfield or "", agg.groupfield or "", agg.cond_op, agg.condition)

    def generate(self, sigmaparser):
        """Method is called for each sigma rule and receives the parsed rule (SigmaParser)"""
        for parsed in sigmaparser.condparsed:
            query = self.generateQuery(parsed)
            if query is not None:
                self.queries += self.panel_pre
                self.queries += self.getRuleName(sigmaparser)
                self.queries += self.panel_inf
                query = query.replace("<", "&lt;")
                query = query.replace(">", "&gt;")
                self.queries += query
                self.queries += self.panel_suf

    def finalize(self):
        self.queries += self.dash_suf
        return self.queries
