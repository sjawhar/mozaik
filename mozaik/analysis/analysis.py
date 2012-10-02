"""
This module contains the Mozaik analysis interface and implementation of
various analysis algorithms
"""

import pylab
import numpy
import time
import quantities as qt
import mozaik.tools.units as munits
from mozaik.stimuli.stimulus import colapse, StimulusID, colapse_to_dictionary
from mozaik.analysis.analysis_data_structures import *
from mozaik.analysis.analysis_helper_functions import psth_across_trials, psth
from mozaik.framework.interfaces import MozaikParametrizeObject
from NeuroTools.parameters import ParameterSet
from mozaik.storage.queries import *
from mozaik.storage.ads_queries import *
from neo.core.analogsignal import AnalogSignal
from NeuroTools import signals
from mozaik.tools.circ_stat import circ_mean, circular_dist
from mozaik.tools.neo_object_operations import *
import logging

logger = mozaik.getMozaikLogger("Mozaik")


class Analysis(MozaikParametrizeObject):
    """
    Analysis encapsulates analysis algorithms.

    The interface is extremely simple: it only requires the implementation of
    the `perform_analysis` function which when called performs the analysis.
    This function should retrieve its own data from the `DataStoreView` that is
    supplied in the `datastore` parameter. Further, it should include `tags`
    as the tags for all `AnalysisDataStructure` objects that it creates.
    (See the description of the `AnalysisDataStructure.tags` attribute.

    Arguments:
        datastore (DataStoreView): the datastore from which to pull data.
        parameters (ParameterSet): the parameter set
        tags (list(str)): tags to attach to the AnalysisDataStructures
                          generated by the analysis

    """

    def __init__(self, datastore, parameters, tags=None):
        MozaikParametrizeObject.__init__(self, parameters)
        self.datastore = datastore
        if tags == None:
            self.tags = []
        else:
            self.tags = tags

    def analyse(self):
        t1 = time.time()
        logger.info('Starting ' + self.__class__.__name__ + ' analysis')
        self.perform_analysis()
        t2 = time.time()
        logger.warning(self.__class__.__name__ + ' analysis took: '
                       + str(t2-t1) + 'seconds')

    def perform_analysis(self):
        """
        The function that implements the analysis
        """
        raise NotImplementedError


class TrialAveragedFiringRate(Analysis):
    """
    This analysis takes all recordings with a
    `FullfieldDriftingSinusoidalGrating` stimulus. It averages over the
    trials and creates tuning curves with respect to the orientation
    parameter. Thus for each combination of the other stimulus parameters
    a tuning curve is created.
    """

    required_parameters = ParameterSet({
      'stimulus_type': str,  # The stimulus type for which to compute AveragedTuning
    })

    def perform_analysis(self):
        dsv = select_stimuli_type_query(self.datastore,
                                        self.parameters.stimulus_type)

        for sheet in dsv.sheets():
            dsv1 = select_result_sheet_query(dsv, sheet)
            segs = dsv1.get_segments()
            st = [StimulusID(s) for s in dsv1.get_stimuli()]
            # transform spike trains due to stimuly to mean_rates
            mean_rates = [numpy.array(s.mean_rates())  for s in segs]
            # collapse against all parameters other then trial
            (mean_rates, s) = colapse(mean_rates, st, parameter_list=['trial'])
            # take a sum of each
            mean_rates = [sum(a)/len(a) for a in mean_rates]

            #JAHACK make sure that mean_rates() return spikes per second
            units = munits.spike / qt.s
            logger.debug('Adding PerNeuronValue containing trial averaged '
                         'firing rates to datastore')
            for mr, st in zip(mean_rates, s):
                self.datastore.full_datastore.add_analysis_result(
                    PerNeuronValue(mr, units,
                                   stimulus_id=str(st),
                                   value_name='Firing rate',
                                   sheet_name=sheet,
                                   tags=self.tags,
                                   analysis_algorithm=self.__class__.__name__,
                                   period=None))


