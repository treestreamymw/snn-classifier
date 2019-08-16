#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Aug 2019

@author: BG

Specify specific neuron type and its prms.
"""

from __future__ import division

import numpy as np

from .escape_noise import ExpRate
from ..parameters import ParamSet
from ..preprocess import pattern2psps


class SRM(object):
    """
    (Simplified) Spike-Response Model (SRM).

    Parameters
    ----------
    stochastic : bool, optional, default False
        Enable stochastic spike generator.
    EscapeRate : class, default ExpRate
        Escape noise model used to distribute spikes, if stochastic enabled.
    tau_m : float
        Membrane time constant (ms).
    tau_s : float
        Synaptic rise time (ms).
    theta : float
        Firing threshold (mV).
    cm : float
        Membrane capacitance (nF)
    kappa_0 : float
        Reset strength (mV).
    q : float
        Charge transferred due to a presynaptic spike (nA).
    """
    def __init__(self, stochastic=False, EscapeRate=ExpRate, **kwargs):
        # Stochastic spike generator
        self.stochastic = stochastic
        # Default cell prms
        self.prms = ParamSet({'tau_m': 10.,
                              'tau_s': 5.,
                              'theta': 15.,
                              'cm': 2.5,
                              'kappa_0': -15.,
                              'q': 5.})
        self.update(EscapeRate=EscapeRate, **kwargs)

    def update(self, EscapeRate=ExpRate, **kwargs):
        self.prms.overwrite(**kwargs)
        # Derived values
        # psp coeff (mV)
        self.prms['psp_coeff'] = self.prms['q'] / self.prms['cm'] * \
            self.prms['tau_m'] / (self.prms['tau_m'] - self.prms['tau_s'])
        # Stochastic spike generator
        if self.stochastic:
            self.esc_rate = EscapeRate(theta=self.prms['theta'], **kwargs)

    def response(self, stimulus, w, dt, duration):
        """
        Neuron's response to a driving stimulus, through a weight vector.

        Parameters
        ----------
        stimulus : list, len (num_inputs)
            Set of input spike trains.
        w : array, shape (num_inputs,)
            Input weight vector.
        dt : float
            Time resolution.
        duration : float
            Cut-off point for determining neuron response.
        """
        # Transform stimulus to PSPs for this neuron
        # psps : array, shape (num_inputs, num_iter)
        psps = pattern2psps(stimulus, dt, duration, **self.prms)
        spike_train = np.array([])

        # State variable updates
        potentials = np.dot(w, psps)
        # Determine spikes
        if self.stochastic:
            unif_samples = self.rng.uniform(size=len(potentials))
