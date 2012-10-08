import simplejson
import rdflib

def json_for_graph(g):
    """
    Pass in a rdflib.Graph and get back a chunk of JSON using 
    the Talis JSON serialization for RDF:
    http://n2.talis.com/wiki/RDF_JSON_Specification
    """
    json = {}

    # go through all the triples in the graph
    for s, p, o in g:

        # initialize property dictionary if we've got a new subject
        if not json.has_key(s):
            json[s] = {}

        # initialize object list if we've got a new subject-property combo
        if not json[s].has_key(p):
            json[s][p] = []

        # determine the value dictionary for the object 
        v = {'value': unicode(o)}
        if isinstance(o, rdflib.URIRef):
            v['type'] = 'uri'
        elif isinstance(o, rdflib.BNode):
            v['type'] = 'bnode'
        elif isinstance(o, rdflib.Literal):
            v['type'] = 'literal'
            if o.language:
                v['lang'] = o.language
            if o.datatype:
                v['datatype'] = unicode(o.datatype)

        # add the triple
        json[s][p].append(v)
        
    return simplejson.dumps(json, indent=2)


if __name__ == '__main__':
    g = rdflib.ConjunctiveGraph()
    g.load('http://inkdroid.org/ehs')
    print json_for_graph(g)