class PeriodicTuningCurvePreferenceAndSelectivity_VectorAverage(Analysis):
    """
    This analysis takes a list of PerNeuronValues and a periodic parameter
    `parameter_name`.

    All PerNeuronValues have to belong to stimuli of the same type and
    contain the same type of values (i.e. have the same `value_name`).

    For each combination of parameters of the stimuli other than `parameter_name`
    `PeriodicTuningCurvePreferenceAndSelectivity_VectorAverage` creates a
    PerNeuronValue which corresponsd to the vector average through the
    periodic domain of `parameter_name`.
    """

    required_parameters = ParameterSet({
        'parameter_name': str,  # The name of the parameter through which to calculate the VectorAverage
    })

    def perform_analysis(self):
        self.datastore.print_content()
        dsv = analysis_data_structure_parameter_filter_query(self.datastore,
                                                             identifier='PerNeuronValue')
        for sheet in self.datastore.sheets():
            # Get PerNeuronValue ASD and make sure they are all associated
            # with the same stimulus and do not differ in any
            # ASD parameters except the stimulus
            dsv = select_result_sheet_query(dsv, sheet)
            if ads_is_empty(dsv):
                break
            assert equal_ads_except(dsv, ['stimulus_id'])
            assert ads_with_equal_stimulus_type(dsv, not_None=True)

            self.pnvs = dsv.get_analysis_result(sheet_name=sheet)
            # get stimuli
            st = [StimulusID(s.stimulus_id) for s in self.pnvs]

            d = colapse_to_dictionary([z.values for z in self.pnvs],
                                      st,
                                      self.parameters.parameter_name)
            result_dict = {}
            for k in d.keys():
                keys, values = d[k]
                y = []
                x = []
                for v, p in zip(values, keys):
                    y.append(v)
                    x.append(numpy.zeros(numpy.shape(v)) + p)

                pref, sel = circ_mean(numpy.array(x),
                                      weights=numpy.array(y),
                                      axis=0,
                                      low=0,
                                      high=st[0].periods[self.parameters.parameter_name],
                                      normalize=True)

                logger.debug('Adding PerNeuronValue to datastore')

                self.datastore.full_datastore.add_analysis_result(
                    PerNeuronValue(pref,
                                   st[0].units[self.parameters.parameter_name],
                                   value_name=self.parameters.parameter_name + ' preference',
                                   sheet_name=sheet,
                                   tags=self.tags,
                                   period=st[0].periods[self.parameters.parameter_name],
                                   analysis_algorithm=self.__class__.__name__,
                                   stimulus_id=str(k)))
                self.datastore.full_datastore.add_analysis_result(
                    PerNeuronValue(sel,
                                   st[0].units[self.parameters.parameter_name],
                                   value_name=self.parameters.parameter_name + ' selectivity',
                                   sheet_name=sheet,
                                   tags=self.tags,
                                   period=1.0,
                                   analysis_algorithm=self.__class__.__name__,
                                   stimulus_id=str(k)))


