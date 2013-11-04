import pickle
from mozaik.tools.misc import result_directory_name
from mozaik.storage.datastore import PickledDataStore
from parameters import ParameterSet
from mozaik.storage.queries import *
import sys
import os
import time

def load_fixed_parameter_set_parameter_search(simulation_name,master_results_dir):
    """
    Loads all datastores of parameter search over a fixed set of parameters. 
    
    Parameters
    ----------
    simulation_name : str
                    The name of the simulation.
    master_results_dir : str
                       The directory where the parameter search results are stored.
    
    Returns
    -------
    A tuple (parameters,datastores), where `parameters` is a list of parameters over which the parameter search was performed.
    The dsvs is a list of tuples (values,datastore) where `values` is a list of values (in the order as im `parameters`) of the
    parameters, and dsv is a DataStore with results recorded to the combination of parameter values.
    """
    f = open(master_results_dir+'/parameter_combinations','rb')
    combinations = pickle.load(f)
    f.close()
    
    # first check whether all parameter combinations contain the same parameter names
    assert len(set([tuple(set(comb.keys())) for comb in combinations])) == 1 , "The parameter search didn't occur over a fixed set of parameters"
    
    parameters = combinations[0].keys()
    
    datastore = []
    number_of_unloadable_datastores = 0
    for i,combination in enumerate(combinations):
        print i
        rdn = result_directory_name('ParameterSearch',simulation_name,combination)
        try:
            data_store = PickledDataStore(load=True,parameters=ParameterSet({'root_directory': master_results_dir + '/' + rdn}),replace=False)
            datastore.append(([combination[k] for k in parameters],data_store))
        except IOError:
            number_of_unloadable_datastores = number_of_unloadable_datastores + 1
            print "Error loading datastore: " + rdn
        
    return (parameters,datastore,number_of_unloadable_datastores)

def run_analysis_on_parameter_search(simulation_name,master_results_dir,analysis_function):
    """
    Runs the *analysis_function* on each of the simualtions that have been executed as a part of the parameter search.
    Results are stored in the corresponding simulation's datastore. The analysis is executed sequentially over results
    of each parameter combination simulation.
    
    Parameters
    ----------
    simulation_name : str
                    The name of the simulation.
    master_results_dir : str
                    The directory where the parameter search results are stored.
    analysis_function : func(datastore)
                    The analysis function to be run. The datastore will be passed as it's sole parameter.
    """
    (a,datastores,n) = load_fixed_parameter_set_parameter_search(simulation_name,master_results_dir)
    for d in datastores:
        analysis_function(d)
        d.save()
      
    
        
def export_as_matricies(simulation_name,master_results_dir,query):
    """
    It assumes that there was a grid parameter search. Providing this it reformats the SingleValues into matricies
    (one per each value_name parameter encountered) and exports them as pickled numpy ndarrays.
    
    Parameters
    ----------
    simulation_name : str
                    The name of the simulation.
    master_results_dir : str
                    The directory where the parameter search results are stored.
    
    Note: currently we only handle the case of 2D parameter search.                        
    """
    (parameters,datastores,n) = load_fixed_parameter_set_parameter_search(simulation_name,master_results_dir)
    
    value_names = set([ads.value_name for ads in param_filter_query(datastores[0][1],identifier='SingleValue').get_analysis_result()])
    
    # Lets first make sure that the value_names uniqly identify a SingleValue ADS in each DataStore and 
    # that they exist in each DataStore.
    for (param_values,datastore) in datastores:
        dsv = query.query(datastore)
        for v in value_names:
            assert len(param_filter_query(dsv,identifier='SingleValue',value_name=v).get_analysis_result()) == 1, "Error, %d ADS with value_name %s found for parameter combination:" % (len(param_filter_query(datastore,identifier='SingleValue').get_analysis_result()), str([str(a) + ':' + str(b) + ', ' for (a,b) in zip(parameters,param_values)]))
        
    params = numpy.array([p for p,ds in datastores])
    num_params = numpy.shape(params)[1]
    
    # lets find out unique values of each parameter set
    param_values  = [sorted(set(params[:,i])) for i in xrange(0,num_params)]
    dimensions = numpy.array([len(x) for x in param_values])
    
    # lets check that the dataset has the same number of entries as the number of all combinations of parameter values
    print len(datastores)+n
    print dimensions
    assert len(datastores)+n == dimensions.prod()
    
    for v in value_names:
        matrix = numpy.zeros(dimensions)
        matrix.fill(numpy.NAN)
        for (pv,datastore) in datastores:
            index = [param_values[i].index(pv[i]) for i in xrange(0,len(param_values))]
            dsv = query.query(datastore)
            matrix[index] = param_filter_query(dsv,identifier='SingleValue',value_name=v).get_analysis_result()[0].value

        f = open(v+'.txt','w')
        pickle.dump((parameters,param_values,matrix),f)
        
        
        
        
        
        
