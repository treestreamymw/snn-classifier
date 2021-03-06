#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Custom learning windows for pre- and post spiking correlations.

This file is part of snn-classifier.

Copyright (C) 2018  Brian Gardner <brgardner@hotmail.co.uk>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import division

import numpy as np


class LearnWindow(object):
    """
    Abstract learning window.
    Implements causal (pre-to-post) spiking correlations only.
    """
    def causal(self, post_spikes, pre_spikes):
        """
        Causal-correlation traces at each [post-spike] due to [pre-spikes].
        """
        raise NotImplementedError

    def causal_reduce(self, post_spikes, pre_spikes, delays=None):
        """
        Summed traces at each post-spike time, due to all pre-spikes.
        Outputs reduced causal-correlation traces, shape (num_post).
        """
        return np.sum(self.causal(post_spikes, pre_spikes, delays), -1)

    def double_conv_psp(self, spikes_o, spikes_h, psp_in):
        raise NotImplementedError


class EXPWindow(LearnWindow):
    """
    Exponentially-shaped learning window.
    Implements the reduced-symmetric interpretation of a nearest neighbour
    spike-pairing scheme (Morrison et al. 2008) as exists in DLS v2.
    """
    def __init__(self, param):
        self.tau_m = param.cell['tau_m']

    def causal(self, post_spikes, pre_spikes, delays=None):
        """
        TODO: Implement delays.
        Causal-correlation traces at each [post-spike] due to most recent
        [pre-spike]. Outputs correlations array, shape (num_post, 1).
        """
        traces = np.zeros((len(post_spikes), 1))
        if len(pre_spikes) > 0:
            for idx, t_post in enumerate(post_spikes):
                pre_mask = pre_spikes <= t_post
                pre_last = pre_spikes[pre_mask]  # pre-spikes before post-spike
                if len(pre_last) > 0:
                    traces[idx] = \
                        np.exp(-(t_post - pre_last[-1]) / self.tau_m)
                    pre_spikes = pre_spikes[~pre_mask]
                if len(pre_spikes) == 0:
                    break
        return traces


class PSPWindow(LearnWindow):
    """
    PSP learning window.
    Causal (pre-to-post) correlation traces only.
    """
    def __init__(self, param):
        self.epsilon_0 = param.cell['psp_coeff']
        self.tau_m = param.cell['tau_m']
        self.tau_s = param.cell['tau_s']

    def causal(self, post_spikes, pre_spikes, delays=None):
        """
        Causal-correlation traces at each [post-spike] due to each [pre-spike].
        Optionally also w.r.t. each subconnection delay.

        Inputs
        ------
        post_spikes : array, shape (num_spikes,)
            Sequence of postsynaptic spike times.
        pre_spikes : array, shape (num_spikes,)
            Sequence of presynaptic spike times.
        delays : array, optional, shape (num_subs,)
            Conduction delay times for each pre_spike.

        Output
        ------
        return : array, shape (num_post[, num_subs], num_pre)
            Causal-correlation traces.
        """
        if delays is not None:
            # Epsilon arguments : array, shape (num_post, num_subs, num_pre)
            lags = post_spikes[:, np.newaxis, np.newaxis] - \
                (pre_spikes + delays[:, np.newaxis])
        else:
            lags = post_spikes[:, np.newaxis] - pre_spikes[np.newaxis, :]
        u = (lags > 0.).astype(float)
        traces = self.epsilon_0 * (np.exp(-lags / self.tau_m) -
                                   np.exp(-lags / self.tau_s)) * u
        return traces

    def double_conv_psp(self, spikes_o, spikes_h, psp_in):
        """
        Double conv function, evaluated at each spikes_o due to shared spikes_h
        and psp_in. psp_in is of size <num_inputs> by <num_spikes_h>.

        Inputs
        ------
        spikes_o : array, shape (num_spikes,)
            Sequence of output spike times.
        spikes_h : array, shape (num_spikes,)
            Sequence of hidden spike times.
        psp_in : array, shape (num_input_nrns, num_hidden_spikes)
            Sequence of psps due to each input spike train, at each hidden
            firing time.

        Output
        ------
        return : array, shape (num_output_spikes, num_input_nrns)
            Double convolution of input-hidden-output spiking.
        """
        # Correlations between each output-hidden spike pair:
        # <# spikes_o> by <# spikes_h>
        corr_oh = self.causal(spikes_o, spikes_h)
        # <# spikes_o> by <1> by <# spikes_h>
        corr_oh = corr_oh[:, np.newaxis, :]
        psp_in = psp_in[np.newaxis, :, :]  # Prep for broadcasting
        return np.sum(corr_oh * psp_in, 2)
#        return np.dot(corr_oh, psp_in.T)