class GSTA(Analysis):
    """
    Computes conductance spike triggered average.

    Note that it does not assume that spikes are aligned with the conductance
    sampling rate and will pick the bin in which the given spike falls
    (within the conductance sampling rate binning) as the center of the
    conductance vector that is included in the STA.
    """

    required_parameters = ParameterSet({
        'length': float,  # length (in ms time) how long before and after spike to compute the GSTA
                          # it will be rounded down to fit the sampling frequency
        'neurons': list,  # the list of neuron indexes for which to compute the
    })

    def perform_analysis(self):
        dsv = self.datastore
        for sheet in dsv.sheets():
            dsv1 = select_result_sheet_query(dsv, sheet)
            st = dsv1.get_stimuli()
            segs = dsv1.get_segments()

            asl_e = []
            asl_i = []
            for n in self.parameters.neurons:
                sp = [s.spiketrains[n] for s in segs]
                g_e = [s.get_esyn(n) for s in segs]
                g_i = [s.get_isyn(n) for s in segs]
                asl_e.append(self.do_gsta(g_e, sp))
                asl_i.append(self.do_gsta(g_i, sp))
            self.datastore.full_datastore.add_analysis_result(
                ConductanceSignalList(asl_e,
                                      asl_i,
                                      self.parameters.neurons,
                                      sheet_name=sheet,
                                      tags=self.tags,
                                      analysis_algorithm=self.__class__.__name__))

    def do_gsta(self, analog_signal, sp):
        dt = analog_signal[0].sampling_period
        gstal = int(self.parameters.length/dt)
        gsta = numpy.zeros(2*gstal + 1,)
        count = 0
        for (ans, spike) in zip(analog_signal, sp):
            for time in spike:
                if time > ans.t_start  and time < ans.t_stop:
                    idx = int((time - ans.t_start)/dt)
                    if idx - gstal > 0 and (idx + gstal + 1) <= len(ans):
                        gsta = gsta + ans[idx-gstal:idx+gstal+1].flatten().magnitude
                        count +=1
        if count == 0:
            count = 1
        gsta = gsta / count
        gsta = gsta * analog_signal[0].units

        return AnalogSignal(gsta,
                            t_start=-gstal*dt,
                            sampling_period=dt,
                            units=analog_signal[0].units)


class Precision(Analysis):
    """
    Computes the precision as the autocorrelation between the PSTH of
    different trials.

    Takes all the responses in the datastore.
    """

    required_parameters = ParameterSet({
        'neurons': list,  # the list of neuron indexes for which to compute the
        'bin_length': float,  # (ms) the size of bin to construct the PSTH from
    })

    def perform_analysis(self):
        for sheet in self.datastore.sheets():
            # Load up spike trains for the right sheet and the corresponding
            # stimuli, and transform spike trains into psth
            dsv = select_result_sheet_query(self.datastore, sheet)
            psths = [psth(seg.spiketrains, self.parameters.bin_length)
                     for seg in dsv.get_segments()]

            st = [StimulusID(s) for s in dsv.get_stimuli()]

            # average across trials
            psths, stids = colapse(psths,
                                   st,
                                   parameter_list=['trial'],
                                   func=neo_mean,
                                   allow_non_identical_stimuli=True)

            for ppsth, stid in zip(psths, stids):
                t_start = ppsth[0].t_start
                duration = ppsth[0].t_stop-ppsth[0].t_start
                al = []
                for n in self.parameters.neurons:
                    ac = numpy.correlate(numpy.array(ppsth[:, n]),
                                         numpy.array(ppsth[:, n]),
                                         mode='full')
                    div = numpy.sum(numpy.power(numpy.array(ppsth[:, n]), 2))
                    if div != 0:
                        ac = ac / div
                    al.append(
                        AnalogSignal(ac,
                                     t_start=-duration+self.parameters.bin_length*t_start.units/2,
                                     sampling_period=self.parameters.bin_length*qt.ms,
                                     units=qt.dimensionless))

                logger.debug('Adding AnalogSignalList:' + str(sheet))
                self.datastore.full_datastore.add_analysis_result(
                    AnalogSignalList(al,
                                     self.parameters.neurons,
                                     qt.ms,
                                     qt.dimensionless,
                                     x_axis_name='time',
                                     y_axis_name='autocorrelation',
                                     sheet_name=sheet,
                                     tags=self.tags,
                                     analysis_algorithm=self.__class__.__name__,
                                     stimulus_id=str(stid)))


