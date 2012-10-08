from rdflib.graph import Graph
from rdflib import RDF, Namespace
from rdflib.plugins.parsers import rdfxml
from rdflib.collection import Collection
from logging import getLogger
from rdf_json import json_for_graph
import zipfile, os, tempfile, shutil, sys
import traceback


log = getLogger(__name__)

class lightbaseParser():
    """This class will parse an RDF file in lightbase format
    """
    def __init__(self):
        """
        Building method with standard parameters
        """
        self.metadata = dict()
        self.rdf_collection = dict()
        self.rdf_identifier = ''
        self.import_error = list()
        self.base_name = None
        
    def parse(self,rdf_content):
        """Parse the RDF file in Lightbase format
        This method returns a dict where the first index is the index and the 
        second is another dict, containing register identifier and the RDF document
        itself
        """
        g = Graph()
        
        lb = Namespace('http://rdf.lightbase.cc/ontology/')
        dc = Namespace('http://purl.org/dc/elements/1.1/')
        
        result = g.parse(data=rdf_content, format="application/rdf+xml")
        self.rdf_collection = result.serialize(format='turtle')
        self.rdf_identifier = g.objects(None,dc['identifier']).next().toPython()

        # Get base name here
        self.base_name = g.objects(None,lb['baseName']).next()
        
        # Test with SPARQL        
        teste = result.query(
                             """
                             PREFIX lb: <http://rdf.lightbase.cc/ontology/> 
                             PREFIX dc: <http://purl.org/dc/elements/1.1/>
                             SELECT ?fieldName ?fieldData
                             WHERE {
                                 ?x lb:fieldName ?fieldName .
                                 ?x dc:description ?fieldData .
                                }
                             """
                             )
        
        
        # I need one specific field
        arquivo = result.query("""
                                PREFIX lb: <http://rdf.lightbase.cc/ontology/>
                                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                                SELECT ?arquivo
                                WHERE {
                                    ?x rdf:type lb:registro .
                                    ?x lb:arquivo ?arquivo .
                                }                               
                               """)
        
        # Return metadata as tuple
        self.metadata = dict(teste.result)
        self.metadata['url'] = arquivo.result[0]
        self.metadata['id'] = self.rdf_identifier
        #print(self.metadata)
        
        #print(self.rdf_identifier)
    
    def json(self,rdf_content):
        """Parse the RDF file in Lightbase format and returns it 
        in a json format        
        """
        g = Graph()
        
        lb = Namespace('http://rdf.lightbase.cc/ontology/')
        dc = Namespace('http://purl.org/dc/elements/1.1/')
        
        #print(rdf_content)
        
        result = g.parse(data=rdf_content, format="application/rdf+xml")
        
        self.rdf_collection = json_for_graph(result)
        self.rdf_identifier = g.objects(None,dc['identifier']).next().toPython()

        # Get base name here
        self.base_name = g.objects(None,lb['baseName']).next()
                  
        # Test with SPARQL        
        teste = result.query(
                             """
                             PREFIX lb: <http://rdf.lightbase.cc/ontology/> 
                             PREFIX dc: <http://purl.org/dc/elements/1.1/>
                             SELECT ?fieldName ?fieldData
                             WHERE {
                                 ?x lb:fieldName ?fieldName .
                                 ?x dc:description ?fieldData .                                 
                                }
                             """
                             )
        
        # I need one specific field
        arquivo = result.query("""
                                PREFIX lb: <http://rdf.lightbase.cc/ontology/>
                                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                                SELECT ?arquivo
                                WHERE {
                                    ?x rdf:type lb:registro .
                                    ?x lb:arquivo ?arquivo .
                                }                               
                               """)
        
        # Return metadata as dict
        self.metadata = dict(teste.result)
        self.metadata['url'] = arquivo.result[0]
        self.metadata['id'] = self.rdf_identifier

    def collection(self, filename):
        """
        Receive a zip file and parse one file at a time, returning a collection of parsed files.
        """
        # Create the zipfile object
        z_root = zipfile.ZipFile(filename)

        # Create a temp dir and unzip file contents
        tmp_dir = tempfile.mkdtemp()

        registros = {
          'import_error' : [],
          'registros' : []
          }

        for arquivo in z_root.namelist():
            # This should be a list with a all the zip files
            #print('00000000000000000000000000000 %s' % arquivo)
            z_root.extract(arquivo,tmp_dir)

            # This is the file object for this registro
            z = zipfile.ZipFile(os.path.join(tmp_dir,arquivo))

            # Unzip this file's content to a tmp dir
            tmp_dir_arquivo = tempfile.mkdtemp()

            registro = dict()

            # Get the important files
            doc_file = None
            rdf_file = None
            for f in z.namelist():
                name, extension = os.path.splitext(f)
                head, tail = os.path.split(f)

                if extension == '.rdf':
                    rdf_file = name + extension
                elif head == 'docs':
                    doc_file = name + extension
                    doc_file_name = tail

            # Now extract RDF file
            z.extract(rdf_file,tmp_dir_arquivo)

            # Parse the RDF register
            f_obj = (z.open(rdf_file))

            # Add exception to handle file not found
            try:
                self.parse(f_obj.read())
                f_obj.close()
            except:
                # Add a call to handle the case where register is not loaded
                f_obj.close()
                self.erro(os.path.join(tmp_dir_arquivo,rdf_file), traceback.format_exc(), filename)
                #log.error('Error importing registro for file %s' % os.path.join(tmp_dir_arquivo,f))
                print >> sys.stderr, 'Error importing registro for file %s' % os.path.join(tmp_dir_arquivo,rdf_file)
                registros['import_error'].append(self.import_error)

                # Set it to None to make sure we don't add this to import list
                self.rdf_identifier = None
                pass

            # Don't parse without doc file
            if not doc_file:
                # There's no doc file.
                self.erro(os.path.join(tmp_dir_arquivo,rdf_file), 'Importing error for file %s: no doc file supplied.  doc_file = %s' % (rdf_file,doc_file), filename)
                print >> sys.stderr, 'Importing error for file %s: no doc file supplied.  doc_file = %s' % (rdf_file,doc_file)
                registros['import_error'].append(self.import_error)

            # If we don't have an identifier, it's a parsing error. Don't open the file
            if self.rdf_identifier:
                # Extract and store doc file
                try:
                    z.extract(doc_file,tmp_dir_arquivo)

                    # This is a directory containing the original files. Store the files
                    tmp_file = tempfile.NamedTemporaryFile(delete=False)
                    tmp_file.close()

                    # Return as URL field a temporary file that will be transferred to
                    # internal storage later
                    shutil.copy2(os.path.join(tmp_dir_arquivo,doc_file),tmp_file.name)

                    self.metadata['url'] = tmp_file.name

                    #FIXME: put original file name inside RDF
                    self.metadata['arq_original'] = doc_file_name

                    # Now setup dict list
                    registro['rdf_identifier'] = self.rdf_identifier
                    registro['rdf_collection'] = self.rdf_collection
                    #print >> sys.stderr, '5555555555555555555555555 %s' % self.metadata['url']
                    registro['metadata'] = self.metadata
                    registro['base_name'] = self.base_name
                    registros['registros'].append(registro)

                except:
                    # there was an error storing file. Log it but don't fail
                    self.erro(os.path.join(tmp_dir_arquivo,rdf_file), 'Error trying to open file %s\n%s' % (doc_file, traceback.format_exc()), filename)
                    print >> sys.stderr, 'Error trying to open file %s\n%s' % (doc_file, traceback.format_exc())
                    registros['import_error'].append(self.import_error)
                    pass

            # Close file
            z.close()

            # Remove tmp dir for this registro
            shutil.rmtree(tmp_dir_arquivo)

        # Remove tmp dir for all registros
        shutil.rmtree(tmp_dir)

        # Return a list with all parsed registros
        return registros

    def erro(self, filename, errmsg, package_file):
        """
        Add filename to a list of import errors
        """
        tmp_file = tempfile.NamedTemporaryFile(delete=False)
        tmp_file.close()
        shutil.copy2(filename,tmp_file.name)
        error = {
          'tmpfile' : tmp_file.name,
          'filename' : filename,
          'errmsg' : errmsg,
          'error_type' : 'ParsingError',
          'package_file': package_file
        }

        self.import_error = error
        self.rdf_identifier = None
        self.metadata = None
        self.base_name = None
