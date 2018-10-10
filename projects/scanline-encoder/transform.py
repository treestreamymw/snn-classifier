#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""
Created on Oct 2018

@author: BG
@licence: GNU v3
"""

import numpy as np
import matplotlib.pyplot as plt
import argparse

from snncls import dataset_loader, preprocess
from lib import scanner, neuron, plotter
import lib.helpers as hp

bounds = (28, 28)


def main(opt):
    # Random generator
    rng = np.random.RandomState(opt.seed)
    # Data
    data_id = 'mnist'
    X, _ = dataset_loader.load_data_file(data_id)
    # Normalisation
    data_min = np.min(X)
    data_range = np.max(X) - data_min
    X = (X - data_min) / data_range
    # [Randomise data selection]
    if opt.randomise:
        rng.shuffle(X)
    # Data selection
    X = X[:opt.num_cases]
    # Scanners
    duration = opt.duration
    dt = 0.1
    times = np.arange(0., duration, dt)
    num_steps = len(times)
    #line_eqs = [(-2, 3), (2, 2)]

    # Matched to Intel's Loihi encoder
    line_eqs = [(0.857, 4.00), (1.00, -3.00), (-80.0, 1060.),
                (-0.615, 17.8), (-1.63, 13.0)]
    scanners = []
    for eq in line_eqs:
        scanners.append(scanner.Scanner(eq, bounds, duration))
    num_scanners = len(scanners)
    # Neurons
    nrns = []
    for i in xrange(num_scanners):
        if opt.nrn == 'lif':
            nrns.append(neuron.LIF(dt, R=10.))
        elif opt.nrn == 'izh':
            # a=0.2: 5 ms recovery time
            # d=12: suppress late spiking
            nrns.append(neuron.Izhikevich(dt, a=.4, d=12.))
        else:
            raise ValueError('Invalid neuron type')
    # Recorder
    rec = dict()
    if opt.plot:
        rec['r'] = [[np.full((num_steps, 2), np.nan)
                     for i in xrange(num_scanners)]
                    for j in xrange(opt.num_cases)]  # Scanner positions
        rec['i'] = [np.full(num_steps, np.nan)
                    for i in xrange(num_scanners)]  # Pixel intensities
        rec['addr'] = [[] for i in xrange(num_scanners)]  # Scanned pixel addrs
        rec['v'] = [np.full((num_steps, num_scanners), np.nan)
                    for i in xrange(opt.num_cases)]  # Nrn voltages
    rec['spikes'] = [[np.array([]) for i in xrange(num_scanners)]
                     for j in xrange(opt.num_cases)]

    # Scan each sample
    for idx_im, x in enumerate(X):
        img_scan = x.reshape(bounds)
        # Reset scanners and associated neurons
        for scan, nrn in zip(scanners, nrns):
            scan.reset()
            nrn.reset()
        for step, t in enumerate(times):
            for idx_sc, scan in enumerate(scanners):
                # Read
                stimulus = scan.read(img_scan)
                # Record
                if opt.plot:
                    rec['r'][idx_sc][step, :] = scan.get_pos()
                    rec['i'][idx_sc][step], addr = scan.read(img_scan, True)
                    rec['addr'][idx_sc].append(addr)
                    rec['v'][step, idx_sc] = nrns[idx_sc].get_v()
                # Update
                fired = nrns[idx_sc].update(stimulus)
                scan.translate(dt)
                # Record nrn
                if fired:
                    spike_time = np.around(t, decimals=1)
                    rec['spikes'][idx_im][idx_sc] = \
                        np.append(rec['spikes'][idx_im][idx_sc], spike_time)
    # [Plot first sample]
    if opt.plot:
        playbk = plotter.Playback(bounds, times, duration, opt.wait)
        playbk.play_nrns(rec, img_scan)
#        plt.plot(times, rec['v'][:, 2])
        plt.show()
    return rec


if __name__ == "__main__":
    parser = argparse.ArgumentParser("scanline encoder")
    # Images
    parser.add_argument("-r", "--randomise", action="store_true",
                        help="optional, randomise data selection")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("-n", "--num_cases", type=int, default=1,
                        help="size of samples selected")
    # Scanners
    parser.add_argument("-d", "--duration", type=float, default=9.,
                        help="scan duration")
    # Neurons
    parser.add_argument("--nrn", type=str, default='lif',
                        help="neuron types: 'lif', 'izh'")
    # Plotting
    parser.add_argument("-p", "--plot", action="store_true",
                        help="plot last sample")
    parser.add_argument("-w", "--wait", type=float, default=0.05,
                        help="plot speed")
    # Save preprocessed data
    parser.add_argument("--fname", type=str, default=None)
    args = parser.parse_args()

    rec = main(args)