class ModulationRatio(Analysis):
    """
    This analysis calculates the modulation ration (as the F1/F0) for all
    neurons in the data using all available responses recorded to the
    FullfieldDriftingSinusoidalGrating stimuli. This method also requires
    that AveragedOrientationTuning has already been calculated.
    """

    required_parameters = ParameterSet({
      'bin_length': float,  # (ms) the size of bin to construct the PSTH from
    })

    def perform_analysis(self):
        for sheet in self.datastore.sheets():
            # Load up spike trains for the right sheet and the corresponding
            # stimuli, and transform spike trains into psth
            dsv = select_result_sheet_query(self.datastore, sheet)
            assert equal_ads_except(dsv, ['stimulus_id'])
            assert ads_with_equal_stimulus_type(dsv)
            assert equal_stimulus_type(dsv)

            psths = [psth(seg.spiketrains, self.parameters.bin_length)
                     for seg in dsv.get_segments()]
            st = [StimulusID(s) for s in dsv.get_stimuli()]

            # average across trials
            psths, stids = colapse(psths,
                                   st,
                                   parameter_list=['trial'],
                                   func=neo_mean,
                                   allow_non_identical_stimuli=True)

            # retrieve the computed orientation preferences
            pnvs = self.datastore.get_analysis_result(identifier='PerNeuronValue',
                                                      sheet_name=sheet,
                                                      value_name='orientation preference')
            if len(pnvs) != 1:
                logger.error("ERROR: Expected only one PerNeuronValue per sheet "
                             "with value_name 'orientation preference' in datastore, got: "
                             + str(len(pnvs)))
                return None
            else:
                or_pref = pnvs[0]

            # find closest orientation of grating to a given orientation
            # preference of a neuron
            # first find all the different presented stimuli:
            ps = {}
            for s in st:
                ps[StimulusID(s).params['orientation']] = True
            ps = ps.keys()

            # now find the closest presented orientations
            closest_presented_orientation = []
            for i in xrange(0, len(or_pref.values)):
                circ_d = 100000
                idx = 0
                for j in xrange(0, len(ps)):
                    if circ_d > circular_dist(or_pref.values[i], ps[j], numpy.pi):
                        circ_d = circular_dist(or_pref.values[i], ps[j], numpy.pi)
                        idx = j
                closest_presented_orientation.append(ps[idx])

            closest_presented_orientation = numpy.array(closest_presented_orientation)

            # collapse along orientation - we will calculate MR for each
            # parameter combination other than orientation
            d = colapse_to_dictionary(psths, stids, "orientation")
            for (st, vl) in d.items():
                # here we will store the modulation ratios, one per each neuron
                modulation_ratio = numpy.zeros((numpy.shape(psths[0])[1],))
                frequency = StimulusID(st).params['temporal_frequency'] * StimulusID(st).units['temporal_frequency']
                for (orr, ppsth) in zip(vl[0], vl[1]):
                    for j in numpy.nonzero(orr == closest_presented_orientation)[0]:
                        modulation_ratio[j] = self.calculate_MR(ppsth[:, j],
                                                                frequency)

                self.datastore.full_datastore.add_analysis_result(
                    PerNeuronValue(modulation_ratio,
                                   qt.dimensionless,
                                   value_name='Modulation ratio',
                                   sheet_name=sheet,
                                   tags=self.tags,
                                   period=None,
                                   analysis_algorithm=self.__class__.__name__,
                                   stimulus_id=str(st)))

            import pylab
            pylab.figure()
            pylab.hist(modulation_ratio)

    def calculate_MR(self, signal, frequency):
        """
        Calculates MR at frequency 1/period for each of the signals in the signal_list

        Returns an array of MRs on per each signal in signal_list
        """
        duration = signal.t_stop - signal.t_start
        period = 1/frequency
        period = period.rescale(signal.t_start.units)
        cycles = duration / period
        first_har = round(cycles)

        fft = numpy.fft.fft(signal)

        if abs(fft[0]) != 0:
            return 2 *abs(fft[first_har]) /abs(fft[0])
        else:
            return 0
