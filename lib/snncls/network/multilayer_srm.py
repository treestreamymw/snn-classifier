#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Mar 2017

@author: BG

Define multilayer network object.
"""

from __future__ import division

import numpy as np

from .base import MultilayerSRMBase, MultilayerBase
from ..neuron import ExpRate, SRM


class MultilayerSRM(MultilayerSRMBase):
    """
    Spiking neural network, optimised specifically for SRM neurons.

    Parameters
    ----------
    sizes : list, len (num_layers)
        Num. neurons in [input, hidden, output layers].
    param : container
        Using cell, pattern, net and common parameters.
    weights : list, optional, len (num_layers - 1)
        Sets initial network weights. Each element is an array of shape
        (num_post, num_pre).
    EscapeRate : class, default EXPRate
        Stochastic spike generator for hidden layer neurons.
    """
    def simulate(self, stimulus, latency=False, return_psps=False,
                 debug=False):
        """
        Network activity in response to an input stimulus driving the
        network. Based on iterative procedure to determine spike times.
        Profiled at t = 0.34 s (iris, defaults (29/08/18), 20 hidden nrns).
        Speedup of 9x compared with non-iterative method.
        Scales less well as number of neurons increases (loops used).

        Parameters
        ----------
        stimulus : array or list
            Input drive to the network, as one of two types:
                - predetermined psps: array, shape (num_inputs, num_iter)
                - set of spike trains: list, len (num_inputs)
        latency : bool, optional
            Restrict to just finding first output spikes.
        return_psps : bool
            Return PSPs evoked due to each layer, excluding output layer, each
            with shape (num_nrns, num_iter).
        debug : bool, optional
            Record network dynamics for debugging.

        Returns
        -------
        spike_trains_l : list
            List of neuron spike trains, for layers l > 0.
        psps : list, optional
            List of PSPs evoked, for layers l < L.
        rec : dict, optional
            Debug recordings containing
            {'psp' as list of evoked PSPs, 'u' as list of potentials}.
        """
        # === Initialise ==================================================== #

        # Cast stimulus to PSPs evoked by input neurons
        psp_inputs = self.stimulus_as_psps(stimulus)
        num_iter = psp_inputs.shape[1]
        # Ensure pattern duration is compatible with look up tables
        assert num_iter == len(self.lut['psp'])

        # Record
        rec = {}
        if return_psps:
            rec['psp'] = [np.empty((i, num_iter))
                          for i in self.sizes[:-1]]
            rec['psp'][0] = psp_inputs
        if debug:
            rec['u'] = [np.empty((i, num_iter))
                        for i in self.sizes[1:]]
        # Spike trains for layers: l > 0
        spike_trains_l = [[np.array([]) for j in xrange(self.sizes[i])]
                          for i in xrange(1, self.num_layers)]

        # === Run simulation ================================================ #

        # PSPs evoked by input neurons
        psps = psp_inputs
        # Hidden layer responses: l = [1, L)
        for l in xrange(self.num_layers - 2):
            potentials = np.dot(self.w[l], psps)
            # Stochastic spiking
            unif_samples = self.rng.uniform(size=np.shape(potentials))
            # PSPs evoked by this layer
            psps = np.zeros((self.sizes[l+1], num_iter))
            for i in xrange(self.sizes[l+1]):
                num_spikes = 0
                while True:
                    rates = self.neuron_h.activation(potentials[i])
                    thr_idxs = \
                        np.where(unif_samples[i] < rates * self.dt)[0]
                    if num_spikes < len(thr_idxs):
                        fire_idx = thr_idxs[num_spikes]
                        iters = num_iter - fire_idx
                        potentials[i, fire_idx:] += self.lut['refr'][:iters]
                        psps[i, fire_idx:] += self.lut['psp'][:iters]
                        spike_trains_l[l][i] = \
                            np.append(spike_trains_l[l][i],
                                      fire_idx * self.dt)
                        num_spikes += 1
                    else:
                        break
            # Record
            if return_psps:
                rec['psp'][l+1] = psps
            if debug:
                rec['u'][l] = potentials
        # Output responses
        potentials = np.dot(self.w[-1], psps)
        # PSPs evoked by this layer
        psps = np.zeros((self.sizes[-1], num_iter))
        for i in xrange(self.sizes[-1]):
            num_spikes = 0
            while True:
                thr_idxs = \
                    np.where(potentials[i] > self.cell_params['theta'])[0]
                if num_spikes < len(thr_idxs):
                    fire_idx = thr_idxs[num_spikes]
                    iters = num_iter - fire_idx
                    potentials[i, fire_idx:] += self.lut['refr'][:iters]
                    psps[i, fire_idx:] += self.lut['psp'][:iters]
                    spike_trains_l[-1][i] = np.append(spike_trains_l[-1][i],
                                                      fire_idx * self.dt)
                    # Optimisation: skip output spikes after first
                    if latency:
                        break
                    else:
                        num_spikes += 1
                else:
                    break
        if debug:
            rec['u'][-1] = potentials

        if debug:
            return spike_trains_l, rec
        elif return_psps:
            return spike_trains_l, rec['psp']
        else:
            return spike_trains_l

    def simulate_steps(self, psp_inputs, debug=False):
        """
        TODO: cleanup
        Network activity in response to an input pattern presented to the
        network.
        Profiled at t = 3.1 s (iris, defaults (29/08/18), 20 hidden nrns).

        Inputs
        ------
        psp_inputs : array
            PSPs from input layer neurons of size: <num_inputs> by <num_iter>.
        debug : bool
            Record network dynamics for debugging.

        Outputs
        -------
        spiked_l : list
            List of boolean spike trains in layers l > 0.
        rec : dict, optional
            Debug recordings containing
            {psps evoked from hidden neurons 'psp', potentials 'u',
             bool spike trains 'S'}.
        """
        # === Initialise ==================================================== #

        # Pattern stats
        num_iter = psp_inputs.shape[1]  # Num. time steps per duration
        # Debug
        if debug:
            rec = {'psp': [np.empty((i, num_iter))
                           for i in self.sizes[1:-1]],
                   'u': [np.empty((i, num_iter))
                         for i in self.sizes[1:]],
                   'S': [np.empty((i, num_iter), dtype=int)
                         for i in self.sizes[1:]]}
        # Bool spike trains in each layer: l > 1
        spiked_l = [np.zeros((i, num_iter), dtype=bool)
                    for i in self.sizes[1:]]
        # PSPs from each layer: 1 <= l < L, reset kernels in each layer: l >= 1
        # Membrane, synaptic exponential decays
        psp_trace_l = [np.zeros((i, 2)) for i in self.sizes[1:-1]]
        refr_l = [np.zeros(i) for i in self.sizes[1:]]

        # === Run simulation ================================================ #
        unif_samples = [self.rng.uniform(size=(i, num_iter))
                        for i in self.sizes[1:-1]]
        if debug:
            rec['smpls'] = unif_samples
        for t_step in xrange(num_iter):
            # Update kernels: l >= 1
            psp_trace_l = [i * [self.decay_m, self.decay_s]
                           for i in psp_trace_l]
            psp_l = [i[:, 0] - i[:, 1] for i in psp_trace_l]
            refr_l = [i * self.decay_m for i in refr_l]

            psps = psp_inputs[:, t_step]
            # Hidden layer responses: 1 <= l < L
            for l in xrange(self.num_layers - 2):
                potentials = np.dot(self.w[l], psps) + refr_l[l]
                rates = self.neuron_h.activation(potentials)
                spiked_l[l][:, t_step] = unif_samples[l][:, t_step] < \
                    self.dt * rates
                psps = psp_l[l]
                # Debugging
                if debug:
                    rec['psp'][l][:, t_step] = psps
                    rec['u'][l][:, t_step] = potentials
            # Output layer response
            potentials = np.dot(self.w[-1], psps) + refr_l[-1]
            spiked_l[-1][:, t_step] = potentials > self.cell_params['theta']
            # Update kernels
            for l in xrange(self.num_layers - 2):
                psp_trace_l[l][spiked_l[l][:, t_step], :] += \
                    self.cell_params['psp_coeff']
            for l in xrange(self.num_layers - 1):
                refr_l[l][spiked_l[l][:, t_step]] += \
                    self.cell_params['kappa_0']
            # Debugging
            if debug:
                rec['u'][-1][:, t_step] = potentials
                for l in xrange(self.num_layers - 1):
                    rec['S'][l][:, t_step] = spiked_l[l][:, t_step]

        # === Gather output spike trains ==================================== #

        # Spike trains: l > 0
        spike_trains_l = []
        for spiked in spiked_l:
            spike_trains_l.append([np.where(isspike)[0] * self.dt
                                   for isspike in spiked])
        if debug:
            return spike_trains_l, rec
        else:
            return spike_trains_l


class MultilayerSRMSub(MultilayerSRMBase):
    """
    Spiking neural network with subconnections. Each connection is split into
    'subconnections' with different conduction delays. The delays are
    linearly-spaced over a specified range.

    Parameters
    ----------
    sizes : list
        Num. neurons in [input, hidden, output layers].
    param : container
        Using cell, pattern, net and common parameters.
    weights : list, optional, len (num_layers-1)
        Sets initial network weights. Each element is an array of shape
        (num_post, num_pre, num_subs).
    num_subs : int, array-like, default 1
        Number of incoming subconnections per neuron for layers l > 0.
    max_delay : int, default 10
        Maximum conduction delay for num_subs > 1.
    conns_fr : float, optional
        Fraction of hidden subconns randomly enabled at init.
    delay_distr : {'lin', 'unif'}, default 'lin'
        Distribution used to set subconnection delay values,
        between 1 and 10 ms.
    EscapeRate : class, default EXPRate
        Stochastic spike generator for hidden layer neurons.
    """
    def __init__(self, sizes, param, weights=None, num_subs=1, max_delay=10.,
                 conns_fr=None, delay_distr='lin', EscapeRate=ExpRate):
        """
        Randomly initialise weights of neurons in each layer. Subconnection
        delays are linearly-spaced. Fractional number of connections are
        approximated by clamping weights to zero on unused subconnections.
        """
        assert max_delay > 1.
        # Set common prms, prototype connectivity and initialise weights
        if np.isscalar(num_subs):
            self.num_subs = [num_subs for i in xrange(len(sizes) - 1)]
        else:
            self.num_subs = np.asarray(num_subs, dtype=int)
        self.conns_fr = conns_fr
        super(MultilayerSRMSub, self).__init__(sizes, param, weights,
                                               EscapeRate)

        # Initialise delay values
        def distr_type(key, low=1., high=10.):
            # Return a desired distribution function, specified over
            # a given range of possible values
            choices = {'lin': lambda num: np.linspace(low, high, num=num),
                       'unif': lambda num: self.rng.uniform(low, high,
                                                            size=num)}
            return choices[key]
        distr = distr_type(delay_distr, high=max_delay)
        self.delays = [self.times2steps(distr(i)) for i in self.num_subs]

    def _build_network(self, weights):
        """
        Prototype network connectivity with subconns. and initialise weight
        values. Clamped hidden weights are determined here.
        """
        self.w = [np.empty((i, j, k))
                  for i, j, k in zip(self.sizes[1:], self.sizes[:-1],
                  self.num_subs)]
        # Hidden weights mask with values clamped to zero
        if self.conns_fr is not None:
            self.clamp_mask = [np.zeros(w.shape, dtype=bool)
                               for w in self.w[:-1]]
            for idx, w in enumerate(self.w[:-1]):
                num_clamps = \
                    np.round((1. - self.conns_fr) *
                             self.num_subs[idx]).astype(int)
                assert 0 <= num_clamps < self.num_subs[idx]
                for coord in np.ndindex(w.shape[:-1]):
                    clamp_idxs = self.rng.choice(self.num_subs[idx],
                                                 num_clamps, replace=False)
                    self.clamp_mask[idx][coord][clamp_idxs] = True
        self.reset(weights=weights)

    def _init_weights(self):
        """
        Randomly intialise weights according to a uniform distribution, and
        normalised w.r.t. num. subconns.
        """
        weights = []
        # Hidden layers
        for i, j, k in zip(self.sizes[1:-1], self.sizes[:-2],
                           self.num_subs[:-1]):
            weights.append(self.rng.uniform(*self.w_h_init,
                                            size=(i, j, k)))
        # Output layer
        weights.append(self.rng.uniform(*self.w_o_init,
                                        size=(self.sizes[-1],
                                              self.sizes[-2],
                                              self.num_subs[-1])))
        # Normalise weights w.r.t. num_subs
        if hasattr(self, 'clamp_mask'):
            # Num. actual hidden weights with clamped values
            for idx, w in enumerate(weights[:-1]):
                num_conns = np.round(self.conns_fr *
                                     self.num_subs[idx]).astype(int)
                w /= num_conns
            weights[-1] /= self.num_subs[-1]
        else:
            weights = [w / w.shape[-1] for w in weights]
        self.set_weights(weights)

    def set_weights(self, weights, assert_bounds=False):
        """
        Set network weights to new values, subject to constraints, including
        missing subconnections (weights clamped to zero).
        """
        super(MultilayerSRMSub, self).set_weights(weights, assert_bounds)
        if hasattr(self, 'clamp_mask'):
            for w, m in zip(self.w[:-1], self.clamp_mask):
                w[m] = 0.

    def simulate(self, stimulus, latency=False, return_psps=False,
                 debug=False):
        """
        Network activity in response to an input stimulus driving the
        network. Based on iterative procedure to determine spike times.
        Expected speedup of ~9x compared with non-iterative method.

        Inputs
        ------
        stimulus : array or list
            Input drive to the network, as one of two types:
                - predetermined psps: array, shape (num_inputs, num_iter)
                - set of spike trains: list, len (num_inputs)
        latency : bool, optional
            Restrict to just finding first output spikes.
        return_psps : bool
            Return PSPs evoked due to each layer, excluding output layer, each
            with shape (num_nrns, num_subconns, num_iter).
        debug : bool, optional
            Record network dynamics for debugging.

        Outputs
        -------
        spike_trains_l : list
            List of neuron spike trains, for layers l > 0.
        psps : list, optional
            List of PSPs evoked, for layers l < L.
        rec : dict, optional
            Debug recordings containing
            {'psp' as list of evoked PSPs, 'u' as list of potentials}.
        """
        # === Initialise ==================================================== #

        # Cast stimulus to PSPs evoked by input neurons
        psp_inputs = self.stimulus_as_psps(stimulus)
        num_iter = psp_inputs.shape[1]
        # Ensure pattern duration is compatible with look up tables
        assert num_iter == len(self.lut['psp'])
        # Expand PSPs: shape (num_inputs, num_iter) ->
        # shape (num_inputs, num_subs, num_iter)
        shape = (len(psp_inputs), self.num_subs[0], num_iter)
        psps = np.zeros(shape)
        for i, delay in enumerate(self.delays[0]):
            psps[:, i, delay:] = psp_inputs[:, :-delay]

        # Record
        rec = {}
        if return_psps:
            rec['psp'] = [np.empty((i, j, num_iter))
                          for i, j in zip(self.sizes[:-1], self.num_subs)]
            rec['psp'][0] = psps
        if debug:
            rec['u'] = [np.empty((i, num_iter))
                        for i in self.sizes[1:]]
        # Spike trains for layers: l > 0
        spike_trains_l = [[np.array([]) for j in xrange(self.sizes[i])]
                          for i in xrange(1, self.num_layers)]

        # === Run simulation ================================================ #

        # Hidden layer responses: l = [1, L)
        for l in xrange(self.num_layers - 2):
            potentials = np.tensordot(self.w[l], psps)
            # Stochastic spiking: the order in which random values are sampled
            # differs from simulate_steps
            unif_samples = self.rng.uniform(size=np.shape(potentials))
            # PSPs evoked by this layer
            psps = np.zeros((self.sizes[l+1], self.num_subs[l+1], num_iter))
            for i in xrange(self.sizes[l+1]):
                num_spikes = 0
                while True:
                    rates = self.neuron_h.activation(potentials[i])
                    thr_idxs = \
                        np.where(unif_samples[i] < rates * self.dt)[0]
                    if num_spikes < len(thr_idxs):
                        fire_idx = thr_idxs[num_spikes]
                        iters = num_iter - fire_idx
                        potentials[i, fire_idx:] += self.lut['refr'][:iters]
                        for j, delay in enumerate(self.delays[l+1]):
                            fire_idx_delay = fire_idx + delay
                            if fire_idx_delay < num_iter:
                                psps[i, j, fire_idx_delay:] += \
                                    self.lut['psp'][:iters-delay]
                        spike_trains_l[l][i] = \
                            np.append(spike_trains_l[l][i],
                                      fire_idx * self.dt)
                        num_spikes += 1
                    else:
                        break
            # Record
            if return_psps:
                rec['psp'][l+1] = psps
            if debug:
                rec['u'][l] = potentials
        # Output responses
        potentials = np.tensordot(self.w[-1], psps)
        for i in xrange(self.sizes[-1]):
            num_spikes = 0
            while True:
                thr_idxs = \
                    np.where(potentials[i] > self.cell_params['theta'])[0]
                if num_spikes < len(thr_idxs):
                    fire_idx = thr_idxs[num_spikes]
                    iters = num_iter - fire_idx
                    potentials[i, fire_idx:] += self.lut['refr'][:iters]
                    spike_trains_l[-1][i] = np.append(spike_trains_l[-1][i],
                                                      fire_idx * self.dt)
                    # Optimisation: skip output spikes after first
                    if latency:
                        break
                    else:
                        num_spikes += 1
                else:
                    break
        if debug:
            rec['u'][-1] = potentials

        if debug:
            return spike_trains_l, rec
        elif return_psps:
            return spike_trains_l, rec['psp']
        else:
            return spike_trains_l

    def simulate_steps(self, stimulus, return_psps=False, debug=False):
        """
        TODO: cleanup
        Network activity in response to an input pattern presented to the
        network. Conduction delays are included.

        Inputs
        ------
        stimulus : array or list
            Input drive to the network, as one of two types:
                - predetermined (pre-shifted) psps: array,
                  shape (num_inputs, num_iter)
                - set of spike trains: list, len (num_inputs)
        return_psps : bool
            Return PSPs evoked due to each layer, excluding output layer, each
            with shape (num_nrns, num_subconns, num_iter).
        debug : bool
            Record network dynamics for debugging.

        Outputs
        -------
        spiked_l : list
            List of boolean spike trains in layers l > 1.
        psps : list, optional
            List of PSPs evoked, for layers l < L.
        rec : dict, optional
            Debug recordings containing
            {hidden layer psps 'psp', potential 'u', bool spike trains 'S'}.
        """
        # === Initialise ==================================================== #

        # Cast stimulus to PSPs evoked by input neurons
        psp_inputs = self.stimulus_as_psps(stimulus)
        num_iter = psp_inputs.shape[1]

        # Record
        rec = {}
        if return_psps:
            rec['psp'] = [np.empty((i, j, num_iter))
                          for i, j in zip(self.sizes[:-1], self.num_subs)]
        if debug:
            rec.update({'u': [np.empty((i, num_iter))
                              for i in self.sizes[1:]],
                        'S': [np.empty((i, num_iter), dtype=int)
                              for i in self.sizes[1:]]})
        # Bool spike trains in each layer: l > 1
        spiked_l = [np.zeros((i, num_iter), dtype=bool)
                    for i in self.sizes[1:]]
        # PSPs are padded to account for maximum conduction delay
        # PSPs : array, shape -> (num_inputs, num_iter + max_delay_iter)
        psp_inputs = np.concatenate((psp_inputs,
                                     np.zeros((self.sizes[0],
                                               self.delays[0][-1]))), axis=1)
        # PSPs from each layer: 1 <= l < L, reset kernels in each layer: l >= 1
        # Membrane, synaptic exponential decays with memory up to max delay
        psp_trace_l = [np.zeros((2, i, delays[-1] + 1))
                       for i, delays in zip(self.sizes[1:-1],
                                            self.delays[1:])]
        reset_l = [np.zeros(i) for i in self.sizes[1:]]

        # === Run simulation ================================================ #

        for t_step in xrange(num_iter):
            # Update kernels: l >= 1
            # psp_trace_l is used to store historic PSP values evoked by hidden
            # layer neurons - values are stored up to the maximum conduction
            # delay, such that oldest PSP values are removed to make space for
            # updated PSP values
            for traces in psp_trace_l:
                traces[:, :, 1:] = traces[:, :, :-1]  # Shift trace memory
                traces[0, :, 0] *= self.decay_m
                traces[1, :, 0] *= self.decay_s
            psp_l = [traces[0] - traces[1] for traces in psp_trace_l]
            reset_l = [traces * self.decay_m for traces in reset_l]
            # PSPs contributed by inputs at each delay
            psps = psp_inputs[:, t_step - self.delays[0]]
            # Hidden layer responses: 1 <= l < L
            for l in xrange(self.num_layers - 2):
                potentials = np.tensordot(self.w[l], psps) + reset_l[l]
                rates = self.neuron_h.activation(potentials)
                spiked_l[l][:, t_step] = self.rng.rand(len(rates)) < \
                    self.dt * rates
                # Record
                if return_psps:
                    rec['psp'][l][:, :, t_step] = psps
                if debug:
                    rec['u'][l][:, t_step] = potentials
                # Propagated, evoked PSPs at next layer
                psps = psp_l[l][:, self.delays[l+1]]
            # Output layer response
            potentials = np.tensordot(self.w[-1], psps) + reset_l[-1]
            spiked_l[-1][:, t_step] = potentials > self.cell_params['theta']
            # Update kernels
            for l in xrange(self.num_layers - 2):
                psp_trace_l[l][:, spiked_l[l][:, t_step], 0] += \
                    self.cell_params['psp_coeff']
            for l in xrange(self.num_layers - 1):
                reset_l[l][spiked_l[l][:, t_step]] += \
                    self.cell_params['kappa_0']
            # Record
            if return_psps:
                rec['psp'][-1][:, :, t_step] = psps
            if debug:
                rec['u'][-1][:, t_step] = potentials
                for l in xrange(self.num_layers - 1):
                    rec['S'][l][:, t_step] = spiked_l[l][:, t_step]

        # === Gather output spike trains ==================================== #

        # Spike trains: l > 1
        spike_trains_l = []
        for spiked in spiked_l:
            spike_trains_l.append([np.where(isspike)[0] * self.dt
                                   for isspike in spiked])
        if debug:
            return spike_trains_l, rec
        else:
            if return_psps:
                return spike_trains_l, rec['psp']
            else:
                return spike_trains_l


class MultilayerSRMMix(MultilayerBase):
    """
    Spiking neural network, implemented for SRM but with mixed time constants
    in hidden layers.

    Parameters
    ----------
    sizes : list, len (num_layers)
        Num. neurons in [input, hidden, output layers].
    param : container
        Using cell, pattern, net and common parameters.
    weights : list, optional, len (num_layers - 1)
        Sets initial network weights. Each element is an array of shape
        (num_post, num_pre).
    tau_s : float or 2-tuple, default 5.
        Specifies hidden synaptic rise times, either as fixed value or a range
        of values.
    factor_m : float or 2-tuple, default 2.
        Determines hidden membrane time constants as multiplicative factor(s)
        of the tau_s value(s).
    EscapeRate : class, default EXPRate
        Stochastic spike generator for hidden layer neurons.
    """
    def __init__(self, sizes, param, weights=None, tau_s=5., factor_m=2.,
                 EscapeRate=ExpRate):
        """
        Randomly initialise weights of neurons in each layer. Layers are
        populated with nrns, where hidden nrns have mixed time constants.
        """
        super(MultilayerSRMMix, self).__init__(sizes, param, weights)

    def simulate(self, stimulus, latency=False, return_psps=False,
                 debug=False):
        """
        Network activity in response to an input stimulus driving the
        network. Based on iterative procedure to determine spike times.
        Profiled at t = 0.34 s (iris, defaults (29/08/18), 20 hidden nrns).
        Speedup of 9x compared with non-iterative method.
        Scales less well as number of neurons increases (loops used).

        Parameters
        ----------
        stimulus : array or list
            Input drive to the network, as one of two types:
                - predetermined psps: array, shape (num_inputs, num_iter)
                - set of spike trains: list, len (num_inputs)
        latency : bool, optional
            Restrict to just finding first output spikes.
        return_psps : bool
            Return PSPs evoked due to each layer, excluding output layer, each
            with shape (num_nrns, num_iter).
        debug : bool, optional
            Record network dynamics for debugging.

        Returns
        -------
        spike_trains_l : list
            List of neuron spike trains, for layers l > 0.
        psps : list, optional
            List of PSPs evoked, for layers l < L.
        rec : dict, optional
            Debug recordings containing
            {'psp' as list of evoked PSPs, 'u' as list of potentials}.
        """
        # === Initialise ==================================================== #

        # Cast stimulus to PSPs evoked by input neurons
        psp_inputs = self.stimulus_as_psps(stimulus)
        num_iter = psp_inputs.shape[1]
        # Ensure pattern duration is compatible with look up tables
        assert num_iter == len(self.lut['psp'])

        # Record
        rec = {}
        if return_psps:
            rec['psp'] = [np.empty((i, num_iter))
                          for i in self.sizes[:-1]]
            rec['psp'][0] = psp_inputs
        if debug:
            rec['u'] = [np.empty((i, num_iter))
                        for i in self.sizes[1:]]
        # Spike trains for layers: l > 0
        spike_trains_l = [[np.array([]) for j in xrange(self.sizes[i])]
                          for i in xrange(1, self.num_layers)]

        # === Run simulation ================================================ #

        # PSPs evoked by input neurons
        psps = psp_inputs
        # Hidden layer responses: l = [1, L)
        for l in xrange(self.num_layers - 2):
            potentials = np.dot(self.w[l], psps)
            # Stochastic spiking
            unif_samples = self.rng.uniform(size=np.shape(potentials))
            # PSPs evoked by this layer
            psps = np.zeros((self.sizes[l+1], num_iter))
            for i in xrange(self.sizes[l+1]):
                num_spikes = 0
                while True:
                    rates = self.neuron_h.activation(potentials[i])
                    thr_idxs = \
                        np.where(unif_samples[i] < rates * self.dt)[0]
                    if num_spikes < len(thr_idxs):
                        fire_idx = thr_idxs[num_spikes]
                        iters = num_iter - fire_idx
                        potentials[i, fire_idx:] += self.lut['refr'][:iters]
                        psps[i, fire_idx:] += self.lut['psp'][:iters]
                        spike_trains_l[l][i] = \
                            np.append(spike_trains_l[l][i],
                                      fire_idx * self.dt)
                        num_spikes += 1
                    else:
                        break
            # Record
            if return_psps:
                rec['psp'][l+1] = psps
            if debug:
                rec['u'][l] = potentials
        # Output responses
        potentials = np.dot(self.w[-1], psps)
        # PSPs evoked by this layer
        psps = np.zeros((self.sizes[-1], num_iter))
        for i in xrange(self.sizes[-1]):
            num_spikes = 0
            while True:
                thr_idxs = \
                    np.where(potentials[i] > self.cell_params['theta'])[0]
                if num_spikes < len(thr_idxs):
                    fire_idx = thr_idxs[num_spikes]
                    iters = num_iter - fire_idx
                    potentials[i, fire_idx:] += self.lut['refr'][:iters]
                    psps[i, fire_idx:] += self.lut['psp'][:iters]
                    spike_trains_l[-1][i] = np.append(spike_trains_l[-1][i],
                                                      fire_idx * self.dt)
                    # Optimisation: skip output spikes after first
                    if latency:
                        break
                    else:
                        num_spikes += 1
                else:
                    break
        if debug:
            rec['u'][-1] = potentials

        if debug:
            return spike_trains_l, rec
        elif return_psps:
            return spike_trains_l, rec['psp']
        else:
            return spike_trains_l
